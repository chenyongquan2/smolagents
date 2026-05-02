---
created: 2026-05-01
status: done
tags: [concept, code-agent, tool-calling-agent, week-1]
---

# CodeAgent vs ToolCallingAgent — 同样的 ReAct，不同的"动作格式"

> 本笔记回答**一个**问题：smolagents 提供的两种 agent 实现，到底差在哪？什么时候选哪个？
> 前置：[what-is-agent.md](what-is-agent.md)
> 阅读来源：[docs/source/zh/conceptual_guides/intro_agents.md](../../../docs/source/zh/conceptual_guides/intro_agents.md) 第 89-107 行
> 对比 demo：[../../compare_agents.py](../../scripts/compare_agents.py)

---

## 1. 一句话区别

> 同一个 LLM 决策，**用不同格式表达**——ToolCallingAgent 让 LLM 输出 JSON，CodeAgent 让 LLM 输出 Python 代码。

但这一点点格式差异，带来了**能力上的指数级差距**。

## 2. LLM 输出长啥样（最直观对比）

任务：查 Beijing/Tokyo/Singapore 的温度，找最热的，换算成华氏度。

### ToolCallingAgent — JSON 风格

LLM 一步只能调一个工具，**至少 4 轮**：

```json
// Step 1
{"name": "get_temperature", "arguments": {"city": "Beijing"}}     // → 25
// Step 2
{"name": "get_temperature", "arguments": {"city": "Tokyo"}}       // → 30
// Step 3
{"name": "get_temperature", "arguments": {"city": "Singapore"}}   // → 28
// Step 4
{"name": "final_answer", "arguments": {"answer": 86}}             // 30 * 1.8 + 32
```

### CodeAgent — Python 代码

LLM 一步内**写完整段逻辑**，**1 轮**搞定：

```python
cities = ["Beijing", "Tokyo", "Singapore"]
temps = {city: get_temperature(city) for city in cities}
hottest = max(temps.values())
final_answer(hottest * 1.8 + 32)
```

> 💡 **直观感受**：CodeAgent 像让一个会编程的人完成任务（用变量、循环、表达式）。ToolCallingAgent 像让一个**只会指令一个一个下**的人，每次还得等结果回来才能下下一个指令。

**论文实验**：CodeAgent 平均**比 ToolCallingAgent 少 30% 步数**。

---

## 3. 能力差异（这才是关键）

| 能力 | ToolCallingAgent | CodeAgent |
|------|------------------|-----------|
| 一步调多个工具 | ❌ 一次只能 1 个 | ✅ 想调几个调几个 |
| 工具输出做计算 | ❌ 必须存 memory 下一步处理 | ✅ 当场用 Python 算 |
| 用循环/条件 | ❌ 只能让 LLM 多轮重新决策 | ✅ `for`/`if` 一步搞定 |
| 中间变量复用 | ❌ 没有变量概念 | ✅ Python 变量自由用 |
| 错误处理 | ❌ 失败只能再让 LLM 决策 | ✅ `try/except` 捕获 |
| 训练数据契合度 | 中（JSON 工具调用是新格式） | 高（互联网海量 Python 代码） |

> 💡 **本质洞察**：JSON 是**数据描述语言**，Python 是**动作描述语言**。
>
> 让 LLM 用 JSON 表达"做什么"，相当于让人用 Excel 表格写小说——勉强能写，但极其别扭。
> 这也就是为什么[官方文档](../../../docs/source/zh/conceptual_guides/intro_agents.md)第 95 行说："如果 JSON 片段是更好的表达方式，JSON 将成为顶级编程语言。"

---

## 4. 源码层面的差异

两者都继承 `MultiStepAgent`，只是 `_step_stream` 实现不同：

| 类 | 文件:行 | 关键差异 |
|----|---------|---------|
| `ToolCallingAgent._step_stream` | [agents.py:1276](../../../src/smolagents/agents.py) | 调 `model.generate(..., tools_to_call_from=tools)`，走 LLM provider 的 native function calling 协议 |
| `CodeAgent._step_stream` | [agents.py:1639](../../../src/smolagents/agents.py) | LLM 输出**纯文本**，自己用 `parse_code_blobs()`(行 1709) 抽出 \`\`\`python ... \`\`\` 代码块；丢给 `python_executor` 执行(行 1727) |

**关键观察**：

```python
# ToolCallingAgent (agents.py:1296)
output_stream = self.model.generate_stream(
    input_messages,
    stop_sequences=["Observation:", "Calling tools:"],
    tools_to_call_from=self.tools_and_managed_agents,  # ← 走原生工具协议
)

# CodeAgent (agents.py:1661)
output_stream = self.model.generate_stream(
    input_messages,
    stop_sequences=stop_sequences,
    # ← 没有 tools_to_call_from！LLM 当成普通文本生成
)
```

> 💡 **架构设计的精妙处**：CodeAgent 不依赖 LLM provider 提供 function calling，**任何**能写 Python 的 LLM 都能用。这是为啥 smolagents 强调"模型无关"。

---

## 5. CodeAgent 的代价（天下没有免费的午餐）

1. **安全风险** ⚠️：执行 LLM 写的代码！README 反复强调要用沙箱（E2B / Docker / Pyodide）。`LocalPythonExecutor` 不是真正的安全边界。
2. **对模型要求高**：弱模型容易写错语法。GPT-3.5 / 早期 Claude Instant 跑 CodeAgent 效果差。现代模型（GPT-4o、Claude 4、DeepSeek-V3、Qwen3）都很稳。
3. **错误更隐蔽**：JSON 错只是 schema 错，明显；代码错可能是逻辑 bug，跑出来"答案看似合理但算错了"，更难发现。

---

## 5.5 实战坑：ToolCallingAgent 对模型有挑剔（2026-05-01 实测）

跑 [compare_agents.py](../../scripts/compare_agents.py) 时，**ToolCallingAgent 直接报 `400 Bad Request`**：

```
huggingface_hub.errors.BadRequestError:
[Step 1] Error while generating output:
... '400 Bad Request' for url 'https://router.huggingface.co/v1/chat/completions'
```

### 根因

`InferenceClientModel()` 不传参时，默认模型是 `Qwen/Qwen3-Next-80B-A3B-Thinking`（见 [models.py:1516](../../../src/smolagents/models.py)）。这是一个 **thinking / reasoning 类模型**，HF Inference Router 上它对应的 provider **不支持 OpenAI 风格的 `tools` 字段**。

ToolCallingAgent 的请求体里硬性带 `tools=[...]`（[models.py:539](../../../src/smolagents/models.py)），服务端识别不了直接 400 拒回。

CodeAgent 不带 `tools` 字段（走 prompt 注入），所以即便用 thinking 模型也能跑。

### 修复

显式换成支持 function calling 的非 thinking 模型：

```python
model = InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct")
```

### 一句话规则

> 💡 **模型名带 `Thinking` / `Reasoning` / `R1` —— 用 ToolCallingAgent 之前先确认 provider 支持 tools；用 CodeAgent 则没这个限制**。这也是 CodeAgent "模型无关"优势的实战体现。

更深入的"协议家族 / 各家字段差异"留到 [05-advanced/llm-protocols-deep-dive.md](../05-advanced/llm-protocols-deep-dive.md)，**学习阶段不必看**。入门级的协议概览见 [model-and-protocols-overview.md](model-and-protocols-overview.md)。

---

## 6. 选型决策表

| 场景 | 选 | 理由 |
|------|----|----|
| 学习 / 研究 / 个人项目 | **CodeAgent** ⭐ | 能力强、步数少、便宜 |
| 强模型可用 | **CodeAgent** | 能力压制 |
| 弱模型 / 低成本 | **ToolCallingAgent** | 不容易代码错乱 |
| 严格安全合规（金融/医疗） | **ToolCallingAgent** | JSON 调用边界清晰，不执行任意代码 |
| 多模态/工具调用本身就是 LLM 训过的 | **ToolCallingAgent** | 走原生协议更稳 |

> 💡 **学习阶段直接用 CodeAgent**。等你做生产项目再考虑 ToolCallingAgent 的安全性优势。

---

## 7. 上手 demo

我做了一个对比脚本：[compare_agents.py](../../scripts/compare_agents.py)

```bash
.venv/Scripts/python.exe compare_agents.py
```

**它做了什么**：
- 同一个任务（查 3 城气温 → 找最热 → 换算华氏度）
- 同一个模型（HF Inference）
- 同一个工具（假的 `get_temperature`，不依赖网络，结果可重复）
- 跑 ToolCallingAgent 和 CodeAgent 各一次
- 最后打印步数对比

**实测结果**（2026-05-01，模型：`Qwen/Qwen2.5-72B-Instruct`）：

```
ToolCallingAgent: 答案=86.0, 总步数=5
CodeAgent:        答案=86.0, 总步数=2
```

两者答案一致，但 step 数差 2.5 倍。

### Step 计数怎么读

`len(agent.memory.steps)` 是框架内部的"step 列表"长度，由 `MultiStepAgent` 在不同阶段 append（[agents.py:488](../../../src/smolagents/agents.py) / [602](../../../src/smolagents/agents.py)）：

| Step 类型 | 含义 | ToolCallingAgent 实测 | CodeAgent 实测 |
|---|---|---|---|
| `TaskStep` | 开场把 task 包成 message | 1 | 1 |
| `ActionStep` ⭐ | **每轮 ReAct 循环（LLM + 执行）** | **4**（Beijing/Tokyo/Singapore + final_answer） | **1**（一段 Python 全干完） |
| 合计 `len(memory.steps)` | | **5** | **2** |

> 💡 **真正反映 ReAct 轮数的是 ActionStep 数量：4 vs 1。** TaskStep 只是开场的固定开销，不算"工作量"。
>
> 这正是 [Executable Code Actions Elicit Better LLM Agents (2402.01030)](https://huggingface.co/papers/2402.01030) 论文里"CodeAgent 平均比 ToolCallingAgent 少 30% 步数"的具体来源。我们这个 4 vs 1 的极端例子直接复现了结论。

### 为什么差异这么大（呼应 § 3 能力对比）

- **ToolCallingAgent**：OpenAI function calling 协议设计成"每次输出仅消化一个工具调用"。3 个城市 = 至少 3 个 ActionStep + 1 个 final_answer = 4。
- **CodeAgent**：LLM 输出一整段 Python，循环 + max + 计算 + final_answer 全在 1 个 ActionStep 内完成。

### 完整执行剧本（对照实际日志理解）

下面把两个 agent 的每一步拆开，**LLM 看到什么、输出什么、框架做什么、memory 加了什么**全部画出来。

#### ToolCallingAgent — 5 步剧本

> 📝 **关于"步数编号"的辨析**（重要！）：
> - `len(memory.steps)` 包含**所有** step 类型（TaskStep + ActionStep + PlanningStep），所以 = 5
> - 但框架日志里打的 `Step 1`、`Step 2`... **只编号 ActionStep，从 1 开始**（[agents.py:543](../../../src/smolagents/agents.py)）
> - **TaskStep 没有 `step_number` 字段**（[memory.py:187](../../../src/smolagents/memory.py)），它是开场白，不参与编号
>
> 下面剧本里的"开场 / 第 1 幕 / 第 2 幕"是为了讲故事用的人话，不是源码里的字段。

```
┌────────────────────────────────────────────────────────────────────┐
│  开场 — TaskStep（agents.py:488，run() 一开始就 append）            │
│  ↑ 在 memory.steps[0]，但不带 step_number                           │
├────────────────────────────────────────────────────────────────────┤
│  框架动作：把用户输入 task 包装成 user message                       │
│  memory.steps += [TaskStep(task="Find the temperature of...")]      │
│  注意：还没调 LLM                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  第 1 幕 — ActionStep(step_number=1)                                │
├────────────────────────────────────────────────────────────────────┤
│  LLM 输入 messages：                                                 │
│    [system: "You are an expert assistant..."（toolcalling.yaml）,   │
│     user:   "Find the temperature of Beijing, Tokyo, Singapore..."] │
│  + tools=[get_temperature schema, final_answer schema]              │
│                                                                      │
│  LLM 输出 tool_calls：                                               │
│    [{name: "get_temperature", arguments: {city: "Beijing"}}]         │
│                                                                      │
│  框架动作：调 Python 函数 get_temperature("Beijing") → 25.0          │
│  memory.steps += [ActionStep(tool_calls=[...], observation="25.0")] │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  第 2 幕 — ActionStep(step_number=2)                                │
├────────────────────────────────────────────────────────────────────┤
│  LLM 输入：[system, user, assistant(call Beijing), tool(25.0)]       │
│  LLM 输出：{name: "get_temperature", arguments: {city: "Tokyo"}}     │
│  框架动作：→ 30.0，append ActionStep                                 │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  第 3 幕 — ActionStep(step_number=3)                                │
├────────────────────────────────────────────────────────────────────┤
│  LLM 输入：[..., tool(25.0), assistant(call Tokyo), tool(30.0)]      │
│  LLM 输出：{name: "get_temperature", arguments: {city: "Singapore"}} │
│  框架动作：→ 28.0，append ActionStep                                 │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  第 4 幕 — ActionStep(step_number=4)（终止步）                      │
├────────────────────────────────────────────────────────────────────┤
│  LLM 输入：完整对话历史（含 3 次温度结果 25/30/28）                   │
│  LLM 输出：{name: "final_answer", arguments: {answer: 86.0}}         │
│           ↑ LLM 自己心算了 max(25,30,28)*1.8+32 = 86                │
│  框架动作：识别到 final_answer 工具，标记 is_final_answer=True       │
│  memory.steps += [ActionStep(...)]                                   │
│  循环结束，run() 返回 86.0                                           │
└────────────────────────────────────────────────────────────────────┘

len(memory.steps) = 1 (TaskStep) + 4 (ActionStep) = 5  ✓
LLM 调用次数 = 4
```

#### CodeAgent — 2 步剧本

```
┌────────────────────────────────────────────────────────────────────┐
│  开场 — TaskStep（不带 step_number）                                │
├────────────────────────────────────────────────────────────────────┤
│  和 ToolCallingAgent 一样，append TaskStep                          │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  第 1 幕 — ActionStep(step_number=1)（唯一一幕）                    │
├────────────────────────────────────────────────────────────────────┤
│  LLM 输入 messages：                                                 │
│    [system: "...用 Python 代码作为动作..."（code_agent.yaml，工具    │
│              说明被渲染成自然语言文本塞进 system prompt）,            │
│     user:   "Find the temperature of Beijing, Tokyo, Singapore..."] │
│  注意：没传 tools 字段！纯文本对话                                    │
│                                                                      │
│  LLM 输出（纯文本）：                                                 │
│    Thought: 我需要查 3 个城市的温度，找最大值，换算华氏度。            │
│    ```python                                                         │
│    cities = ["Beijing", "Tokyo", "Singapore"]                        │
│    temps = {c: get_temperature(c) for c in cities}                   │
│    hottest = max(temps.values())                                     │
│    final_answer(hottest * 1.8 + 32)                                  │
│    ```                                                               │
│                                                                      │
│  框架动作：                                                           │
│    1. parse_code_blobs() 用正则抠出代码段（utils.py:198）            │
│    2. LocalPythonExecutor 执行整段代码                               │
│       - 循环调 get_temperature 3 次（25, 30, 28）                    │
│       - max() 得到 30                                                │
│       - final_answer(30*1.8+32) = final_answer(86.0)                 │
│    3. 检测到 final_answer 被调用 → 标记终止                          │
│  memory.steps += [ActionStep(code="...", observation=...)]          │
│  循环结束，run() 返回 86.0                                           │
└────────────────────────────────────────────────────────────────────┘

len(memory.steps) = 1 (TaskStep) + 1 (ActionStep) = 2  ✓
LLM 调用次数 = 1
```

> 💡 **对照剧本看核心差异**：
>
> 1. **协议层**：ToolCallingAgent 每步走"OpenAI tools 协议 → LLM 返回结构化 tool_calls → 框架查表执行"；CodeAgent 走"普通 chat → LLM 返回含代码的文本 → 框架正则抠出代码 → Python 执行器跑"。
> 2. **计算位置**：ToolCallingAgent 的算术（`max() * 1.8 + 32`）发生在 LLM **大脑里**（靠模型心算）；CodeAgent 发生在 Python **解释器里**（精确无误差）。这也是为什么 CodeAgent 在数学密集任务上更可靠 —— 它不让 LLM 心算。
> 3. **LLM 调用成本**：4 次 vs 1 次，**直接对应你 token 账单的 4 倍差**。这才是 step 数差异的真实代价。

> 💡 **如何在自己的代码里验证这些剧本**：跑 agent 后遍历 `agent.memory.steps`，每个元素打印 `step.model_input_messages`（LLM 看到啥）、`step.model_output_message`（LLM 输出啥）、`step.tool_calls` / `step.code_action`（框架抠出的动作）、`step.observations`（执行结果）。**Week 2 读 [memory.py](../../../src/smolagents/memory.py) 时这些字段都会精读到**。

---

## 8. LLM 怎么知道执行进度？—— ReAct 循环的核心机制

> 这是一个看完剧本之后必然冒出来的疑问：第 1 幕调 LLM 输出 `查Beijing`，第 2 幕调 LLM 又输出 `查Tokyo`。**LLM 是怎么知道"现在该轮到 Tokyo 了"的？它有进度记忆吗？**

### 8.1 核心洞察：LLM 没有任何"进度感"

**LLM 是无状态的，每次调它都是冷启动**。它不知道"现在是第 2 步"，它只知道"前面发生过什么" —— 因为框架每次调 LLM 前，都会**把 `memory.steps` 里所有历史重新翻译成 messages 发给它**。

LLM 看到完整的对话历史，就像人看到上文能推断下文 —— "查 Beijing 已经做完，结果 25，自然该轮到 Tokyo"。**进度感是 LLM 自己从历史里推断出来的，不是框架告诉它的**。

### 8.2 源码证据

[agents.py:1284](../../../src/smolagents/agents.py)：每幕开始时强制重写完整 messages：
```python
memory_messages = self.write_memory_to_messages()
input_messages = memory_messages.copy()
```

[agents.py:758-770](../../../src/smolagents/agents.py) `write_memory_to_messages`：
```python
messages = self.memory.system_prompt.to_messages(...)
for memory_step in self.memory.steps:
    messages.extend(memory_step.to_messages(...))   # ← 每个 step 翻译成 messages
return messages
```

[memory.py:92-150](../../../src/smolagents/memory.py) `ActionStep.to_messages()`：每个 ActionStep 还原成 **3 条** message：
- `assistant`：LLM 之前的思考文字（`model_output`）
- `tool_call`：之前的工具调用（`tool_calls`）
- `tool_response`：工具执行的结果（`observations`）

### 8.3 每幕 messages 实际怎么演进

```
                    messages 内容
                    ─────────────────────────────────────────────────
第 1 幕（2 条）:    [system, user(task)]
                                                         ↓ 追加 3 条
第 2 幕（5 条）:    [system, user(task),
                     assistant(思考1), tool_call(查Beijing), tool_response(25.0)]
                                                         ↓ 追加 3 条
第 3 幕（8 条）:    [system, user(task),
                     assistant(思考1), tool_call(查Beijing),    tool_response(25.0),
                     assistant(思考2), tool_call(查Tokyo),      tool_response(30.0)]
                                                         ↓ 追加 3 条
第 4 幕（11 条）:   [system, user(task),
                     assistant(思考1), tool_call(查Beijing),    tool_response(25.0),
                     assistant(思考2), tool_call(查Tokyo),      tool_response(30.0),
                     assistant(思考3), tool_call(查Singapore),  tool_response(28.0)]
```

### 8.4 三个值得记住的规律

#### 规律 1：前缀完全不变

第 1 幕的 `[system, user(task)]` 是后面所有幕的"前 2 条"。第 2 幕新增的 3 条又会**原封不动**出现在第 3、4 幕的开头。

> 💡 **为什么这样设计**：让 LLM 永远看到完整任务背景 + 完整历史，避免"忘记任务"。

#### 规律 2：每幕固定追加 3 条（来自上一幕的 ActionStep）

来自 `ActionStep.to_messages()` 的 3 类输出（[memory.py:92-150](../../../src/smolagents/memory.py)）。如果启用 planning，每隔几幕还会多出 PlanningStep 的 2 条。

#### 规律 3：token 成本随轮数线性增长

第 4 幕的 prompt ≈ 第 1 幕的 5 倍长。10 步的 agent 跑到最后，单次 prompt 可能是开局的 30 倍 token。

> 💡 **延伸**：现代 LLM provider 推 **prompt caching** 就是为了这个场景 —— 因为前缀完全一致，第 N 幕的前 N-1 幕内容能命中缓存，**只为新增的 3 条付钱**。OpenAI / Anthropic / DeepSeek 都已支持。Agent 是 prompt caching 的最大受益者。

#### 规律 3 延伸 — Prompt caching 是怎么生效的？（深入阅读）

> ⚠️ 这一节属于**实战优化原理**，主线学习不必精读，但理解了能帮你设计 caching 友好的 agent。

##### 一个表面矛盾

第 1 幕的 messages 是第 2 幕的前 2 条，**完全相同**。但 LLM 在两幕里的输出可以不同（因为第 2 幕后面多了 3 条新历史）。**那 caching 到底缓存了什么？**

答案：**缓存的不是"LLM 的输出"，而是 LLM 内部"读 prompt 时产生的中间计算结果（KV cache）"**。

##### LLM 推理分两阶段

| 阶段 | 做什么 | 计算量 |
|---|---|---|
| **Prefill**（读 prompt） | 把 prompt 每个 token 跑过 transformer，算出每个位置的 KV 张量（attention 中间产物） | **正比于 prompt 长度，是大头** |
| **Decode**（生成 output） | 基于上面的 KV，逐个生成输出 token | 正比于输出长度，通常很短 |

**Prompt caching 缓存的是 Prefill 阶段算出来的 KV**。

##### 为什么前缀的 KV 能跨幕复用 —— Causal Attention

Transformer 的核心特性：

> 位置 `i` 的 KV 计算时，**只能看到位置 0 到 i 的 token**，看不到 i 之后的任何 token。

所以**第 50 个 token 的 KV 只取决于前 50 个 token 是什么，跟第 51、52、53……是什么完全无关**。

```
第 1 幕 prompt: [A, B]                          ← 2 token
第 2 幕 prompt: [A, B, C, D, E]                 ← 5 token
```

- 位置 0（A）的 KV：第 1 幕和第 2 幕**完全相同**（只看 A）
- 位置 1（B）的 KV：第 1 幕和第 2 幕**完全相同**（只看 A、B）
- 位置 2、3、4 的 KV：第 2 幕新算

**第 2 幕的 Prefill 计算量从 5 token 降到 3 token**，前 2 个直接从缓存拿。

##### 那为什么输出还能不同 —— Decode 阶段看完整 KV

```
第 1 幕 decode 看到的 KV: [KV(A), KV(B)]                          → 输出 X
第 2 幕 decode 看到的 KV: [KV(A), KV(B), KV(C), KV(D), KV(E)]      → 输出 Y
                          ↑↑↑↑↑↑↑↑↑↑↑↑
                          缓存复用，但 decode 时仍然参与计算
```

虽然前 2 个 KV 完全一样，但第 2 幕 decode 时还要参考多出来的 KV(C)、KV(D)、KV(E) —— 输出**必须不同**，因为 LLM 要响应新历史。

##### 一个直观类比

> 💡 **想象 LLM 是个学生在做阅读理解**：
>
> - **Prefill** = 一行一行读题目，每读一行做一条笔记
> - **Decode** = 读完所有笔记后开始答题
>
> 关键点：每条笔记**只取决于这一行写了什么**，不会因为后面有什么而改变（causal attention）。
>
> Prompt caching = "上次读过的前 100 行的笔记保留下来，这次读到第 101 行时，前 100 行的笔记直接用旧的，只新做第 101 行的笔记"。
>
> 但答题（decode）阶段，学生还是会**把所有笔记从头读一遍再答**，所以最终答案可以跟上次不同 —— 取决于这次新增的笔记内容。

##### 一句话总结

| | 是什么 | 跨幕能否复用 |
|---|---|---|
| **KV cache（前缀）** | "读 prompt 时的笔记" | ✅ 能（因为 causal attention） |
| **输出 token** | "看完笔记后的答题" | ❌ 不能（必须基于完整 prompt 重新决策） |

> **caching 省的是"读 prompt"的算力，不是"生成输出"的算力**。

##### 实战影响（设计 agent 时记住）

1. **典型节省**：OpenAI / Anthropic / DeepSeek 缓存 token ≈ 普通 token 的 **10%~50% 价格**。
2. **agent 是最大受益者**：前缀稳定（system + task + 前面所有幕），命中率 80%+。
3. **触发条件**：prompt 前缀**字节级一致**（连标点都不能差）。所以：
   - ❌ 不要在 system prompt 里塞时间戳、随机 ID
   - ❌ 不要在 messages 中间插内容（只能在末尾追加）
   - ✅ smolagents 设计本身就是 caching 友好的 —— 永远末尾追加 ActionStep
4. **缓存有 TTL**：OpenAI 默认 5-10 分钟。Agent 跑得太慢缓存可能失效。

> 💡 **回头看**：理解了 prompt caching，你就能解释 § 8.4 规律 1 "前缀完全不变" 为什么不只是"看着规整"，而是**实打实省钱的设计原则**。

---

### 8.5 失忆症类比（帮你记住）

> 💡 **想象一个失忆症患者每天醒来都不记得昨天，但身边有一本日记。他读完日记就知道"哦，我昨天查了 Beijing 和 Tokyo，今天该查 Singapore 了"。**
>
> - **LLM** = 失忆症患者（每次调用都是新的开始）
> - **`memory.steps`** = 日记
> - **`write_memory_to_messages()`** = 把日记摆到他面前的动作
> - **每天读完日记再决定** = LLM 看完完整 messages 再生成下一步

LLM 的"智能"不是"记得做过什么"，而是"读完上文能推断下文"。这就是为什么 LLM 又被叫做 **chat completion** —— 它做的事就是"把对话补完"，而不是"维护对话状态"。

### 8.6 一个反直觉的点

LLM 看第 1 幕的 messages 和看第 2 幕的前 2 条**完全相同**，但产生的输出可能不同 —— 因为第 2 幕后面多了 3 条新历史，影响了它的整体决策。

**LLM 不是"基于上次响应再继续"，而是每次都从 messages[0] 读到最后一条，再决定下一步**。这是 LLM 工作机制的本质。

### 8.7 这条机制对 CodeAgent 一样适用

如果 CodeAgent 跑了多步（罕见但可能），第 N 步开始时 LLM 看到的 messages 包含：
```
[system, user(task),
 assistant("Thought: ...\n```python\nx = ...\n```"),  ← 第 1 步的代码
 tool_response("Observation:\nstdout: ..."),          ← 第 1 步执行结果
 ...重复直到第 N-1 步]
```
LLM 据此推断下一步代码。区别只在 assistant 内容是代码块文本（不是 tool_calls 字段）。

### 8.8 这个机制带来的实战影响

1. **memory 膨胀问题**：长任务（50+ 步）prompt 会爆 context。smolagents 的应对见 [memory.py](../../../src/smolagents/memory.py)（Week 2 精读时关注）。
2. **改 memory = 改 LLM 看到的世界**：手动修改 `agent.memory.steps` 能让 LLM "误以为"某些事发生过 —— agent 调试 / soft redirect 的常用招。
3. **prompt caching 是 agent 的省钱利器**：因为前缀稳定，能省 80%+ 的 token 成本。

---

**官方对比 demo**（更简单的版本）：[examples/agent_from_any_llm.py](../../../examples/agent_from_any_llm.py)
> 只问"巴黎天气"，单个工具调用，差异不明显，但代码更短可以参考。

**配套 examples**（同样涉及两种 agent 切换）：
- [examples/multiple_tools.py](../../../examples/multiple_tools.py) — 货币兑换 + 时间查询多工具，注释里展示了如何在两种 agent 间切换
- [examples/rag_using_chromadb.py](../../../examples/rag_using_chromadb.py) — RAG 例子，注释展示两种切换

---

## 关键认知清单

学完这一节，你应该能回答：

- [x] 两种 agent 的本质区别（动作格式：JSON vs Python）
- [x] 为什么 CodeAgent 通常更省步数（一步多工具 + 计算）
- [x] CodeAgent 不依赖 provider 的 function calling（"模型无关"）
- [x] CodeAgent 的代价（安全、模型要求）
- [x] 学习阶段优先选哪个（CodeAgent）
- [x] **`len(memory.steps)` 包含 TaskStep + ActionStep；`step_number` 只编号 ActionStep 从 1 开始**
- [x] **LLM 是无状态的，"进度感"完全来自每幕重发的对话历史**（失忆症 + 日记）
- [x] **每幕 messages 前缀不变 + 固定追加 3 条 → token 线性增长 → prompt caching 价值所在**
- [x] **Prompt caching 缓存的是 prefill 阶段的 KV（不是输出）；causal attention 保证前缀 KV 不依赖后续 token，所以能跨幕复用**

---

## 相关链接

- [what-is-agent.md](what-is-agent.md) — 什么是 agent（前置概念）
- [tool-creation-decorator-vs-subclass.md](tool-creation-decorator-vs-subclass.md) — `@tool` vs `Tool` 子类的选择
- [compare_agents.py](../../scripts/compare_agents.py) — 对比 demo（自己做的）
- [examples/agent_from_any_llm.py](../../../examples/agent_from_any_llm.py) — 官方简版对比
- 源码：
  - [agents.py:1276 ToolCallingAgent._step_stream](../../../src/smolagents/agents.py)
  - [agents.py:1639 CodeAgent._step_stream](../../../src/smolagents/agents.py)
- 论文：
  - [Executable Code Actions Elicit Better LLM Agents (2402.01030)](https://huggingface.co/papers/2402.01030)
  - [TaskBench (2411.01747)](https://huggingface.co/papers/2411.01747)

## 遗留问题

放进 [questions.md](../questions.md)：

- [ ] 跑 `compare_agents.py` 实际观察到的步数差是多少？和预期 4 vs 1 一致吗？如果不一致，是哪个模型表现不同？
- [ ] CodeAgent 的代码解析器 `parse_code_blobs()` 在 [src/smolagents/utils.py](../../../src/smolagents/utils.py) 里，怎么实现的？支持嵌套代码块吗？
- [ ] ToolCallingAgent 走的是 LLM 的 native function calling，但万一 LLM 不支持（比如老的 Llama）怎么办？fallback 是什么？
