---
created: 2026-05-06
status: active
tags: [concepts, llm, api-server, internals, architecture, mental-model]
---

# LLM API 服务器内部架构：与 LLM 模型如何协作

⚠️ **必读前置**：[llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md)（4 角色术语约定 + LLM 模型 vs LLM API 服务器分层）

> 本笔记是 [llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md) 的**延伸**：前者讲"两层是什么"，本篇讲"它们内部怎么协作工作"。读懂之后所有协议字段（temperature/stop/max_tokens/response_format）的施加位置都清晰了。

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

---

## 1. ⭐ 一句话本质

**LLM 模型 = 一个无状态的纯函数**：吃 token 序列，吐下一个 token 的概率分布。**就这一件事**。

**LLM API 服务器 = 协调器**：拿用户请求 → 跑一个生成循环（反复调 LLM 模型）→ 在循环里施加所有协议控制 → 包响应回去。

```
LLM 模型           = "脑"   ← 只会预测下一个 token
LLM API 服务器     = "身体"  ← I/O、循环、控制、调度
```

---

## 2. ⭐ LLM 模型的真实样子

很多人把 LLM 想成"会聊天的对象"，其实底层超级简单：

```python
# LLM 模型的本质（伪代码）
def llm_model(token_ids: list[int]) -> list[float]:
    """
    输入：一串 token id（如 [101, 234, 567, ...]）
    输出：长度 = 词汇表大小（如 50000）的概率向量
          每个位置表示"下一个 token 是该 token 的概率"
    """
    # 神经网络前向传播（亿万次矩阵乘法）
    logits = neural_network_forward(token_ids)
    probabilities = softmax(logits)
    return probabilities    # shape: [vocab_size]
```

**特性**：
- ✅ **纯函数**：相同输入永远相同输出（除非 dropout / 多线程随机性）
- ✅ **无状态**：每次调用独立，模型不记得上一次说了什么
- ✅ **单步**：一次调用只产出**一个**概率分布（不是整个回答）
- ❌ **不知道**：HTTP / JSON / messages 结构 / role / stop / temperature / 你是谁

**模型完全无知**于协议世界。它只懂 token 数组进 → 概率向量出。

---

## 3. ⭐⭐ LLM API 服务器内部 8 步流水线

收到一个 HTTP 请求后，LLM API 服务器内部干 8 件事：

```
HTTP request 进来
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ① HTTP 解析层                                                  │
│    - 验证 API key                                              │
│    - 解析 JSON body                                            │
│    - 路由到对应模型（基于 "model": "gpt-4" 字段）               │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ② 请求队列 / 批处理（可选）                                      │
│    - 多个并发请求合批一起送进模型（提高 GPU 利用率）              │
│    - vLLM / TGI 的 continuous batching                         │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ③ Chat template 应用                                          │
│    messages = [{role: "user", content: "查天气"}]              │
│    → "<|im_start|>user\n查天气<|im_end|>\n<|im_start|>assistant\n" │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ④ Tokenize                                                    │
│    "<|im_start|>user\n查天气..." → [101, 5234, 8721, 102, ...] │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ⑤ ⭐ 生成循环（核心）                                            │
│                                                              │
│    generated_tokens = []                                     │
│    full_input = tokenized_prompt                             │
│                                                              │
│    while not should_stop():                                  │
│        # 调 LLM 模型一次（纯函数）                             │
│        logits = LLM_MODEL(full_input)                        │
│                                                              │
│        # 采样下一个 token                                      │
│        next_token = sampler(logits, temperature, top_p, ...) │
│                                                              │
│        # 拼回去                                                │
│        full_input.append(next_token)                         │
│        generated_tokens.append(next_token)                   │
│                                                              │
│        # 检查停止条件                                          │
│        if next_token == EOS_TOKEN: break                     │
│        if matches_stop_sequence(): break                     │
│        if len(generated_tokens) >= max_tokens: break         │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ⑥ Detokenize                                                  │
│    [342, 678, 234] → "北京今天 -3°C 雪"                       │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ⑦ 结构化响应                                                   │
│    {"choices": [{"message": {...}}], "usage": {...}}         │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│ ⑧ HTTP 序列化 + 返回                                           │
└──────────────────────────────────────────────────────────────┘
```

**核心洞察**：模型在 **⑤ 生成循环里被反复调用**。生成 100 个 token 的回答 = 调模型 100 次。

---

## 4. ⭐ 协议字段在哪一步生效（全局对照表）

| 协议字段 | 生效在哪步 | 怎么生效 |
|---|---|---|
| `messages` | ③ chat template | 转成纯字符串 prompt |
| `tools` | ③ chat template | 嵌入 prompt 文本（"Available tools: ..."）|
| `tool_choice` | ⑤ 采样器 | 约束首个 token 走 tool_call 触发标记 |
| `temperature` | ⑤ 采样器 | 调整 logits 分布尖锐度 |
| `top_p` / `top_k` | ⑤ 采样器 | 限制采样候选范围 |
| `max_tokens` | ⑤ 循环计数 | `len(generated_tokens) >= max_tokens` 退出 |
| `stop` | ⑤ 后缀检查 | `matches_stop_sequence()` 退出 |
| `response_format` | ⑤ 采样器 | constrained decoding 屏蔽不合法 token |

**LLM 模型本身只参与一件事**：输出 logits（步骤 ⑤ 里 `LLM_MODEL(full_input)` 那一行）。其他**全是 LLM API 服务器干的**。

---

## 5. ⭐⭐ 关键概念：模型是"逐 token 调用 N 次"，不是"调一次拿整个回答"

很多人会以为：

```python
# ❌ 错误想象
answer = LLM("查天气")
# 一次调用拿到完整回答
```

**实际上**：

```python
# ✅ 真实情况
generated = []
input_tokens = tokenize("查天气")

while True:
    logits = LLM(input_tokens + generated)     # ← 每次调用！
    next_token = sample(logits)
    if next_token == EOS: break
    generated.append(next_token)

answer = detokenize(generated)
```

**生成 100 token 的回答 → LLM 模型被调用 100 次**！

### 为什么这么慢还要这么做？

因为 LLM 是**自回归（autoregressive）模型**：每生成下一个 token 都需要看到前面所有已生成的 token 作为上下文。**没法一次性预测全部**。

### 实际后果

| 后果 | 解释 |
|---|---|
| **token 计费** | 输出长度直接决定计算成本（100 token 跑 100 次模型）|
| **流式响应可行** | 因为是逐 token 生成，可以**边生成边返回** —— SSE 流式输出的根基 |
| **stop 能即时生效** | 服务器在每次循环结束都能检查 stop，**不用等完整生成** |
| **KV cache 优化** | 前 99 次的中间计算结果可以复用 |

---

## 6. ⭐ 关键优化：KV cache（生产级 LLM API 服务器必备）

### 朴素实现的问题

```
第 1 次调用 LLM：输入 [t1, t2, t3]              （prompt 3 token）
第 2 次调用 LLM：输入 [t1, t2, t3, g1]          （多 1 个生成的 token）
第 3 次调用 LLM：输入 [t1, t2, t3, g1, g2]      （多 1 个）
...
第 100 次调用：输入 [t1, t2, t3, g1, g2, ..., g99]    （越来越长）
```

每次都要把**整个**前缀重新跑一遍 → 计算量 **平方级增长**。

### KV cache 解决方案

LLM 内部 attention 机制对每个 token 算"key/value 向量"。**这些向量只依赖当前位置和之前的位置**，不依赖后续 token（causal attention）。

所以服务器**缓存每个 token 的 K/V**：

```
第 2 次调用：只算 g1 的 K/V，复用 t1/t2/t3 的 K/V    ← 增量计算
第 100 次调用：只算 g99 的 K/V，复用前 99 个         ← 增量计算
```

**整体计算量从 O(N²) 降到 O(N)** —— 这是 LLM 推理的**核心优化**。

> 💡 **Week 1 [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md) §7 "Prompt caching"** 提过的"前缀 KV 复用让 agent 多轮 ReAct 受益" —— 那是**跨请求**的 KV cache。本节讲的是**单次请求内**的 KV cache。**同一个机制，两个层级**。

---

## 7. ⭐ 流式 vs 非流式：差异就在 ⑦ 步

LLM API 服务器步骤 ⑤ 的生成循环**本质上就是流式的**（一个 token 一个 token 生成）。区别只在**返回模式**：

| 模式 | ⑦ 响应阶段做法 |
|---|---|
| 非流式（`stream=False`，默认）| 等整个循环跑完 → 一次性 detokenize → 包成完整 JSON 返回 |
| 流式（`stream=True`）| 每生成一个 token → 立刻 detokenize → 用 Server-Sent Events 推一段 chunk → 客户端实时拿 |

**生成过程完全一样**。流式只是"提前送货"。

> 💡 这就是为什么 [InferenceClientModel.generate_stream](../../../src/smolagents/models.py#L1591) 和 `generate` 共享同一个 `_prepare_completion_kwargs` —— body 完全一样，只多个 `stream=True` 标记，告诉 LLM API 服务器"用流式响应模式"。详见 [inference-client-model-impl.md §7](../03-source/day3-models/inference-client-model-impl.md)。

---

## 8. ⭐ 云端 vs 本地：架构对比

### 8.1 云端场景（OpenAI / HF Inference）

```
你电脑                        远程数据中心
─────────                    ──────────────────
agent 框架  ──HTTP──→  LLM API 服务器（独立进程）
                            │
                            ├─ 步骤 ①-⑧ 全在这里
                            │
                            └─ LLM 模型（GPU 上的权重）
```

**LLM 模型和 LLM API 服务器在同一台机器**（甚至同一个 Python 进程），但通过网络远离用户。**HTTP 是它们对外的唯一接口**。

### 8.2 本地场景（TransformersModel / VLLMModel）

```
你电脑（一切都在这里）
────────────────────────────────────
agent 框架（smolagents）
    │
    ├─ TransformersModel.generate()  ← 直接 Python 函数调用
    │       │
    │       ├─ 步骤 ①（HTTP 解析）→ 跳过！没 HTTP
    │       ├─ 步骤 ②（队列）→ 跳过！只有自己一个请求
    │       ├─ 步骤 ③ chat template
    │       ├─ 步骤 ④ tokenize
    │       ├─ 步骤 ⑤ ⭐ 生成循环
    │       │       └─ LLM 模型（你 GPU/CPU 上的权重）
    │       ├─ 步骤 ⑥ detokenize
    │       └─ 步骤 ⑦ 包 ChatMessage
    │
    └─ 拿到 ChatMessage 继续 ReAct
```

**没有 HTTP / 没有独立服务器进程**。"LLM API 服务器" 这个角色被 **TransformersModel 这个 Python 类承担了**（在同一个进程里）。

> 💡 **Day 3 [inference-client-model-impl.md §1](../03-source/day3-models/inference-client-model-impl.md)** 讲的"本地模型直接继承 Model 跳过 ApiModel" —— 现在更深一层理解：**因为本地模型不需要 ApiModel 的 HTTP/限流/重试机制**，但仍然需要做步骤 ③-⑦（chat_template / tokenize / 生成循环 / detokenize）。这些事被 transformers 库内部接管了。

### 8.3 协议无关性

无论云端还是本地，**核心生成循环（步骤 ⑤）的逻辑完全一致**：
- 输入 token 序列
- 调模型拿 logits
- 采样选 next_token
- 检查停止条件
- 重复

所以 smolagents 的子类（InferenceClientModel / TransformersModel / VLLMModel）虽然实现不同，**对 agent 框架暴露的接口完全相同**：传入 messages，返回 ChatMessage。这就是 [Model 基类抽象](../03-source/day3-models/model-class-role-overview.md)的真正威力。

---

## 9. 一图厘清"协调"角色

```
            ┌─────────────────────────────────────────────┐
            │             LLM API 服务器（"指挥官"）        │
            │                                             │
HTTP req ──→  解析 → chat_template → tokenize             │
            │                              ↓              │
            │   ┌──────────────────────────┴─────────┐   │
            │   │ 生成循环（"轮转门"）                  │   │
            │   │                                    │   │
            │   │   while not stop:                  │   │
            │   │     ┌──────────────────┐           │   │
            │   │     │  调用 LLM 模型     │ ←──────┐  │   │
            │   │     │  （"工人"）        │        │  │   │
            │   │     │  纯函数：吃token    │        │  │   │
            │   │     │  吐 logits 概率    │        │  │   │
            │   │     └────────┬─────────┘        │  │   │
            │   │              ↓                  │  │   │
            │   │     采样器（应用 temperature）    │  │   │
            │   │              ↓                  │  │   │
            │   │     next_token                  │  │   │
            │   │              ↓                  │  │   │
            │   │     拼回输入序列  ───────────────┘  │   │
            │   │              ↓                     │   │
            │   │     检查停止（EOS / stop / max）     │   │
            │   └──────────────┬─────────────────────┘   │
            │                  ↓                         │
            │   detokenize → 包响应                       │
HTTP resp ←──                                            │
            └─────────────────────────────────────────────┘

LLM 模型只懂："给我 token 序列，我吐 logits 概率"
LLM API 服务器懂：HTTP / JSON / chat_template / 采样 / 停止 / 缓存 / 队列 / 流式 / ...
```

---

## 10. 总结表

| 问题 | 答案 |
|---|---|
| LLM 模型本质是什么？ | 纯函数：吃 token 序列 → 吐下一个 token 的概率分布 |
| LLM 模型有状态吗？ | ❌ 无状态，每次调用独立 |
| 一次 LLM 模型调用产出什么？ | **一个**概率向量（不是整个回答）|
| 生成 100 token 的回答需要调几次模型？ | **100 次** |
| LLM API 服务器干什么？ | 协调器：解析 HTTP / 跑生成循环 / 调模型 N 次 / 在循环里施加所有协议控制 |
| 协议字段（temperature/stop/max_tokens）在哪生效？ | **采样器 + 循环退出条件**（步骤 ⑤）—— 都在 LLM API 服务器，模型完全不知道 |
| KV cache 是什么？ | 复用之前 token 的 K/V 向量，避免每次重算前缀 → O(N²) 降到 O(N)|
| 流式和非流式的本质区别？ | 生成循环完全相同，区别只在响应阶段是"等完一次性返回"还是"边生成边推 chunk"|
| 本地模型（TransformersModel）也有 LLM API 服务器吗？ | **概念上有**（步骤 ③-⑦ 仍然存在），只是被 transformers 库在同一 Python 进程内承担，没 HTTP |
| 为什么 agent 框架不需要关心这些内部？ | 子类（Model 基类抽象）封装了云端 vs 本地的差异，对 agent 框架只暴露 `generate(messages) → ChatMessage` |

---

## 相关链接

- 必读前置：
  - [llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md) — 4 角色术语 + 两层关系
- 应用本心智模型的笔记：
  - [model-stop-sequences.md §7](../03-source/day3-models/model-stop-sequences.md) — stop 是被动检测，对应步骤 ⑤ 的 `matches_stop_sequence()`
  - [model-generate-params-explained.md](../03-source/day3-models/model-generate-params-explained.md) — 7 参数对应表 4 的"生效在哪步"
  - [inference-client-model-impl.md](../03-source/day3-models/inference-client-model-impl.md) — 子类如何把"通用 8 步"翻译成具体实现
- Week 1 概念：
  - [codeagent-vs-toolcallingagent.md §7](codeagent-vs-toolcallingagent.md) — Prompt caching 与本笔记的 KV cache 是同一机制的不同层级

## 遗留问题

- [ ] vLLM / TGI 的 continuous batching 详细机制（步骤 ② 队列）—— 留作后续探索
- [ ] Speculative decoding（用小模型预测、大模型验证）—— 步骤 ⑤ 的高级优化
- [ ] Paged attention（vLLM 的 KV cache 内存管理）—— 步骤 ⑥ 优化
- [ ] 多模态模型（视觉 + 文本）的步骤 ④ tokenize 怎么处理图像 patch
