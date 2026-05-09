---
created: 2026-05-06
status: active
tags: [day3, self-check, study-aid, models, comprehension]
---

# Day 3 自查手册：7 道题 + 详细答案 + 笔记溯源

> **使用方法**：每道题先用纸盖住答案 → 心里答一遍 → 揭开对照 → 答错的地方点开"笔记溯源" 链接精读对应章节。**不需要一次做完，遇到 Day 4-5 卡壳时回来补**。

> **目的**：验证 Day 3 学习是否到 [LEARNING_PLAN.md:84-90](../../../LEARNING_PLAN.md) 的层次 2 ("看透 — 想到替代设计并说出 trade-off")。

---

## 题目分布

| # | 类型 | 难度 | 主要考点 |
|---|---|---|---|
| 1 | 事实记忆 | ★ | `_prepare_completion_kwargs` 5 步流水线 |
| 2 | 概念应用 | ★★ | 三层优先级合并 |
| 3 | 设计意图 | ★★ | `REMOVE_PARAMETER` vs `None` 哨兵设计 |
| 4 | 跨层闭环 | ★★ | CodeAgent 不传 tools 时工具怎么进 prompt |
| 5 | ⭐⭐ 心智模型 | ★★★ | 被动检测 vs 主动控制 |
| 6 | ⭐⭐ 跨笔记闭环 | ★★★ | 5→3 role 降维的根因 |
| 7 | ⭐⭐ 看会层 | ★★★★ | 给 smolagents 加 AnthropicModel 子类 |

---

## ★ Q1 [事实记忆] `_prepare_completion_kwargs` 5 步分别做什么？

### 题目

合上笔记，默写 `_prepare_completion_kwargs` 的 5 步流水线（每步一句话即可）。

<details>
<summary>📖 点开看答案</summary>

| 步骤 | 做什么 |
|---|---|
| ① | 调 `get_clean_message_list` 清洗 messages（deepcopy / role 验证 / role 转换 / image 编码 / **连续同 role 合并** / flatten）|
| ② | 写 specific 参数（最低优先级）：`stop_sequences` → `stop`、`response_format`、`tools` (调 `get_tool_json_schema`)、`tool_choice`（默认 "required"）|
| ③ | `completion_kwargs.update(kwargs)` —— caller 调用时传的 kwargs 合并进去（中间优先级，覆盖 ②）|
| ④ | 遍历 `self.kwargs` —— 实例化时存下的默认（最高优先级，覆盖 ③）；遇到 `REMOVE_PARAMETER` 哨兵 `pop` 字段 |
| ⑤ | `return completion_kwargs` —— 子类拿去发请求 |

**关键设计哲学**："**最早写入的优先级最低**" —— 用户实例化时给的最早就存下了，但**留到最后才生效**，因为它代表用户最强烈的意图。

📚 **笔记溯源**：[model-generate-mental-model.md §3](model-generate-mental-model.md)

</details>

---

## ★★ Q2 [概念应用] 三层优先级实战

### 题目

用户写：
```python
model = InferenceClientModel(model_id="...", temperature=0.7, max_tokens=1024)
```
然后 agent 内部调：
```python
model.generate(messages, temperature=0.3, top_p=0.95)
```

最终 HTTP body 里这 3 个参数分别是什么值？为什么？

<details>
<summary>📖 点开看答案</summary>

| 字段 | body 里的值 | 来自哪一层 | 解释 |
|---|---|---|---|
| `temperature` | **0.7** | ④ self.kwargs | self.kwargs 是最高优先级，**覆盖** caller 的 0.3 |
| `max_tokens` | **1024** | ④ self.kwargs | 只在 self.kwargs 里 |
| `top_p` | **0.95** | ③ caller kwargs | 只在 caller kwargs 里，没人覆盖 |

**为什么这样设计？**

让"用户实例化时给的默认值压住 agent 框架的临时决定"。比如用户希望 `temperature=0.0` 确定性输出，agent 框架内某些路径却想用 0.7 创意输出 → **用户意图保住**。

**实证**：[inference_request_trace.py Demo 4](../scripts/inference_request_trace.py)。

📚 **笔记溯源**：[model-generate-mental-model.md §4](model-generate-mental-model.md)

</details>

---

## ★★ Q3 [设计意图] `REMOVE_PARAMETER` vs `None` 区别

### 题目

用户写以下两种代码，最终发出去的 HTTP body 有什么不同？为什么需要这个区分？

```python
# 写法 A
model = InferenceClientModel(model_id="...", stop=None)

# 写法 B
from smolagents.models import REMOVE_PARAMETER
model = InferenceClientModel(model_id="...", stop=REMOVE_PARAMETER)
```

<details>
<summary>📖 点开看答案</summary>

### 区别

| 写法 | body 里 | JSON 序列化 | LLM API 服务器收到 |
|---|---|---|---|
| A: `stop=None` | `body["stop"] = None` | `{"stop": null, ...}` | "stop 字段存在，值为空" |
| B: `stop=REMOVE_PARAMETER` | body 里**根本没有** stop 这个 key | `{...}` （字段缺失）| "stop 字段不存在" |

### 为什么需要区分？

**JSON 协议层面**："stop": null 和"没有 stop 字段"**是两种不同状态**：
- 某些 LLM API 服务器看到 `"stop": null` 会报 400 "unexpected field"（因为它根本不该接收 stop 参数）
- 用户真正想说的 = "字段根本不该存在"

### 哨兵设计精髓

把"删除操作"伪装成"赋一个特殊值" —— 复用了"配置覆盖"流程，**零额外 API 表面**。

`REMOVE_PARAMETER` 是**单例对象**，用 `is` 严格比较（不能用 `==` 防伪造）。

**实证**：[inference_request_trace.py Demo 5](../scripts/inference_request_trace.py)。

📚 **笔记溯源**：[python-sentinel-pattern.md](../python-prep/python-sentinel-pattern.md) §3 经典三场景

</details>

---

## ★★ Q4 [跨层闭环] CodeAgent 不传 tools，工具信息怎么进 prompt？

### 题目

ToolCallingAgent 通过 `tools_to_call_from` 把工具信息写进 HTTP body 的 `tools` 字段（Demo 2 验证过）。但 **CodeAgent 不传 `tools_to_call_from`**。那它的工具信息怎么让 LLM 模型知道？

<details>
<summary>📖 点开看答案</summary>

### 答案：通过 prompt 文本路径

CodeAgent 调 `Tool.to_code_prompt()` 把每个工具渲染成"假装的 Python def"代码块：

```python
def get_weather(city: str) -> str:
    """查询某城市当前天气

    Args:
        city: 城市名（中文或英文）
    """
```

然后**把这段文字塞进 system prompt** 的 messages.content 里。LLM 模型经 chat template + tokenize 后**作为普通文本**看到这段。

### 关键洞察：两条不同路径

| Agent 类型 | 工具信息怎么到模型 | HTTP body 里 |
|---|---|---|
| **ToolCallingAgent** | 走 `body["tools"]` 字段 → LLM API 服务器 → 服务器内部把 tools 渲染进 system prompt | `tools` 字段有内容 |
| **CodeAgent** | agent 框架直接把工具描述塞进 system prompt 文字里 → 经 messages 走 | `tools` 字段**为空** |

**两条路径最终殊途同归**：模型最终看到的都是**文本描述**（因为模型只懂 token 序列）。

### 为什么 CodeAgent 选这条路？

因为 CodeAgent 期望 LLM 模型输出**Python 代码块**而不是 OpenAI 协议的结构化 `tool_calls` JSON。整个对话用纯文本协议（"Code: ... `<end_code>`"），不需要走 OpenAI function calling 的结构化路径。

📚 **笔记溯源**：[tool-schema-rendering-mental-model.md](../day2-tools/tool-schema-rendering-mental-model.md)（Day 2 写过的"4 种渲染形状"，Q4 这题就是其中两种的对比）

</details>

---

## ★★★ Q5 ⭐⭐ [心智模型] 被动检测 vs 主动控制

### 题目

下面 3 个场景中，LLM 模型会不会输出 `<end_code>`？最终生成会怎么停？

**场景 A**：agent 框架在 prompt 里教 "End your code with `<end_code>`"，**且** HTTP body 传 `stop=["<end_code>"]`

**场景 B**：agent 框架**只**在 prompt 里教，**不**传 stop

**场景 C**：agent 框架**只**传 stop，**不**在 prompt 里教

<details>
<summary>📖 点开看答案</summary>

### 答案

| 场景 | 模型输出 `<end_code>`? | 怎么停？ | 后果 |
|---|---|---|---|
| A | ✅ 会（被 prompt 教过）| 服务器检测到 `<end_code>` 就 break | ✅ 完美工作 |
| B | ✅ 会（被 prompt 教过）| **不会因 stop 停**（没传），靠 EOS 或 max_tokens 才停 | ⚠️ 模型输出 `<end_code>` **后**会继续编造 Observation 文字 |
| C | ❌ 不会 | 永远不会因 stop 停 | ❌ stop 等于白传，靠 EOS / max_tokens 兜底 |

### 核心心智模型

**LLM API 服务器对 stop 是"被动检测"，不能"主动控制"**：
- 服务器**不能强制** LLM 模型输出 `<end_code>` 字符串
- 服务器只能**等模型自己输出，然后抓到了就截断**

**所以**：
- prompt 教 = **主动**机制（影响模型 token 分布，让它"想"输出 stop 字符串）
- stop 字段 = **被动**机制（监听 + 截断）
- **第 2 层完全依赖第 1 层成功** —— 没有 prompt 教，stop 永远不触发

### 双保险的真正含义

不是"两道独立防线"，而是**主动 + 被动协同**：
- prompt 让 LLM 模型**想**写 stop 字符串
- 服务器一旦看到就**强制截断**

📚 **笔记溯源**：[model-stop-sequences.md §7](model-stop-sequences.md)（⭐⭐ 关键澄清）

</details>

---

## ★★★ Q6 ⭐⭐ [跨笔记闭环] 5→3 role 降维的根因

### 题目

smolagents 内部有 5 个 role：USER / ASSISTANT / SYSTEM / TOOL_CALL / TOOL_RESPONSE。但在喂 LLM API 服务器之前，[`get_clean_message_list`](../../../../src/smolagents/models.py#L332) 会通过 `tool_role_conversions` 把它们降维成 3 个（user / assistant / system）。

**表面原因**是"OpenAI 协议没这两个 role"。但**根本原因**在哪一层？为什么模型层面也不能直接接受 TOOL_CALL / TOOL_RESPONSE？

<details>
<summary>📖 点开看答案</summary>

### 表面原因 vs 根本原因

| 层次 | 原因 |
|---|---|
| 表面 | OpenAI Chat Completion 协议规范只定义 user/assistant/system/tool 4 个 role，没有 tool-call / tool-response |
| **根本** | **LLM 模型训练时根本没见过 TOOL_CALL / TOOL_RESPONSE 这种 role**。模型从训练数据里学到的"特殊 token"（`<|im_start|>` 等）只覆盖标准 role |

### 完整因果链

```
LLM 模型训练数据
    ↓ 只有 user/assistant/system 角色边界标记 token
LLM 模型学到的"特殊 token 词汇"
    ↓ 不包含 "tool-call" / "tool-response" 对应的特殊 token
chat template
    ↓ 只能渲染模型识别的特殊 token
LLM API 服务器协议
    ↓ 字段只允许标准 role
smolagents 内部
    ↓ 5 role 喂出去前必须降维成 3 个
```

**所以 5→3 降维是 chat template 层级的硬约束** —— 如果传 TOOL_CALL，chat template 不知道怎么渲染（没对应特殊 token）→ 报错或忽略。

### 为什么 smolagents 内部还要保留 5 个？

**内部表达清晰度**：
- TOOL_CALL ≠ ASSISTANT 普通输出（前者是要求执行工具的特殊语义）
- TOOL_RESPONSE ≠ USER 普通输入（前者是工具的真实执行结果）

**memory 层用 5 role 让"思考-行动-观察"语义清楚** → 喂给 LLM 时**降维成对方协议认识的形状**。

📚 **笔记溯源**：[chat-template-explained.md §9](../../02-concepts/chat-template-explained.md)（⭐ 揭示根因）+ [chat-message-roles.md](../../02-concepts/chat-message-roles.md)（Week 1 概念前置）

</details>

---

## ★★★★ Q7 ⭐⭐ [看会层 / 设计能力] 实现 AnthropicModel 子类

### 题目

让你给 smolagents 加一个 `AnthropicModel` 子类（接 Anthropic Claude API）。**心里写出实现方案**：

1. 应该继承哪个类？
2. 必须重写哪几个方法？
3. 哪些方法可以白嫖父类？
4. Anthropic 协议字段名跟 OpenAI 不同（如 `stop_sequences` vs `stop`），怎么处理？

<details>
<summary>📖 点开看答案</summary>

### 1. 继承层级

```python
class AnthropicModel(ApiModel):  # ← 继承 ApiModel（因为走 HTTP）
    ...
```

**理由**：
- Claude API 走 HTTP / 有 rate limit / 需要重试 → 必须用 ApiModel 的 client + rate_limiter + retryer 三件武器
- 如果继承 Model 直接，要重新写网络层代码，不优雅

### 2. 必须重写的方法

| 方法 | 为什么 |
|---|---|
| `__init__` | 接收 Anthropic 特有的 `api_key` / `base_url` 等参数，存进 `self.client_kwargs` |
| `create_client` | ApiModel 抽象方法（`raise NotImplementedError`），必须实现 —— 返回 Anthropic SDK 的 client 实例 |
| **`generate`** | **核心** —— 因为协议字段名差异 + 响应格式差异 |

### 3. `generate` 的实现思路

```python
def generate(self, messages, stop_sequences=None, ..., **kwargs):
    # 第 ② 件：拼 body —— 关键：协议字段名翻译
    completion_kwargs = self._prepare_completion_kwargs(
        messages=messages,
        stop_sequences=stop_sequences,   # 内部仍叫 stop_sequences
        ...
        **kwargs,
    )

    # ⭐ 字段名翻译：OpenAI "stop" → Anthropic "stop_sequences"
    if "stop" in completion_kwargs:
        completion_kwargs["stop_sequences"] = completion_kwargs.pop("stop")

    # 节流 + 重试发请求
    self._apply_rate_limit()
    response = self.retryer(self.client.messages.create, **completion_kwargs)

    # 解析 Anthropic 响应（结构和 OpenAI 不同）
    return ChatMessage(
        role="assistant",
        content=response.content[0].text,        # Anthropic 的响应格式
        tool_calls=self._parse_anthropic_tools(response),  # 可能要写解析
        raw=response,
        token_usage=TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        ),
    )
```

### 4. 可以白嫖的（不重写）

| 方法 / 属性 | 来自 | 为什么能白嫖 |
|---|---|---|
| `_prepare_completion_kwargs` | Model 基类 | 拼 body 的 5 步流水线对所有子类一样 |
| `parse_tool_calls` | Model 基类 | 兜底解析，可能用得上 |
| `to_dict` / `from_dict` | Model 基类 | 序列化（自动过滤 token / api_key 安全字段）|
| `self.rate_limiter` / `self._apply_rate_limit` | ApiModel | 限流 |
| `self.retryer` | ApiModel | 重试 |
| `is_rate_limit_error` | 模块级函数 | 重试谓词 |

### 5. 协议碎片化的应对

**这个题暴露了 smolagents 多子类的本质**：每家 provider 协议字段名 / 响应格式 / 错误码都不同，必须**逐家手工适配 + 字段名翻译**。

**但 5 步流水线 + 三层优先级 + 限流重试这些"公共部分" 在基类共享** —— 这就是 [Model 基类抽象的真正威力](model-class-role-overview.md)。

📚 **笔记溯源**：
- [model-class-role-overview.md](model-class-role-overview.md) §6 "为什么 Model 基类自己不发请求"
- [inference-client-model-impl.md](inference-client-model-impl.md) §1-4 (3 层继承 + generate 五件事)
- [model-stop-sequences.md §9.3](model-stop-sequences.md) (协议碎片化挑战)

</details>

---

## 学完后的自我评估

按 [LEARNING_PLAN.md:84-90](../../../LEARNING_PLAN.md) 3 层标准对照：

| 题目 | 答对意味着 |
|---|---|
| Q1, Q2 答得出 | ✅ **看懂层** |
| Q3, Q4, Q5, Q6 答得出 | ✅ **看透层**（达到 Day 3 计划要求）|
| Q7 答得出 | ✅ **看会层**（超出 Day 3 计划要求，已为 Week 3 实战做好准备）|

**至少 Q1-Q6（前 6 题）能答出**，Day 3 就算真消化到位 —— 可以放心进 Day 4。

---

## 相关链接

- 笔记总入口：[model-class-role-overview.md](model-class-role-overview.md)
- 实验脚本：[inference_request_trace.py](../scripts/inference_request_trace.py)（每题"实证"链接指向）
- Day 3 总结：[LEARNING_PLAN.md Day 3 学习总结](../../../LEARNING_PLAN.md)
