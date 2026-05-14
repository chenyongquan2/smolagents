---
created: 2026-05-14
status: active
tags: [smolagents, agents, step-stream, codeagent, toolcallingagent, diff, day5, source-reading]
---

# Day 5 两子类逐环节差异对比

> ⚠️ **必读前置**：
> - [00-step-stream-role-overview.md](00-step-stream-role-overview.md) — 5 步骨架 + 2 个分歧点 mental model
> - [01-toolcalling-walkthrough.md](01-toolcalling-walkthrough.md) — ToolCallingAgent 演出版（10 幕）
> - [02-codeagent-walkthrough.md](02-codeagent-walkthrough.md) — CodeAgent 演出版（8 幕）
>
> 本笔记**不重述 01 / 02 已讲过的剧本**。聚焦"两个剧本并排时，差异落在哪里、为什么"。每节回答**一个具体差异维度**，附对比表 + 设计意图。

---

## 1. 一句话定调：3 个根本差异决定一切

两个子类**继承同一个 `MultiStepAgent`**、走**完全相同的 5 步骨架**（00 ⭐⭐ 已讲）。但 3 个根本差异层层放大，最终长出两套完全不同的 ReAct 风格：

```
┌─ 根本差异 1 ─ system_prompt 教 LLM 什么 ─────────────────────┐
│  ToolCalling: "用 JSON 工具调用，一次一个"                    │
│  CodeAgent:   "用 Python 代码，<code>...</code> 包起来"      │
└─────────┬─────────────────────────────────────────────────────┘
          ↓
┌─ 根本差异 2 ─ LLM 输出形态 ─────────────────────────────────┐
│  ToolCalling: response.tool_calls (结构化 JSON 字段)         │
│  CodeAgent:   response.content (自由文本 + 代码块)           │
└─────────┬─────────────────────────────────────────────────────┘
          ↓
┌─ 根本差异 3 ─ 谁在哪里执行动作 ────────────────────────────┐
│  ToolCalling: agent framework 在主进程直接 tool(**args)      │
│  CodeAgent:   python_executor 在沙箱（local / e2b / docker） │
└──────────────────────────────────────────────────────────────┘
```

其他所有"小差异"（事件数 / 步数 / 错误类型 / memory 字段 ...）都是这 3 个根本差异**派生**出来的。

---

## 2. 一图压缩：两条调用链并排

```
┌─ ToolCallingAgent._step_stream (84 行) ───┐ ┌─ CodeAgent._step_stream (127 行) ────┐
│                                           │ │                                       │
│ ① read messages                           │ │ ① read messages                       │
│   write_memory_to_messages().copy()       │ │   write_memory_to_messages().copy()   │
│   ↓ memory_step.model_input_messages      │ │   ↓ memory_step.model_input_messages  │
│                                           │ │                                       │
│ ② call LLM                                │ │ ② call LLM                            │
│   model.generate(                         │ │   model.generate(                     │
│     stop=["Observation:", "Calling..."]   │ │     stop=[...同左..., "</code>"]      │ ⭐
│     tools_to_call_from=[...] ⭐           │ │     # 不传 tools_to_call_from         │ ⭐
│   )                                       │ │     **additional_args (含 response_   │
│                                           │ │       format if structured)           │ ⭐
│                                           │ │   )                                   │
│   yield delta × N (if stream)             │ │   yield delta × N (if stream)         │
│   ↓ memory_step.model_output*             │ │   手动补 closing tag                  │ ⭐
│                                           │ │   ↓ memory_step.model_output*         │
│                                           │ │                                       │
│ ③ parse output                            │ │ ③ parse output                        │
│   chat_message.tool_calls                 │ │   parse_code_blobs(text, tags)        │ ⭐
│   parse_json_if_needed(args)              │ │   fix_final_answer_code(code)         │ ⭐
│                                           │ │   ↓ memory_step.code_action           │ ⭐
│                                           │ │   合成 ToolCall("python_interpreter") │
│                                           │ │   yield ToolCall                      │
│                                           │ │                                       │
│ ④ execute action                          │ │ ④ execute action                      │
│   process_tool_calls (107 行 嵌套):       │ │   python_executor(code)               │
│     阶段 A: yield ToolCall × N            │ │   → CodeOutput(out, logs, is_final)   │
│     阶段 B: ThreadPoolExecutor 并行       │ │                                       │
│       execute_tool_call:                  │ │                                       │
│         查名 + state + 质检 + tool(**args)│ │                                       │
│       yield ToolOutput × N                │ │                                       │
│   写回 memory_step.tool_calls / observ.   │ │   ↓ memory_step.observations          │
│                                           │ │   ↓ memory_step.action_output         │ ⭐
│                                           │ │                                       │
│ ⑤ write back + yield                      │ │ ⑤ yield                               │
│   yield ActionOutput(final, is_final)     │ │   yield ActionOutput(out, is_final)   │
│   (action_output 由 Day 4 外层写)         │ │   (action_output 已在 ④ 写)          │
└───────────────────────────────────────────┘ └───────────────────────────────────────┘
```

⭐ 标的就是差异点。下面 §3-§9 逐个展开。

---

## 3. ⭐ 差异维度 1：LLM 输出格式

| | ToolCallingAgent | CodeAgent（默认）| CodeAgent（structured）|
|---|---|---|---|
| 协议路径 | **function calling 协议**（02 笔记专题）| 自由文本 | structured output 协议 |
| 请求 body 加什么 | `tools=[...]` | 啥都不加 | `response_format=CODEAGENT_RESPONSE_FORMAT` |
| LLM 响应字段 | `tool_calls` 列表（结构化 JSON）| `content` 文本 | `content` JSON 字符串 |
| LLM 看到的 system_prompt 教什么 | "JSON 调用，一次一个" | "Python 代码 + `<code>...</code>` 包裹" | "Python 代码 + 输出 `{thoughts, code}` JSON" |
| LLM 实际写什么 | `{"name": "...", "arguments": {...}}` × N | "思考...<code>代码</code>"自由文本 | `{"thoughts": "...", "code": "..."}` 严格 JSON |

**为什么差这么多** —— 02 笔记 §专题"控制 LLM 输出的 3 条路径"已经讲透：function calling 是"点菜模式"（LLM 一次只能勾选一道菜），自由文本 + 代码块是"白纸作文"（LLM 写多行代码塞任意逻辑），structured 是"答题卡"（强制 JSON 结构但代码内容自由）。

**派生差异**：
- ToolCallingAgent **每步只能调一个工具** —— JSON 结构每个 `tool_calls[i]` 是离散调用，无法表达"循环 / 计算 / 分支"
- CodeAgent **一段代码塞任意多操作** —— Python 是 Turing complete，能写循环 + 条件 + 中间变量
- 这就是后面 §10 "4 步 vs 1 步" 的根源

---

## 4. ⭐ 差异维度 2：解析路径（动作 ③）

| | ToolCallingAgent ([agents.py:1327-1334](../../../../src/smolagents/agents.py#L1327)) | CodeAgent ([agents.py:1703-1714](../../../../src/smolagents/agents.py#L1703)) |
|---|---|---|
| 优先路径 | 直接读 `chat_message.tool_calls`（结构化字段已在）| `parse_code_blobs(output_text, code_block_tags)` 抠 |
| 优先路径做的事 | `parse_json_if_needed(arguments)` 转 dict | regex `<code>(.*?)</code>` 抠代码字符串 |
| Fallback | `model.parse_tool_calls(chat_message)` 从文本 regex 抠 | 3 把刀（[utils.py:198-251](../../../../src/smolagents/utils.py#L198)）：① 自定义 tags ② markdown 模式 ③ `ast.parse(text)` 裸代码 |
| 后处理 | — | `fix_final_answer_code(code)` 修补"`final_answer = X`" 赋值错误 |
| structured 模式特例 | — | `json.loads(output_text)["code"]` 直接取 JSON 字段 |
| 失败抛 | `AgentParsingError` | `AgentParsingError`（特殊错误消息提示"final + answer"误用）|

**本质差异**：
- ToolCallingAgent **拿的是结构化数据**（LLM API 服务器替它解析过的 JSON）—— 框架只做"json 字符串 → dict"这种细小转换
- CodeAgent **拿的是纯文本中的代码块** —— 需要 3 把刀逐级尝试 + 后处理修补 LLM 偶尔的格式错误

> 💡 **CodeAgent 的解析为什么需要 3 把刀**？因为 LLM 不完美 —— 即使 system_prompt 教 LLM 用 `<code>`，LLM 也可能：
> - 用 markdown ```` ```python ``` ```` 反弹（刀②兜底）
> - 直接吐一段 Python 代码没包标签（刀③兜底）
> - 把 `final_answer` 当变量赋值（`fix_final_answer_code` 修补）

---

## 5. ⭐ 差异维度 3：执行机制（动作 ④）

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| 入口 | `process_tool_calls(...)` ([agents.py:1361-1442](../../../../src/smolagents/agents.py#L1361)) | `python_executor(code_action)` ([agents.py:1727](../../../../src/smolagents/agents.py#L1727)) |
| 执行什么 | N 个 tool call（list） | 1 段 Python 代码字符串 |
| 单次 vs 多次 | 多个 tool 调用 | 一段代码 1 次执行 |
| 并行机制 | `ThreadPoolExecutor` 并发跑 + `copy_context()` 隔离 contextvars | 沙箱内部串行（代码本身是线性 Python）|
| 真正调 tool 的那一行 | `tool(**args, sanitize_inputs_outputs=True)` (execute_tool_call) | 沙箱内 `get_temperature("Beijing")` 这行代码（沙箱解析 AST 后调）|
| 嵌套深度 | `_step_stream` → `process_tool_calls` → `process_single_tool_call` → `execute_tool_call` → `tool(**args)` 5 层 | `_step_stream` → `python_executor(code)` → 沙箱内 `tool(**args)` 3 层 |
| 失败抛 | `AgentToolCallError` / `AgentToolExecutionError` | `AgentExecutionError`（特判 import 错误提示 `additional_authorized_imports`）|

**关键认知**：

- **两边最终都调 `tool(**args)` Python 函数**（呼应 [tools-are-python-callables.md](../../02-concepts/tools-are-python-callables.md)）—— 工具本身没差异
- 真正的差异在 **"谁安排这次调用、在哪里调"**：
  - ToolCallingAgent：framework 在主 Python 进程
  - CodeAgent：沙箱（默认 LocalPythonExecutor 也是同进程，但 `executor_type="e2b" / "docker" / "wasm"` 时是远程进程 / 容器 / WebAssembly）

> 💡 **远程沙箱模式**：CodeAgent 通过 `python_executor.send_tools(...)` 把 Tool 函数序列化发送到远程沙箱。**工具仍然是 Python callable，只是"调用的物理位置"变了**。详见 Day 6 沙箱深度笔记（待读）。

---

## 6. 差异维度 4：跨步骤状态机制

| | ToolCallingAgent | CodeAgent |
|---|---|---|
| 数据结构 | `agent.state: dict[str, Any]` | 沙箱 Python namespace（`executor.state` dict 也存，但本质是 namespace） |
| LLM 怎么用 | LLM 输出 `{"image_path": "image.png"}` 这种**字符串 key** | LLM 直接写变量名：`x = get_temperature("Beijing")` |
| 跨步骤传递 | tool 返回 AgentImage / AgentAudio → 框架存 state → LLM 下轮通过 key 引用 → `_substitute_state_variables` 替换回真对象 | tool 返回值 → 沙箱内变量 → **同一个 namespace 跨步骤共享**，下一步代码直接 `print(x)` |
| 适用对象 | 二进制资产（图 / 音）| 任意 Python 对象 |
| LLM 看到的内容 | 观察 = "Stored 'image.png' in memory." 描述字符串 | 观察 = `print(...)` 的输出 logs |

**本质差异**：
- ToolCallingAgent 用 `state` 字典是因为 LLM 跨步骤只能传"字符串"（JSON 协议限制）—— 二进制对象不能塞进 JSON，所以用 key 引用机制绕过
- CodeAgent 不需要 `state` 是因为变量在 Python namespace 里**天然跨步骤存活** —— 只要同一个 executor 实例

**这是 CodeAgent 隐藏优势**：跨步骤传任意对象零摩擦，不需要 LLM 学"image_path 引用"这种约定。

---

## 7. 差异维度 5：事件流（yield 几下对讲机）

按 Day 4 ③'' [stream-event-types](../day4-agents/03c-stream-event-types.md) 的 4 种事件，**每步内部 yield 的事件数**：

| 事件类型 | ToolCallingAgent（单 tool call 单步）| CodeAgent（单步）|
|---|---|---|
| `ChatMessageStreamDelta` | N（stream_outputs=True 时每 token 一个）| 同左 |
| `ToolCall`（执行前预告）| 1 | 1（合成的 "python_interpreter" ToolCall）|
| `ToolOutput`（执行后反馈）| **1** ⭐ | **0** ⭐⭐ —— CodeAgent 不发！|
| `ActionOutput`（步收尾）| 1 | 1 |
| **总计**（非 stream）| **3** 下对讲机响 | **2** 下 |

⭐⭐ **CodeAgent 为什么没有 ToolOutput 事件**？

- ToolCallingAgent 每个离散 tool call 都有"前置预告（ToolCall）+ 后置反馈（ToolOutput）"配对 —— UI 能显示"loading…→ 结果"两阶段
- CodeAgent 整段代码是 1 次执行 —— 没有"调多个工具的 latency"概念，沙箱跑完整段返回 1 个 `CodeOutput`
- 设计哲学呼应 Day 4 ③'''' [event-design-philosophy](../day4-agents/03e-stream-event-design-philosophy.md) §"ToolCall vs ToolOutput 前置 vs 后置反馈"：**没有 latency 期间，就没必要分两段事件**

**UI 影响**：

- ToolCallingAgent UI：可以渲染"⏳ 正在搜索 Paris..." → "✓ 12°C" 两阶段
- CodeAgent UI：只能渲染"⏳ 正在执行代码..." → "✓ 结果 86.0"（不知道沙箱里跑到哪一行了）

---

## 8. 差异维度 6：错误处理（异常类型）

| 抛出阶段 | ToolCallingAgent | CodeAgent | Day 4 ③ §错误处理 3 层定位 |
|---|---|---|---|
| 动作 ② LLM 调用失败 | `AgentGenerationError` | `AgentGenerationError` | **实现 bug fail-fast**（冲出外层）|
| 动作 ③ 解析失败 | `AgentParsingError` | `AgentParsingError` | **ReAct 反馈信号**（记 step 写下轮 messages 让 LLM 改）|
| 动作 ④ tool 找不到 | `AgentToolExecutionError` | — | ReAct 反馈信号 |
| 动作 ④ tool 参数错 | `AgentToolCallError` | — | ReAct 反馈信号 |
| 动作 ④ tool 执行炸 | `AgentToolExecutionError` | — | ReAct 反馈信号 |
| 动作 ④ 代码执行炸 | — | `AgentExecutionError`（特判 import 错误）| ReAct 反馈信号 |
| 动作 ④ 多 final_answer | `AgentExecutionError` / `AgentToolExecutionError` | — | ReAct 反馈信号 |
| **总计** | **5 种异常** | **3 种异常** | — |

**差异**：
- ToolCallingAgent 异常更细（5 种）—— 因为 execute_tool_call 内部有 "查名 / state / 质检 / 调用" 4 阶段，每阶段独立抛
- CodeAgent 异常较粗（3 种）—— 整段代码 1 次执行，沙箱内部各种错误都被收成 1 个 `AgentExecutionError`

**所有解析 / 执行类异常都是 `AgentError` 子类**，不冲出外层 —— Day 4 ③ §错误处理 3 层"ReAct 反馈信号"层。只有 `AgentGenerationError`（实现 bug）是冲出外层。

---

## 9. 差异维度 7：`memory_step` 字段谁写

呼应 Day 1 [action-step-anatomy](../day1-memory/action-step-anatomy.md) 13 字段：

| 字段 | ToolCallingAgent 写吗 | CodeAgent 写吗 | 写入时机 |
|---|---|---|---|
| `model_input_messages` | ✅ | ✅ | 动作 ① |
| `model_output_message` | ✅ | ✅ | 动作 ② |
| `model_output` | ✅ | ✅ | 动作 ② |
| `token_usage` | ✅ | ✅ | 动作 ② |
| `tool_calls` | ✅（真实 ToolCall list）| ✅（**合成**的 `[ToolCall("python_interpreter", code)]`）| ToolCall: 动作 ③；CodeAgent 内部立刻；ToolCalling: 动作 ④ 末 |
| `observations` | ✅（ToolOutput.observation 拼接）| ✅（"Execution logs:" + code_output.logs）| 动作 ④ 末 |
| `action_output` | ❌ **不在 _step_stream 写** | ✅ **在 _step_stream 写** | CodeAgent 写在动作 ⑤；ToolCalling 由 Day 4 外层处理 |
| `code_action` | ❌ 不写 | ✅ **CodeAgent 独有字段** | CodeAgent 动作 ③ 末 |

**两个最值得记的差异**：

1. **`code_action` 是 CodeAgent 独占字段** —— 存原始代码字符串，用于 replay / debug。ToolCallingAgent 不需要（结构化 tool_calls 已经够 replay）
2. **`action_output` 谁写不一致** —— Day 5 mental model §6 注脚提过的"两子类不一致点"。CodeAgent 在 _step_stream 内部直接写；ToolCallingAgent 通过 yield ActionOutput 让 Day 4 外层 _run_stream 处理

> 💡 **为什么 ToolCallingAgent 不在 _step_stream 写 `action_output`**？看 [agents.py:1356-1359](../../../../src/smolagents/agents.py#L1356) 末尾确实没写 —— 这可能是 smolagents 一个**轻微的设计不一致**（不是 bug，但不够对称）。CodeAgent 写了反而是"多此一举"的对称尝试，但对一致性更好。

---

## 10. 差异维度 8：步数与代价

跑同一个任务"找 3 个城市最高温转华氏"（[compare_agents.py](../../../scripts/compare_agents.py)）：

| | ToolCallingAgent (Qwen2.5-72B 实测) | CodeAgent |
|---|---|---|
| `memory.steps` 总数 | **5**（1 TaskStep + 4 ActionStep） | **2**（1 TaskStep + 1 ActionStep） |
| ActionStep 数（真正反映 ReAct 轮数） | **4**（3 次 get_temperature + 1 次 final_answer）| **1** |
| LLM 调用次数 | **4** | **1** |
| token 成本 ≈ | 4× （system_prompt + 累积 memory 重发） | 1× |
| Latency（顺序）| 4 × LLM 响应时间 | 1 × LLM 响应时间 + 沙箱执行时间（毫秒级）|

> ⚠️ **ToolCallingAgent 的 4 步是模型选择，不是框架强制**：function calling 协议支持 **parallel tool calling**（一轮 LLM 响应里返回多个 `tool_calls`），但 Qwen2.5-72B 在本任务下选了**串行**（每步 1 个 tool）。如果换成 GPT-4 这种擅长 parallel 的模型，可能变成 **2 步**（第 1 步一次 parallel 调 3 个 get_temperature，第 2 步 final_answer）。详见 [01 §番外 2 "LLM 什么时候会一次返回多个 tool_calls"](01-toolcalling-walkthrough.md#关键问题llm-什么时候会一次返回多个-tool_calls)。
>
> **CodeAgent 1 步的优势更稳健** —— 与模型 parallel 能力无关，**靠 Python Turing complete 表达能力**一次性塞完所有逻辑。

**关键认知**：

- **token 成本不是线性 4 倍** —— 因为每次都要重发整个 messages 历史（Day 1 [memory.py](../day1-memory/memory-data-structures.md) 已讲）。ToolCallingAgent 第 4 步的 messages 比第 1 步长得多 → 实际可能 6-10 倍 token
- **CodeAgent 不仅快还便宜** —— 这是 Week 1 [codeagent-vs-toolcallingagent §8.4](../../02-concepts/codeagent-vs-toolcallingagent.md) 实测数据的根因
- **prompt caching 加持下差距会被压缩**（Week 1 已揭示）—— 前缀缓存让第 2 / 3 / 4 步的 prefix 部分不重新计算，但仍然有 N 次 round-trip latency

### ⭐⭐ 为什么 parallel 救不了 ToolCallingAgent 的根本成本

直觉陷阱：既然 LLM 能一次 parallel 返回多个 `tool_calls`，那 ToolCallingAgent 的步数差距不就拉平了吗？**不会**。

#### 3 种情景下的 LLM 调用次数对比

同任务"查 3 个城市最高温转华氏"：

| 情景 | ToolCallingAgent | CodeAgent |
|---|---|---|
| 模型支持 parallel（GPT-4） | **2 次**（1 次并行查 + 1 次心算最大值+转华氏）| **1 次** |
| 模型不支持 parallel（Qwen2.5-72B 实测）| **4 次**（3 次串行查 + 1 次心算）| **1 次** |
| 任务依赖前一步结果（链式决策）| **N+1 次** | **1 次**（代码里直接写条件分支）|

**关键观察**：
- ToolCallingAgent 永远 ≥ **2 次** —— 除非任务真的只调 1 个工具就能直接给答案
- CodeAgent 永远 = **1 次** —— 除非有真正的 ReAct 决策点（看了某结果才能决定下一步策略）

#### LLM 一次返回 1 个 vs N 个 tool_calls 的两个原因

**原因 A · 协议层不支持**（少数）：

| 协议字段 | 时代 | 能力 |
|---|---|---|
| `function_call`（单数）| 2023.6 OpenAI 初版 | 每次只能调 1 个 |
| `tool_calls`（复数 list） | 2023.11 GPT-4 Turbo 起 | 支持 parallel |

现在 smolagents 只走 `tool_calls`（复数），**协议层面都支持 parallel**。

**原因 B · 协议支持但模型选择不用**（多数）：

即使字段是 list，LLM 也可能只放 1 个进去。决定因素：
- 模型能力：GPT-4 / Claude 3.5+ 训练时见过大量 parallel 示例 → 倾向 parallel；Qwen2.5-72B / 小模型 / 老模型见得少 → 倾向 sequential
- 任务性质：真正可独立并行 → LLM 更愿 parallel；有依赖关系 → 强行 parallel 反而错
- prompt 引导：[toolcalling_agent.yaml](../../../../src/smolagents/prompts/toolcalling_agent.yaml) 没明确教 → LLM 按自己默认偏好

#### 根本原因：JSON `tool_calls` 不能引用"运行时返回值"

LLM 在 Step 1 决定 parallel 调 3 个 `get_temperature` 时，**还不知道返回值是什么**（沙箱还没跑）。所以 Step 1 的 tool_calls 里**不可能**写：

```json
{
  "name": "final_answer",
  "arguments": {"value": "max(返回值1, 返回值2, 返回值3) × 1.8 + 32"}
                            ↑ JSON 协议无法表达"上一步返回值"
}
```

JSON 只能放**死值**（`{"value": 86.0}`）。但 LLM 在 Step 1 写时还不知道 86.0 是什么 → **必须等结果回来 + 重新调一次 LLM 让它心算** → 第 2 轮 LLM 调用。

CodeAgent 的 Python 代码**天然能引用上下文变量**（`max(temps)` / `temps[0]+1` / 中间赋值），所以**计算 + 决策 + 控制流全塞进沙箱**，LLM 只过一次。

#### 公式分解：ToolCallingAgent 成本拆解

```
ToolCallingAgent 总 LLM 调用 = N（调工具）+ 1（看结果做计算/决策）
                                ↑              ↑
                          parallel 能优化     parallel 救不了
                          (N → 1)            (永远多这 1 次)
```

**Parallel 解决一半问题**（独立工具调用 N → 1）；**另一半解决不了** —— "看完结果做计算 / 决策" 必然多一次 LLM 调用。

#### 一句话本质

| | LLM 的角色 |
|---|---|
| ToolCallingAgent | **LLM 当"控制器"** —— 每个决策点都要过 LLM |
| CodeAgent | **LLM 当"代码生成器"** —— 一次性写完控制流，剩下交给 Python 解释器 |

**CodeAgent 把"算力消耗"从昂贵的 LLM 端转移到便宜的 Python 端**。这是它便宜的根本原因，**与模型是否支持 parallel 无关**。

#### 极端例子（帮记忆）

**任务**：「查 5 个城市天气，找最暖的两个，温度相加后乘以 2」

| | ToolCallingAgent（GPT-4 parallel） | CodeAgent |
|---|---|---|
| Step 1 | parallel 调 5 次 `get_weather` | 写代码：`temps=[get_weather(c) for c in cities]; sorted_t=sorted(temps,reverse=True); final_answer((sorted_t[0]+sorted_t[1])*2)` |
| Step 2 | 看到 5 个结果 → LLM 心算"哪两个最暖 + 相加 + 乘 2" → final_answer | — |
| **LLM 调用次数** | **2** | **1** |
| 沙箱代码工作量 | 0 | sort + 加法 + 乘法（毫秒级，几乎免费）|

LLM 调用 = 钱 + 延迟。沙箱代码 = 几乎免费。

### ⭐ 扩展认知：3 个维度决定 LLM 调用次数

LLM 调用次数受 **3 个独立维度**影响。每个维度都把 ToolCallingAgent 和 CodeAgent 的差距打开一次：

#### 维度 1：协议批量能力（parallel vs sequential）

ToolCallingAgent + Qwen2.5（不支持 parallel，实测）跑"查 3 城市最高温转华氏"的**精确流程**：

```
进入 _run_stream 外循环

Step 1（LLM 第 1 次）：
  ├─ write_memory_to_messages() → [SYS, USER]
  ├─ model.generate(...) → tool_calls=[get_temperature("Beijing")]
  ├─ 调 → 25.0
  └─ memory.steps.append → [SystemPrompt, TaskStep, ActionStep1]

Step 2（LLM 第 2 次）：
  ├─ write_memory_to_messages() → [SYS, USER, ASSISTANT(act1), USER(obs1=25°C)]
  ├─ model.generate(...) → 看到 25°C → tool_calls=[get_temperature("Tokyo")]
  ├─ 调 → 30.0
  └─ memory.steps.append → [..., ActionStep2]

Step 3（LLM 第 3 次）：
  ├─ messages 含 [SYS, Task, act1, obs1, act2, obs2]
  ├─ LLM 看到 [25, 30] → tool_calls=[get_temperature("Singapore")]
  └─ → ActionStep3

Step 4（LLM 第 4 次）：
  ├─ messages 含 [SYS, Task, act1, obs1, act2, obs2, act3, obs3]
  ├─ LLM 看到 [25, 30, 28] → 心算 max=30 → 30*1.8+32=86 → tool_calls=[final_answer(86.0)]
  └─ 退出循环
```

**核心机理**：每次调一个 → 写 step → 把所有历史打包重发 → LLM 决定下一个。这正是 [Day 4 ⑤ write-memory-to-messages-deep-dive](../day4-agents/05-write-memory-to-messages-deep-dive.md) 讲的 messages 累积重发机制。

#### 维度 2：链式依赖任务（parallel 救不了）

**示例任务**："查 Paris 天气。**如果下雨**就查飞 London 的机票；**否则**查 Paris 的酒店"

LLM 在 Step 1 调 `get_weather("Paris")` 时**还不知道结果**，没法在同一个 tool_calls list 里既写"查机票"又写"查酒店"：

```
Step 1: tool_calls=[get_weather("Paris")]                       ← LLM 第 1 次
        → 拿到 "rainy"
Step 2: LLM 看到 "rainy" → tool_calls=[search_flight(...)]      ← LLM 第 2 次
        → 拿到机票
Step 3: tool_calls=[final_answer(...)]                           ← LLM 第 3 次
```

**3 次 LLM 调用，parallel 完全救不了**。`tool_calls` JSON list 元素都是**死的**，无法表达 "如果上一步是 X 就调 A 否则调 B" 这种条件。

**CodeAgent 同一任务**（决策逻辑离线化到代码）：

```python
weather = get_weather("Paris")
if "rain" in weather.lower():
    result = search_flight("Paris", "London")
else:
    result = search_hotel("Paris")
final_answer(result)
```

**1 次 LLM 调用**。沙箱跑时 evaluate `weather` 变量决定走哪条 if 分支 —— LLM 不需要看结果再决定。

#### 维度 3：探索式任务（CodeAgent 也救不了）

"先研究下 X，然后**根据你的发现**决定要不要进一步研究 Y" —— 这种本质需要 LLM 看到中间结果**做创造性决策**的任务，**再聪明的代码也写不出来**。这才是真正的 ReAct 多步循环存在意义。

#### 三维成本对照表

| 任务类型 | ToolCalling (parallel) | ToolCalling (no parallel) | CodeAgent |
|---|---|---|---|
| 1 个独立工具 + 直接 final_answer | 2 | 2 | 1 |
| N 个独立工具 + 算数/选择 | 2 | N+1 | 1 |
| **链式依赖**（A→B→C，每步参数依赖前一步返回值） | **N+1** | **N+1** | **1** |
| **条件分支**（参数依赖运行时 if-else 判断） | ≥2 | ≥2 | **1** |
| **真正的探索式**（看结果做创造性决策） | 多次 | 多次 | 多次（救不了） |

**Parallel 救不了的两种场景**：链式依赖 + 条件分支 —— CodeAgent 在这两种下都 1 次搞定。

**CodeAgent 也救不了的场景**：真正的探索式任务 —— ReAct 多步循环本来就是为这种存在的（不是为了"调 3 个独立 API"）。

---

## 11. 差异维度 9：能力边界（LLM 能做什么 / 不能做什么）

前面 §3-§10 讲的都是"实现层差异"。本节回答一个更根本的问题：**LLM 能做的事情有多大范围**？

### ToolCallingAgent：严格白名单工具池

LLM **只能调注册的工具**。具体看 [execute_tool_call 第 ① 步](../../../../src/smolagents/agents.py#L1463)：

```python
available_tools = {**self.tools, **self.managed_agents}
if tool_name not in available_tools:
    raise AgentToolExecutionError(f"Unknown tool {tool_name}, should be one of: ...")
```

LLM 输出未注册的 tool 名 → 抛 `AgentToolExecutionError` → 写下轮 messages → LLM 看到错误改正。

**白名单 3 个组成部分**：
1. 用户注册的 tools（`tools=[...]`）
2. managed_agents（子 agent 也实现了 `__call__`，长得像 tool）
3. 内置 `final_answer`（[Day 4 ④ init-setup-flow](../day4-agents/04-init-setup-flow.md) `_setup_tools` 兜底注册）

**不能做的事**（白名单之外）：
- 算 `max(25, 30, 28)` —— 除非你给它 `max_tool`
- 字符串处理 / 排序 / 算数 —— 除非每个操作都做成 tool
- 调用未注册的 Python 函数

### CodeAgent：沙箱化 Python 程序（呼应 Week 1 codeagent-how-it-works Q3）

LLM 能写**任意 Python 代码**，但被沙箱限制在 3 层内（[Week 1 codeagent-how-it-works Q3](../../02-concepts/codeagent-how-it-works.md)）：

#### Layer 1：调用注册工具（同 ToolCallingAgent）

```python
weather = get_weather("Paris")    # ← 注册工具
final_answer(86.0)                 # ← 内置工具
```

#### Layer 2：纯 Python（沙箱允许）

```python
# 算数
max_t = max(temps) * 1.8 + 32

# 控制流
for c in cities:
    temps.append(get_temperature(c))

# 条件分支
if "rain" in weather.lower():
    flights = search_flight("Paris", "London")

# 列表 / 字典 / 字符串处理
sorted_t = sorted(temps, reverse=True)
formatted = f"Max temp: {max_t:.1f}°F"

# 白名单 import
import math
result = math.sqrt(temps[0])
```

`authorized_imports` 控制能 import 啥（[02 第 1 幕 已讲](02-codeagent-walkthrough.md)）：
- 默认 `BASE_BUILTIN_MODULES` = `['math', 'json', 're', 'datetime', 'itertools', 'collections', ...]`
- 用户追加：`CodeAgent(additional_authorized_imports=["pandas", "numpy"])`

#### Layer 3：沙箱禁止（拒绝）

```python
import os              # ❌ 不在白名单 → InterpreterError
import subprocess      # ❌ 同上
os.system("rm -rf /")  # ❌ 即便能 import 也禁危险操作

exec("malicious code") # ❌ 危险 builtin
eval("...")            # ❌ 同上
__import__("os")       # ❌ 绕过白名单也不行
globals()              # ❌ 反射类危险 builtins

while True: pass       # ⚠️ 沙箱可加超时（默认不一定开）
```

具体白名单实现 / 危险 builtins 拦截 / AST 校验 → Day 6 [local_python_executor.py](../../../../src/smolagents/local_python_executor.py) 详讲。

### 9 个具体边界点对照表

| 边界 | ToolCallingAgent | CodeAgent |
|---|---|---|
| 调注册工具 | ✅ | ✅ |
| 算数 / 字符串处理 / 排序 | ❌（除非每个做成 tool）| ✅（沙箱内自由）|
| 循环 / 条件分支 | ❌ | ✅ |
| 列表推导 / 字典操作 | ❌ | ✅ |
| import 白名单模块（math/json/...） | ❌（没沙箱概念）| ✅ |
| import 危险模块（os/subprocess/socket）| ❌ N/A | ❌ 沙箱拒绝 |
| 文件系统访问 | ❌（除非有对应 tool）| ❌（除非白名单 + tool）|
| 网络 IO | ❌（除非有 tool）| ❌（除非 tool 提供）|
| 调用未注册的 tool | ❌ AgentToolExecutionError | ❌ NameError 在沙箱抛 |
| 危险 builtins（exec/eval/__import__）| ❌ N/A | ❌ 沙箱拒绝 |

### 常见疑问：ToolCallingAgent 真的不能算 max？

**是的**。如果你不给 ToolCallingAgent 提供 `max_tool` / `calculator` 之类的工具，它**只能让 LLM 心算**（在下一轮 LLM 调用里看着数字心算）。

| 计算复杂度 | LLM 心算靠谱吗 | 实际效果 |
|---|---|---|
| `max(25, 30, 28)` 3 个数 | ✅ 靠谱 | LLM 直接说 "30" |
| `max([1,2,...,100])` 100 个数 | ⚠️ 可能错 | 数大或顺序乱时漏看 |
| 复杂统计 / 排序 / 数据处理 | ❌ 经常错 | LLM 不是计算器 |

**这是 ToolCallingAgent 在数据处理任务上的本质短板** —— 常需要给它包一堆算数工具。CodeAgent 沙箱里 `max(...)` 永远准确。

### 类比帮记忆

| | 类比 | 边界本质 |
|---|---|---|
| **ToolCallingAgent** | 🍽️ 点菜模式 | 菜单上有啥点啥，菜单之外吃不到 |
| **CodeAgent** | 🏠 租了间小厨房 | 有食材（tool）+ 灶具（白名单 import）+ Python 表达力，但厨房门有锁（沙箱），不能拿菜刀去隔壁砸（系统级操作）|

### 设计哲学

| | 设计哲学 | 安全性 vs 表达力的权衡 |
|---|---|---|
| ToolCallingAgent | **能力 = 你显式给的工具** | 安全（白名单严格）但表达力有限 |
| CodeAgent | **能力 = 你显式给的工具 + Python 表达力**（沙箱内） | 表达力强但需要信任沙箱 |

**两条路服务两种用户**：
- 担心安全 / 控制可见性强 → ToolCallingAgent（每个能力点都是你显式开的）
- 需要复杂逻辑 / 信任沙箱 → CodeAgent（能力上限是 Python 本身）

---

## 12. 实战选型决策树

```
你的任务是什么？
│
├─ 简单流程（每步 1 个工具，无计算逻辑）？
│     → 选 ToolCallingAgent（默认）
│
├─ 复杂逻辑（循环 / 计算 / 分支 / 多步组合）？
│     → 选 CodeAgent
│     │
│     ├─ provider 支持 response_format 且代码格式偶尔不规范？
│     │     → 加 use_structured_outputs_internally=True
│     │
│     └─ provider 不支持 / 小模型 / 不在乎严格性？
│           → 默认 mode（自由文本）
│
├─ 担心 LLM 写代码乱跑？
│     ├─ 本地沙箱可接受 → CodeAgent + executor_type="local"（默认）
│     ├─ 严格隔离 → CodeAgent + executor_type="e2b" / "docker"
│     └─ 完全不放心 → ToolCallingAgent（白名单工具调用更可控）
│
└─ 想省钱（LLM 调用次数关键）？
      → CodeAgent（通常 1-2 步 vs 5+ 步）
```

**默认推荐**：**CodeAgent**（smolagents 团队也这么推）。除非有上述特殊原因，选它就对了。

---

## 13. 闭环回收

| 上游笔记 | 闭环点 |
|---|---|
| **Week 1** [codeagent-vs-toolcallingagent](../../02-concepts/codeagent-vs-toolcallingagent.md) | "动作格式 = JSON vs 代码" 的实现层落地 |
| **Week 1** [codeagent-how-it-works](../../02-concepts/codeagent-how-it-works.md) | Q1-Q4 工具传递 / LLM 编排 / 3 Layer 限制 / 三层闭环全部印证 |
| **Day 1** [action-step-anatomy](../day1-memory/action-step-anatomy.md) | §9 字段差异表（含 code_action 独有 + action_output 不一致）|
| **Day 2** [tool-class-role-overview](../day2-tools/tool-class-role-overview.md) | §5 两边都最终调 `Tool.__call__` —— 工具本身无差异 |
| **Day 3** [model-stop-sequences](../day3-models/model-stop-sequences.md) | §3 stop_sequences 在两边的不同用法（`</code>` 是 CodeAgent 独有）|
| **Day 4 ③** [agent-run-mental-model](../day4-agents/03-run-mental-model.md) | §8 错误处理 3 层在两子类的对应 |
| **Day 4 ③''** [stream-event-types](../day4-agents/03c-stream-event-types.md) | §7 事件流差异（3 下 vs 2 下） |
| **Day 4 ③''''** [event-design-philosophy](../day4-agents/03e-stream-event-design-philosophy.md) | §7 ToolCall vs ToolOutput 前置/后置反馈在 CodeAgent 不适用的原因 |
| **Day 5 00** [step-stream-role-overview](00-step-stream-role-overview.md) | §3 2 个分歧点的实证 |
| **Day 5 01** [toolcalling-walkthrough](01-toolcalling-walkthrough.md) | 10 幕剧本的差异维度索引 |
| **Day 5 02** [codeagent-walkthrough](02-codeagent-walkthrough.md) | 8 幕剧本的差异维度索引 |
| **概念** [tools-are-python-callables](../../02-concepts/tools-are-python-callables.md) | §5 "工具本质都是 Python callable" 的实证 |

---

## 自检（学完本笔记应能）

- [ ] 不看笔记默写 3 个根本差异（system_prompt / LLM 输出形态 / 执行环境）
- [ ] 解释为什么 CodeAgent 通常 1 步搞定但 ToolCallingAgent 要 4 步（追溯到根本差异 1 → JSON 结构限制）
- [ ] 一句话说出 ToolCallingAgent 和 CodeAgent 在错误处理上抛多少种异常、为什么差这么多
- [ ] 说出 state 储物柜（ToolCalling）vs 沙箱 namespace（Code）在跨步骤上的本质差异
- [ ] 解释 CodeAgent 为什么"老板对讲机只响 2 下"（少了 ToolOutput 事件，因为整段代码 1 次执行无 latency 期间）
- [ ] 用决策树回答"我这个任务选哪个 agent"
