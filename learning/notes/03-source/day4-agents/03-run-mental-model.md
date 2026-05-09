---
created: 2026-05-07
status: active
tags: [smolagents, agents, mental-model, run, stream, day4, react-loop]
---

# `run()` + `_run_stream` 外循环 mental model：ReAct 控制流剧本

> ⚠️ **必读前置**（按阅读顺序）：
> 1. [smolagents-package-overview.md](00-package-overview.md) — Day 4 包级鸟瞰
> 2. [multi-step-agent-role-overview.md](01-multi-step-agent-role-overview.md) — MultiStepAgent 类角色
> 3. [stream-abstraction-explained.md](../../02-concepts/stream-abstraction-explained.md) — 通用 stream 概念
> 4. [agents-stream-naming-explained.md](02-stream-naming-explained.md) — `_run_stream` 命名 + 两层 stream
>
> 没读过会卡在很多地方（`yield` 流式、ABC 边界、术语 4 角色）。

## 背景 / 动机

读完 ⓪ ① ②a ②b 之后，你已经知道：

- MultiStepAgent 是 ReAct 外圈骨架（① §1）
- 外圈是个 generator，yield 步骤事件（②b §2）
- `run` 是非流式包装，`_run_stream` 是真正的核心实现（②b §3）

但你还**不知道**：

1. `run()` 100 行里到底**做了哪 N 件事**？
2. `_run_stream` 70 行里 `while` 循环的**控制流骨架**长什么样？
3. 错误处理为什么有 3 层（`AgentGenerationError` / `AgentError` / `finally`）？
4. **一步内部**（`_step_stream` 调用前后）`_run_stream` 做了什么？
5. `max_steps` 用完了怎么兜底？为什么源码里有看似"重复 yield 同一个 action_step"？
6. `RunResult` 收尾时是怎么聚合 token / state 的？

本笔记一次性回答这 6 个问题。读完之后**应该能徒手默写 `_run_stream` 的伪代码**（这是 [LEARNING_PLAN.md Day 4 验收标准](../../../LEARNING_PLAN.md) 的硬要求）。

---

## 1. 一句话定调

> **`run()` 负责"准备 + 收尾"，`_run_stream` 负责"反复跑一步直到 final_answer 或撞 max_steps"。两者一起把 ReAct 论文的伪代码翻译成可流式消费的 Python generator。**

```
run()                                          _run_stream()
─────                                          ─────────────
准备阶段（9 件事）                              while step <= max_steps:
   ├── 设 task                                    ├── 该规划? → _generate_planning_step
   ├── reset memory                               ├── 建 ActionStep
   ├── 加 TaskStep                                ├── try _step_stream() ◄── 子类实现 (Day 5)
   └── ...                                        ├── except 错误处理
       │                                          ├── finally 写回 memory + yield
       ▼                                          └── step += 1
   _run_stream() ──── 流式 → 非流式 ─────────►   收尾: yield FinalAnswerStep
       │
       ▼
收尾阶段（包 RunResult）
```

---

## 2. ⭐ `run()` 做的 9 件事（带源码行号）

[agents.py:436-538](../../../../src/smolagents/agents.py#L436)：

| # | 做什么 | 行 | 备注 |
|---:|---|---:|---|
| ① | 解析 max_steps（参数 > 实例默认） | [468](../../../../src/smolagents/agents.py#L468) | 允许单次 run 临时调步数上限 |
| ② | 设 `self.task` + 清中断标志 | [469-470](../../../../src/smolagents/agents.py#L469) | task 字符串保存到实例上 |
| ③ | 处理 `additional_args` | [471-475](../../../../src/smolagents/agents.py#L471) | 把额外变量塞进 `self.state` + 把"提示"附加到 task 字符串末尾 |
| ④ | 重新生成 system_prompt | [477](../../../../src/smolagents/agents.py#L477) | 调 `self.system_prompt`（property → `initialize_system_prompt`），**每次 run 重新拼**（因为 tools 可能动态变） |
| ⑤ | 如果 reset：清 memory + reset monitor | [478-480](../../../../src/smolagents/agents.py#L478) | `reset=False` 时复用上次记忆（少见用法） |
| ⑥ | 日志：宣告任务开始 | [482-487](../../../../src/smolagents/agents.py#L482) | rich 控制台漂亮输出 |
| ⑦ | **`memory.steps.append(TaskStep(...))`** | [488](../../../../src/smolagents/agents.py#L488) | ⭐ Day 1 闭环：TaskStep 入 memory，后续 `to_messages` 会翻译它 |
| ⑧ | 如果有 python_executor：传变量 + 工具 | [490-492](../../../../src/smolagents/agents.py#L490) | **CodeAgent 独有**（ToolCallingAgent 没沙箱） |
| ⑨ | 决定流式 / 非流式分支 | [494-538](../../../../src/smolagents/agents.py#L494) | 见 §3 |

### ⑨ 流式 / 非流式分支详解

```python
if stream:
    return self._run_stream(...)        # ← 直接返回 generator，用户自己 for 消费

run_start_time = time.time()
steps = list(self._run_stream(...))     # ← 内部 list() 把所有 yield 收集起来
assert isinstance(steps[-1], FinalAnswerStep)
output = steps[-1].output

if return_full_result:
    # 聚合 token usage（遍历 memory.steps 求和）
    # 判定 state（"max_steps_error" if 最后 step 是 AgentMaxStepsError else "success"）
    return RunResult(...)
return output
```

> 💡 **`assert isinstance(steps[-1], FinalAnswerStep)`** 这一行揭示了一个不变量：**`_run_stream` 一定会在末尾 yield 一个 `FinalAnswerStep`**（即使是超步兜底也会有）。这是后面剧本图（§9）的关键。

---

## 3. `_run_stream` 的骨架（伪代码默写版）

[agents.py:540-611](../../../../src/smolagents/agents.py#L540)：

```python
def _run_stream(self, task, max_steps, images):
    self.step_number = 1
    returned_final_answer = False

    while not returned_final_answer and self.step_number <= max_steps:
        if self.interrupt_switch:                          # ── 中断检查
            raise AgentError("Agent interrupted.")

        if 该规划吗?(planning_interval, step_number):       # ── 周期性规划
            for element in self._generate_planning_step(...):
                yield element                              # 透传 token delta + PlanningStep
                planning_step = element                    # 最后一个一定是 PlanningStep
            self._finalize_step(planning_step)             # 触发 callbacks
            self.memory.steps.append(planning_step)        # 进 memory

        action_step = ActionStep(step_number=...)          # ── 建 ActionStep

        try:
            for output in self._step_stream(action_step):  # ── ⭐ 子类实现的"一步内部"
                yield output                               # 透传所有子事件
                if output 是 ActionOutput 且 是 final_answer:
                    final_answer = output.output
                    if self.final_answer_checks:
                        self._validate_final_answer(...)   # 校验失败抛 AgentError
                    returned_final_answer = True
                    action_step.is_final_answer = True

        except AgentGenerationError:                       # ── ⚠️ 实现 bug，立即抛
            raise
        except AgentError as e:                            # ── LLM/解析错误，记 step 继续
            action_step.error = e
        finally:                                           # ── ⭐ 不管成败都写回
            self._finalize_step(action_step)
            self.memory.steps.append(action_step)
            yield action_step
            self.step_number += 1

    # ── while 退出后
    if not returned_final_answer and self.step_number == max_steps + 1:
        final_answer = self._handle_max_steps_reached(task)
        yield action_step                                  # ⚠️ 看似"重复 yield"，见 §7

    final_answer_step = FinalAnswerStep(handle_agent_output_types(final_answer))
    self._finalize_step(final_answer_step)
    yield final_answer_step                                # ── ⭐ 最后一个一定是它
```

> 💡 **拆解之后只有 3 个核心结构**：
> 1. **while 头部 2 个退出条件**（`returned_final_answer` OR 撞上限）
> 2. **每轮 5 件事**（中断检查 → 规划 → 建 step → 跑一步 → 写回）
> 3. **末尾兜底 + 必发 FinalAnswerStep**

---

## 4. ⭐ 错误处理的 3 层（最容易被低估的设计）

`try-except-except-finally` 这套写法不是装饰，每一层都对应**不同的错误类型 + 不同的应对策略**：

```python
try:
    # 跑一步
except AgentGenerationError:
    # 立即抛（停止整个 run）
    raise
except AgentError:
    # 记到 step.error，继续下一步
    action_step.error = e
finally:
    # 不管成败，把 step 写回 memory 并 yield
    self._finalize_step(action_step)
    self.memory.steps.append(action_step)
    yield action_step
    self.step_number += 1
```

### 3 层职责

| 层 | 触发条件 | 应对 | 设计意图 |
|---|---|---|---|
| `except AgentGenerationError` | **agent 框架自己代码 bug**（实现错误，不是 LLM 问题） | 立即 raise，整个 run 退出 | 实现 bug 必须 fail-fast，不能掩盖 |
| `except AgentError` | **LLM/解析/工具调用错误**（含子类 `AgentParsingError` / `AgentToolCallError` / `AgentToolExecutionError`） | 把错误记到 `action_step.error`，**继续下一步** | 让 LLM 自己看到错误信息，下一步可能就修好 |
| `finally` | **不管成败** | 写回 memory + yield + step++ | 保证 ① memory 一定有这一步的记录（即使错了）② 用户一定能看到这一步发生了 ③ 不会死循环 |

> 💡 **AgentError 不抛 —— 这是 ReAct 的关键设计**：
> - 如果一抛错就退出，agent 就只有"一次试错机会"
> - 让 agent 看到自己的错误，下次循环就有机会改正（错误信息会通过 [action-step-anatomy.md](../day1-memory/action-step-anatomy.md) 的 `to_messages` 翻译成 user 角色的 observation 喂回 LLM）
> - **错误是 ReAct 循环的"反馈信号"，不是终止信号**

> 💡 **AgentGenerationError 抛 —— 因为它不是 LLM 错**：
> - 比如 `_step_stream` 返回类型错、callback 写错代码 …
> - 这些是开发者代码 bug，不是 LLM 的问题
> - LLM 看到这种错也无能为力，所以必须立即停

> 💡 **`finally` 里的 `yield action_step` 是关键**：
> - 即使 try 里抛了 AgentError，consumer 仍能从 generator 收到这个带 error 的 action_step
> - **错误对外是"事件"，不是"异常"**（这是 stream 设计的优雅 —— 错误事件化）
> - 呼应 [stream-abstraction-explained.md §3](../../02-concepts/stream-abstraction-explained.md) 的"错误传播"周边概念

### 8 个 AgentError 子类（[utils.py:92-138](../../../../src/smolagents/utils.py#L92)）

```
AgentError                        ← 基类（被 except AgentError 捕获）
├── AgentParsingError             ← LLM 输出解析失败（CodeAgent 找不到代码块 / ToolCallingAgent 解析不出 tool_calls）
├── AgentExecutionError           ← 执行动作时出错
│   ├── AgentToolCallError        ← tool 调用前的参数校验失败
│   └── AgentToolExecutionError   ← tool.forward() 自己抛的错
├── AgentMaxStepsError            ← 超步兜底用（_handle_max_steps_reached 创建）
└── AgentGenerationError          ← ⚠️ 唯一会被 raise 出去的
```

---

## 5. ⭐ Planning 触发条件（呼应 Day 1）

[agents.py:550-552](../../../../src/smolagents/agents.py#L550)：

```python
if self.planning_interval is not None and (
    self.step_number == 1 or (self.step_number - 1) % self.planning_interval == 0
):
```

呼应 [planning-mechanics.md](../day1-memory/planning-mechanics.md) Day 1 的公式：触发于 **step_number = 1, 1+N, 1+2N, ...**（N = planning_interval）。

| step_number | 是否规划 |
|---:|---|
| 1 | ✅（首次必规划） |
| 2 | （N=3 时）❌ |
| 3 | ❌ |
| 4 | ✅（4 = 1 + 3）|
| 5 | ❌ |
| 6 | ❌ |
| 7 | ✅（7 = 1 + 6）|

`_generate_planning_step` 自身也是 generator，**`_run_stream` 用 `for ... yield`手动透传**（不是 `yield from`）—— 因为还要把最后一个 yield 出来的 PlanningStep 抓出来设 timing + 写 memory。

---

## 6. ⭐ "一步内部"`_step_stream` 调用前后做了什么（Day 5 边界）

```python
# 调用前
action_step_start_time = time.time()
action_step = ActionStep(
    step_number=self.step_number,
    timing=Timing(start_time=action_step_start_time),
    observations_images=images,
)
self.logger.log_rule(f"Step {self.step_number}", level=LogLevel.INFO)

# 调用 ─ 这是 Day 5 的内容
for output in self._step_stream(action_step):
    yield output
    if isinstance(output, ActionOutput) and output.is_final_answer:
        ...

# 调用后（finally 块）
self._finalize_step(action_step)         # ← 设 end_time + 跑 callbacks
self.memory.steps.append(action_step)    # ← 进 memory（即使错了）
yield action_step                         # ← 给 consumer 看完整 step（含 error）
self.step_number += 1
```

> 💡 **`_step_stream(action_step)` 接的是同一个对象引用**：子类（CodeAgent / ToolCallingAgent）会**直接往 action_step 上写字段**（`model_output` / `tool_calls` / `observations` / `action_output` / `error` 等）。这是为什么 `_step_stream` 不需要返回 ActionStep —— 它是被传进去**就地修改**的。
>
> 这也呼应 [action-step-anatomy.md](../day1-memory/action-step-anatomy.md) Day 1 的 13 字段：那 13 字段是**子类填的**，基类的 `_run_stream` 只负责框架（建 ActionStep + finally 写回）。

---

## 7. ⚠️ Max steps 兜底分支 + 看似"重复 yield"的真相

[agents.py:606-611](../../../../src/smolagents/agents.py#L606)：

```python
if not returned_final_answer and self.step_number == max_steps + 1:
    final_answer = self._handle_max_steps_reached(task)
    yield action_step                    # ⚠️ 这个 action_step 是哪个？
final_answer_step = FinalAnswerStep(handle_agent_output_types(final_answer))
self._finalize_step(final_answer_step)
yield final_answer_step
```

### `_handle_max_steps_reached` 做了什么（[625-637](../../../../src/smolagents/agents.py#L625)）

```python
def _handle_max_steps_reached(self, task):
    final_answer = self.provide_final_answer(task)              # ← 让 LLM 看完所有 memory 写一个总结
    final_memory_step = ActionStep(                              # ← 建一个新的 ActionStep
        step_number=self.step_number,
        error=AgentMaxStepsError("Reached max steps."),          # ← 标记是超步兜底
        timing=Timing(...),
        token_usage=final_answer.token_usage,
    )
    final_memory_step.action_output = final_answer.content
    self._finalize_step(final_memory_step)                       # ← 跑 callbacks
    self.memory.steps.append(final_memory_step)                  # ← 进 memory（但**没 yield**）
    return final_answer.content
```

### `provide_final_answer` 做了什么（[810-853](../../../../src/smolagents/agents.py#L810)）

把 memory 重新喂给 LLM，加 SYSTEM 指令"基于历史给出答案" + USER post_message → 调 `model.generate` 拿 ChatMessage 返回。**这是兜底机制**：循环用完了，让 LLM 强制给一个答案，哪怕半成品。

### 那行"重复 yield action_step" 是什么意思？

这行 `yield action_step` 的 `action_step` **是 while 循环最后一次迭代里的那个变量**（Python 的 while 不形成新作用域，变量泄漏到外层）。

按 finally 的执行顺序：
- 最后一轮 step=max_steps：finally 已经 `yield action_step` 一次 + `step_number += 1` 变成 max_steps+1
- while 退出条件 `step_number <= max_steps` 不再满足 → 跳出
- 进入 max_steps 兜底分支
- `_handle_max_steps_reached` 创建了一个新的 `final_memory_step` 进了 memory（但没 yield）
- `yield action_step` 把**老的最后一轮 action_step 又 yield 了一次** ⚠️

> 💡 **看起来像 bug**：consumer 会收到同一个 action_step 对象两次。`_handle_max_steps_reached` 里的 `final_memory_step` 反而没被 yield。
>
> **可能的解释**：
> 1. **历史遗留**：早期版本可能这里逻辑不一样，重构时漏改
> 2. **故意**：让 consumer 看到"超步分支被触发"的信号（虽然这个信号其实没多大意义 —— 老 step 已经看过了）
>
> 已记入 [questions.md](../../questions.md) / 本笔记的遗留问题，**Week 3 实战时可以提个 issue 或 PR 验证**。

### 不管怎样，最后必发 FinalAnswerStep

无论是正常完成还是超步兜底，**最后一行总是 `yield final_answer_step`** —— 这就是 `run()` 里 `assert isinstance(steps[-1], FinalAnswerStep)` 能成立的原因。

---

## 8. RunResult 收尾：token / state / steps 的聚合

[agents.py:505-536](../../../../src/smolagents/agents.py#L505)：

```python
if return_full_result:
    total_input_tokens = 0
    total_output_tokens = 0
    correct_token_usage = True
    for step in self.memory.steps:
        if isinstance(step, (ActionStep, PlanningStep)):
            if step.token_usage is None:
                correct_token_usage = False
                break
            else:
                total_input_tokens += step.token_usage.input_tokens
                total_output_tokens += step.token_usage.output_tokens

    if correct_token_usage:
        token_usage = TokenUsage(input_tokens=total_input_tokens, output_tokens=total_output_tokens)
    else:
        token_usage = None  # ← 一旦有任何 step 缺 token_usage，全局放弃聚合

    if self.memory.steps and isinstance(getattr(self.memory.steps[-1], "error", None), AgentMaxStepsError):
        state = "max_steps_error"
    else:
        state = "success"

    step_dicts = self.memory.get_full_steps()

    return RunResult(
        output=output,
        token_usage=token_usage,
        steps=step_dicts,
        timing=Timing(start_time=run_start_time, end_time=time.time()),
        state=state,
    )
```

3 个事实：

1. **token 聚合只看 ActionStep + PlanningStep**（TaskStep / FinalAnswerStep 不计 token）
2. **All-or-nothing 策略**：任何一步缺 `token_usage` → 整个 RunResult 的 `token_usage = None`（不混着算）
3. **state 判定**：`memory.steps[-1].error is AgentMaxStepsError` → "max_steps_error"，否则 "success"

> 💡 **state 怎么知道是 max_steps_error**：因为 §7 的 `_handle_max_steps_reached` 把 `final_memory_step.error = AgentMaxStepsError(...)` 塞进 memory 了。这就是为什么那一步**必须**进 memory（即使没 yield）—— state 判定要靠它。

---

## 9. ⭐ Day 4 完整剧本图（一张图打通）

```
用户:  agent.run("查北京天气")
        │
        ▼
┌─ run() ──────────────────────────────────────────────────┐
│ ① 解析 max_steps                                          │
│ ② 设 self.task                                            │
│ ③ 处理 additional_args                                    │
│ ④ system_prompt 重新生成                                  │
│ ⑤ memory.reset() + monitor.reset()                       │
│ ⑥ 日志: 任务开始                                           │
│ ⑦ memory.steps.append(TaskStep)            ◄─ Day 1 闭环 │
│ ⑧ python_executor.send_variables/tools (CodeAgent only)  │
│ ⑨ if stream: return _run_stream(...)                     │
│    else: list(_run_stream(...))                          │
└─────────────────┬─────────────────────────────────────────┘
                  │
                  ▼
┌─ _run_stream() ──────────────────────────────────────────┐
│ step_number=1, returned_final_answer=False               │
│                                                           │
│ while not returned_final_answer and step <= max_steps:   │
│   ┌──────────────────────────────────────────────────┐  │
│   │ ▸ 中断检查: interrupt_switch?                     │  │
│   │ ▸ 该规划? → _generate_planning_step              │  │
│   │     yield 透传 + memory.append(PlanningStep)     │  │
│   │ ▸ action_step = ActionStep(step_number=...)      │  │
│   │ ▸ try:                                            │  │
│   │     for ev in _step_stream(action_step):  ⭐Day5│  │
│   │       yield ev   (透传子事件)                    │  │
│   │       if final_answer: 校验 + 标记退出           │  │
│   │   except AgentGenerationError: raise (实现 bug)  │  │
│   │   except AgentError: action_step.error = e       │  │
│   │   finally:                                        │  │
│   │     _finalize_step(action_step)                   │  │
│   │     memory.append(action_step)                    │  │
│   │     yield action_step                             │  │
│   │     step_number += 1                              │  │
│   └──────────────────────────────────────────────────┘  │
│                                                           │
│ if 撞 max_steps: _handle_max_steps_reached + yield 老step│
│                                                           │
│ yield FinalAnswerStep(handle_agent_output_types(...))    │
│                              ▲                            │
│                              │ 必发                        │
└──────────────────────────────┼───────────────────────────┘
                               │
                               ▼
┌─ run() 收尾 ─────────────────────────────────────────────┐
│ steps = list(...)                                         │
│ assert isinstance(steps[-1], FinalAnswerStep)            │
│ output = steps[-1].output                                │
│                                                           │
│ if return_full_result:                                   │
│   聚合 token / 判定 state / 包 RunResult                  │
│ else:                                                    │
│   return output                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 10. 容易出错的认知点（FAQ）

### Q1: `run(stream=True)` 里 `_run_stream` 抛错会怎样？

**generator 不会立即执行 `_run_stream` 函数体** —— `run` 直接 `return self._run_stream(...)` 时，函数体一行没跑。等用户开始 `for step in agent.run(...)` 才真正执行。所以 `AgentGenerationError` 会在用户的 for 循环里抛出，不在 `run()` 调用本身里抛。

### Q2: 为什么 `final_answer` 变量在 while 外能用？

Python 的 `while` 不形成新作用域，`final_answer = output.output` 在 try 块里赋值后，整个函数都能访问。配合 `returned_final_answer` 标志位保证 while 退出时它一定有值。

### Q3: `final_answer_checks` 校验失败会怎样？

`_validate_final_answer` 抛 `AgentError`，被 `except AgentError` 捕获 → `action_step.error = e` → finally 块照常 yield + step++ → 下轮循环让 LLM 看到错误重新尝试。**这是优雅的设计**：校验失败不是终止，而是给 LLM 反馈让它改。

### Q4: `interrupt()` 调用后下一步才停？

是的。`interrupt_switch = True` 在外部线程设置，但 `_run_stream` 只在 while 头部检查一次。所以**当前正在跑的 step 会跑完**，下一个 while 迭代开始时才抛 AgentError。这是单线程 generator 的合理代价。

### Q5: `images` 参数为什么传给每个 ActionStep？

[agents.py:574](../../../../src/smolagents/agents.py#L574) `observations_images=images` —— 用户开始 run 时传的图，**每个 ActionStep 都能看到**。这是为了让 vision LLM 在每一步都能"看图思考"。但这也意味着 token 成本随 step 数线性增长（每步都重发图）。

### Q6: 为什么 `_finalize_step` 既给 ActionStep 也给 PlanningStep 也给 FinalAnswerStep？

通用收尾：① 设 `end_time`（FinalAnswerStep 没 timing 字段，跳过）② 触发 `step_callbacks` —— 这 3 类 step 都注册过 callback（呼应 [callback-registry.md](../day1-memory/callback-registry.md) Day 1）。

---

## 11. 接下来：怎么验证

按 Day 4 验收标准：

- [x] 默写 `run()` 伪代码（while 循环 + max_steps + callback + error 捕获）—— **§3**
- [x] 解释 `agent.run()` 的 `stream=True` 区别 —— **§2 ⑨ + ②b 笔记**
- [ ] **在 `run()` 设断点跟一个完整 task** —— **下一篇 ⑤ 单步调试笔记**

剩下的最后一步：拿 [my_first_agent.py](../../../scripts/my_first_agent.py) 在 [agents.py:436 `run`](../../../../src/smolagents/agents.py#L436) 设断点，单步走完一个完整 task，把本笔记 §9 的剧本图**亲眼看一遍**。

---

## 相关链接

- ⚠️ 必读前置：[smolagents-package-overview.md](00-package-overview.md)、[multi-step-agent-role-overview.md](01-multi-step-agent-role-overview.md)、[stream-abstraction-explained.md](../../02-concepts/stream-abstraction-explained.md)、[agents-stream-naming-explained.md](02-stream-naming-explained.md)
- 上游 Day 1：[action-step-anatomy.md](../day1-memory/action-step-anatomy.md)（13 字段被 `_step_stream` 就地写）、[planning-mechanics.md](../day1-memory/planning-mechanics.md)（planning 触发公式）、[final-answer-step.md](../day1-memory/final-answer-step.md)（FinalAnswerStep 不入 memory）、[callback-registry.md](../day1-memory/callback-registry.md)（`_finalize_step` 触发的回调）
- 上游 Day 3：[model-class-role-overview.md](../day3-models/model-class-role-overview.md)（`provide_final_answer` 调 `model.generate`）
- 概念：[llm-vs-api-server-architecture.md §2](../../02-concepts/llm-vs-api-server-architecture.md)（4 角色术语）
- 源码：[agents.py:436-538 run](../../../../src/smolagents/agents.py#L436)、[agents.py:540-611 _run_stream](../../../../src/smolagents/agents.py#L540)、[agents.py:625-637 _handle_max_steps_reached](../../../../src/smolagents/agents.py#L625)、[agents.py:810-853 provide_final_answer](../../../../src/smolagents/agents.py#L810)
- 异常类清单：[utils.py:92-138](../../../../src/smolagents/utils.py#L92)

## 遗留问题

- [ ] ⚠️ [agents.py:608](../../../../src/smolagents/agents.py#L608) 的 `yield action_step` 看起来重复 yield 了上一轮的 step（`_handle_max_steps_reached` 创建的新 `final_memory_step` 反而没被 yield）。**Week 3 实战时去 GitHub 找历史 commit 验证**：是 bug 还是有意？
- [ ] `provide_final_answer` 里 `messages = [SYSTEM_pre] + write_memory_to_messages()[1:] + [USER_post]` —— **`[1:]` 切片是为了跳过 system_prompt**（避免重复）。这个细节先记下，Day 4 ④ `write-memory-to-messages-deep-dive` 时再深挖
- [ ] `additional_args` 直接拼到 `task` 字符串末尾（[473-475](../../../../src/smolagents/agents.py#L473)），但同时也存进了 `self.state`。**两条路径**给 LLM 看（task 字符串）vs 给 Python 沙箱看（state dict）—— Day 5 看 CodeAgent 时验证
