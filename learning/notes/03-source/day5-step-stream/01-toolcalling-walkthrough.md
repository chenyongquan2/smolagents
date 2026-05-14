---
created: 2026-05-09
status: active
tags: [smolagents, agents, walkthrough, toolcallingagent, step-stream, day5, react-loop]
---

# 小组长李四的一步内部：ToolCallingAgent 单步完整剧本

> 🔬 **实证状态（2026-05-09）**：HF 暂时访问不了，主线 10 幕中有 **3 个细节是我推演而非实测**。详见 [questions.md "Day 5 待实证"](../../questions.md#-day-5-待实证hf-暂访问不了调试推迟)：① 第 2 幕 arguments 类型；② 第 4d 幕 memory_step.tool_calls 写回时机；③ 番外 3 state 储物柜闭环。**阅读时心里打个小问号**，能联网后再回头实证。
>
> 💡 **本篇定位**：[01 实现笔记](01-toolcalling-step-stream-impl.md) 是"小组长岗位的所有规章制度"（line-by-line），本篇是 **"小组长李四真的干一步给你看"**（具体演出）。
>
> **强烈建议**：第一次读 Day 5，先读 [00 mental-model 骨架](00-step-stream-role-overview.md) → 然后**直接来本篇**走一遍剧本 → 再回 01 笔记看代码细节。
>
> 配合 Day 4 [③' 项目经理张三的一天](../day4-agents/03b-run-walkthrough-leopard-demo.md) 阅读 —— **张三处理完一整天**，本篇 zoom into **张三某一步内部的小组长李四怎么干**。

---

## 这场戏的人物 & 道具

延续 Day 4 ③' 的剧组，**新增 1 个人 + 2 间储物间**：

| 角色 / 道具 | 对应代码 | 备注 |
|---|---|---|
| 老板 | 用户脚本 `agent.run(...)` | 延续 Day 4 |
| 项目经理张三 | `ToolCallingAgent` 实例 | 延续 Day 4，今天是 ToolCalling 风格 |
| ⭐ **小组长李四（新）** | `_step_stream(action_step)` | 张三派他执行"一步内部" |
| 顾问 | LLM API 服务器 + LLM 模型（Day 3）| 延续 Day 4 |
| 🆕 工具人小王 | `web_search` tool | Day 2 已认识 |
| 🆕 工具人小赵 | `final_answer` tool | 内置 tool |
| 笔记本 | `agent.memory` | 延续 Day 4 |
| 一张工作记录 | `action_step` (ActionStep) | 张三派李四前已建好（Day 4 ③ 第 3 幕）|
| 🆕 **活页夹（新）** | `memory_step.tool_calls / observations / model_output...` | 工作记录上的若干字段，李四就地写 |
| 🆕 **储物柜（新）** | `agent.state` | 跨步骤传图片/音频对象（§番外 3）|
| 老板的对讲机 | `_run_stream` yield 出去的事件流 | 老板在收（Day 4 ③''）|

## 这场戏的设定

```python
from smolagents import ToolCallingAgent, InferenceClientModel, tool

@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"Search result: Paris is 12°C right now, partly cloudy."

agent = ToolCallingAgent(
    tools=[web_search],         # final_answer 自动加（Day 4 ④ §_setup_tools）
    model=InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct"),
    max_steps=3,
    planning_interval=None,     # 不规划（简化）
    stream_outputs=False,       # 非流式（简化第 2 幕，留 §番外 4 讲流式）
)
result = agent.run("What's the weather in Paris right now? Answer in Fahrenheit.")
```

**预想中张三的两步**：

| 第几步 | 张三派李四干啥 | 李四的 5 步骨架 |
|---|---|---|
| **Step 1** | 调用 `web_search("Paris weather")` 拿气温 | 本篇主线剧本（10 幕）|
| **Step 2** | 调用 `final_answer("53.6°F")` 收尾 | §番外 1 简化版 |

> 💡 **本篇 zoom 范围 = Step 1 内部的一次 `_step_stream(action_step)` 调用**。"张三派李四" 这件事 Day 4 ③ §6 已经讲过了，本篇接力到李四接到任务那一秒。

---

## 第 0 幕 · 张三把工作记录递给李四

**李四视角**：

桌上一张半空的工作记录纸（`action_step`）。上面只填了两栏：
- `step_number = 1`
- `timing.start_time = 现在`

其他 11 栏全空。"好，我开干。"

**代码层面**：[agents.py:1276](../../../../src/smolagents/agents.py#L1276) `ToolCallingAgent._step_stream(memory_step)` 入口。`memory_step` 是张三在 [Day 4 ③ 第 3 幕](../day4-agents/03b-run-walkthrough-leopard-demo.md) 已经建好的对象引用。

**此刻状态**：

| 变量 | 值 |
|---|---|
| `memory_step.step_number` | `1` |
| `memory_step.timing.start_time` | 当前时间戳 |
| `memory_step.model_input_messages` | `None` |
| `memory_step.tool_calls` | `None` |
| `memory_step.observations` | `None` |
| ...其他 8 个字段 | 全 `None` |
| `agent.memory.steps` | `[SystemPromptStep, TaskStep]` ← 张三第 1 幕已写入 |
| `agent.state` | `{}` （储物柜空的）|

---

## 第 1 幕 · 动作 ① · 李四翻笔记本，整理给顾问看的材料

**李四视角**：

打开笔记本（`agent.memory`），里面有 2 条记录：系统提示词 + 老板那张任务通知单。我把它们**翻译成顾问看得懂的对话格式**（messages）。

翻译完拷一份留底：**原版进活页夹（给张三留快照）**，拷贝送顾问（防顾问改坏原版）。

**代码层面**（[agents.py:1284-1289](../../../../src/smolagents/agents.py#L1284)）：

```python
memory_messages = self.write_memory_to_messages()    # ← Day 4 ⑤ 的翻译机制
input_messages = memory_messages.copy()              # ⭐ 防御性 copy
memory_step.model_input_messages = input_messages    # 写进活页夹"输入材料"栏
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `memory_step.model_input_messages` | `None` | `[SYSTEM msg, USER msg]` ← 2 条消息 |

> 💡 **为什么要 `.copy()`**？回看 [01 §3](01-toolcalling-step-stream-impl.md#3-动作--read-messagesagentspy1284-1289) —— 防 callback 干预污染下次调用。这是**典型防御性编程**，平时跑不出问题，出问题就是诡异 bug。

---

## 第 2 幕 · 动作 ② · 李四打电话问顾问

**李四视角**：

把整理好的材料念给顾问听，顺便交代 3 件事：
1. "如果你说到 `Observation:` 或 `Calling tools:` 就立刻停"（stop_sequences）
2. "这是工具人小王和小赵的名片"（tools_to_call_from）
3. "等你回话"

顾问思考几秒（实际是 [Day 3](../day3-models/inference-client-model-impl.md) 的 LLM API 服务器在跑生成循环），然后回话：

> "你应该调用 `web_search`，参数是 `{"query": "Paris weather right now"}`"

顾问这次很贴心 —— **HTTP 协议里直接帮我把 tool_calls 字段填好了**，不用我从纯文本里抠。

**代码层面**（[agents.py:1291-1325](../../../../src/smolagents/agents.py#L1291)，非 stream 分支）：

```python
try:
    chat_message: ChatMessage = self.model.generate(
        input_messages,
        stop_sequences=["Observation:", "Calling tools:"],
        tools_to_call_from=self.tools_and_managed_agents,   # ⭐ [web_search, final_answer]
    )
    # Record model output
    memory_step.model_output_message = chat_message
    memory_step.model_output = chat_message.content
    memory_step.token_usage = chat_message.token_usage
except Exception as e:
    raise AgentGenerationError(f"Error while generating output:\n{e}", self.logger) from e
```

**顾问回话的 `chat_message` 长这样**：

```python
ChatMessage(
    role="assistant",
    content=None,                            # ← 没文字内容
    tool_calls=[                              # ⭐ 服务器替我解析好了
        ChatMessageToolCall(
            id="call_abc123",
            function=ChatMessageToolCallFunction(
                name="web_search",
                arguments='{"query": "Paris weather right now"}',   # JSON 字符串
            )
        )
    ],
    token_usage=TokenUsage(input_tokens=234, output_tokens=18),
)
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `memory_step.model_output_message` | `None` | 完整 `ChatMessage` |
| `memory_step.model_output` | `None` | `None`（因为 content 为 None；如果是文本回话才有）|
| `memory_step.token_usage` | `None` | `TokenUsage(input=234, output=18)` |

**Yield 出去什么？** 非 stream 模式，**这一幕李四不 yield**。老板对讲机静默。

> 💡 **stream 模式下这一幕会持续 yield N 个 `ChatMessageStreamDelta`**（每 token 一个），老板对讲机会响 N 次。详见 §番外 4。

---

## 第 3 幕 · 动作 ③ · 李四读懂顾问的回话

**李四视角**：

顾问回话的 `tool_calls` 字段非空（服务器已解析）—— 走优先分支，**跳过 fallback regex 抠取**。但 `arguments` 字段是字符串（`'{"query": "Paris weather right now"}'`），我得把它转成 dict 才能解包传给小王。

**代码层面**（[agents.py:1327-1334](../../../../src/smolagents/agents.py#L1327)）：

```python
if chat_message.tool_calls is None or len(chat_message.tool_calls) == 0:
    # fallback：从文本 regex 抠 —— 这次没走
    try:
        chat_message = self.model.parse_tool_calls(chat_message)
    except Exception as e:
        raise AgentParsingError(...)
else:
    # 优先分支：tool_calls 已经在
    for tool_call in chat_message.tool_calls:
        tool_call.function.arguments = parse_json_if_needed(tool_call.function.arguments)
        #   ↑ '{"query": "..."}'  →  {"query": "..."}
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `chat_message.tool_calls[0].function.arguments` | `'{"query": "Paris weather right now"}'` (str) | `{"query": "Paris weather right now"}` (dict) |

> 💡 **如果顾问回话格式不规范**（比如只有 content 没 tool_calls）：走 fallback `parse_tool_calls` 从文本里 regex 抠。**还失败**：抛 `AgentParsingError` → 写进 `action_step.error` → Day 4 ③ §⭐ 错误处理 3 层中的"ReAct 反馈信号"层 → 下轮 LLM 自己看到错误改格式。

---

## 第 4 幕 · 动作 ④ · 李四派工具人干活（核心戏！）

这一幕里李四调 `process_tool_calls`（[1361-1442](../../../../src/smolagents/agents.py#L1361)），它内部分**两阶段**：

### 第 4a 幕 · 阶段 A：先把所有差事念出来（执行前预告）

**李四视角**：

我把顾问列的 tool_calls 一个个**先大声念一遍**（"我要调 web_search，参数是 ..."），让老板的对讲机先收到"即将调用"信号。**还没真调用**。

这次只有 1 个 tool_call（单 web_search），所以念 1 次。如果顾问让调 3 个，我会念 3 次（参考 §番外 2 并行）。

**代码层面**（[agents.py:1373-1380](../../../../src/smolagents/agents.py#L1373)）：

```python
parallel_calls: dict[str, ToolCall] = {}
for chat_tool_call in chat_message.tool_calls:
    tool_call = ToolCall(
        name=chat_tool_call.function.name,           # "web_search"
        arguments=chat_tool_call.function.arguments, # {"query": "Paris weather right now"}
        id=chat_tool_call.id,                        # "call_abc123"
    )
    yield tool_call                                  # ⭐ 阶段 A：先预告
    parallel_calls[tool_call.id] = tool_call         # 攒着等阶段 B 执行
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `parallel_calls` | `{}` | `{"call_abc123": ToolCall("web_search", {...})}` |
| **Yield 出去** | — | `ToolCall(name="web_search", arguments={...}, id="...")` ⭐ 老板对讲机响了 |

> 💡 **阶段 A 为什么先 yield 全部预告**？回看 [01 §6.1](01-toolcalling-step-stream-impl.md#61--process_tool_callsagentspy1361-1442的两阶段-yield) —— 让 Web UI 立即显示"loading 中：正在调 web_search…"占位符。如果合并到阶段 B（执行完才 yield）就丢失了 latency 期间的状态。

### 第 4b 幕 · 阶段 B · 派人执行：execute_tool_call 的 4 个动作

**李四视角**：

只有 1 个差事，不开线程池（避免开销）—— 直接顺序跑。我去找工具人小王干活。但**真把活塞给小王前我得做 4 件事**：

**① 查名片夹**：小王（`web_search`）在我的工具人花名册里吗？在。
**② 储物柜替换**：顾问给的参数 `{"query": "Paris weather right now"}`，"query" 这个值是字符串 `"Paris weather right now"` —— **储物柜 `agent.state` 里有这个 key 吗**？没有 → 不替换。
**③ 上岗质检**：参数符合小王名片上写的 `query: str` 形状吗？符合（Day 2 ② [出岗质检](../day2-tools/tool-lifecycle-checks-mental-model.md) 第二次）。
**④ 真调用**：`web_search(query="Paris weather right now", sanitize_inputs_outputs=True)`。

**代码层面**（[agents.py:1453-1502 execute_tool_call](../../../../src/smolagents/agents.py#L1453)）：

```python
def execute_tool_call(self, tool_name, arguments):
    # ① 查名
    available_tools = {**self.tools, **self.managed_agents}
    if tool_name not in available_tools:
        raise AgentToolExecutionError(f"Unknown tool {tool_name}...")
    
    # ② state 替换 + 标记 managed_agent
    tool = available_tools[tool_name]
    arguments = self._substitute_state_variables(arguments)
    is_managed_agent = tool_name in self.managed_agents
    
    # ③ 上岗质检
    try:
        validate_tool_arguments(tool, arguments)
    except (ValueError, TypeError) as e:
        raise AgentToolCallError(str(e), self.logger) from e
    
    # ④ 真调用
    try:
        if isinstance(arguments, dict):
            return tool(**arguments) if is_managed_agent else tool(**arguments, sanitize_inputs_outputs=True)
        else:
            return tool(arguments) if is_managed_agent else tool(arguments, sanitize_inputs_outputs=True)
    except Exception as e:
        raise AgentToolExecutionError(error_msg, self.logger) from e
```

**小王干完，返回**：`"Search result: Paris is 12°C right now, partly cloudy."`

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `tool_call_result` | — | `"Search result: Paris is 12°C ..."` |

### 第 4c 幕 · 阶段 B · 把执行结果包成 ToolOutput 反馈

**李四视角**：

拿到小王的返回值，包装成"反馈卡"（`ToolOutput`），念给老板对讲机听。

**代码层面**（[agents.py:1391-1414 process_single_tool_call](../../../../src/smolagents/agents.py#L1391)）：

```python
tool_call_result = self.execute_tool_call(tool_name, tool_arguments)  # ← 上一幕
tool_call_result_type = type(tool_call_result)

if tool_call_result_type in [AgentImage, AgentAudio]:
    # 二进制对象：存进储物柜（§番外 3）
    ...
else:
    observation = str(tool_call_result).strip()

is_final_answer = tool_name == "final_answer"   # ⭐ 仅凭 tool 名检测（不是 web_search）

return ToolOutput(
    id=tool_call.id,
    output=tool_call_result,                    # "Search result: Paris is 12°C ..."
    is_final_answer=is_final_answer,            # False
    observation=observation,
    tool_call=tool_call,
)
```

回到 process_tool_calls 主体（[1418-1423](../../../../src/smolagents/agents.py#L1418)）：

```python
if len(parallel_calls) == 1:
    tool_call = list(parallel_calls.values())[0]
    tool_output = process_single_tool_call(tool_call)
    outputs[tool_output.id] = tool_output
    yield tool_output                           # ⭐ 阶段 B：反馈
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `outputs` | `{}` | `{"call_abc123": ToolOutput(...)}` |
| **Yield 出去** | — | `ToolOutput(output="Search result...", is_final_answer=False)` ⭐ 老板对讲机响了 |

### 第 4d 幕 · 阶段 B · 把执行结果写进活页夹（持久化）

**李四视角**：

老板对讲机已经收到反馈了，**但活页夹（memory_step）还没更新** —— 现在是写回笔记本的时候。

**代码层面**（[agents.py:1436-1442](../../../../src/smolagents/agents.py#L1436)）：

```python
memory_step.tool_calls = [parallel_calls[k] for k in sorted(parallel_calls.keys())]
memory_step.observations = memory_step.observations or ""
for tool_output in [outputs[k] for k in sorted(outputs.keys())]:
    memory_step.observations += tool_output.observation + "\n"
memory_step.observations = memory_step.observations.rstrip("\n") if memory_step.observations else memory_step.observations
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `memory_step.tool_calls` | `None` | `[ToolCall("web_search", {...}, id="call_abc123")]` |
| `memory_step.observations` | `None` | `"Search result: Paris is 12°C right now, partly cloudy."` |

> 💡 **为什么按 `sorted(keys())` 写回**？因为 ThreadPoolExecutor 并行时（§番外 2），`outputs` 里 ToolOutput 的顺序是"谁先完先填"，不一定等于"原始 tool_calls 顺序"。**按 id 排序**让 memory 里的顺序**确定**，保证 replay 行为可重现。

---

## 第 5 幕 · 动作 ⑤ · 李四交差

**李四视角**：

5 步全干完了。最后再喊一句"工作交付！" —— `ActionOutput` —— 让老板对讲机收到"这一步结束了"信号。然后我下班。

**代码层面**（[agents.py:1335-1359 主体收尾](../../../../src/smolagents/agents.py#L1335)）：

```python
final_answer, got_final_answer = None, False
for output in self.process_tool_calls(chat_message, memory_step):
    yield output                                      # 透传第 4a/c 幕的 yield
    if isinstance(output, ToolOutput):
        if output.is_final_answer:                    # ← False（不是 final_answer）
            ...                                       # 不进
            
yield ActionOutput(
    output=final_answer,            # None（不是 final_answer 的 step）
    is_final_answer=got_final_answer, # False
)
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| **Yield 出去** | — | `ActionOutput(output=None, is_final_answer=False)` ⭐ 最后一响 |

**李四下班。控制权交回张三。** 张三看到 `is_final_answer=False`，知道还没拿到答案 → `step_number += 1` → 派李四再来一次 Step 2。

---

## 🎬 一图压缩：Step 1 的 10 个变化点

```
进入 _step_stream(action_step):
  ┌──────────────────────────────────────────────────────────┐
  │ 第 0 幕 │ action_step 出生：step_number=1, 其他 None      │
  ├──────────────────────────────────────────────────────────┤
  │ 第 1 幕 │ ↓ memory_step.model_input_messages = [SYS, USER]│
  ├──────────────────────────────────────────────────────────┤
  │ 第 2 幕 │ ↓ memory_step.model_output_message = ChatMessage│
  │         │ ↓ memory_step.token_usage = TokenUsage(234, 18) │
  ├──────────────────────────────────────────────────────────┤
  │ 第 3 幕 │ ↓ chat_message.tool_calls[0].arguments → dict   │
  ├──────────────────────────────────────────────────────────┤
  │ 第 4a 幕│ ⭐ yield ToolCall("web_search", {...})          │
  │ 第 4b 幕│ ↓ execute_tool_call: 查名+state+质检+调用       │
  │ 第 4c 幕│ ⭐ yield ToolOutput(output="12°C...", is_final=F)│
  │ 第 4d 幕│ ↓ memory_step.tool_calls = [...]                │
  │         │ ↓ memory_step.observations = "12°C..."          │
  ├──────────────────────────────────────────────────────────┤
  │ 第 5 幕 │ ⭐ yield ActionOutput(None, is_final=False)     │
  └──────────────────────────────────────────────────────────┘
退出 _step_stream（generator 终止）
```

**老板对讲机这一步总共响了 3 下**：`ToolCall` → `ToolOutput` → `ActionOutput`。
**笔记本活页夹被写了 6 个字段**：`model_input_messages` / `model_output_message` / `model_output` / `token_usage` / `tool_calls` / `observations`。

---

## 🌟 番外篇 1 · final_answer 特判（Step 2 简化版）

Step 2 的 `_step_stream` 重复 Step 1 的 5 步骨架，**唯一不同**在第 4c 幕的 `is_final_answer` 检测：

```python
is_final_answer = tool_name == "final_answer"   # ← True 了
```

**第 5 幕收尾**会走完整的 final_answer 处理（[agents.py:1338-1355](../../../../src/smolagents/agents.py#L1338)）：

```python
for output in self.process_tool_calls(chat_message, memory_step):
    yield output
    if isinstance(output, ToolOutput):
        if output.is_final_answer:                    # ← True
            if len(chat_message.tool_calls) > 1:
                raise AgentExecutionError("...")      # ⚠️ 防御：不许混调其他 tool
            if got_final_answer:
                raise AgentToolExecutionError("...")  # ⚠️ 防御：不许重复 final
            final_answer = output.output              # "53.6°F"
            got_final_answer = True
            # state 替换：如果 final_answer 是 state key 字符串，取出真对象
            if isinstance(final_answer, str) and final_answer in self.state.keys():
                final_answer = self.state[final_answer]

yield ActionOutput(
    output=final_answer,            # ⭐ "53.6°F"
    is_final_answer=True,           # ⭐ True
)
```

**张三收到 `is_final_answer=True`** → `returned_final_answer = True` → Day 4 ③ §RunResult 收尾 → 老板拿到结果。

---

## 🌟 番外篇 2 · 并行多 tool call（ThreadPoolExecutor + copy_context）

**新场景**：顾问回话 `tool_calls = [web_search("Paris"), web_search("Tokyo")]` —— 想并行搜两个城市。

**第 4a 幕变化**（先全部预告）：

```python
yield ToolCall("web_search", {"query": "Paris weather"}, id="call_abc")
yield ToolCall("web_search", {"query": "Tokyo weather"}, id="call_def")
# parallel_calls = {"call_abc": ..., "call_def": ...}
```

**第 4b/c 幕变化**（走 else 分支：[agents.py:1424-1434](../../../../src/smolagents/agents.py#L1424)）：

```python
else:
    # If multiple tool calls, process them in parallel
    with ThreadPoolExecutor(self.max_tool_threads) as executor:
        futures = []
        for tool_call in parallel_calls.values():
            ctx = copy_context()                        # ⭐ contextvars 隔离
            futures.append(executor.submit(ctx.run, process_single_tool_call, tool_call))
        for future in as_completed(futures):            # ⭐ 谁先完先 yield
            tool_output = future.result()
            outputs[tool_output.id] = tool_output
            yield tool_output
```

**老板对讲机收到的顺序可能是**：

```
ToolCall(Paris)         ← 第 4a 幕 i=0
ToolCall(Tokyo)         ← 第 4a 幕 i=1
ToolOutput(Tokyo)       ← Tokyo 服务器快，先返回
ToolOutput(Paris)       ← Paris 服务器慢，后返回
ActionOutput(None, F)
```

**但 memory 里**写入 `tool_calls` 和 `observations` 按 `sorted(keys())` —— 顺序确定（call_abc 在 call_def 前）—— 不受谁先完影响。

> 💡 **`copy_context()` 是什么**？Python 3.7+ `contextvars`（线程/协程隔离的全局状态）。如果不 copy，多个线程共用一份 context，并发覆盖 → 比如日志的 `trace_id` 会乱串。`ctx.run(fn, ...)` 在该子线程的 context 副本下跑函数。
>
> 💡 **为什么是 `as_completed` 而不是 `executor.map`**？前者**谁先完先 yield**（流式反馈，UI 早响应）；后者要等全部完成才返回（批处理）。这就是 §"两阶段 yield 设计意图"里"流式优先"哲学的延续。

> 💡 **`max_tool_threads=None` 的默认行为**：`ThreadPoolExecutor(None)` 等价于 `ThreadPoolExecutor(min(32, os.cpu_count() + 4))` —— Python 标准库的合理默认。IO bound（HTTP 请求）32 并发是好的；CPU bound 可能要手动调小。

---

## 🌟 番外篇 3 · state 储物柜机制（跨步骤传图片）

**场景**：tool 返回 PIL.Image 对象，LLM 下一轮想用这张图。

**Step N 的第 4c 幕**（[agents.py:1392-1399](../../../../src/smolagents/agents.py#L1392)）：

```python
if tool_call_result_type in [AgentImage, AgentAudio]:
    if tool_call_result_type == AgentImage:
        observation_name = "image.png"
    elif tool_call_result_type == AgentAudio:
        observation_name = "audio.mp3"
    self.state[observation_name] = tool_call_result    # ⭐ 存进储物柜
    observation = f"Stored '{observation_name}' in memory."
```

`observation` 字符串就是 `"Stored 'image.png' in memory."`，**写进 memory_step.observations**，下一轮 LLM 看 messages 时会看到这句话。

**Step N+1 的第 4b 幕**（[agents.py:1444-1451 _substitute_state_variables](../../../../src/smolagents/agents.py#L1444)）：

LLM 输出 `{"image_path": "image.png"}` → 进 `execute_tool_call` 第 ② 步 state 替换：

```python
def _substitute_state_variables(self, arguments):
    if isinstance(arguments, dict):
        return {
            key: self.state.get(value, value) if isinstance(value, str) else value
            for key, value in arguments.items()
        }
    return arguments
```

`self.state.get("image.png", "image.png")` 命中 → 返回 PIL.Image 对象 → 真传给 tool。

**循环闭合**：tool 返回 → 存 state → LLM 描述 → 下一步替换回真对象 → 下个 tool 拿到真对象。

---

## 🌟 番外篇 4 · stream_outputs=True 时的第 2 幕

**第 2 幕变化**（[agents.py:1292-1307](../../../../src/smolagents/agents.py#L1292)）：

```python
output_stream = self.model.generate_stream(
    input_messages,
    stop_sequences=["Observation:", "Calling tools:"],
    tools_to_call_from=self.tools_and_managed_agents,
)
chat_message_stream_deltas: list[ChatMessageStreamDelta] = []
with Live("", console=self.logger.console, vertical_overflow="visible") as live:
    for event in output_stream:                          # ← 顾问一个 token 一个 token 回话
        chat_message_stream_deltas.append(event)
        live.update(Markdown(agglomerate_stream_deltas(chat_message_stream_deltas).render_as_markdown()))
        yield event                                       # ⭐ 老板对讲机每 token 响一下
chat_message = agglomerate_stream_deltas(chat_message_stream_deltas)
```

**老板对讲机这一步响的次数**：N+3（N 个 ChatMessageStreamDelta + 1 ToolCall + 1 ToolOutput + 1 ActionOutput）

实战场景：Web UI 用 N 个 delta 实时渲染 LLM 思考过程（呼应 Day 4 ③''' 实战选型）。

---

## 🌟 番外篇 5 · 两阶段 yield 的设计意图（为什么不合并）

第 4a 幕（yield ToolCall）和第 4c 幕（yield ToolOutput）**完全可以合并**成"执行完一个就 yield 整套"，比如：

```python
# 假想的"合并版"
for tc in chat_message.tool_calls:
    result = execute(tc)
    yield (ToolCall, ToolOutput)  # 一次 yield 整套
```

**为什么不这样做**？呼应 Day 4 ③'''' [设计哲学笔记](../day4-agents/03e-stream-event-design-philosophy.md)：**前置意图 vs 后置反馈是两条独立信号**。

| 时机 | 老板对讲机收到 | Web UI 能做什么 |
|---|---|---|
| 第 4a 幕（执行前） | ToolCall("web_search", {...}) | 立即显示 **"正在搜索 Paris…"** 转圈 loading 状态 |
| 第 4b 幕（执行中） | — | 转圈持续中 |
| 第 4c 幕（执行后） | ToolOutput(...) | 替换 loading 为实际结果 |

如果合并 → 用户在 4a-4c 期间（可能数秒）**完全不知道发生了什么** —— Web UI 看起来卡死。这就是为什么 ChatGPT / Claude 等 UI 都会先显示"🔍 Searching the web..."占位符再渲染结果。

**这是流式 UI 的通用设计模式**，不是 smolagents 独创。

---

## 老板视角事件序列（呼应 Day 4 ③'）

`agent.run(stream=True, ...)` 模式下，老板 for 循环里**这一步**收到的事件顺序：

```
# Step 1
ChatMessageStreamDelta × N    （只在 stream_outputs=True）
ToolCall                       （第 4a 幕：执行前预告）
ToolOutput                     （第 4c 幕：执行后反馈）
ActionOutput(is_final=False)   （第 5 幕：交差）
ActionStep                     ← Day 4 外层 _run_stream yield（step 结束档案）

# Step 2
ChatMessageStreamDelta × M    （只在 stream_outputs=True）
ToolCall(final_answer)         （第 4a 幕）
ToolOutput(is_final=True)      （第 4c 幕）
ActionOutput("53.6°F", True)   （第 5 幕收尾）
ActionStep                     ← Day 4 外层 yield
FinalAnswerStep("53.6°F")      ← Day 4 外层 yield（任务终结）
```

---

## 单步调试断点对照表

跑 [compare_agents.py](../../../scripts/compare_agents.py) ToolCallingAgent 部分，每个断点应命中**哪一幕**：

| 断点位置 | 应命中哪一幕 | Watch |
|---|---|---|
| [agents.py:1284](../../../../src/smolagents/agents.py#L1284) | **第 1 幕**（写 model_input_messages 前）| `memory_step.model_input_messages` (None → list) |
| [agents.py:1320](../../../../src/smolagents/agents.py#L1320) | **第 2 幕末**（写 model_output_message 后）| `chat_message.tool_calls` |
| [agents.py:1336](../../../../src/smolagents/agents.py#L1336) | **第 4 幕前**（进 process_tool_calls 前）| — |
| [agents.py:1379](../../../../src/smolagents/agents.py#L1379) | **第 4a 幕**（每个 ToolCall yield 前）| `parallel_calls` 累积 |
| [agents.py:1390](../../../../src/smolagents/agents.py#L1390) | **第 4b 幕**（execute_tool_call 入口）| `tool_arguments` 替换前 |
| [agents.py:1423](../../../../src/smolagents/agents.py#L1423) | **第 4c 幕**（ToolOutput yield）| `tool_output` |
| [agents.py:1436](../../../../src/smolagents/agents.py#L1436) | **第 4d 幕**（写 memory_step.tool_calls 那一刻）| `memory_step.tool_calls` (None → list) |
| [agents.py:1356](../../../../src/smolagents/agents.py#L1356) | **第 5 幕**（yield ActionOutput）| `final_answer`, `got_final_answer` |

---

## 📋 附录 A · 项目经理张三的 3 个怪癖（ToolCallingAgent 类构造）

张三是 `ToolCallingAgent` 实例。除了 [Day 4 ④ init-setup-flow](../day4-agents/04-init-setup-flow.md) 已经讲的基类 `__init__` 13 件事，张三**自己**还有 3 个特殊设置（[agents.py:1231-1274](../../../../src/smolagents/agents.py#L1231)）：

### 怪癖 1：默认从 `toolcalling_agent.yaml` 读 prompt 模板

```python
prompt_templates = prompt_templates or yaml.safe_load(...toolcalling_agent.yaml...)
```

—— Day 1 [planning-mechanics](../day1-memory/planning-mechanics.md) 已经看过的"YAML 模板填空机"。**用户没传 prompt_templates 就用默认的**。

### 怪癖 2：实例化时校验 `stream_outputs` 是否可行

```python
self.stream_outputs = stream_outputs
if self.stream_outputs and not hasattr(self.model, "generate_stream"):
    raise ValueError("`stream_outputs` is set to True, but the model class implements no `generate_stream` method.")
```

—— Day 2 ② "出厂质检" 思想：**早暴露错误**。用户实例化时就崩，不要等到第 2 幕调 LLM 才报"AttributeError: no attribute 'generate_stream'"。

### 怪癖 3：`tools_and_managed_agents` 属性，给第 2 幕用

```python
@property
def tools_and_managed_agents(self):
    return list(self.tools.values()) + list(self.managed_agents.values())
```

—— 第 2 幕把这个 list 传给 `tools_to_call_from`，让 LLM API 服务器拼 HTTP `tools` JSON。**为什么不缓存**？因为 tools / managed_agents 都是 dict（运行时可能被改），每次重新拼是安全做法。

### 怪癖 4：`initialize_system_prompt`（基类 `@abstractmethod` 硬约束实证）

```python
def initialize_system_prompt(self) -> str:
    system_prompt = populate_template(
        self.prompt_templates["system_prompt"],
        variables={"tools": self.tools, "managed_agents": self.managed_agents,
                   "custom_instructions": self.instructions},
    )
    return system_prompt
```

—— 这是 [Day 4 self-check Q11](../day4-agents/self-check.md) 实证的 `@abstractmethod` 硬约束 —— 基类强制子类实现。把 prompt template 里 `{{tools}}` `{{managed_agents}}` 占位符填进去。Day 2 [tool-schema-rendering](../day2-tools/tool-schema-rendering-mental-model.md) 4 种渲染中"prompt 文字"那一种就在这里渲染（`tool.to_tool_calling_prompt` 间接被 yaml 模板调用）。

---

## ❓ FAQ：5 个新手常问

### Q1：为什么 fallback `parse_tool_calls` 在 model 而不在 agent？

A：因为不同 provider 的 fallback 格式可能不同（OpenAI 用 `<|tool_call|>` 包裹，Anthropic 用别的）。让 model 类做 provider 适配是 Day 3 [model-class-role-overview](../day3-models/model-class-role-overview.md) 的"调用渠道抽象"职责。

### Q2：`process_tool_calls` 是 generator，但又 in-place 修改 memory_step。这设计奇怪吗？

A：不奇怪 —— Generator 边 yield 事件边写 memory 是 smolagents 的核心设计模式（Day 4 ⑤ "双通道" / 持久化 vs 事件）。yield 给消费者实时反馈；memory 累积持久化档案。两者解耦，互不干扰。

### Q3：`max_tool_threads=None` 的默认行为？

A：`ThreadPoolExecutor(None)` 等价于 `ThreadPoolExecutor(min(32, os.cpu_count() + 4))` —— Python 标准库的合理默认。IO bound（HTTP 请求）32 并发是好的；CPU bound 可能要手动调小。

### Q4：multi-agent 场景，managed_agent 也走这条路径？

A：是。`available_tools = {**self.tools, **self.managed_agents}` —— managed_agent 在调用上和 tool 长得一样（都被 `tool(**args)` 调用），只是不传 `sanitize_inputs_outputs=True`。这是 Day 4 ④ init 里给 managed_agent 设 `inputs/output_type` 的目的：让它 quack like a tool。

### Q5：为什么 "多个 final_answer" 防御要 raise，不是 warning？

A：因为 LLM 同一轮返回 2 个 final 是逻辑混乱信号（不知道哪个是真答案），让 ReAct 反馈让 LLM 自己改。`AgentToolExecutionError` 是 `AgentError` 子类（记 step 写进下轮 messages），不是冲出外层崩。

---

## 🔗 跟 Day 1-4 + Week 1 的闭环回收 8 处

| 上游 | 闭环点 |
|---|---|
| **Day 1** [action-step-anatomy](../day1-memory/action-step-anatomy.md) | 13 字段中 6 个被 ToolCallingAgent 直接写：model_input_messages / model_output_message / model_output / token_usage / tool_calls / observations |
| **Day 2** [tool-lifecycle-checks](../day2-tools/tool-lifecycle-checks-mental-model.md) | 第 4b 幕第 ③ 步 `validate_tool_arguments`（第二次上岗质检）|
| **Day 2** [tool-schema-rendering](../day2-tools/tool-schema-rendering-mental-model.md) | 第 2 幕 `tools_to_call_from` 走 HTTP `tools` JSON；附录 A 怪癖 4 `system_prompt` 走 prompt 文字渲染 |
| **Day 3** [model-generate-mental-model](../day3-models/model-generate-mental-model.md) | 第 2 幕入口 |
| **Day 3** [model-stop-sequences](../day3-models/model-stop-sequences.md) | 第 3 幕 fallback `parse_tool_calls` 是为协议碎片化兜底（reasoning 模型不支持 tools 字段）|
| **Day 4 ③** [agent-run-mental-model](../day4-agents/03-run-mental-model.md) | 第 2 幕 `AgentGenerationError` 立即抛 / 第 3 幕 `AgentParsingError` 记 step；`action_output` 由外层而非 _step_stream 写 |
| **Day 4 ③''** [stream-event-types](../day4-agents/03c-stream-event-types.md) | 番外 5 两阶段 yield (ToolCall vs ToolOutput) 的设计意义 |
| **Day 4 ④** [init-setup-flow](../day4-agents/04-init-setup-flow.md) | 附录 A 怪癖 2 stream_outputs 校验时机；第 4c 幕 `final_answer` 兜底注册的为什么 |
| **Week 1** [codeagent-vs-toolcallingagent](../../02-concepts/codeagent-vs-toolcallingagent.md) | "动作格式 = JSON" 的实现层落地 |

---

## 关联阅读

- 上游骨架：[00-step-stream-role-overview.md](00-step-stream-role-overview.md) — 5 步 mental model
- 对照阅读：[02-codeagent-walkthrough.md](02-codeagent-walkthrough.md) — CodeAgent 单步剧本（同一任务，不同活法）
- Day 4 同源模板：[③' agent-run-walkthrough-leopard-demo.md](../day4-agents/03b-run-walkthrough-leopard-demo.md) — 张三的一天（zoom out 一层）
- 上游事件类型：[Day 4 ③'' agents-stream-event-types.md](../day4-agents/03c-stream-event-types.md) — ToolCall / ToolOutput / ActionOutput 分别长啥样

---

## 自检（学完本篇应能）

- [ ] 不看笔记默讲 Step 1 的 10 个变化点（第 0 → 第 5 幕）
- [ ] 解释为什么 `ToolCall` 在第 4a 幕 yield，`ToolOutput` 要等到第 4c 幕（番外 5）
- [ ] 解释为什么 `memory_step.tool_calls` 在第 4d 幕才写，不是第 4a 幕
- [ ] 说出 stream_outputs=True 时第 2 幕会发生什么变化
- [ ] 描述并行多 tool call 时老板对讲机的事件顺序（结合 §番外 2）
- [ ] 描述 state 储物柜在跨步骤传图片的两步交接（结合 §番外 3）
- [ ] 说出 ToolCallingAgent 类构造的 3 个怪癖（附录 A）
- [ ] 回答 5 个 FAQ 中的 3 个
