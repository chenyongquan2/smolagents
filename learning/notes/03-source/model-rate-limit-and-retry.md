---
created: 2026-05-06
status: active
tags: [smolagents, models, rate-limit, retry, networking, source-reading]
---

# 节流（Rate Limiting）vs 重试（Retry）：调 LLM API 服务器的双层保险

⚠️ **必读前置**：[inference-client-model-impl.md](inference-client-model-impl.md)（ApiModel 中间层 + InferenceClientModel.generate 五件事）

> 本笔记拆解 [`ApiModel`](../../../src/smolagents/models.py#L1138) 的两个网络武器：`self.rate_limiter` 和 `self.retryer`。两者**独立但互补**，是所有"走网络的 LLM 调用"的标配。

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](../02-concepts/llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。"客户端"在本笔记里特指多个 HTTP 客户端进程（如多个并发跑的 agent 实例），不是 4 角色之一。

---

## 1. 一句话区分

| 机制 | 时机 | 解决的问题 | 类比 |
|---|---|---|---|
| **节流（Rate Limiting）** | 发请求**之前** | "我即将打爆 LLM API 服务器，让我自己慢一点" | 高速公路上**主动减速** |
| **重试（Retry）** | 发请求**失败之后** | "刚才那次失败了，再试一次" | 撞了护栏后**重新发车** |

**两个独立机制**，但通常一起用 —— 因为即使节流也防不住偶发失败。

---

## 2. 为什么需要它们？—— LLM API 服务器的现实

OpenAI / HuggingFace / Anthropic 等 provider 都有 **rate limit**（速率限制）：

- **RPM**：requests per minute，每分钟最多 N 次请求
- **TPM**：tokens per minute，每分钟最多 N 个 token

**例子**：OpenAI 免费层 `gpt-4o-mini` = **3 RPM**。1 秒钟发 3 次会怎样：

```
00:00.0  请求 ① → ✅ 200 OK
00:00.3  请求 ② → ✅ 200 OK
00:00.6  请求 ③ → ✅ 200 OK
00:00.9  请求 ④ → ❌ 429 Too Many Requests   ← 第 4 次被拒
```

**Agent 场景特别容易触发**：一个 ReAct 循环 5-10 步，每步一次 LLM 调用，几个 agent 并行跑就轻松超 RPM。

---

## 3. ⭐ 节流（Rate Limiting）：主动减速

### 3.1 问题
"我手头攒着 100 个请求要发，但 provider 说每分钟最多 60 个，应该怎么发？"

### 3.2 错误做法
全部一口气发出去 → 第 60 个之后全部 429 → 数据丢了一半。

### 3.3 正确做法
**自己估算节奏，把请求均匀分散**：

```
60 RPM → 每个请求间隔 1 秒 → 100 个请求需要 100 秒发完
```

每次发请求前**先检查"距离上次发了多久"**，没到节奏就 `time.sleep()` 等一下。

### 3.4 smolagents 怎么做？

[ApiModel.__init__](../../../src/smolagents/models.py#L1173)：

```python
self.rate_limiter = RateLimiter(requests_per_minute)
```

[ApiModel._apply_rate_limit](../../../src/smolagents/models.py#L1189)：

```python
def _apply_rate_limit(self):
    self.rate_limiter.throttle()   # ← 内部检查节奏，必要时 time.sleep
```

`InferenceClientModel.generate` 第 ③ 件就是调它（[line 1575](../../../src/smolagents/models.py#L1575)）：

```python
self._apply_rate_limit()                                                  # ← 主动减速
response = self.retryer(self.client.chat_completion, **completion_kwargs) # ← 然后才发
```

> 💡 **节流是发出去之前的"预防"** —— 它根本不让你触发 429。RateLimiter 内部一般用 token bucket 算法（一个桶按时间慢慢加令牌，每次发请求消耗一个），实现细节第一遍跳过。

### 3.5 用户怎么配置？

```python
model = InferenceClientModel(
    model_id="...",
    requests_per_minute=60,   # ← 用户告诉框架自己的 RPM 限制
)
```

不传就**不节流**（让你自己负责速率，agent 单跑场景 OK）。

---

## 4. ⭐ 重试（Retry）：失败后再来

### 4.1 问题
"我已经节流到 60 RPM 了，但 provider 临时抽风（共享集群高峰）还是给我 429，怎么办？"

### 4.2 错误做法
立刻报错给用户："请求失败，请重试" → 让用户去刷新页面 → 体验崩溃。

### 4.3 正确做法
**框架内部默默重试几次**，且每次间隔越来越长（**指数退避**）：

```
第 1 次发请求 → ❌ 429
等 2 秒
第 2 次发请求 → ❌ 429
等 4 秒
第 3 次发请求 → ✅ 200 ← 成功了，用户根本不知道刚才挫折过
```

### 4.4 为什么要"指数退避"（exponential backoff）？

如果失败后立刻重试，会**雪上加霜** —— provider 还在限流，你又冲一发只会被再拒。

**等的时间越来越长**：
- 给 provider 缓冲机会（让它的限流窗口过去）
- 避免你和别的客户端同时撞过去（**羊群效应**）

加 **jitter（随机抖动）**进一步打散并发：原本 100 个客户端都"等 2 秒后重试" → 全部同一秒重试再次撞墙。jitter 让每个客户端等 1.5 ~ 2.5 秒，分散冲击。

### 4.5 smolagents 怎么做？

[ApiModel.__init__](../../../src/smolagents/models.py#L1174)：

```python
self.retryer = Retrying(
    max_attempts=RETRY_MAX_ATTEMPTS if retry else 1,   # 最多重试 N 次
    wait_seconds=RETRY_WAIT,                            # 初始等待
    exponential_base=RETRY_EXPONENTIAL_BASE,            # 指数底数（一般 2）
    jitter=RETRY_JITTER,                                # 随机抖动避免羊群效应
    retry_predicate=is_rate_limit_error,                # ← 只重试 rate limit 错误
    reraise=True,                                       # 最终还是失败就抛出
    ...
)
```

`Retrying` 是个**可调用对象**，"包裹"另一个函数：

```python
response = self.retryer(self.client.chat_completion, **completion_kwargs)
#         ──────────────  ─────────────────────────  ──────────────────
#         retry 包装器     被包装的函数               传给被包装函数的参数
```

意思是：**"帮我执行 `self.client.chat_completion(**completion_kwargs)`，失败就自动重试"**。

### 4.6 ⭐ `retry_predicate` 的精髓：不是所有错误都该重试

[is_rate_limit_error](../../../src/smolagents/models.py#L1194)（伪代码）：

```python
def is_rate_limit_error(exception):
    error_str = str(exception).lower()
    return ("rate limit" in error_str
            or "429" in error_str
            or "too many requests" in error_str
            ...)
```

**重试规则**：

| 错误类型 | 重试？ | 为什么 |
|---|---|---|
| 429 / rate limit / "too many requests" | ✅ | LLM API 服务器临时拒绝，等等可能成功 |
| 401（认证失败）| ❌ | token 错的，重试一万次也错 |
| 400（请求体错）| ❌ | agent 框架 bug，重试也错 |
| 500（服务器内部错误）| ❌ | provider 自己挂了，重试也错（设计上有争议）|
| 503（服务暂时不可用）| 视情况 | 通常算"临时"，可以重试 |

`retry_predicate` 是**判断函数**：异常**满足条件**才重试，否则直接抛给上层。**这是重试机制的关键设计** —— 否则会把"永远不可能成功"的错也死磕几遍浪费时间。

---

## 5. ⭐ "retry 包裹"是什么意思？

回顾这一行：

```python
response = self.retryer(self.client.chat_completion, **completion_kwargs)
```

**用等价伪代码理解**：

```python
# self.retryer(func, **kwargs) 大致等价于：

def retry_wrapper(func, **kwargs):
    for attempt in range(max_attempts):
        try:
            return func(**kwargs)        # ← 真正调用
        except Exception as e:
            if not is_rate_limit_error(e):
                raise                    # 不该重试的直接抛
            if attempt == max_attempts - 1:
                raise                    # 最后一次还失败就放弃
            wait = wait_seconds * (exponential_base ** attempt) + random_jitter()
            time.sleep(wait)
            # ↑ 等待时间：第 1 次 2 秒、第 2 次 4 秒、第 3 次 8 秒...
```

**"包裹"的意思**：原本你只调一次的函数，现在被外层 retry 逻辑**包了一层** —— 输入输出对外完全一致（拿同样参数返回同样结果），但内部加了"失败自动重试"的能力。

> 💡 **包裹模式 = 装饰器思想的应用**。回顾 Day 2 [python-decorators-explained.md](python-decorators-explained.md)：装饰器 = 给函数加横切能力（日志、重试、缓存…）而不改原函数。这里 `Retrying` 类的 `__call__` 就是典型的"重试装饰器"实现，只是用对象封装而不是 `@decorator` 语法糖。
>
> **同样的设计哲学已在 smolagents 多处出现**：[Tool 类的 `__call__` vs `forward`](tool-class-role-overview.md) 也是一层包装一层 —— 横切关注点（清洗 / 重试 / 节流）和业务逻辑（真正发请求 / 真正执行工具）分离。

---

## 6. ⭐ 节流 + 重试一起用 = 双层保险

```
agent 想发请求
    ↓
[第 1 道防线] 节流：检查节奏，慢一点
    ├─ 没到节奏：sleep(0.x 秒)
    └─ 到了：放行
    ↓
真发请求
    ├─ ✅ 成功 → 返回响应
    └─ ❌ 失败：
            ├─ 是 rate limit 错误 → [第 2 道防线] retry：等待 + 重试（最多 N 次）
            └─ 其他错误 → 直接抛给上层
```

| 防线 | 解决场景 | 缺点 |
|---|---|---|
| 节流 | 我自己控制不超 RPM 限制 | 没法应对 provider 临时抽风 |
| 重试 | 即使我控制好了，provider 共享集群高峰还是可能临时拒我 | 总会增加延迟，能避免就避免 |

**两个机制相互独立但互补**：节流是积极预防（prevention），重试是消极兜底（mitigation）。

> 💡 **smolagents 总结回顾的"双保险"模式**：
> - [model-stop-sequences.md](model-stop-sequences.md)：prompt 指令（教 LLM 模型）+ LLM API 服务器硬截断
> - [inference-client-model-impl.md §4.5](inference-client-model-impl.md)：LLM API 服务器 stop 截断 + Python fallback strip（agent 框架本地）
> - **本笔记**：节流（防）+ 重试（治）
>
> **永远不要单独信任一道防线**。这是 smolagents 反复出现的设计哲学。

---

## 7. 三种"走网络模型"的差异

| 模型 | 节流？ | 重试？ | 客户端 |
|---|---|---|---|
| `InferenceClientModel`（HF）| ✅ ApiModel 共享 | ✅ ApiModel 共享 | `huggingface_hub.InferenceClient` |
| `OpenAIModel` | ✅ ApiModel 共享 | ✅ ApiModel 共享 | `openai.OpenAI` |
| `LiteLLMModel` | ✅ ApiModel 共享 | ✅ ApiModel 共享 | `litellm` 库 |
| `AmazonBedrockModel` | ✅ ApiModel 共享 | ✅ ApiModel 共享 | `boto3.client('bedrock-runtime')` |
| `TransformersModel`（本地）| ❌ | ❌ | 不走网络，直接 GPU |
| `VLLMModel`（本地）| ❌ | ❌ | 同上 |

**这就是 ApiModel 中间层存在的价值** —— 把 4 个走网络子类（InferenceClient/OpenAI/LiteLLM/Bedrock）的共性抽出来，本地子类绕开（详见 [inference-client-model-impl.md §1](inference-client-model-impl.md)）。

---

## 8. 总结表

| 问题 | 答案 |
|---|---|
| 节流是什么？ | 主动减速，发请求**之前**控制速率不超 provider RPM |
| 重试是什么？ | 失败**之后**自动再试几次，配合指数退避 |
| 时机差异？ | 节流在 before（预防），重试在 after（兜底）|
| smolagents 哪里实现？ | [ApiModel](../../../src/smolagents/models.py#L1138) 的 `self.rate_limiter` 和 `self.retryer` |
| "retry 包裹"什么意思？ | `retryer(func, **kwargs)` 把 func 调用**装饰**一层，加失败重试逻辑 |
| 为什么 retry 要指数退避？ | 给 provider 缓冲；避免羊群效应（jitter 进一步打散）|
| 所有错误都该重试吗？ | ❌ 只重试 rate limit 类临时性错误；401/400/500 等直接抛 |
| `retry_predicate` 是什么？ | 判断函数：异常满足条件才重试，否则直接抛 |
| 节流 + 重试关系？ | 双层独立防线，互补不冲突（预防 + 兜底）|
| 为什么本地模型不需要它们？ | 本地推理不走网络，没有 RPM/429 概念 |

---

## 相关链接

- 源码：
  - [models.py:1138-1192](../../../src/smolagents/models.py#L1138) — ApiModel `self.rate_limiter` + `self.retryer` 定义
  - [models.py:1194-1203](../../../src/smolagents/models.py#L1194) — `is_rate_limit_error` 判断函数
  - [models.py:1575-1576](../../../src/smolagents/models.py#L1575) — `_apply_rate_limit` + `retryer(...)` 调用
- 必读前置：
  - [inference-client-model-impl.md](inference-client-model-impl.md) — ApiModel 中间层 + generate 五件事的全局位置
- 设计哲学呼应：
  - [tool-class-role-overview.md](tool-class-role-overview.md) — `__call__` vs `forward` 的横切关注点分离
  - [python-decorators-explained.md](python-decorators-explained.md) — 装饰器思想（包裹模式的语法糖版本）
  - [model-stop-sequences.md](model-stop-sequences.md) — 双保险机制的另一例
- 通用知识：
  - Token bucket 算法（节流的经典实现）
  - Exponential backoff with jitter（AWS 经典 [博客](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)）

## 遗留问题

- [ ] `RateLimiter` 内部具体算法（token bucket / leaky bucket / sliding window）—— 用到再查
- [ ] `Retrying` 类完整源码（应该在 utils 模块）—— 知道有这层包装就够，细节不深究
- [ ] 5xx 错误是否应该重试？smolagents 现在的策略是只重试 rate limit；某些场景 503 也值得重试，可对比上游 issue
