---
created: 2026-05-01
status: deferred    # 当前学习阶段不必读，存档备用
tags: [advanced, protocol, deferred, week-4-or-later]
revisit_when: 做生产项目 / 跨厂商接 LLM / Week 4 进阶专题
---

# LLM 协议家族深入对比 —— 暂存档，时机到了再看

> ⚠️ **不是当前学习阶段的内容**。
>
> 这篇是 2026-05-01 学习对话中"顺着好奇心问出来"的内容，超出了 [LEARNING_PLAN.md](../../LEARNING_PLAN.md) Week 1-2 的范围。
> 入门级的协议概览见 [02-concepts/model-and-protocols-overview.md](../02-concepts/model-and-protocols-overview.md)。
>
> **何时回来看这篇**：
> - Week 4 进阶专题阶段
> - 真的要做跨厂商接 LLM 的项目
> - 调试一个跨协议的诡异 bug

---

## 1. 协议家族（按时间线）

### 1.1 Completion 协议（老一代，2020）
端点 `POST /v1/completions`，输入是**单个 prompt 字符串**，输出续写文本。适合 base 模型。
现在云厂商基本废弃，仅 vLLM / 本地推理框架还见得到。

### 1.2 Chat Completion 协议（当前主流，2023）
OpenAI 2023 年随 GPT-3.5-turbo 推出，事实上的工业标准。已在 [overview](../02-concepts/model-and-protocols-overview.md) 讲过。

### 1.3 Anthropic Messages 协议
Claude 自己的，端点 `POST /v1/messages`。和 Chat Completion 像但不通用：
- `system` 是顶层独立字段，不在 `messages` 数组里
- `tools` schema 嵌套结构不同
- 返回是 `content: [{type: "text"|"tool_use", ...}]` 数组，不是 `choices[0].message`

### 1.4 AWS Bedrock Converse 协议
AWS 想用一份协议覆盖 Claude / Llama / Mistral / Titan。字段全改：
- `modelId` 而不是 `model`
- `inferenceConfig`（stop 在这里）
- `toolConfig`

smolagents 的 [`AmazonBedrockModel`](../../../src/smolagents/models.py) (models.py:1859) 就是适配它。

### 1.5 Google Gemini API
端点 `POST /v1beta/models/{model}:generateContent`。字段全变：
- `contents` 而不是 `messages`
- `parts` 数组组合文本/图片
- `tools.functionDeclarations` 而不是 `tools`

### 1.6 OpenAI Responses 协议（2025 新出）
端点 `POST /v1/responses`。Chat Completion 的"agent 增强版"：
- 服务端保存多轮对话状态
- 内置工具：`web_search`、`code_interpreter`、`file_search`
- 适合 agent 场景，但生态还在追赶

### 1.7 其他能力的独立协议
- **Embeddings** — `POST /v1/embeddings`（RAG 必用）
- **Audio** — `transcriptions`（Whisper）/ `speech`（TTS）
- **Images** — `images/generations`
- **Files / Batch / Fine-tuning**

---

## 2. 协议差异有 4 层（重要心智模型）

### 表层：字段名/结构

```
OpenAI:    messages: [{role, content}]
Anthropic: messages: [{role, content}], system: "..."   ← system 拎出来
Gemini:    contents: [{role, parts: [...]}]             ← 名字全变
Bedrock:   messages: [{role, content: [{text}]}]        ← content 永远是数组
```

### 中层：能力差异（有/没有）

| 能力 | OpenAI | Anthropic | Gemini | Bedrock |
|---|---|---|---|---|
| `response_format`（强制 JSON） | ✅ | ❌（靠 prompt） | ✅ `responseSchema` | ❌ |
| `logprobs` | ✅ | ❌ | ❌ | ❌ |
| 并行 tool calls | ✅ | ✅ | ✅ | 看模型 |
| 服务端会话状态 | Responses API ✅ | ❌ | ❌ | ❌ |
| 多个 system message | ✅ | ❌（只能一个） | 无 system 概念 | ❌ |

### 中层：语义差异（同名但行为不同）

- **`stop` / `stop_sequences`**：截断时机各家不同
- **`tool_choice="required"`**：OpenAI 这么写；Anthropic 用 `{"type": "any"}`；Gemini 用 `toolConfig.functionCallingConfig.mode = "ANY"`
- **`role: "tool"`**：OpenAI 平铺一条 `{role: "tool", tool_call_id, content}`；Anthropic 把 tool result 嵌套在 user message 的 content 块里

### 深层：状态模型 / 流式 / 鉴权 / 多模态

- **无状态 vs 有状态**：Chat Completion 是无状态（每次发全部历史）；Responses API / Assistants API 是有状态
- **流式 wire format**：OpenAI 用 SSE；Bedrock 用 AWS EventStream（二进制帧）；Gemini 用 chunked JSON
- **鉴权**：OpenAI/Anthropic 用 Bearer；Bedrock 用 SigV4 签名；Azure 用 `api-key` header；Gemini 用 query 参数
- **多模态**：图片格式四套规范，base64 / URL / bytes / inline_data 各不一样

---

## 3. smolagents 是怎么吸收这些差异的

适配器模式，每家协议一个 `Model` 子类（[models.py](../../../src/smolagents/models.py)）：

```
Model
├── ApiModel
│   ├── LiteLLMModel              # LiteLLM 转发，自带跨厂商适配
│   ├── InferenceClientModel      # HF Router
│   ├── OpenAIModel               # OpenAI 协议
│   │   └── AzureOpenAIModel
│   └── AmazonBedrockModel        # Bedrock Converse
├── TransformersModel             # 本地推理
├── VLLMModel
└── MLXModel                      # Apple Silicon
```

### 实例：Bedrock 子类怎么覆盖父类适配协议怪癖

[models.py:1968-2008 `AmazonBedrockModel._prepare_completion_kwargs`](../../../src/smolagents/models.py)：

```python
def _prepare_completion_kwargs(self, ...):
    completion_kwargs = super()._prepare_completion_kwargs(
        messages=messages,
        stop_sequences=None,  # ← Bedrock 不支持顶层 stop，要塞 inferenceConfig
        ...
    )
    completion_kwargs.pop("toolConfig", None)  # Bedrock 不认 toolConfig

    # Bedrock 的 message content 不接受 "type" 字段，逐个删
    for message in completion_kwargs.get("messages", []):
        for content in message.get("content", []):
            if "type" in content:
                del content["type"]

    return {
        "modelId": self.model_id,   # ← Bedrock 用 modelId 不是 model
        **completion_kwargs,
    }
```

[models.py:2028](../../../src/smolagents/models.py)：
```python
if response_format is not None:
    raise ValueError("Amazon Bedrock does not support response_format")
```

**每一行都在解决一个协议差异**。

> 💡 **我的理解**：协议差异 ≈ 30% 字段名 + 30% 能力支持 + 30% 语义 + 10% 传输细节。字段名是表面，能力/语义/状态模型才是真正的"协议形状"。LiteLLM 这种库的代码量大部分不在改字段名，而在抹平能力和语义差异。

---

## 4. "OpenAI 兼容"是怎么回事

2023 年起新出的开源推理框架和云厂商默认都支持 Chat Completion 协议：
- vLLM、Ollama、LM Studio、TGI、Llama.cpp server —— 全部
- HuggingFace Inference Router
- DeepSeek、Qwen、Moonshot、智谱

只要 HTTP 端点路径、请求体字段、返回字段全模仿 OpenAI，客户端用 OpenAI SDK 改 `base_url` 就能直连。这是为什么 smolagents 里 `OpenAIModel` 是通用主力。

---

## 5. 实战教训（已踩过的坑）

### Thinking 模型 + tools 字段 → 400 Bad Request

`Qwen/Qwen3-Next-80B-A3B-Thinking` 等 thinking/reasoning 模型在 HF Inference Router 上常常**不支持 `tools` 字段**，ToolCallingAgent 直接 400。

**经验法则**：
- 模型名带 `Thinking` / `Reasoning` / `R1` —— 配 ToolCallingAgent 前先验证
- 同一模型在不同 provider 上能力不同，HF `provider="auto"` 不稳定，需要时显式指定

详见 [02-concepts/codeagent-vs-toolcallingagent.md § 5.5](../02-concepts/codeagent-vs-toolcallingagent.md)。

---

## 6. 给未来的自己：什么时候真的需要懂这些？

- **真的要跨厂商接 LLM**：直接用 LiteLLM 库，比自己写适配靠谱
- **遇到 4xx 报错查协议字段**：报 `unknown field` / `missing field` 八成是协议字段名/结构不对
- **做安全合规 / 企业项目要走 Bedrock 或 Azure**：才需要精读对应 Model 子类
- **agent 性能调优要细控 prompt caching / structured output**：会撞到不同协议的能力上限

> 💡 **回看建议**：来这里之前，先确认 Week 1-3 的内容已经稳定吃透。否则容易"广而不深"。

---

## 相关链接

- [02-concepts/model-and-protocols-overview.md](../02-concepts/model-and-protocols-overview.md) — 入门级协议概览（当前阶段读这个）
- [02-concepts/codeagent-vs-toolcallingagent.md](../02-concepts/codeagent-vs-toolcallingagent.md) — 实战坑：thinking 模型 + tools
- 源码：
  - [models.py 各 Model 子类](../../../src/smolagents/models.py)
  - [models.py:502 `_prepare_completion_kwargs`](../../../src/smolagents/models.py)
  - [models.py:1968 Bedrock 子类适配](../../../src/smolagents/models.py)
- 外部：
  - OpenAI Chat Completion 文档：https://platform.openai.com/docs/api-reference/chat
  - Anthropic Messages 文档：https://docs.anthropic.com/en/api/messages
  - LiteLLM 跨厂商适配库：https://docs.litellm.ai/
