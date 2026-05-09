---
created: 2026-05-06
status: active
tags: [concepts, chat-template, llm, tokenizer, mental-model]
---

# Chat Template：把结构化 messages 翻译成 LLM 模型能吃的扁平字符串

⚠️ **必读前置**：
- [chat-message-roles.md](chat-message-roles.md)（role 概念）—— Week 1 已写
- [llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md)（4 角色术语）
- [llm-api-server-internals.md](llm-api-server-internals.md) §3 步骤 ③（chat template 在服务器流水线的位置）

> 本笔记把 [chat-message-roles.md](chat-message-roles.md) 留下的悬念落地：role 标记最终怎么影响 LLM 模型？答案是**经 chat template 翻译成特殊 token**。这是 "role 概念 → 模型实现" 的完整闭环。

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

---

## 1. ⭐ 一句话角色

**Chat template = 把"结构化 messages 列表"翻译成 LLM 模型能吃的"扁平字符串"的模型专属格式规则**。

```
agent 框架发的：           LLM 模型实际看到的：
─────────────────         ─────────────────────────
[                          "<|im_start|>system
  {"role": "system",        你是个 helpful assistant
   "content": "你是..."},   <|im_end|>
  {"role": "user",          <|im_start|>user
   "content": "查天气"}     查天气
]                           <|im_end|>
                            <|im_start|>assistant
                            "
                            ↑ 接下来由模型续写
```

**核心**：LLM 模型只吃 token 序列（最终是字符串），不吃 JSON。chat template 就是中间这层"翻译器"。

---

## 2. ⭐ 为什么需要？—— LLM 模型不认 JSON

回顾 [llm-api-server-internals.md §2](llm-api-server-internals.md)：LLM 模型本质是 `(token序列) → (下一token概率)`。它只懂 token，不懂 "role" / "messages" / "content" 这些 JSON 字段。

但 agent 框架希望用结构化 API（按角色分清 user/assistant/system），所以**必须有人把结构变扁平**。这件事就是 chat template 干的，由 **LLM API 服务器在 [步骤 ③](llm-api-server-internals.md)** 完成。

---

## 3. ⭐⭐ 关键事实：不同模型有不同 chat template

每个模型在**训练时**就用某种特定格式喂数据。**推理时必须用同一个格式**，否则模型会困惑。

### 真实例子对比（同样的 messages，4 种格式）

#### Qwen / ChatML 格式
```
<|im_start|>system
你是个 helpful assistant<|im_end|>
<|im_start|>user
查天气<|im_end|>
<|im_start|>assistant
```

#### Llama-2 格式（完全不同）
```
[INST] <<SYS>>
你是个 helpful assistant
<</SYS>>

查天气 [/INST]
```

#### Llama-3 格式（又变了）
```
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

你是个 helpful assistant<|eot_id|><|start_header_id|>user<|end_header_id|>

查天气<|eot_id|><|start_header_id|>assistant<|end_header_id|>
```

#### Mistral 格式
```
<s>[INST] 你是个 helpful assistant

查天气 [/INST]
```

**4 个模型，4 种完全不同的拼法**。每家都是模型训练时**烧死**的格式。

> 💡 **没有统一标准**。chat template 是 LLM 圈"协议碎片化"的另一个体现（类似 [model-stop-sequences.md §9.3](../03-source/day3-models/model-stop-sequences.md) 讲的 stop 字段名碎片化）。

---

## 4. ⭐ "特殊 token" 的本质

`<|im_start|>` / `<|im_end|>` / `[INST]` / `<|eot_id|>` —— 这些**不是普通字符串**，而是 **tokenizer 词汇表里的特殊 token**：

```
普通文字："hello"        → tokenize → [t1, t2]    （拆成 2 个常见 token）
特殊token："<|im_start|>" → tokenize → [token_32011]  （直接 1 个特殊 token）
```

**作用**：让模型在训练时学到"看到这个 token = 角色边界 / 对话结束 / 系统消息开始"。这是模型学会"按 role 分隔信息"的根基。

> 💡 **回顾 Week 1 [chat-message-roles.md](chat-message-roles.md) 闭环**：
> - Week 1 结论："role 是 LLM 行为的方向盘"
> - Day 3 现在看清细节：role 标记**通过 chat template 翻译成特殊 token**，**这些特殊 token 才是真正影响模型行为的东西**
> - "role" 只是 OpenAI 协议层的结构化抽象 → chat template 是把抽象落地成模型可识别 token 的**翻译层**

---

## 5. ⚠️ 用错 chat template 会怎样？

模型会**严重混乱**。比如用 Llama-3 模型但喂 Llama-2 格式：

```
LLM 模型期望看到：<|begin_of_text|><|start_header_id|>...
实际收到：[INST] <<SYS>> ...

LLM 模型反应：
- 把 [INST] 当成一段普通文字（因为不在它的特殊 token 列表里）
- 不知道哪里是 user / 哪里是 system
- 输出质量大幅退化（可能只回答最后一段、忽略 system prompt、瞎扯…）
```

**这就是为什么 chat template 必须严格匹配模型版本**。同一家 Llama-2 → Llama-3 升级时换 template，不兼容旧客户端。

---

## 6. ⭐ chat template 是谁应用的？

**LLM API 服务器**（不是 agent 框架，不是 LLM 模型）。

```
agent 框架：  发送 [{role: "user", content: "..."}]
                   ↓ HTTP
LLM API 服务器：
              ① 解析 JSON
              ② 查这个模型用什么 chat template
              ③ 应用 template → 拼成扁平字符串    ← 这一步！
              ④ tokenize 成 token 序列
              ⑤ 调 LLM 模型生成
LLM 模型：    只看到 token 序列，根本不知道有过 messages 结构
```

**agent 框架完全不用关心 chat template** —— 只要按 OpenAI 协议传 messages，服务器自己根据 model_id 选对 template。

### HF transformers 库的 `apply_chat_template`

如果你用本地模型（[TransformersModel](../03-source/day3-models/inference-client-model-impl.md)），`transformers` 库的 tokenizer 自带这个方法：

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
messages = [{"role": "user", "content": "查天气"}]

# apply_chat_template 把 messages 变成扁平字符串
text = tokenizer.apply_chat_template(messages, tokenize=False)
print(text)
# "<|im_start|>user\n查天气<|im_end|>\n<|im_start|>assistant\n"
```

**chat template 的"规则"存在 tokenizer 配置文件 `tokenizer_config.json` 里**，作为 Jinja2 模板字符串。每个模型都有自己的版本。

---

## 7. ⭐ 一个有趣的副作用：同模型不同 provider 输出可能不同

回顾 [llm-vs-api-server-architecture.md §8 误区 ②](llm-vs-api-server-architecture.md)：

**同样的 Llama-3 模型，部署在 HF / Together / Fireworks 上输出可能不一样**。

原因之一就是 **chat template 实现细节差异**：
- 哪一家是不是漏了 `<|begin_of_text|>` 前缀？
- 哪一家在 system 缺失时自动加默认 system message？
- 多轮对话的 token 拼接方式有没有微小差异（如末尾换行、空格）？
- system prompt 注入位置是否一致？

**这些都不是模型差异，是 chat template 应用细节差异**。**模型权重完全相同，输出可能不同**。

---

## 8. ⭐ agent 场景里的特殊关切：`tools` 字段也走 chat template

回顾 Day 2 [tool-schema-rendering-mental-model.md](../03-source/day2-tools/tool-schema-rendering-mental-model.md)：HTTP `tools` 字段不是直接喂模型，而是**被 LLM API 服务器渲染进 system prompt 文本**，再走 chat template 喂模型。

```
HTTP body:
{
    "messages": [...],
    "tools": [{"type": "function", "function": {...}}, ...]
}

LLM API 服务器步骤 ③：
    将 tools 拼接到 system prompt:
    "<|im_start|>system
    你是个 agent。可用工具列表：
    - get_weather(city: str): 查询某城市天气
    - calculator(expr: str): 计算表达式
    <|im_end|>
    <|im_start|>user
    ..."
```

**所以"tools 字段是给模型还是给服务器看？"答案**：服务器解析 + 服务器渲染进 prompt → 通过 chat template → 模型才看到（作为文本）。又一次印证 [llm-vs-api-server-architecture.md §3](llm-vs-api-server-architecture.md) 的"两层 + 翻译"模型。

> 💡 **不同模型的 tools 渲染格式也不同**：Qwen 把 tools 渲染成 JSON Schema 风格描述；Llama-3 用 `<|python_tag|>` 特殊 token 标记 tool call 区域；Mistral 用纯文字描述。**协议字段一致 → 渲染细节因模型 chat template 而异**。

---

## 9. role 转换的真实影响（呼应 Day 3 mental-model）

回顾 [model-generate-mental-model.md §5](../03-source/day3-models/model-generate-mental-model.md)：smolagents 的 5 个内部 role（USER / ASSISTANT / SYSTEM / TOOL_CALL / TOOL_RESPONSE）经 `tool_role_conversions` **降维成 3 个**（OpenAI 协议认的 user/assistant/system）。

**为什么降维？因为 LLM API 服务器的 chat template 只认 OpenAI 标准 3 role**：

| smolagents 内部 role | OpenAI 协议 role | chat template 翻译后的特殊 token |
|---|---|---|
| USER | user | `<|im_start|>user` |
| ASSISTANT | assistant | `<|im_start|>assistant` |
| SYSTEM | system | `<|im_start|>system` |
| TOOL_CALL（→ ASSISTANT）| assistant | `<|im_start|>assistant` |
| TOOL_RESPONSE（→ USER）| user | `<|im_start|>user` |

**不降维就传过去**：服务器的 chat template **不认识** "tool-call" / "tool-response" → 报错或忽略。

> 💡 **所以"5 → 3 降维"的真实根因 = chat template 不支持 5 role**。Day 3 [model-generate-mental-model.md](../03-source/day3-models/model-generate-mental-model.md) 当时只说"OpenAI 协议没这两个 role"，本笔记把根因挖到 chat template 层。

---

## 10. 一图归位

```
agent 框架                    LLM API 服务器                  LLM 模型
──────────                   ──────────────                 ─────────
[结构化 messages JSON]
    ↓ HTTP
                            步骤 ① HTTP 解析
                            步骤 ② 队列
                            步骤 ③ ⭐ chat template
                                ↓
                            ┌───────────────────────────┐
                            │ messages →               │
                            │   "<|im_start|>system\n"  │
                            │   "你是...\n"             │
                            │   "<|im_end|>\n"          │
                            │   "<|im_start|>user\n"    │
                            │   "查天气\n"              │
                            │   "<|im_end|>\n"          │
                            │   "<|im_start|>assistant" │
                            └───────────────────────────┘
                                ↓
                            步骤 ④ tokenize
                                ↓
                                                          [token序列：t1, t2, ...]
                                                              ↓
                                                          模型生成下一个 token
                                                              ↓ logits
                                                          ...
```

---

## 11. 总结表

| 问题 | 答案 |
|---|---|
| chat template 是什么？ | 把结构化 messages 翻译成扁平字符串的**模型专属格式规则** |
| 为什么需要？ | LLM 模型只吃 token 序列，不吃 JSON 结构 |
| 谁应用 chat template？ | **LLM API 服务器**（步骤 ③），不是 agent 框架不是 LLM 模型 |
| 不同模型 template 一样吗？ | ❌ 完全不同（Qwen ChatML / Llama-2 / Llama-3 / Mistral 各一种）|
| 用错 template 会怎样？ | LLM 模型严重混乱，输出质量大幅退化 |
| 特殊 token 是什么？ | tokenizer 词汇表里的特殊条目（`<|im_start|>` / `[INST]` 等），是模型识别 role 边界的根基 |
| template 规则存在哪？ | 模型 tokenizer 配置 `tokenizer_config.json` 里的 Jinja2 模板字符串 |
| 同模型不同 provider 输出会不同吗？ | ✅ 可能！chat template 应用细节差异是常见原因 |
| `tools` 字段怎么进模型？ | LLM API 服务器步骤 ③ 把它拼接进 system prompt 文本 → 走 chat template → 喂模型（作为文本）|
| agent 框架要关心 chat template 吗？ | 99% 不用 —— 只要按 OpenAI 协议传 messages，服务器自动选对 |
| 为什么 smolagents 5 role 要降维成 3 role？ | ⭐ 根因 = chat template 不支持 "tool-call" / "tool-response" 这 2 个非标准 role |

---

## 相关链接

- 必读前置：
  - [chat-message-roles.md](chat-message-roles.md) — role 概念（Week 1）
  - [llm-vs-api-server-architecture.md](llm-vs-api-server-architecture.md) — 4 角色术语
  - [llm-api-server-internals.md](llm-api-server-internals.md) §3 — chat template 在服务器流水线的位置
- 应用本心智模型的笔记：
  - [tool-schema-rendering-mental-model.md](../03-source/day2-tools/tool-schema-rendering-mental-model.md) — tools 字段的 chat template 渲染
  - [model-generate-mental-model.md §5](../03-source/day3-models/model-generate-mental-model.md) — 5 → 3 role 降维的根因
  - [model-and-protocols-overview.md](model-and-protocols-overview.md) — Chat Completion 协议家族
- 源码：
  - [models.py:332 `get_clean_message_list`](../../../src/smolagents/models.py#L332) — smolagents 在客户端做的 messages 整理（**不**应用 chat template，留给服务器）

## 遗留问题

- [ ] 多模态模型（图像 + 文本）的 chat template 怎么处理图像 patch token？
- [ ] tool_choice="required" 在不同模型上的渲染差异（如 Llama-3 用 `<|python_tag|>`）
- [ ] HF Hub 上 `tokenizer_config.json` 里 Jinja2 模板的具体语法（待 Week 3-4 实战看）
- [ ] 为什么 OpenAI / Anthropic 等闭源模型不公开 chat template？（推测：保护训练数据格式 + 防 prompt injection）
