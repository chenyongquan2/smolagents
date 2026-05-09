---
created: 2026-05-06
status: active
tags: [concepts, llm, api-server, architecture, mental-model, prerequisite]
---

# LLM 模型 vs LLM API 服务器：两层架构与协议字段归属

## 背景 / 动机

读 [model-stop-sequences.md](../03-source/day3-models/model-stop-sequences.md) 时容易混淆这句话：

> "prompt 是给 LLM 看的指令；stop 是给 API 服务器的指令"

**LLM 和 LLM API 服务器不是一回事吗？**

—— 不是。理解这两层的区别**是读懂所有 LLM 协议字段（stop / temperature / tools / max_tokens / response_format / tool_choice...）的前提**。本笔记建立这个底层心智模型。

---

## 1. ⭐ 一句话区分

| 维度 | LLM（模型本体）| LLM API 服务器 |
|---|---|---|
| **本质** | 神经网络权重 + 架构 | HTTP 服务程序 |
| **输入** | 一串 token（数字数组）| HTTP 请求（JSON）|
| **输出** | 下一个 token 的概率分布 | HTTP 响应（JSON）|
| **知道 HTTP 吗** | ❌ 不知道 | ✅ 它就是干这个的 |
| **知道 `stop`/`temperature` 字段吗** | ❌ 完全不知道 | ✅ 它解析并施加这些控制 |
| **能改变行为的方式** | 重新训练 / 换权重 | 改服务器端代码 / 升级协议 |

**LLM 是"引擎"，API 服务器是"车"**。用户操作的是方向盘、油门、刹车 —— 不是直接拽引擎活塞。

---

## 2. ⭐⭐ 术语约定（从此固定使用）

后续所有 smolagents 学习笔记**必须**用这套术语，避免"调用方 / 客户端 / 应用层 / 服务器" 混用导致心智模型混乱。

### 4 个角色（按数据流方向）

```
                        ┌──────────────────────┐
                        │   LLM API 服务器       │
   ┌────────┐          │   (HTTP 服务程序)      │
   │ 用户    │          │                      │
   │ (你)    │ ────→    │   ┌──────────────┐   │
   └────────┘   task    │   │   LLM 模型    │   │
       ↑               │   │ (神经网络)     │   │
       │               │   └──────────────┘   │
       │ 答案           └──────────────────────┘
       │                          ↑
       │                          │ HTTP
       │                          │
       │              ┌──────────────────────┐
       └──────────── │   smolagents agent    │
                     │   (Python 库)         │
                     └──────────────────────┘
```

| 术语 | 指什么 | 在哪运行 | ❌ 不再用的别名 |
|---|---|---|---|
| **用户** | 你（敲键盘的人）| 你的电脑 | ~~调用方~~ |
| **agent 框架** | smolagents 这个 Python 库 | 你的电脑（本地进程）| ~~调用方 / 客户端 / 应用层~~ |
| **LLM API 服务器** | 跑在 HuggingFace / OpenAI 机房的 HTTP 服务 | 远程数据中心 | ~~服务器 / API 服务器~~（简写场景下可接受）|
| **LLM 模型** | 神经网络权重（如 Qwen-72B / GPT-4）| LLM API 服务器内部 | ~~模型 / LLM~~（简写场景下可接受）|

### 进程边界

```
你电脑（本地进程）：
   - 用户（你 + 操作系统）
   - agent 框架（smolagents Python 库）
   ───────────────── 网络 ─────────────────
远程数据中心：
   - LLM API 服务器（HTTP 进程，多副本）
       └─ LLM 模型（GPU 上的神经网络权重）
```

### 关键关系

```
用户   →   agent 框架   →   HTTP   →   LLM API 服务器   →   LLM 模型
       (smolagents)               (HuggingFace 机房)        (内部)
```

### 注意：ChatGPT 场景没有 agent 框架这一层

| 场景 | 用户 | agent 框架 | LLM API 服务器 | LLM 模型 |
|---|---|---|---|---|
| 你用 smolagents | 你 | smolagents | HF / OpenAI | Qwen / GPT-4 |
| 你用 ChatGPT 网页 | 你 | ❌ 没有（直接对话）| OpenAI 后端 | GPT-4 |
| 你直接调 OpenAI SDK | 你 | ❌ 没有 / 你自己写的 | OpenAI 后端 | GPT-4 |

> 💡 **因此当我们讨论 agent 协议字段（stop/tools/tool_choice）时，agent 框架角色必须存在**。普通 ChatGPT 对话不涉及这些字段。

---

## 3. 形象类比：自动售货机里的计算器

```
┌─────────────────────────────────────────┐
│      自动售货机（LLM API 服务器）          │
│                                         │
│   ┌─────────────────────────────┐       │
│   │   里面装了一个计算器          │       │
│   │   （LLM 模型）               │       │
│   │   只会做：1+1=2 这种事        │       │
│   └─────────────────────────────┘       │
│                                         │
│   售货机自己负责：                        │
│   - 接收硬币（HTTP 请求）                 │
│   - 显示菜单（路由 / 模型选择）            │
│   - 找零钱（限流 / 计费）                 │
│   - 控制出货时机（stop / max_tokens）     │
│   - 安全检查（rate limit / safety filter）│
└─────────────────────────────────────────┘
```

**计算器（模型）只会算数，不知道"硬币"、"菜单"、"找零"是什么**。这些都是售货机（服务器）干的事。

---

## 4. ⭐ 协议字段对谁有意义？

HTTP body：

```json
{
    "messages": [...],          ← 部分进模型，部分给服务器
    "stop": ["<end_code>"],     ← 完全是给服务器看的
    "temperature": 0.7,         ← 完全是给服务器看的
    "tools": [...],             ← 部分进模型，部分给服务器
    "max_tokens": 1024,         ← 完全是给服务器看的
    "tool_choice": "required",  ← 完全是给服务器看的
    "response_format": {...}    ← 完全是给服务器看的
}
```

### 逐个分析

#### `messages` —— 部分进模型，部分给服务器

```
服务器拿到 messages 后：
  ① 用 chat template 拼成纯字符串："<|system|>...<|user|>...<|assistant|>"
  ② 用 tokenizer 切成 token：[101, 234, 567, ...]
  ③ 这串 token 才喂给模型 ← 模型从这里开始工作
```

**模型只看到 token 序列**，根本没看到 JSON、role 字段、message 边界。

#### `stop` —— **完全在服务器层**，模型不知道

```
模型每生成一个 token：
  生成 "<"     → 服务器累积："<"
  生成 "end"   → 服务器累积："<end"
  生成 "_code" → 服务器累积："<end_code"
  生成 ">"     → 服务器累积："<end_code>"
                 ↑ 服务器检测到匹配 stop 列表
                 → 立刻 break 循环，不再让模型继续生成
```

**模型完全不知道"停止字符串"这个概念存在**。它只是在某一刻被服务器**强制掐断** —— 就像跑步时被人按下停止键，跑步者不知道为什么停。

#### `temperature` —— **完全在服务器的采样层**，模型不知道

```
模型每一步输出：下一个 token 的概率分布
  P(token_A) = 0.5
  P(token_B) = 0.3
  P(token_C) = 0.2
  ...

服务器拿到分布后：
  - 按 temperature 调整概率（调高更随机、调低更确定）
  - 按调整后分布采样选 token
  - 把选中的 token 拼回输入序列，下一轮再喂模型
```

**模型只输出"概率"，不知道"温度"的存在**。temperature 是服务器在模型输出之上做的**后处理**。

#### `tools` —— 服务器把它"嵌"进 prompt 文本喂给模型

```
服务器拿到 tools 字段后：
  - 按 chat template 把每个 tool 的 JSON schema 拼成文字描述
    "Available tools: get_weather(city: str) -> str ..."
  - 这段文字混入 system prompt 部分
  - 整个被 tokenize 喂给模型

模型看到的只是文字，它不知道这段文字来自 JSON `tools` 字段。
```

> 💡 [tool-schema-rendering-mental-model.md](../03-source/day2-tools/tool-schema-rendering-mental-model.md) 讲的"**LLM 始终只看 messages**"—— 哪怕协议层有 `tools` 字段，最终也是被服务器渲染进 prompt 文本喂给模型。

#### `max_tokens` —— 服务器层的循环计数器

```
服务器内部循环：
  while 已生成 token 数 < max_tokens:
      让模型输出下一个 token
      if 命中 stop:
          break
  返回所有已生成的 token
```

模型本来会**永远生成下去**（除非碰到 EOS），是服务器在外面套循环 + 计数控制。

#### `tool_choice` / `response_format` —— 服务器对采样的约束

服务器实现 **constrained decoding** / **grammar-constrained sampling**：在每一步采样时**只允许选符合约束的 token**。例如 `response_format=json_schema` 时，服务器会动态屏蔽不符合 schema 的 token。

模型还是吐"概率分布"，但服务器**只在合法 token 集合上采样**。模型不知道有约束。

---

## 5. ⭐ 一图说清两层关系

```
              ┌──────────────────────────────────────────────┐
              │            LLM API 服务器                      │
              │                                              │
HTTP request ─→  ① 解析 JSON                                  │
              │     ↓                                        │
              │  ② 协议字段处理：                              │
              │     - tools  → 嵌入 prompt 文本                │
              │     - stop   → 准备截断规则（自己拿着）          │
              │     - max_tokens → 准备计数器（自己拿着）        │
              │     - temperature → 准备采样参数（自己拿着）     │
              │     - response_format → 准备语法约束（自己拿着）  │
              │     ↓                                        │
              │  ③ chat_template + tokenize → token 序列      │
              │     ↓                                        │
              │  ┌────────────────────────────────────┐      │
              │  │     LLM 模型（神经网络）              │      │
              │  │                                    │      │
              │  │   循环每一步：                        │      │
              │  │     - 接收当前 token 序列              │      │
              │  │     - 输出下一个 token 的概率分布      │      │
              │  │                                    │      │
              │  │   ⚠️ 只懂 token，不懂 HTTP/JSON/协议   │      │
              │  └────────────────────────────────────┘      │
              │     ↓                                        │
              │  ④ 服务器拿到概率分布：                          │
              │     - 套 temperature 调整                     │
              │     - 按 tool_choice / response_format 约束    │
              │     - 采样选 token                            │
              │     - 检查是否命中 stop / 超 max_tokens         │
              │     - 命中就停；没命中就拼回 token 序列回到 ③     │
              │     ↓                                        │
              │  ⑤ 把 token 序列 detokenize 回字符串           │
              │     包成 HTTP response                        │
HTTP response ←                                              │
              └──────────────────────────────────────────────┘
```

**关键洞察**：服务器是"翻译官 + 监工"。它把协议层（agent ↔ 服务器）翻译成模型层（服务器 ↔ 神经网络），同时在模型工作时施加各种控制。

---

## 6. 回到 stop 的例子：双保险的"双"指什么

```json
{
    "messages": [
        {"role": "system",
         "content": "End your code with <end_code>"},   ← 这段文字
        ...
    ],
    "stop": ["<end_code>"]                              ← 这个字段
}
```

**两条信息送到不同的"耳朵"**：

| 信息 | 谁解读 | 怎么生效 |
|---|---|---|
| `messages.content` 里的 "End with `<end_code>`" | **LLM 模型**（经 tokenize 进入输入）| 模型"自觉"在生成代码后输出 `<end_code>` |
| `stop` 字段 | **API 服务器**（不进模型）| 服务器边监控模型输出边检查，看到 `<end_code>` 强制截断 |

**所以双保险的"双"指 LLM 模型 + API 服务器协同工作** —— 一个主动写出停止标记，一个被动检测停止标记。**两个不同主体一起兜底**才叫双保险。

---

## 7. ⭐ 这个心智模型贯穿哪些 smolagents 学习内容

| 学习内容 | 用到这个心智模型的地方 |
|---|---|
| [model-stop-sequences.md](../03-source/day3-models/model-stop-sequences.md) | "prompt 给 LLM / stop 给服务器"双保险 |
| [model-generate-params-explained.md](../03-source/day3-models/model-generate-params-explained.md) | 7 参数中哪些是服务器层、哪些是 prompt 层 |
| [tool-schema-rendering-mental-model.md](../03-source/day2-tools/tool-schema-rendering-mental-model.md) | tools 字段最终也是服务器渲染成 prompt 文本 |
| [chat-message-roles.md](chat-message-roles.md) | role 是 chat template 的 token，最终被 tokenize 进模型 |
| [model-and-protocols-overview.md](model-and-protocols-overview.md) | "调用渠道" = "去找哪个 API 服务器"，模型权重可能完全相同 |
| 后续 Day 4-5 agents.py | agent 框架是服务器之外的**第三层**（agent → server → model）|

---

## 8. ⚠️ 常见认知误区

### 误区 ① "调 LLM 就是直接和模型对话"

❌ 错。你和 API 服务器对话，服务器**代理**你和模型对话。模型在大多数云端场景**完全不可见**。

### 误区 ② "同一个模型在不同 provider 输出应该一致"

❌ 不一定。同样的 Llama-3 部署在 HF / Together / Fireworks 上，**模型权重一致**但**服务器实现不一致**：tokenizer 版本可能不同、采样策略可能不同、`stop` 实现可能不同（详见 [model-stop-sequences.md §6.1](../03-source/day3-models/model-stop-sequences.md) 原因 ②）—— 同样的 prompt 可能输出不同结果。

### 误区 ③ "改 temperature 就是改模型行为"

❌ 不准确。模型行为没变（仍输出同一个概率分布），变的是**服务器的采样策略**。

### 误区 ④ "LLM API 服务器都长一样"

❌ 错。OpenAI / Anthropic / HF / 自研服务器的实现细节差异巨大。这就是为什么 smolagents 要为每家写一个 [Model 子类](../03-source/day3-models/model-class-role-overview.md)。

---

## 9. 总结表

| 问题 | 答案 |
|---|---|
| LLM 和 LLM API 服务器一样吗？ | ❌ 不是。LLM 是神经网络，API 服务器是 HTTP 服务程序 |
| 谁知道 HTTP / JSON？ | API 服务器知道；LLM 完全不知道 |
| 谁能看到 `stop` 字段？ | API 服务器看到；模型完全不知道 |
| 模型能看到什么？ | 只看到 token 序列（messages 经 chat template + tokenize 来的）|
| `temperature` 是模型参数还是服务器参数？ | **服务器参数**，在模型概率分布之上采样调整 |
| `tools` 字段是给模型看吗？ | 部分是 —— 服务器把它渲染成 prompt 文字嵌入 messages 再喂模型 |
| 双保险的"双"指什么？ | LLM 模型 + API 服务器**两个不同主体**协同工作 |
| 类比？ | 模型 = 引擎；服务器 = 车（用户操作车上的控制，不直接碰引擎）|

---

## 相关链接

- 应用本心智模型的笔记：
  - [model-stop-sequences.md](../03-source/day3-models/model-stop-sequences.md) — 双保险的两个主体
  - [model-generate-params-explained.md](../03-source/day3-models/model-generate-params-explained.md) — 7 参数分别属于哪一层
  - [tool-schema-rendering-mental-model.md](../03-source/day2-tools/tool-schema-rendering-mental-model.md) — tools 字段的两层渲染
- Week 1 概念前置：
  - [model-and-protocols-overview.md](model-and-protocols-overview.md) — Model 子类 = 调用渠道（不同 API 服务器）
  - [chat-message-roles.md](chat-message-roles.md) — role 进 chat template 进 tokenize 进模型

## 遗留问题

- [ ] 本地模型（TransformersModel / VLLMModel）跳过 HTTP 这一层，但**仍然有"模型 vs 推理引擎"两层** —— 推理引擎扮演 API 服务器的角色（采样 / stop / temperature 仍由引擎做）。本质架构相同
- [ ] **三层 agent 架构**：agent 框架 → API 服务器 → LLM 模型 —— 每一层都有自己的"协议"和"翻译"。Day 4-5 读 agents.py 时再深入
