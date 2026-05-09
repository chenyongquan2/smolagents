---
created: 2026-05-08
status: active
tags: [smolagents, agents, stream, events, mental-model, day4]
---

# Stream 里到底 yield 出哪些事件？consumer 拿来干啥

> 💡 **本篇定位**：[③' walkthrough](03b-run-walkthrough-leopard-demo.md) 末尾的事件清单（ToolCall / ActionOutput / ActionStep / FinalAnswerStep）你已经见过。本篇回答两个延伸问题：
> 1. **完整 8 种事件类型分别是什么？**（豹子 demo 只见过 5 种）
> 2. **上游拿到这些事件分别会怎么处理？**

> ⚠️ **必读前置**：[③ mental-model](03-run-mental-model.md) + [③' walkthrough](03b-run-walkthrough-leopard-demo.md) + [②a stream 通用概念](../../02-concepts/stream-abstraction-explained.md)

## 一句话本质

> **不同事件 = 不同粒度的"进度信号"。Consumer 用 `isinstance(event, X)` 派发到不同处理逻辑。**

延续 [项目经理比喻](01-multi-step-agent-role-overview.md)：
- 老板可以选**只关心最终答案**（最粗粒度）
- 也可以选**每一步都看档案**（中粒度）
- 也可以选**顾问每蹦一个字都看**（最细粒度）
- 同一个 stream，不同 consumer 各取所需

---

## 1. 完整事件类型清单（8 种）

源码里的"官方清单" [agents.py:256](../../../../src/smolagents/agents.py#L256)：

```python
StreamEvent: TypeAlias = Union[
    ChatMessageStreamDelta,    # ① token 增量
    ChatMessageToolCall,       # ② LLM 原始 tool_call（OpenAI 格式）
    ActionOutput,              # ③ 一步刚执行完的产出
    ToolCall,                  # ④ smolagents 规范化后的 tool 调用
    ToolOutput,                # ⑤ tool 执行后的输出包
    PlanningStep,              # ⑥ 规划档案
    ActionStep,                # ⑦ 整步完整档案
    FinalAnswerStep,           # ⑧ 全任务结束通告
]
```

按 **"信号粒度"** 分 4 层（这是理解的关键）：

```
最细 ────────────────────────────────────────────────────► 最粗
                                                              │
① token 增量 │ ②③④⑤ 一步中途子事件 │ ⑥⑦ 整步档案 │ ⑧ 全任务终结
                                                              │
            一个 LLM 回复 ≈ 几十~几百 token
            一个 ActionStep ≈ 一次思考 + 一次工具调用
            一个 run ≈ 多个 ActionStep + 1 个 FinalAnswerStep
```

---

## 2. 4 个粒度层 × 8 种事件详解

### 🔹 层 1 · token 级（最细）

#### ① `ChatMessageStreamDelta`（[models.py:214](../../../../src/smolagents/models.py#L214)）

**是什么**：LLM 一个 token 的增量（"逐字蹦出"那一字）。

**谁产生**：`Model.generate(stream=True)` 从 LLM API 服务器拿回来的 SSE 事件，被 `_step_stream` 透传出去。

**什么时候出现**：仅当 `agent.stream_outputs = True`。默认 False，**所以豹子 demo 没见过它**。

**项目经理视角**：顾问每说一个字，张三就**实时转发给老板**。

**consumer 用来干嘛**：
- ✅ Web UI 渲染**打字效果**（ChatGPT 那种逐字蹦）
- ✅ 实时日志（看 LLM 思考过程）
- ❌ 计费 / 进度（粒度太细，没意义）

---

### 🔹 层 2 · 一步中途子事件

#### ② `ChatMessageToolCall`（[models.py:102](../../../../src/smolagents/models.py#L102)）

**是什么**：**LLM 原始格式**的 tool 调用（OpenAI 协议格式：含 `function.name` + `function.arguments` + `id` + `type`）。

**谁产生**：LLM API 服务器返回的 `tool_calls` 字段被解析出来，由 ToolCallingAgent 的 `_step_stream` yield。

**什么时候出现**：**ToolCallingAgent 才会出现**，CodeAgent 不会（它走代码不走 tool_calls）。

**项目经理视角**：顾问按 OpenAI 协议格式说"调 X 工具，参数是 Y"。

**consumer 用来干嘛**：很少直接用 —— 大部分 consumer 用规范化后的 `ToolCall`（见 ④）。

#### ③ `ActionOutput`（[agents.py:111](../../../../src/smolagents/agents.py#L111)）⭐ 关键

**是什么**：

```python
@dataclass
class ActionOutput:
    output: Any              # 这一步动作的产物
    is_final_answer: bool    # ⭐ 这是最终答案吗？
```

**谁产生**：`_step_stream` 每步**必发一个**作为收尾。

**项目经理视角**："助手跑完了。输出是 X。**这是不是最终答案我也告诉你**：是 / 不是"。

**consumer 用来干嘛**：
- ⭐⭐ **`_run_stream` 自己用它退 while 循环**（[agents.py:582](../../../../src/smolagents/agents.py#L582)）
- ✅ 早停 / 流控：拿到答案就 break
- ✅ Web UI：提前展示答案（不必等到 ActionStep）

#### ④ `ToolCall`（[memory.py:25](../../../../src/smolagents/memory.py#L25)）⭐ 常见

**是什么**：**smolagents 规范化后**的 tool 调用：`name` / `arguments` / `id`。

**谁产生**：
- CodeAgent：合成的 `ToolCall(name="python_interpreter", arguments=<code>)`
- ToolCallingAgent：从 `ChatMessageToolCall` 转换而来

**项目经理视角**："我马上要让助手调 X 工具，参数是 Y"。

**consumer 用来干嘛**：
- ✅ Web UI 显示**工具调用卡片**
- ✅ 调试日志：看 LLM 决定调啥
- ✅ 后处理：累计某工具被调用次数

> 💡 **`ToolCall` vs `ChatMessageToolCall` 的差异**：前者是 smolagents 的**统一抽象**（CodeAgent / ToolCallingAgent 都用），后者是 ToolCallingAgent 专用的 LLM 原始格式。**新手只用记 `ToolCall`**。

#### ⑤ `ToolOutput`（[agents.py:117](../../../../src/smolagents/agents.py#L117)）

**是什么**：tool 执行后的输出包（`id` + `output` + `is_final_answer` + `observation` + `tool_call`）。

**谁产生**：ToolCallingAgent 的 `_step_stream` 内部 yield。

**项目经理视角**："助手 X 调用刚跑完，输出 Y、observation Z"。

**consumer 用来干嘛**：
- ✅ 跟踪每个工具的产出
- ✅ Web UI 把"工具结果卡片"附在工具调用卡片下面

> 💡 **CodeAgent 不发 ToolOutput**（它走代码沙箱，没有"单个 tool 调用"的概念，整个 step 一次性出 ActionOutput）。

---

### 🔹 层 3 · 整步档案

#### ⑥ `PlanningStep`（[memory.py:154](../../../../src/smolagents/memory.py#L154)）

**是什么**：规划事件（含 `plan` 文本 + `model_input_messages` + `token_usage` 等）。

**谁产生**：`_run_stream` 周期性调 `_generate_planning_step` → 它 yield 的最后一个事件。

**什么时候出现**：仅当 `planning_interval is not None`。**豹子 demo 没见过**。

**项目经理视角**：张三阶段性地停下来，写一份"接下来打算怎么干"的规划文档。

**consumer 用来干嘛**：
- ✅ Web UI 显示**规划阶段卡片**（让用户看 LLM 的思考）
- ✅ 计费：累加规划阶段的 token

#### ⑦ `ActionStep`（[memory.py 各处](../../../../src/smolagents/memory.py)）⭐⭐ 最重要

**是什么**：**完整工作档案** —— 13 个字段全部填好（[Day 1 anatomy](../day1-memory/action-step-anatomy.md)）：
- 问了顾问啥（`model_output`）
- 顾问让我调啥工具（`tool_calls`）
- 跑了啥代码（`code_action`）
- 助手输出了啥（`observations`）
- 这一步的产物（`action_output`）
- 出错没（`error`）
- 用了多少 token（`token_usage`）
- 这一步耗时（`timing`）
- ……

**谁产生**：`_run_stream` 的 `finally` 块（**不管 try 里成功还是失败都发**）。

**项目经理视角**：把这一步的**完整档案**给老板。**这是 7 个事件里信息最全的一种**。

**consumer 用来干嘛**：⭐ **几乎所有 consumer 都需要它**：
- ✅ Web UI 渲染步骤卡片
- ✅ 计费：累加 `token_usage`
- ✅ 错误监控：检查 `error` 字段
- ✅ 调试：审计每一步细节
- ✅ 历史回看（`replay()`）

---

### 🔹 层 4 · 全任务终结

#### ⑧ `FinalAnswerStep`（[Day 1 final-answer-step](../day1-memory/final-answer-step.md)）⭐ 必发

**是什么**：只有一个 `output` 字段的简单事件。

**谁产生**：`_run_stream` 末尾**只发一次**，不管成功还是 max_steps 兜底都必发。

**项目经理视角**："**全部任务完成**。最终答案是 X。"

**consumer 用来干嘛**：
- ✅ **退出 for 循环的信号**
- ✅ 默认 `agent.run("...")` 内部用它取最终答案

> 💡 **重点**：`FinalAnswerStep` **不进笔记本**（[Day 1 final-answer-step.md 设计哲学](../day1-memory/final-answer-step.md)）—— 它是事件不是记录。

---

## 3. 8 种事件速查表

| # | 事件 | 粒度 | 谁产生 | 必发吗 | 最常被谁消费 |
|---:|---|---|---|:---:|---|
| ① | `ChatMessageStreamDelta` | token | `Model.generate` 透传 | ❌ 仅 stream_outputs | Web UI 打字效果 |
| ② | `ChatMessageToolCall` | tool 调用 | LLM API 服务器 | ❌ ToolCallingAgent 才有 | （内部用，少直接消费）|
| ③ | `ActionOutput` ⭐ | 一步产出 | `_step_stream` | ✅ 每步 1 个 | `_run_stream` 退 while 信号 / 早停 |
| ④ | `ToolCall` | tool 调用 | `_step_stream` | ✅ 一般有 | Web UI / 调试 |
| ⑤ | `ToolOutput` | tool 输出 | `_step_stream` | ❌ ToolCallingAgent 才有 | Web UI 工具结果卡片 |
| ⑥ | `PlanningStep` | 整步档案 | `_run_stream` | ❌ 仅 planning_interval | Web UI 规划卡片 / 计费 |
| ⑦ | `ActionStep` ⭐⭐ | 整步档案 | `_run_stream` finally | ✅ 每步 1 个 | **几乎所有 consumer** |
| ⑧ | `FinalAnswerStep` ⭐ | 任务终结 | `_run_stream` 末尾 | ✅ 必发 1 个 | 默认 run() 取答案 |

---

## 4. ⭐⭐ 5 类典型 consumer：分别用来干嘛

| consumer 类型 | 关心的事件 | 处理逻辑 |
|---|---|---|
| **默认 `agent.run("...")` 用户**（80% 用户） | 只看 `FinalAnswerStep` | `list()` 全收下，只取 `steps[-1].output` |
| **Web UI / Gradio** | `ActionStep` + `PlanningStep` + `FinalAnswerStep` + `ChatMessageStreamDelta` | 每种渲染成不同 UI 卡片 + 打字效果 |
| **计费 / 监控** | 主要看 `ActionStep` / `PlanningStep` 的 `token_usage` | 每步累加 |
| **早停 / 流控** | 看 `ActionOutput.is_final_answer` 或 `ActionStep.token_usage` | 拿到答案就 break / 超预算就 interrupt |
| **调试 / 日志** | 全部 8 种 | 按 isinstance 派发到不同 logger |

---

## 5. 真实代码：仓库里的 5 个 consumer

仓库里**真的有**多种 consumer 在做 `isinstance` 派发：

### Consumer A · 默认 `run(stream=False)` 内部（最简单）

[agents.py:499-503](../../../../src/smolagents/agents.py#L499)：

```python
steps = list(self._run_stream(...))                     # 全收下
assert isinstance(steps[-1], FinalAnswerStep)           # ⭐ 只用最后一个
output = steps[-1].output
```

**80% 用户走这条** —— 只在乎最终答案，前面所有事件全扔。

### Consumer B · `run()` 收尾的 token 聚合

[agents.py:510-517](../../../../src/smolagents/agents.py#L510)：

```python
for step in self.memory.steps:
    if isinstance(step, (ActionStep, PlanningStep)):    # ⭐ 只看这两类
        total_input_tokens += step.token_usage.input_tokens
        total_output_tokens += step.token_usage.output_tokens
```

**计费系统** —— 只关心**有 token_usage 字段的事件**。其他 6 种没意义。

### Consumer C · Gradio Web UI（最复杂）⭐

[gradio_ui.py:262-276](../../../../src/smolagents/gradio_ui.py#L262)：

```python
for event in agent.run(task, stream=True):
    if isinstance(event, ActionStep | PlanningStep | FinalAnswerStep):
        # ⭐ 整步档案 → 渲染成"步骤卡片"
        for message in pull_messages_from_step(event, ...):
            yield message
        accumulated_events = []                        # 清空 token 缓冲
    elif isinstance(event, ChatMessageStreamDelta):
        # ⭐ token 增量 → 实时渲染"打字效果"
        accumulated_events.append(event)
        text = agglomerate_stream_deltas(accumulated_events).render_as_markdown()
        yield text
```

**Web UI** 用了**两条独立渲染路径** —— 一条粗粒度（步骤卡片），一条细粒度（打字效果）。

> 💡 **Gradio 故意忽略了 ToolCall** —— 因为已经被 ActionStep.tool_calls 字段包含了，不必重复渲染。**Consumer 可以挑着用！**

### Consumer D · `replay()` 历史回看

[memory.py:261-267](../../../../src/smolagents/memory.py#L261)：

```python
for step in self.memory.steps:
    if isinstance(step, ActionStep):                    # 一种渲染
        ...
    elif isinstance(step, PlanningStep):                # 另一种渲染
        ...
```

**历史回看** —— 把笔记本里的 step 漂亮打印出来。

### Consumer E · `vision_web_browser.py` 自动截图清理

[vision_web_browser.py:72](../../../../src/smolagents/vision_web_browser.py#L72)：

```python
if isinstance(previous_memory_step, ActionStep) and previous_memory_step.step_number <= current_step - 2:
    # ⭐ 只对 2 步前的 ActionStep 删旧截图（节省 LLM 输入）
    previous_memory_step.observations_images = None
```

**截图清理** —— 只关心 ActionStep（**只有它有 `observations_images` 字段**）。

---

## 6. 自己写一个 consumer：完整 dispatch 模板

```python
total_tokens = 0
all_tool_calls = []

for event in agent.run("查北京天气", stream=True):

    if isinstance(event, ChatMessageStreamDelta):
        # 顾问每蹦一个 token：实时打字
        print(event.content, end="", flush=True)

    elif isinstance(event, ToolCall):
        # 张三宣布要调工具：记下来
        all_tool_calls.append(event.name)
        print(f"\n[工具调用] {event.name}({event.arguments})")

    elif isinstance(event, ToolOutput):
        # 工具输出（仅 ToolCallingAgent）
        print(f"[工具结果] {event.output}")

    elif isinstance(event, ActionOutput):
        # 一步刚执行完：检查是不是最终答案
        if event.is_final_answer:
            print(f"\n[拿到答案] {event.output}")

    elif isinstance(event, PlanningStep):
        # 规划档案（如果配置了 planning_interval）
        print(f"\n[规划] {event.plan}")
        if event.token_usage:
            total_tokens += event.token_usage.input_tokens

    elif isinstance(event, ActionStep):
        # 整步档案：累加 token + 检查错误
        if event.token_usage:
            total_tokens += event.token_usage.input_tokens + event.token_usage.output_tokens
        if event.error:
            print(f"\n[step {event.step_number} 出错] {event.error}")

    elif isinstance(event, FinalAnswerStep):
        # 整个 run 结束：清理 + 报告
        print(f"\n\n=== 任务完成 ===")
        print(f"总 token: {total_tokens}")
        print(f"调用过的工具: {set(all_tool_calls)}")
        break
```

**用这个模板**：你可以删掉不关心的分支，留下需要的就好。**没人逼你处理全部 8 种**。

---

## 7. ⭐ 为什么这样设计？事件类型驱动的优雅

为什么 smolagents 选**多种事件 + isinstance 派发**，而不是**一个 onProgress 回调**？

| 维度 | smolagents 选的（多类型事件）| 替代方案（统一回调）|
|---|---|---|
| **类型安全** | `isinstance` 自然带 IDE 类型提示 + 字段补全 | dict 字段名容易拼错 / 漏字段 |
| **粒度选择** | consumer 一句 `if isinstance` 就过滤掉不关心的 | 必须解 dict / 看 `type` 字段判断 |
| **扩展性** | 加新事件类型只需加新类，旧 consumer 不影响 | dict 加字段会让旧 consumer 一头雾水 |
| **多 consumer 灵活** | 同一 stream 不同 consumer 关心不同事件 | 难做 |

> 💡 **这就是"事件类型驱动"模式（Event-driven typing）的优雅** —— Java AWT / DOM events / RxJS Observable 用的也是同一套思想。**Stream + 多类型事件**给了 consumer 最大灵活性。

---

## 8. 关键启示

| 启示 | 含义 |
|---|---|
| **事件类型 = 粒度选择器** | consumer 通过 `isinstance` 选择关心的粒度 |
| **80% 场景只需 FinalAnswerStep** | 默认 `run(stream=False)` 就够了 |
| **Web UI 关心 ActionStep + ChatMessageStreamDelta** | 步骤卡片 + 打字效果 |
| **计费关心 token_usage 字段所在的事件** | ActionStep / PlanningStep |
| **没人逼你处理全部 8 种** | dispatch 模板里删掉不关心的分支即可 |
| **CodeAgent 和 ToolCallingAgent 出现的事件不同** | CodeAgent 不发 ToolOutput / ChatMessageToolCall |

---

## 相关链接

- ⚠️ 必读前置：[③ agent-run-mental-model.md](03-run-mental-model.md)、[③' agent-run-walkthrough-leopard-demo.md](03b-run-walkthrough-leopard-demo.md)
- 概念基石：[stream-abstraction-explained.md](../../02-concepts/stream-abstraction-explained.md)（事件流是 stream 的一种实例）、[agents-stream-naming-explained.md](02-stream-naming-explained.md)（命名规律）
- 上游 Day 1：[action-step-anatomy.md](../day1-memory/action-step-anatomy.md)（ActionStep 13 字段详解）、[final-answer-step.md](../day1-memory/final-answer-step.md)（事件不入 memory 设计）、[planning-mechanics.md](../day1-memory/planning-mechanics.md)（PlanningStep 触发）
- 上游 Day 2：[tool-class-role-overview.md](../day2-tools/tool-class-role-overview.md)（ToolCall 怎么产生）
- 源码：[agents.py:256 StreamEvent](../../../../src/smolagents/agents.py#L256)、[gradio_ui.py:262 真实 consumer](../../../../src/smolagents/gradio_ui.py#L262)

## 遗留问题

- [ ] `ChatMessageToolCallStreamDelta`（[models.py:204](../../../../src/smolagents/models.py#L204)）—— 没在 `StreamEvent` 联合里，看起来是 ToolCallingAgent + 流式输出时的中间态。Day 5 看 ToolCallingAgent._step_stream 时验证
- [ ] CodeAgent 的 `_step_stream` 具体 yield 哪几种事件？vs ToolCallingAgent 的 yield 哪几种？做一张对比表 —— Day 5 落地
