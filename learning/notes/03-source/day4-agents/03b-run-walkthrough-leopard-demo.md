---
created: 2026-05-07
status: active
tags: [smolagents, agents, walkthrough, mental-model, day4, react-loop]
---

# 项目经理张三的一天：豹子 demo 完整剧本

> 💡 **本篇定位**：[③ mental-model](03-run-mental-model.md) 是"项目经理岗位说明书"（抽象骨架），本篇是**"项目经理张三某一天的日记"**（具体演出）。
>
> 配合 [① role-overview "项目经理比喻"](01-multi-step-agent-role-overview.md) 阅读 —— 同一套人物关系延续到底。

## 这场戏的人物 & 道具

| 角色 | 对应代码 |
|---|---|
| **老板** | 用户脚本（`agent.run("...")`） |
| **项目经理张三** | `MultiStepAgent` 实例（具体是 `CodeAgent`）|
| **顾问** | LLM（通过 `model.generate` 联系） |
| **代码助手** | Python 沙箱（`python_executor`） |
| **笔记本** | `agent.memory`（写各种 Step 进去）|
| **工作记录** | 一张 `ActionStep`（每步建一张新的） |
| **任务通知单** | 一张 `TaskStep`（老板下单时写的）|

## 这场戏的设定

```python
agent = CodeAgent(
    tools=[],                       # 'final_answer' 自动加上
    model=InferenceClientModel(model_id="Qwen/Qwen2.5-72B-Instruct"),
    max_steps=4,                    # 最多反复 4 轮
    planning_interval=None,         # 不规划（简化）
    final_answer_checks=None,       # 不校验（简化）
)
result = agent.run("What is the result of 2 power 3.7384?")
print(result)   # 期待打印 13.166094...
```

**预想中张三的工作流程**：

| 第几步 | 张三干啥 |
|---|---|
| Step 1 | 问顾问 → 顾问说"先算一下" → 张三让代码助手跑 `result = 2 ** 3.7384; print(result)` → 拿到 `13.166094` |
| Step 2 | 再问顾问 → 顾问说"答案是 13.166094" → 张三让代码助手跑 `final_answer(13.166094)` → 通过 |

> 💡 不深入"顾问那一步具体怎么算的"（那是 [Day 5 `_step_stream`](03-run-mental-model.md) 的内容）—— **本篇把"问顾问 + 让助手干"打包成一个黑盒**。

---

## 第 0 幕 · 老板按下下单按钮

**张三视角**：还没人找我，办公室空的。

**代码层面**：用户写下 `agent.run("...")`，但 `run()` 函数体还没开始执行。

**此刻状态**：

| 变量 | 值 |
|---|---|
| `agent.task` | `None`（还没接单）|
| `agent.step_number` | `0` |
| `agent.memory.steps` | `[]`（笔记本里啥都没）|

---

## 第 1 幕 · 张三打开办公室门，准备开工

**张三视角**：接到老板下单 → 把任务记墙上 → 翻新一页笔记本 → 把任务写进笔记本第 1 行。

**代码层面**：[`run()` 方法](../../../../src/smolagents/agents.py#L436) 一口气干 9 件事 —— 解析 `max_steps`、保存 `self.task`、清中断标志、重新拼 system_prompt、reset 笔记本和监控、打日志、把任务塞进笔记本（[:488 `memory.steps.append(TaskStep(...))`](../../../../src/smolagents/agents.py#L488)）、给代码助手送变量和工具、最后决定"流式还是非流式"（这里是非流式，所以走 `list(self._run_stream(...))`）。

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `agent.task` | `None` | `"What is the result of 2 power 3.7384?"` |
| `agent.memory.steps` | `[]` | `[TaskStep(task="...")]` ← 笔记本第 1 行写好了 |
| `agent.interrupt_switch` | — | `False` |

> 💡 **关键概念**：`self._run_stream(...)` **调用本身不立即跑函数体**（generator 特性 —— 见 [②b agents-stream-naming-explained](02-stream-naming-explained.md)）。它只是返回一个 generator 对象。`list(...)` 才会反复 `next()` 真正驱动函数往下走。

---

## 第 2 幕 · 张三走进流水线（_run_stream 入口）

**张三视角**：开始正式工作。我先把"还没拿到答案"和"现在是第 1 步"两个状态写在便签纸上。

**代码层面**：进入 [`_run_stream`](../../../../src/smolagents/agents.py#L540)，初始化 2 个变量。

**此刻状态**：

| 变量 | 值 |
|---|---|
| `self.step_number` | `1` |
| `returned_final_answer` | `False` |
| 局部 `max_steps` | `4` |

---

## 第 3 幕 · Step 1 启动（建一张空白工作记录）

**张三视角**：

1. 检查"老板按急停了吗？" → 没按
2. "现在该规划一下吗？" → 这次配置不规划，跳过
3. 拿一张空白工作记录纸（ActionStep），上面填"step_number=1，开始时间是现在"，其他字段全留空

**代码层面**（[:545-575](../../../../src/smolagents/agents.py#L545)）：

```python
while not returned_final_answer and self.step_number <= max_steps:
    if self.interrupt_switch: raise AgentError(...)
    if 该规划?(...): ...                                     # 跳过
    action_step = ActionStep(step_number=1, timing=..., observations_images=None)
```

**此刻 `action_step` 长这样**：

只有 `step_number=1` 和 `timing.start_time` 有值，**其他 11 个字段全是 `None`**（model_output / tool_calls / observations / action_output / error / is_final_answer / token_usage / …）。

> 💡 **重点**：这张记录纸是**"等顾问 + 助手填进去"** 的。下一幕我们会看到它怎么被填满。

---

## 第 4 幕 · 顾问 + 助手干活（Step 1 的核心）

**张三视角**：

1. 把笔记本翻给顾问看（`write_memory_to_messages`）
2. 问顾问"下一步该咋办？"
3. 顾问说："先算一下，跑这段代码 → `result = 2 ** 3.7384; print(result)`"
4. 张三把代码交给代码助手 → 代码助手跑出 `13.166094`
5. 张三把"顾问说啥、跑了啥代码、算出啥结果"全部填进刚才那张记录纸

**代码层面**：[:577-580](../../../../src/smolagents/agents.py#L577)

```python
try:
    for output in self._step_stream(action_step):
        yield output
        if isinstance(output, ActionOutput) and output.is_final_answer: ...
```

`_step_stream` 是 [Day 5 才深入的黑盒](03-run-mental-model.md)。它在这一幕里：
- **就地修改** `action_step` 的字段（model_output / tool_calls / code_action / observations 全填上）
- 中途 yield 几个事件（`ToolCall`、`ActionOutput`）给上层透传出去

**这一幕结束后 `action_step` 长这样**：

| 字段 | 值 |
|---|---|
| `step_number` | `1` |
| `model_output` | `"Thought: I should compute...\n```py\nresult = 2 ** 3.7384\nprint(result)\n```<end_code>"` |
| `tool_calls` | `[ToolCall(name="python_interpreter", arguments=<code>)]` |
| `code_action` | `"result = 2 ** 3.7384\nprint(result)"` |
| `observations` | `"Execution logs:\n13.166094..."` |
| `action_output` | `None`（没调 `final_answer`）|
| `is_final_answer` | `False` |

**老板看到了什么**（如果 `stream=True` 跟着看）：

```
事件 ① ToolCall(name="python_interpreter", arguments=<code>)
事件 ② ActionOutput(output=None, is_final_answer=False)
```

---

## 第 5 幕 · Step 1 收尾（finally 块照常跑）

**张三视角**：没出错，但顾问说"还没到最终答案" → 把这一步的工作记录订进笔记本 → 步号 +1 → 进入下一轮。

**代码层面**：[:600-604](../../../../src/smolagents/agents.py#L600) 的 `finally` 块。

```python
finally:
    self._finalize_step(action_step)        # 设结束时间 + 跑 callbacks
    self.memory.steps.append(action_step)   # 订进笔记本
    yield action_step                       # 让老板看到完整 step
    self.step_number += 1                   # 步号 → 2
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `self.memory.steps` 长度 | `1` | `2`（多了 step 1 的 ActionStep）|
| `self.step_number` | `1` | `2` |

**老板看到的事件 ③**：刚才那张完整的 ActionStep 记录纸被 yield 出去了。

---

## 第 6 幕 · Step 2 启动（再来一张空白记录）

**张三视角**：检查 while 条件 —— "还没拿到答案"（True）且 `2 <= 4`（True） → 继续干。再拿一张空白工作记录纸。

**代码层面**：和第 3 幕同构 —— while 头部检查 + 建 `action_step = ActionStep(step_number=2, ...)`

---

## 第 7 幕 · 顾问拍板（Step 2 的关键转折）⭐

**张三视角**：

1. 把笔记本翻给顾问看 —— 这次笔记本已经包含 step 1 的内容（`13.166094` 写在里面了）
2. 顾问看完说："答案就是 13.166094，跑 `final_answer(13.166094)` 就行"
3. 代码助手跑这行 → 触发 `FinalAnswerTool` → 返回 `is_final_answer=True` 的信号
4. 张三的 try 块里**第一次有分支被走进去**：

**代码层面**：[:582-592](../../../../src/smolagents/agents.py#L582)

```python
yield output
if isinstance(output, ActionOutput) and output.is_final_answer:    # ⭐ 这次是 True
    final_answer = output.output                  # = 13.166094
    self.logger.log(...)                          # 漂亮打印
    if self.final_answer_checks: ...              # 跳过
    returned_final_answer = True                  # ⭐ 翻标志位
    action_step.is_final_answer = True
```

**关键变量变化**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `final_answer`（局部）| 不存在 | `13.166094` |
| `returned_final_answer` | `False` | `True` ⭐ |
| `action_step.is_final_answer` | `False` | `True` |

**老板看到了**：`ToolCall` + `ActionOutput(output=13.166094, is_final_answer=True)` —— 这一刻就已经知道答案了，**不用等收尾**。

---

## 第 8 幕 · Step 2 收尾（finally 照常跑）

**张三视角**：把这步记录订进笔记本 → 步号 → 3。

**代码层面**：和第 5 幕一样的 finally 块。

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `self.memory.steps` 长度 | `2` | `3` |
| `self.step_number` | `2` | `3` |

---

## 第 9 幕 · while 循环退场

**张三视角**：再检查 while 头部 —— "还没拿到答案"（False，已经拿到了！）→ **退出循环**。

**代码层面**：[:545](../../../../src/smolagents/agents.py#L545)

```python
while not returned_final_answer (False) and ...:    # 整体 False → 退出
```

**接着检查超时分支**：

```python
if not returned_final_answer and self.step_number == max_steps + 1:
    # not True (False) → 跳过这个 if
```

也跳过。

---

## 第 10 幕 · 必发"完结"通告

**张三视角**：流水线结束，发一份"任务完成通告"给老板。

**代码层面**：[:609-611](../../../../src/smolagents/agents.py#L609)

```python
final_answer_step = FinalAnswerStep(handle_agent_output_types(13.166094))
self._finalize_step(final_answer_step)
yield final_answer_step
```

> 💡 **重点**：`FinalAnswerStep` **不进笔记本**（呼应 [Day 1 final-answer-step.md](../day1-memory/final-answer-step.md) 的"事件不入 memory" 设计）。它只是 yield 出去给老板。

**老板看到的最后一个事件**：`FinalAnswerStep(output=13.166094)`

---

## 第 11 幕 · `run()` 收尾 + 老板拿到结果

**张三视角**：流水线吐完所有事件 → `list()` 把它们收进列表 → 检查最后一个一定是"完结通告" → 抽出答案 → 交给老板。

**代码层面**：[:499-538](../../../../src/smolagents/agents.py#L499)

```python
steps = list(self._run_stream(...))       # 收齐所有 yield 的事件
assert isinstance(steps[-1], FinalAnswerStep)    # ✅ 必发不变量验证
output = steps[-1].output                  # = 13.166094
return output                              # 默认不包 RunResult
```

**老板的脚本**：`result = 13.166094` ✅ 完成。

---

## 老板视角：从头到尾看到的事件清单

如果 `stream=True` 跟着看，老板的 `for` 循环按顺序收到：

```
事件 1   ToolCall(name="python_interpreter", ...)         ← 第 4 幕
事件 2   ActionOutput(is_final_answer=False)              ← 第 4 幕
事件 3   ActionStep(step_number=1, ...)                   ← 第 5 幕（finally 写出去的）

事件 4   ToolCall(name="python_interpreter", ...)         ← 第 7 幕
事件 5   ActionOutput(output=13.166094, is_final=True)    ← 第 7 幕 ⭐ 答案在这里就知道了
事件 6   ActionStep(step_number=2, ...)                   ← 第 8 幕

事件 7   FinalAnswerStep(output=13.166094)                ← 第 10 幕（必发）
```

> 💡 **关键观察**：老板在事件 5 就**已经知道答案**了，不用等到事件 7。这就是 [stream 抽象 §5](../../02-concepts/stream-abstraction-explained.md) 说的"首字节快"价值。

---

## 番外篇 1 · 如果顾问回话格式错了 ⭐

假设第 7 幕里顾问回了个糟糕的回答：

```
Thought: I have the answer.
Code: final_answer(13.166094)     ← 没用 ```py 包代码块！
```

代码助手解析时 `parse_code_blobs` 找不到代码块 → **抛 `AgentParsingError`**。

**和正常剧本的差异**：

| 幕 | 正常 | 出错 |
|---|---|---|
| 第 7 幕 | 拿到 `is_final=True` → 翻标志位 | `_step_stream` 中途抛 `AgentParsingError` |
| 跳过 try 内剩余代码 | — | 进入 [`except AgentError as e:`](../../../../src/smolagents/agents.py#L597) 分支 → `action_step.error = e` |
| finally 块 | 照常 yield + step_number=3 | **照常跑！**（finally 不管异常）yield + step_number=3 |
| 下一轮 while 检查 | 退出（标志位翻了）| **继续！**（标志位没翻，且 3 ≤ 4）|

**第三次 Step**：张三再问顾问 → 笔记本里这次包含 `step 2 错误信息`（`AgentParsingError: 没找到代码块`）→ 顾问看到错误老老实实用 ```py 包代码 → Step 3 成功。

> 💡 **错误事件化** 的具体表现：
> - 老板的 `for` 循环会收到一个**带 `error` 字段**的 ActionStep（事件 6 那个位置）
> - 但 stream **没断** —— 流水线继续转
> - 这就是 [③ mental-model §4](03-run-mental-model.md) 反复强调的："**错误是 ReAct 的反馈信号，不是终止信号**"

> 💡 **如果 LLM 一直犯同样错误** → while 头部 `step_number <= max_steps` 兜底，撞上限后走番外篇 2。

---

## 番外篇 2 · 如果时间不够（max_steps=1）⭐

把配置改成 `max_steps=1`：第 1 步算了但没出 final_answer，第 2 步还没开始就被砍。

**关键差异时刻**：

| 幕 | 正常（max_steps=4）| 时间不够（max_steps=1）|
|---|---|---|
| 第 5 幕 finally | step_number → 2 | step_number → 2 |
| 第 6 幕 while 检查 | `2 <= 4` ✅ 继续 | `2 <= 1` ❌ **退出 while** |
| while 后超时分支 | 不进（已拿到答案）| ⭐ **进入！**（`not False` 且 `2 == 1+1`） |

**进入超时兜底分支**（[:606-608](../../../../src/smolagents/agents.py#L606)）：

1. 张三调 `_handle_max_steps_reached(task)`：
   - 调 `provide_final_answer(task)` —— **让顾问看完整本笔记本，强制写一个总结**
   - 创建一张**新的工作记录** `final_memory_step`，标 `error=AgentMaxStepsError`
   - 把这张新记录订进笔记本（**但没 yield**！）
   - 返回顾问的总结答案
2. 接下来一行 `yield action_step` —— ⚠️ **这里 yield 的是 step 1 的老记录**（局部变量泄漏到 while 外面），新建的 `final_memory_step` 反而没被 yield

**老板看到的事件清单**（对比正常）：

```
正常路径：
  ToolCall(s1) → ActionOutput(s1, is_final=False) → ActionStep(s1)
  → ToolCall(s2) → ActionOutput(s2, is_final=True) → ActionStep(s2)
  → FinalAnswerStep(13.166)

超时路径：
  ToolCall(s1) → ActionOutput(s1, is_final=False) → ActionStep(s1)
  → ActionStep(s1) ⚠️                            ← 重复 yield 了 step 1 的老记录
  → FinalAnswerStep("Based on my computation...")
```

**`RunResult.state` 怎么知道是超时**？

虽然 `final_memory_step` 没被 yield，但**它已经进了笔记本**（`memory.steps[-1]`）。run() 收尾时检查：

```python
if isinstance(getattr(self.memory.steps[-1], "error", None), AgentMaxStepsError):
    state = "max_steps_error"
```

✅ 判定成"超时"。

> 💡 **这就是为什么 `final_memory_step` 必须进笔记本（即使没 yield）**：state 判定靠它。

---

## 一图压缩整个剧本

```
第 0 幕   老板按下 agent.run("...")
第 1 幕   张三准备：task 挂上 / system_prompt 重建 / 笔记本翻新页 / 任务记上第 1 行
第 2 幕   进入流水线 _run_stream，初始化 step_number=1, 没拿到答案=False

  ╔════════════════ while 循环 ════════════════╗
  ║                                            ║
  ║ 第 3 幕  Step 1 建空白工作记录              ║
  ║ 第 4 幕  顾问 + 助手干活，记录被填满         ║
  ║ 第 5 幕  finally：订进笔记本 + step++        ║
  ║                                            ║
  ║ 第 6 幕  Step 2 建空白工作记录              ║
  ║ 第 7 幕  ⭐ 顾问说"答案是 13.166094"         ║
  ║         → returned_final_answer = True     ║
  ║ 第 8 幕  finally：订进笔记本 + step++        ║
  ║                                            ║
  ╚════════════════════════════════════════════╝

第 9 幕   while 退出（标志位翻了）/ 跳过超时兜底
第 10 幕  必发 FinalAnswerStep(13.166094)
第 11 幕  run() 收 list → 抽答案 → 老板拿到 13.166094
```

---

## 接下来：去单步调试（B 方案）

把本笔记当"剧本"放屏幕一边，VS Code 调试器在另一边 —— **每命中一个断点，对照本笔记的"第 N 幕"确认变量值是不是这样**。

| 断点位置 | 应命中第几幕 | 应该看到的 |
|---|---|---|
| [agents.py:436 `def run`](../../../../src/smolagents/agents.py#L436) | 第 0 幕进 / 第 1 幕开始 | self.task=None, memory.steps=[] |
| [agents.py:488 `memory.steps.append(TaskStep)`](../../../../src/smolagents/agents.py#L488) | 第 1 幕 | 笔记本即将多一行 |
| [agents.py:543 `step_number=1`](../../../../src/smolagents/agents.py#L543) | 第 2 幕 | 进入 _run_stream |
| [agents.py:571 build ActionStep](../../../../src/smolagents/agents.py#L571) | 第 3 幕 / 第 6 幕 | step_number=1 / 2，action_step 几乎全 None |
| [agents.py:578 `for output in _step_stream`](../../../../src/smolagents/agents.py#L578) | 第 4 幕 / 第 7 幕 | _step_stream 在 yield 各种事件 |
| [agents.py:582 `is_final_answer` 检查](../../../../src/smolagents/agents.py#L582) | 第 7 幕的⭐转折 | output.is_final_answer=True 这次走进去 |
| [agents.py:601 finally `_finalize_step`](../../../../src/smolagents/agents.py#L601) | 第 5 幕 / 第 8 幕 | action_step 字段已被填满 |
| [agents.py:609 FinalAnswerStep](../../../../src/smolagents/agents.py#L609) | 第 10 幕 | final_answer=13.166094 |
| [agents.py:502 `assert`](../../../../src/smolagents/agents.py#L502) | 第 11 幕 | steps 列表完整 |

**Watch 窗口建议加**：

```
self.step_number
returned_final_answer
action_step.is_final_answer
len(self.memory.steps)
final_answer        ← 第 7 幕之前是 NameError，正常
```

**亲眼验证 5 个 ⭐ 现象**：

1. **笔记本长度的演进**：第 1 幕后 0→1，第 5 幕后 1→2，第 8 幕后 2→3（FinalAnswerStep 不进笔记本！）
2. **action_step 的 13 字段从全 None 到被填满** —— 第 3 幕断点 step over 几次看 Variables 面板
3. **try-finally 的执行顺序**：第 7 幕之后会先看到 `returned_final_answer = True`，**然后**进 finally 块 yield
4. **`final_answer` 变量的诞生**：第 7 幕之前 Watch 显示 `NameError`，第 7 幕后突然有值
5. **stream_outputs=False 时 `_step_stream` yield 多少个事件**：第 4 幕断点处数 next() 命中次数

---

## 相关链接

- 必读前置：[③ agent-run-mental-model.md](03-run-mental-model.md)（抽象骨架 → 本篇是它的具体演出版）
- 上游 ① [multi-step-agent-role-overview.md](01-multi-step-agent-role-overview.md)（项目经理比喻起源）
- 上游 Day 1：[action-step-anatomy.md](../day1-memory/action-step-anatomy.md)（ActionStep 13 字段就是被 _step_stream 填的）
- 上游 Day 4：[smolagents-package-overview.md](00-package-overview.md)、[agents-stream-naming-explained.md](02-stream-naming-explained.md)
- 单步调试指南：[01-setup/vscode-debugging.md](../../01-setup/vscode-debugging.md)
- 实验脚本：[my_first_agent.py](../../../scripts/my_first_agent.py)
- 源码：[agents.py:436 run](../../../../src/smolagents/agents.py#L436)、[agents.py:540 _run_stream](../../../../src/smolagents/agents.py#L540)

## 遗留问题

- [ ] 本剧本里"顾问的假设回答"和真实跑起来差距多大？建议跑一次 `agent.run(...)` 把每一步的 `action_step.model_output` 打印出来对比
- [ ] `stream_outputs=True` 时事件序列里多出的 `ChatMessageStreamDelta` 具体长什么样 —— Day 5 看 _step_stream 时验证
