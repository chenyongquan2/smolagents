---
created: 2026-05-03
status: active
tags: [action-step, react, source-reading, summary-mode, week2-day1]
---

# ActionStep 解剖：ReAct 一步的"完整黑匣子"

## 背景 / 动机

Day 1 阶段 2.6。ActionStep 是 [memory.py](../../../../src/smolagents/memory.py) 里**最核心**的 Step 类，前面 5 个 Step 类（[memory-data-structures.md](memory-data-structures.md) + [planning-mechanics.md](planning-mechanics.md)）都是为它热身。

由于内容多（13 字段 + 5 分支 `to_messages()` + 重写 `dict()`），单独成文。

---

## 一、为什么这是 memory.py 的核心

| 维度 | ActionStep | 其他 Step 类 |
|---|---|---|
| 字段数量 | **13 个** | 1-5 个 |
| 出现频率 | **占 `memory.steps` 大半** | 出现 0-N 次不等 |
| `to_messages()` 分支 | **5 个** | 1-2 个 |
| `step_number` 来源 | **唯一**会让计数器递增的 step 类型 | 不递增 |

> 💡 **一句话定位**：ActionStep 是 ReAct 一轮"思考-行动-观察"的**完整录像**。13 个字段记录从"输入什么 messages"→"LLM 输出什么"→"工具执行什么"→"产出什么"全流程。

---

## 二、13 个字段：按 4 个阶段分组

源码 [memory.py:50-64](../../../../src/smolagents/memory.py:50)：

```python
@dataclass
class ActionStep(MemoryStep):
    step_number: int                                          # 元数据
    timing: Timing                                            # 元数据
    model_input_messages: list[ChatMessage] | None = None     # 输入
    tool_calls: list[ToolCall] | None = None                  # 模型输出
    error: AgentError | None = None                           # 执行
    model_output_message: ChatMessage | None = None           # 模型输出
    model_output: str | list[dict[str, Any]] | None = None    # 模型输出
    code_action: str | None = None                            # 模型输出
    observations: str | None = None                           # 执行
    observations_images: list["PIL.Image.Image"] | None = None # 执行
    action_output: Any = None                                  # 执行
    token_usage: TokenUsage | None = None                     # 元数据
    is_final_answer: bool = False                             # 元数据
```

### 4 阶段分组（强烈建议这样记）

| 阶段 | 字段 | 含义 |
|---|---|---|
| 📥 **输入侧 (1)** | `model_input_messages` | 这次发给 LLM 的完整 messages 历史（留档/调试黄金）|
| 🧠 **模型输出侧 (4)** | `model_output_message` | LLM 返回的**原始 ChatMessage 对象**（含完整嵌套结构）|
| | `model_output` | 提取出来的**纯文本输出**（LLM 的"思考"内容）|
| | `tool_calls` | 提取出来的 **`ToolCall` 列表**（如果 LLM 决定调工具）|
| | `code_action` | 提取出来的 **Python 代码字符串**（CodeAgent 用，ToolCallingAgent 不用）|
| ⚙️ **执行侧 (4)** | `observations` | 工具/代码执行后的**文本结果**（"巴黎温度 20°C"）|
| | `observations_images` | 执行产出的图片（多模态场景）|
| | `action_output` | 执行的最终输出值（用于传后续步骤或 final_answer）|
| | `error` | 执行失败时的 `AgentError` 对象 |
| 📊 **元数据 (4)** | `step_number` | 这是第几个 ActionStep（**唯一递增此计数器的 Step 类型**）|
| | `timing` | 本步耗时 |
| | `token_usage` | 本步 token 用量 |
| | `is_final_answer` | 这一步是否为 `final_answer` 调用 |

### `model_output_message` vs `model_output` —— 看起来重复，为何都要保留？

| | 类型 | 用途 |
|---|---|---|
| `model_output_message` | `ChatMessage` 对象 | **精确还原** —— replay/debug 时要看完整结构 |
| `model_output` | `str` 或 `list[dict]` | **喂回 messages 历史** —— `to_messages()` 直接拿它当 ASSISTANT 内容 |

→ 冗余存储 = 一份给机器精确还原，一份给下游消费。

### CodeAgent vs ToolCallingAgent 字段使用差异

| 字段 | CodeAgent | ToolCallingAgent |
|---|---|---|
| 通用 11 字段（step_number / timing / model_input_messages / model_output_message / model_output / token_usage / observations / observations_images / action_output / error / is_final_answer）| ✅ 都用 | ✅ 都用 |
| `tool_calls` | ✅ **填 1 个合成** `ToolCall(name="python_interpreter", arguments=<code>)`（[agents.py:1716-1722](../../../../src/smolagents/agents.py:1716)） | ✅ 填 LLM 输出的真实 tool_calls 列表 |
| `code_action` | ✅ **独占**（实际 Python 代码字符串）| ❌ 永远 None |

> 💡 **设计精髓**：**只有 `code_action` 是 CodeAgent 独占字段**。`tool_calls` 是**两种 agent 共用** —— CodeAgent 把代码包装成"python_interpreter"合成工具，让 replay / log / dict() 序列化机制对两种 agent 统一。这是 OOP 多态的实战：复用抽象而非为新 agent 单独搞一套字段。

---

## 三、`to_messages()` 的 5 个分支（[memory.py:92-150](../../../../src/smolagents/memory.py:92)）

```python
def to_messages(self, summary_mode: bool = False) -> list[ChatMessage]:
    messages = []

    # 分支 ①：model_output → ASSISTANT 消息（"我刚才在想什么"）
    if self.model_output is not None and not summary_mode:    # ⭐ 唯一响应 summary_mode 的分支
        messages.append(ChatMessage(role=ASSISTANT, ...))

    # 分支 ②：tool_calls → TOOL_CALL 消息（"我决定调这些工具"）
    if self.tool_calls is not None:
        messages.append(ChatMessage(role=TOOL_CALL,
            content=[{"type":"text", "text": "Calling tools:\n" + str(...)}]))

    # 分支 ③：observations_images → USER 消息（多模态执行结果）
    if self.observations_images:
        messages.append(ChatMessage(role=USER, content=[{"type":"image", "image": img}]))

    # 分支 ④：observations → TOOL_RESPONSE 消息（"工具返回了什么"）
    if self.observations is not None:
        messages.append(ChatMessage(role=TOOL_RESPONSE,
            content=[{"type":"text", "text": f"Observation:\n{self.observations}"}]))

    # 分支 ⑤：error → TOOL_RESPONSE 消息（"出错了，记得换思路"）
    if self.error is not None:
        error_message = "Error:\n" + str(self.error) + "\nNow let's retry: ..."
        messages.append(ChatMessage(role=TOOL_RESPONSE, ...))

    return messages
```

→ 单个 ActionStep 可产出 **0-5 条 messages**（按字段填充情况）。

### ⭐⭐ 设计精髓：只有 `model_output` 响应 `summary_mode`

| 分支 | 响应 summary_mode？ | 理由 |
|---|---|---|
| ① model_output（LLM 思考文本）| ✅ **隐身** | **主观"想法"**，是 anchor 风险（让 LLM 看到自己之前的想法会被绑架）|
| ② tool_calls | ❌ 永远输出 | **客观事实**：调了什么工具 |
| ③ observations_images | ❌ 永远输出 | 客观事实：拿到了什么图 |
| ④ observations | ❌ 永远输出 | 客观事实：工具返回了什么 |
| ⑤ error | ❌ 永远输出 | 客观事实：发生了什么错误 |

> 💡 **核心洞察**：summary_mode 的过滤逻辑是 **"隐藏想法，保留事实"**。
> 与 PlanningStep 的"整体隐身"形成对比 ——
> - PlanningStep 整体是"想法"（计划 = 主观判断），所以**全部隐身**
> - ActionStep **混合了想法和事实**，所以**只藏想法那部分**

这就是 [planning-mechanics.md](planning-mechanics.md) 实验里看到的：重 plan 时 LLM 看不到旧 plan 文本，但**仍然看得到所有 observation**。机制就在这里 —— ActionStep 的**事实分支不响应 summary_mode**。

### 错误重试的"剧本提示"（分支 ⑤）

注意 error 消息的全文（[memory.py:139-145](../../../../src/smolagents/memory.py:139)）：

```python
"Error:\n" + str(self.error) +
"\nNow let's retry: take care not to repeat previous errors!
If you have retried several times, try a completely different approach.\n"
```

这又是一个**伪造的"剧本提示"**（和 PlanningStep 的 "Now proceed" 一脉相承）。当工具失败时，框架**主动塞这段话**到 messages 历史，引导 LLM 换思路而不是硬撞。

→ 进一步印证 **agent 工程精髓 = messages 操控术**。

---

## 四、`dict()` 重写（[memory.py:66-90](../../../../src/smolagents/memory.py:66)）

ActionStep 是**第二个**重写 `dict()` 的类（PlanningStep 是第一个）。原因相同：

- `model_input_messages` 是嵌套 dataclass list → 默认 `asdict()` 处理不了
- `tool_calls` 是 `list[ToolCall]` → 需要调每个 ToolCall 的 `dict()`
- `observations_images` 是 PIL Image 对象 → 用 `image.tobytes()` 序列化二进制
- `action_output` 类型 `Any` → 用 `make_json_serializable()` 兜底

**特别注意**（[memory.py:76](../../../../src/smolagents/memory.py:76)）：
```python
"tool_calls": [tc.dict() for tc in self.tool_calls] if self.tool_calls else [],
```
**空时返回 `[]` 而不是 `None`**。其他字段空时返回 `None`。

→ 这是给下游 JSON 消费方的友好处理：tool_calls 永远是数组，避免 `null vs []` 的判空麻烦。

---

## 五、🎬 Live Trace：[planning_demo.py](../../../scripts/planning_demo.py) 里的真实 ActionStep

实验输出的 `[2] ActionStep`：

```
--- [2] ActionStep (step_number=1) ---
  tool_call: get_temperature({'city': 'Beijing'})
  observations: 25.0
```

背后的字段填充：

```python
ActionStep(
    # 元数据
    step_number=1,
    timing=Timing(start_time=..., end_time=...),
    token_usage=TokenUsage(input_tokens=1448, output_tokens=18),
    is_final_answer=False,

    # 输入
    model_input_messages=[<system>, <user task>, <assistant plan>, <user "Now proceed">],

    # 模型输出
    model_output_message=<原始 ChatMessage 对象 from LLM>,
    model_output=None,                                   # ToolCallingAgent 通常没有"思考文本"
    tool_calls=[ToolCall(name="get_temperature",
                         arguments={"city": "Beijing"},
                         id="call_xxx")],
    code_action=None,                                    # 这是 ToolCallingAgent，不写代码

    # 执行
    observations="25.0",
    observations_images=None,
    action_output=25.0,
    error=None,
)
```

调 `to_messages()` 输出 **2 条 messages**（分支 ② 和 ④）：

```python
[
  ChatMessage(role=TOOL_CALL,
              content="Calling tools:\n[{'id': 'call_xxx', 'type': 'function', "
                      "'function': {'name': 'get_temperature', "
                      "'arguments': '{\"city\": \"Beijing\"}'}}]"),
  ChatMessage(role=TOOL_RESPONSE, content="Observation:\n25.0"),
]
```

→ 下次 LLM 调用时，这 2 条接在历史末尾。LLM 看到："上次我调了 get_temperature(Beijing) 拿到 25.0，接下来该做什么？"

---

## 六、🌐 把 5 个 Step 类串起来：messages 全图

Day 1 主要内容收尾时的全景：

```
agent.memory                                  → write_memory_to_messages() → 喂给 LLM
├─ system_prompt                              → SystemPromptStep.to_messages() = 1 条 SYSTEM
└─ steps[]
   ├─ TaskStep(原任务)                        → 1 条 USER
   ├─ PlanningStep(可选)                      → 2 条 (ASSISTANT plan + USER "Now proceed")
   ├─ ActionStep                              → 1-5 条 (ASSISTANT思考 + TOOL_CALL + USER图 + TOOL_RESPONSE观察 + error)
   ├─ ActionStep                              → ...
   ├─ PlanningStep(每 N 步)                   → ...（重 plan 时旧 plan 隐身）
   ├─ ActionStep                              → ...
   └─ ActionStep(is_final_answer=True)        → 循环终止
```

---

## 七、3 条核心规律（Day 1 收官）

1. **每个 Step 决定自己变成几条 messages**（多态契约）—— `MemoryStep.to_messages()` 是 1 个抽象方法，6 个子类各自实现，产出 0-5 条不等的 messages
2. **`step_number` 只在 ActionStep 上递增** —— PlanningStep / TaskStep 不递增。这就是 `planning_interval` 公式里 "step_number" 的真实含义
3. **summary_mode 隐藏"想法"，保留"事实"** —— PlanningStep 全隐身（它整体是想法），ActionStep 只藏 model_output（其他都是事实）。这是 smolagents 长上下文压缩的基础机制

---

## 相关链接

- 源码：[src/smolagents/memory.py:50-150](../../../../src/smolagents/memory.py:50)
- 关联笔记：
  - [memory-data-structures.md](memory-data-structures.md) Step 家族整体 + 4 个简单类
  - [planning-mechanics.md](planning-mechanics.md) PlanningStep 深入 + summary_mode 完整机制
  - [../02-concepts/chat-message-roles.md](../../02-concepts/chat-message-roles.md) 5 种 role 的含义

## 遗留问题

### ✅ Q1：`is_final_answer=True` 的 ActionStep 还会被 `to_messages()` 翻译吗？

**会**。源码 [agents.py:758-770](../../../../src/smolagents/agents.py:758) 的 `write_memory_to_messages` **不过滤 `is_final_answer`**，遍历所有 steps。`is_final_answer` 字段唯一作用是让 while 循环退出（[agents.py:592](../../../../src/smolagents/agents.py:592)）。

**3 种实际触发翻译的场景**：
1. **Multi-agent 中作为 sub-agent**（[agents.py:884-887](../../../../src/smolagents/agents.py:884)）—— 父 agent 用 `summary_mode=True` 翻译子 agent 的整个 memory（含 final_answer）
2. **Managed agent 跨 run 记忆继承**（[agents.py:830-832](../../../../src/smolagents/agents.py:830)）—— 上次 run 的 memory 拼到这次 run 的 prompt 里
3. **同一 agent 复用多次 run 且没 reset**：第二次 `agent.run(...)` 时第一次的全部 memory 仍在

### ✅ Q2：长上下文压缩具体怎么配合 `summary_mode`？

`summary_mode` 是 smolagents **预留的、未在主流程深度使用**的钩子。设计思路：

```python
def compress_old_steps(agent, keep_recent: int = 5):
    if len(agent.memory.steps) <= keep_recent: return

    # ① 用 summary_mode 抽取"事实视图"（自动隐藏旧 plan 和 LLM 思考文本）
    to_compress = agent.memory.steps[:-keep_recent]
    fact_messages = []
    for step in to_compress:
        fact_messages.extend(step.to_messages(summary_mode=True))

    # ② 喂给 LLM 让它写紧凑总结
    summary_text = llm.generate([SYSTEM("Summarize..."), *fact_messages]).content

    # ③ 替换前面 steps 为一个虚拟 TaskStep
    summarized = TaskStep(task=f"[Previous progress summary]\n{summary_text}")
    agent.memory.steps = [summarized] + agent.memory.steps[-keep_recent:]
```

**关键点**：
- `summary_mode=True` 自动隐藏 PlanningStep 整体 + ActionStep 的 model_output（LLM 思考），保留 tool_calls/observations/errors（事实）
- 总结输入只含**客观事实**，避免 LLM 被旧想法绑架
- smolagents 当前**没有内置压缩**，但可以通过 [`CallbackRegistry`](../../../../src/smolagents/memory.py:280) 在每个 ActionStep 后挂钩实现（Stage 4 待看）

### ⏸ 待回答的（留给 Day 5）

- [ ] CodeAgent 的 `model_output` 既包含思考文本也包含代码块，框架怎么把代码块抠出来填到 `code_action`？（→ 已看到 [agents.py:1709](../../../../src/smolagents/agents.py:1709) `parse_code_blobs`，细节待读）
- [ ] `model_input_messages` 每个 step 都存一份，10 步后多份相互嵌套，会不会内存爆炸？（→ 跑长任务测一下）
