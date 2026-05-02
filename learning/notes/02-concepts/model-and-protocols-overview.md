---
created: 2026-05-01
status: active
tags: [concept, model, protocol, week-1]
---

# 模型与协议入门 —— 学习阶段需要懂这些就够了

> 本笔记只回答**一个**问题：smolagents 调 LLM 时背后是什么协议？我现在阶段需要懂多深？
>
> 前置：[codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md)
> 进阶（暂不必看）：[../05-advanced/llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md)

---

## 1. 你只需要先记住这 3 句话

1. **Chat Completion 是工业标准**。OpenAI 在 2023 年随 GPT-3.5-turbo 推出的 `POST /v1/chat/completions`，现在几乎所有 LLM 服务（vLLM、Ollama、Together、DeepSeek、Qwen、HF Router……）都提供"OpenAI 兼容"端点。学协议先吃透它就行。
2. **不同厂商协议有差异**（Anthropic、Gemini、Bedrock 各家字段名/能力都不一样），但 smolagents 用 `Model` 子类把这层差异封装了，**学习阶段不用碰**。
3. **请求体里有/没有 `tools` 字段**就是 ToolCallingAgent 和 CodeAgent 的分水岭，已在 [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md) 讲过。

---

## 2. Chat Completion 协议长啥样（最小可用认知）

**请求**（HTTP POST body 关键字段）：

```json
{
  "model": "Qwen/Qwen2.5-72B-Instruct",
  "messages": [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "查 Beijing 温度"}
  ],
  "tools": [...],          // 可选：function calling，ToolCallingAgent 用
  "stop": ["Observation:"],
  "stream": true
}
```

**返回**：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "...",
      "tool_calls": [...]   // 如果请求带了 tools，LLM 会返回这个字段
    }
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 20}
}
```

> 💡 **我的理解**：这套协议最妙的是 `messages` 数组本身就是"对话历史 + 当前问题"，无状态，每次重新发。这意味着 agent 框架要自己管 memory（smolagents 的 `memory.py` 干的就是这个）。

---

## 3. 为什么叫"Chat Completion"这个名字？

拆开看：**Completion** + **Chat**。

### Completion = 补全 / 续写（LLM 的本质）

LLM 底层永远在做同一件事：给一段文本，预测**下一个 token**，再下一个，直到停。这就是 "text completion"。

OpenAI 2020 年发 GPT-3 时，API 端点叫 `POST /v1/completions`，请求体就一个字段 `prompt`：

```json
{"model": "text-davinci-003", "prompt": "Once upon a time", "max_tokens": 100}
```

模型把这段文字续写完。名字诚实地反映了底层机制 —— 没有"对话""理解""思考"，**就是补全**。

### Chat = 输入格式升级成对话

2023 年 GPT-3.5-turbo 推出，输入从单个 prompt 字符串升级成结构化 `messages` 数组（带 role），新端点叫 `POST /v1/chat/completions`。

**Chat** 只修饰输入格式（对话式），**Completion** 保留是因为底层行为没变。

### 心智模型：把对话当"未完成的剧本"

```
[剧本]
system: 你是助手
user: 你好
assistant: ___  ← 让模型把这一句"补完"
```

模型看完对话历史，**把 assistant 的下一句台词补完**。整个 API 直译就是"对话式的文本补全"。

> 💡 **本质洞察**：API 名字里没有 "chat agent"、"conversation"、"assistant"，因为这些都是上层应用概念。`completion` 强调的是**这只是个文本预测引擎**，对话历史只是输入格式，状态/记忆/工具调用全部是客户端自己拼出来的。

> 💡 **为什么不叫 `/v1/chat`**：如果叫 `/v1/chat`，会暗示"服务端在维护对话"。但 Chat Completion **是无状态的** —— 每次请求都要把整个 `messages` 数组重发，服务端不记任何东西。保留 `completion` 是在提醒你：**它就是个无状态的 token 预测器**。
>
> OpenAI 2025 年新出的 `/v1/responses` 才是真正"有状态的对话 API"，名字也变了，因为底层机制变了。详见 [../05-advanced/llm-protocols-deep-dive.md § 1.6](../05-advanced/llm-protocols-deep-dive.md)。

### 一句话记住

> **Chat = 输入是对话格式；Completion = 行为还是补全。**
> 把对话历史当未完成的剧本，让模型把 assistant 的下一句台词补完。

---

## 4. smolagents 怎么对接协议？

简单版：每个云/本地服务对应一个 `Model` 子类，子类内部把 smolagents 内部数据翻译成对应协议格式。

```
Model (基类)
├── InferenceClientModel   ← 你目前在用，对接 HF Inference Router
├── OpenAIModel            ← 对接 OpenAI 协议（也能接所有"OpenAI 兼容"服务）
├── LiteLLMModel           ← 用 LiteLLM 库做跨厂商适配
└── ...                    ← 还有 Bedrock / Azure / vLLM 等，先不管
```

关键统一入口在 [models.py:502 `_prepare_completion_kwargs`](../../../src/smolagents/models.py)，所有子类都共享这个组装逻辑。Week 2 读源码时会精读它。

---

## 4.5 如何选 Model 子类？—— 看完文档仍然懵的正确解法

> 看完 [guided_tour.md "构建您的 agent"](../../../docs/source/zh/guided_tour.md) 里 6 种 model 类容易懵：为什么有这么多？该选哪个？
>
> 关键认知：**这些 model 类对应的不是"模型"，而是"调用渠道/基础设施"**。

### 4.5.1 先破除一个误解

**model 类 ≠ 模型**。smolagents 里**没有** `LlamaModel` / `Qwen2Model` / `DeepSeekModel` 这种东西。

每个 model 类**对应一种基础设施 / 调用方式**，跟你想用哪个具体模型无关：

```
                       要用 Llama-3.3-70B-Instruct
                       想问"在哪跑？怎么调？"
                              ↓
        ┌───────────┬───────────┬───────────┬───────────┐
        ↓           ↓           ↓           ↓           ↓
InferenceClient   Transformers   LiteLLM    OpenAIModel  AmazonBedrock
   Model           Model       Model      (兼容端点)     Model
   ↓               ↓             ↓            ↓             ↓
   HF 云端       下载到本地     Together     DeepSeek      AWS
   付 HF token    GPU 跑       /Fireworks   /Qwen API     企业账号
```

**同一个模型可经多种调用方式触达**。选哪种取决于你的**部署条件**，不是模型本身。

### 4.5.2 主要 Model 子类对照表

| Model 类 | 模型跑在哪 | 协议 | 谁付钱 | 适用场景 |
|---|---|---|---|---|
| **InferenceClientModel** | HF 云端 | HF Router → OpenAI 兼容 | HF token 配额 | 学习、原型、HF 仓库主力 |
| **TransformersModel** | **你本地 GPU** | 直接调 PyTorch | 你的电费 | 本地实验、隐私、离线 |
| **LiteLLMModel** | 取决于 model_id | LiteLLM 适配各家 | 各家 API key | 跨厂商切模型、Ollama、混合栈 |
| **OpenAIModel** | OpenAI / 任何 OpenAI 兼容端点 | OpenAI 官方协议 | OpenAI / 兼容服务 | OpenAI 模型 + 接 DeepSeek/Qwen/Moonshot 等"兼容"服务 |
| **AzureOpenAIModel** | Azure 云 | Azure OpenAI 协议 | Azure 订阅 | 企业走 Azure 合规 |
| **AmazonBedrockModel** | AWS 云 | Bedrock Converse 协议 | AWS 账号 | 企业走 AWS 合规 |
| **MLXModel** | **你的 Mac (Apple Silicon)** | MLX 本地推理 | 你的电费 | M 系列芯片本地用，比 Transformers 快 |
| **VLLMModel** | 你/团队的 vLLM 服务器 | vLLM 接口 | 你的服务器电费 | 自部署 + 高并发 |

> 💡 **为什么要分这么多类**：每家协议字段名/能力/鉴权/流式格式都不同（详见 [05-advanced/llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md)）。Smolagents 用**适配器模式**，每家一个子类，让 agent 主流程不必关心协议差异。

### 4.5.3 选型决策树（3 步搞定）

```
第 1 步：模型跑在哪里？
   ├─ 我自己电脑 GPU         → TransformersModel
   ├─ 我的 Mac (M 系列)      → MLXModel
   ├─ 自部署的 vLLM 服务器    → VLLMModel
   └─ 云端                  → 进入第 2 步

第 2 步（云端）：要用什么云？
   ├─ HuggingFace           → InferenceClientModel
   ├─ OpenAI 官方           → OpenAIModel  或  LiteLLMModel
   ├─ DeepSeek/Qwen/Moonshot 等"OpenAI 兼容" → OpenAIModel + base_url
   ├─ Anthropic Claude      → LiteLLMModel (model_id="anthropic/...")
   ├─ Azure                 → AzureOpenAIModel  或  LiteLLMModel
   ├─ AWS Bedrock           → AmazonBedrockModel
   └─ 想跨多家随便切          → LiteLLMModel

第 3 步：能用专用类就别用 LiteLLM
   专用类  = 直接对接，少一层依赖
   LiteLLM = 多一层抽象，灵活但偶尔有 bug
```

### 4.5.4 OpenAIModel vs LiteLLMModel 的纠结

很多人在这里卡住，给个简单原则：

```
要用 OpenAI 官方（gpt-4 / gpt-4o）             → OpenAIModel
要用 OpenAI 兼容服务（DeepSeek/Qwen/Together）   → OpenAIModel + base_url
要用 Anthropic / Bedrock / Cohere             → LiteLLMModel
要在多家间频繁切换                             → LiteLLMModel
其他                                          → 优先专用类
```

**LiteLLMModel 的价值**是"一份代码接 N 家"。只接一家时专用类更简单；做对比实验/容灾切换时 LiteLLM 省事。

### 4.5.5 几个常见场景

#### 场景 1：学习阶段（你现在）
```python
model = InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct")
```
HF 免费配额够用，模型选择多。**就是 [compare_agents.py](../../scripts/compare_agents.py) 现在的写法**。

#### 场景 2：用 DeepSeek（性价比高）
```python
from smolagents import OpenAIModel
model = OpenAIModel(
    model_id="deepseek-chat",
    api_base="https://api.deepseek.com/v1",   # ← OpenAI 兼容端点
    api_key=os.getenv("DEEPSEEK_API_KEY"),
)
```
**这就是 § 5 讲的"OpenAI 兼容"** —— 同一个 SDK 接 N 家服务。

#### 场景 3：用 Claude
```python
from smolagents import LiteLLMModel
model = LiteLLMModel(
    model_id="anthropic/claude-3-5-sonnet-latest",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)
```
Anthropic 协议跟 OpenAI 不一样，**走 LiteLLM 让它帮你适配**。

#### 场景 4：本地玩
```python
from smolagents import TransformersModel
model = TransformersModel(model_id="meta-llama/Llama-3.2-3B-Instruct")
```
小模型本地跑，调试 agent 流程不烧钱。

### 4.5.6 学习阶段建议

> 💡 **前 3 周不要折腾这个**。`InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct")` 一种就够你跑完所有 demo + 读完所有源码。
>
> **Week 4 才考虑**：如果想做生产 agent，再认真选。那时你已经懂底层，决策树自然能走通。

### 4.5.7 一句话总结

> 💡 **不同的 model 类是"插头"，对应不同的"插座"（基础设施 + 协议）**。
> 模型本身是"电器"，可以接到不同插座上 —— 选哪个插头取决于你想插哪个插座，不是电器本身。

---

## 5. 什么是"OpenAI 兼容"端点？

很多服务（DeepSeek、Qwen、Moonshot、vLLM、Ollama、LM Studio）都说自己**兼容 OpenAI 协议**。意思是：

- HTTP 端点路径模仿 `POST /v1/chat/completions`
- 请求体字段、返回字段一模一样

你只要把 OpenAI SDK 的 `base_url` 指向它的端点，代码就能直连：

```python
# 例如接 DeepSeek
from openai import OpenAI
client = OpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key="sk-..."
)
```

> 💡 **我的理解**：这是开源生态共识 —— 没人想从头造一套客户端 SDK，干脆都模仿 OpenAI。所以学一套协议等于学十家。

---

## 6. 现阶段 NOT to learn 清单（重要！）

下面这些**当前学习阶段不必碰**，已存档到 [llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md)，等 Week 4 或做生产项目时再回来看：

- ❌ Anthropic Messages 协议字段细节
- ❌ Gemini API 的 `contents` / `parts` 结构
- ❌ AWS Bedrock Converse 协议、SigV4 鉴权
- ❌ OpenAI Responses API（2025 新出的 agent 增强版）
- ❌ 各家协议在 stop / tool_choice / 多模态的语义差异
- ❌ 流式协议的 wire format（SSE / EventStream / chunked JSON）
- ❌ Embeddings / Audio / Image 等其他能力协议

> 💡 **学习节奏建议**：现在抓主干（agent 怎么跑一步），不要被协议广度拉走注意力。等你 Week 3 能写自己的 agent 后，这些细节自然会有"哦原来如此"的契机。

---

## 7. 现阶段 do learn 清单

- [x] Chat Completion 协议的请求/返回长啥样（看本笔记 § 2）
- [x] `tools` 字段是 ToolCallingAgent vs CodeAgent 的分水岭
- [x] 模型选型坑：thinking 模型常不支持 `tools`（实战见 [codeagent-vs-toolcallingagent.md § 5.5](codeagent-vs-toolcallingagent.md)）
- [ ] **Week 2** 读 [models.py](../../../src/smolagents/models.py) 时精读 `_prepare_completion_kwargs` 和 `InferenceClientModel.generate()`，看请求体怎么组装、返回值怎么翻译
- [x] **Model 子类 = "调用渠道"，不是"模型"**（详见 § 4.5）；学习阶段用 `InferenceClientModel` 就够

---

## 相关链接

- [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md) — 两种 agent 的差异
- [../05-advanced/llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md) — 协议家族深入（暂时不看）
- 源码：
  - [models.py:288 `get_tool_json_schema`](../../../src/smolagents/models.py)（工具定义 → JSON Schema）
  - [models.py:502 `_prepare_completion_kwargs`](../../../src/smolagents/models.py)（请求体组装）
  - [models.py:1456 `InferenceClientModel`](../../../src/smolagents/models.py)（HF 适配）

## 遗留问题

挪到 [questions.md](../questions.md)。
