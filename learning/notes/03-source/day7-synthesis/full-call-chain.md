---
created: 2026-05-15
status: active
tags: [smolagents, synthesis, call-chain, day7, week2-summary]
---

# Week 2 综合：完整调用链全图

> 📋 **本笔记定位**：Week 2 Day 7 综合产出 —— **不读新源码**，把 Day 1-6 已经学过的内容**串成一张完整的调用链图**。
>
> Week 2 LEARNING_PLAN 终极目标兑现：
>
> > "能默画出这张调用链 —— User 输入 task → memory 加 task → model 生成 → 解析代码 → 执行 → 结果回 memory → 再生成…直到 final_answer。**每个箭头都能指出对应哪个文件、哪个函数、哪一行**。"

---

## 0. 一句话定调

一次 `agent.run("...")` 调用，是**外循环（Day 4）反复触发内循环（Day 5），内循环每幕都用 Day 1-3 / Day 6 的零件**，直到拿到 `final_answer` 或超 `max_steps` 退出。

```
Day 4 外层骨架   →   Day 5 一步内部   →   Day 1-3 / Day 6 零件
    (主控)             (心脏)               (砖瓦)
```

---

## 1. 一图压缩：完整调用链全景

用 [compare_agents.py](../../../scripts/compare_agents.py) 任务（CodeAgent 跑 "查 3 城市最高温转华氏"）作为参照剧本，画完整调用链：

```
用户：agent.run("Find temp of Beijing/Tokyo/Singapore, max → Fahrenheit") ← Day 4 ③
   │
   ▼
┌─ MultiStepAgent.run() ────────────────────────────────────── Day 4 ④ + ③ ─┐
│  9 件事：解析 max_steps → 写 self.task → 清中断标志                          │
│           → reset memory → 重拼 system_prompt（Day 4 ④ initialize_*）        │
│           → memory.steps.append(TaskStep(...))      ← Day 1 memory.py        │
│           → 选 stream vs 非 stream                  ← Day 4 ③'''             │
│           → list(self._run_stream(task, max_steps, images))                  │
└────────────────────┬─────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─ _run_stream() (Day 4 ③ §5) ───────────────────────────────────────────────┐
│  while not returned_final_answer and step_number <= max_steps:               │
│      if interrupt_switch: raise                                              │
│      if is_planning_step?: yield from _generate_planning_step ← Day 1 plan   │
│      action_step = ActionStep(step_number=N, timing=...)  ← Day 1            │
│      try:                                                                    │
│          for output in self._step_stream(action_step):       ◄── ★ Day 5    │
│              if isinstance(output, ActionOutput) and output.is_final_answer: │
│                  returned_final_answer = True                                │
│              yield output                                                    │
│      except AgentError as e: action_step.error = e                          │
│      except AgentGenerationError: raise   ← 冲出外层 fail-fast (Day 4 ③)    │
│      finally:                                                                │
│          self._finalize_step(action_step)                                    │
│          self.memory.steps.append(action_step)   ← Day 1                     │
│          yield action_step       ← step 结束档案 (Day 4 ③'')                │
│          step_number += 1                                                    │
│                                                                              │
│  收尾：if not returned_final_answer: _handle_max_steps_reached()             │
│        yield FinalAnswerStep(final_answer)  ← Day 1 事件不入 memory.steps    │
│        return RunResult(content, state, ...) ← Day 4 ③ token 聚合           │
└────────────────────┬─────────────────────────────────────────────────────────┘
                     │
                     ▼ for each step (重复 N 次直到 final)
┌─ _step_stream(action_step) ★ Day 5 心脏 ────────────────────────────────────┐
│                                                                              │
│  ① read messages                                                             │
│     write_memory_to_messages()   ← Day 4 ⑤ 多态翻译                        │
│     按 Day 1 各 Step.to_messages() 把 memory.steps 翻译成 [SYS, USER, ...]   │
│     memory_step.model_input_messages = ...                                   │
│                                                                              │
│  ② call LLM                                                                  │
│     model.generate(input, stop_sequences=..., tools_to_call_from=...)        │
│     ↓ Day 3 入口                                                             │
│     ┌─ Model._prepare_completion_kwargs (Day 3 ②) ─────────────────────┐    │
│     │   ① 清洗 messages（role 转换 + 连续合并）                          │    │
│     │   ② 写 specific 参数（HTTP tools 字段 ⭐ Day 2 §5）              │    │
│     │   ③ caller kwargs ④ self.kwargs 压舱石 (Day 3 ②)                │    │
│     │   ⑤ 返回 completion_kwargs                                        │    │
│     └────────────────────────────────────────────────────────────────────┘    │
│     ↓                                                                        │
│     发 HTTP 请求 → LLM API 服务器（Day 3 概念笔记）→ LLM 模型               │
│     ↓ 拿到 ChatMessage                                                       │
│     memory_step.model_output_message / model_output / token_usage           │
│     yield ChatMessageStreamDelta × N (if stream)  ← Day 4 ③''               │
│                                                                              │
│  ③ parse output    ⭐ 分歧点 1                                              │
│     ToolCalling: chat_message.tool_calls + parse_json_if_needed              │
│     CodeAgent:   parse_code_blobs(text, code_block_tags) + fix_final_answer  │
│                                                                              │
│  ④ execute action  ⭐ 分歧点 2                                              │
│     ToolCalling:                                                             │
│       process_tool_calls (Day 5 01 §6.1):                                   │
│         阶段 A: yield ToolCall × N                                          │
│         阶段 B: ThreadPoolExecutor + copy_context() 并行                    │
│           → execute_tool_call (Day 5 01 §6.3):                              │
│             查名 + state 替换 + validate_tool_arguments + tool(**args)      │
│           → yield ToolOutput × N                                            │
│     CodeAgent:                                                               │
│       python_executor(code_action)  ─── Day 6 入口 ───────────────────┐    │
│         ↓ LocalPythonExecutor.__call__                                  │    │
│         ↓ evaluate_python_code (Day 6 01):                              │    │
│           ① ast.parse(code) → AST 树                                    │    │
│           ② 初始化 state / static_tools                                  │    │
│           ③ ⭐ 包装 final_answer → raise FinalAnswerException           │    │
│           ④ ⭐⭐ for node in AST: evaluate_ast(node, ...)              │    │
│              ├─ Assign → evaluate_assign                                │    │
│              ├─ Call → evaluate_call → tool(args) ← Day 2 Tool.__call__│    │
│              ├─ Import → evaluate_import → 白名单检查 ← Day 6 §3 层 1  │    │
│              ├─ BinOp / For / If / ... (30+ evaluator)                  │    │
│              └─ 危险 builtins → InterpreterError ← Day 6 §3 层 2       │    │
│           ⑤ 捕获 FinalAnswerException → is_final=True                   │    │
│         ↓ 返回 CodeOutput(output, logs, is_final_answer)                │    │
│       ────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ⑤ write back + yield                                                       │
│     memory_step.tool_calls / observations / [code_action] / [action_output] │
│     yield ActionOutput(output, is_final_answer)  ← Day 4 ③''                │
└────────────────────┬─────────────────────────────────────────────────────────┘
                     │
                     ▼ 控制权回到 _run_stream
              if is_final_answer:  returned_final_answer = True
              else:                step_number += 1，继续下一轮
              ...
```

**全 Week 2 知识浓缩到一张图**。后面 §2-§8 是这张图的 zoom in。

---

## 2. 顶层：用户调用 → run() （Day 4 ④）

[agents.py:436](../../../../src/smolagents/agents.py#L436) `MultiStepAgent.run()` 9 件事（[Day 4 ④ init-setup-flow](../day4-agents/04-init-setup-flow.md) 详）：

```
1. 解析 max_steps           （None → 用实例 max_steps）
2. self.task = task         （记墙上）
3. 清 self.interrupt_switch
4. 重拼 system_prompt        （子类 initialize_system_prompt）← Day 4 ④
5. reset memory + monitor    （Day 1 AgentMemory）
6. 打日志
7. memory.steps.append(TaskStep(task=task))  ← Day 1
8. send_tools / send_variables 给 python_executor（如果 CodeAgent）← Day 6
9. 选 stream vs 非 stream → list(self._run_stream(...))
                                   或者 → return self._run_stream(...)
```

**调用方式分支**（[Day 4 ③''' stream-modes](../day4-agents/03d-run-stream-modes.md)）：

| 调用方式 | run() 返回 |
|---|---|
| `agent.run(task)` | `Any`（最终答案）|
| `agent.run(task, return_full_result=True)` | `RunResult` |
| `agent.run(task, stream=True)` | `Generator`（让外部 for 循环消费）|

---

## 3. 外循环：_run_stream() 反复跑 step（Day 4 ③）

[agents.py:540](../../../../src/smolagents/agents.py#L540) `_run_stream()` 伪代码（[Day 4 ③ run-mental-model](../day4-agents/03-run-mental-model.md) 详）：

```python
self.step_number = 1
returned_final_answer = False

while not returned_final_answer and self.step_number <= max_steps:
    # ── 中断检查 ──
    if self.interrupt_switch: raise AgentError(...)

    # ── 周期性规划（Day 1 planning-mechanics）──
    if self.planning_interval and self.step_number % self.planning_interval == 1:
        yield from self._generate_planning_step(task, ...)

    # ── 新建 action_step ──
    action_step = ActionStep(
        step_number=self.step_number,
        timing=Timing(start_time=time.time()),
    )

    # ── 内循环 ──
    try:
        for output in self._step_stream(action_step):   # ★ Day 5
            if isinstance(output, ActionOutput) and output.is_final_answer:
                returned_final_answer = True
            yield output
    except AgentError as e:
        action_step.error = e                            # ReAct 反馈信号
    # 注意: AgentGenerationError 是冲出外层（Day 4 ③ §错误处理 3 层）

    finally:
        self._finalize_step(action_step)                 # 触发 step_callbacks
        self.memory.steps.append(action_step)            # Day 1
        yield action_step                                # Day 4 ③'' step 档案

    self.step_number += 1

# ── 收尾 ──
if not returned_final_answer:
    final_answer = self._handle_max_steps_reached(task)  # 兜底
else:
    final_answer = last_action_output

yield FinalAnswerStep(final_answer)                      # Day 1 事件不入 memory.steps

if return_full_result:
    return RunResult(content=final_answer, state=..., messages=..., ...)
else:
    return final_answer
```

**关键事实**：`_run_stream` 是 generator —— 调用它**不立即跑**，被 `list(...)` 或 for 循环驱动才动（[Day 4 ②a stream-naming](../day4-agents/02-stream-naming-explained.md)）。

---

## 4. 内循环：_step_stream() 5 步骨架（Day 5 心脏）

详见 [Day 5 00 mental-model](../day5-step-stream/00-step-stream-role-overview.md) + [01 ToolCalling 演出版](../day5-step-stream/01-toolcalling-walkthrough.md) + [02 CodeAgent 演出版](../day5-step-stream/02-codeagent-walkthrough.md)：

```
① read messages    write_memory_to_messages() → input_messages
                   memory_step.model_input_messages = ...

② call LLM         model.generate(input, stop, [tools])
                   yield ChatMessageStreamDelta × N (if stream)
                   memory_step.model_output / model_output_message / token_usage

③ parse output     ⭐ 分歧点 1
                   ToolCalling: chat_message.tool_calls + parse_json_if_needed
                   CodeAgent:   parse_code_blobs + fix_final_answer_code

④ execute action   ⭐ 分歧点 2
                   ToolCalling: process_tool_calls → execute_tool_call → tool(**args)
                                yield ToolCall × N → yield ToolOutput × N
                   CodeAgent:   python_executor(code) → CodeOutput
                                yield ToolCall(合成的 "python_interpreter")

⑤ yield ActionOutput(output, is_final_answer)
   memory_step.tool_calls / observations / [code_action] / [action_output]
```

**两子类 9 维度差异**详见 [Day 5 03 impl-diff-deep-dive](../day5-step-stream/03-impl-diff-deep-dive.md)。

---

## 5. 沙箱执行：python_executor 内部（Day 6）

CodeAgent 第 ④ 步进入 [Day 6 01 evaluate-python-code-walkthrough](../day6-executor/01-evaluate-python-code-walkthrough.md) 5 幕：

```
LocalPythonExecutor.__call__(code_action):
  evaluate_python_code(code, static_tools, ...):
    
    第 1 幕: ast.parse(code) → AST 树（[Day 6 00 §5 AST 解释器入门](../day6-executor/00-sandbox-role-overview.md)）
    
    第 2 幕: 初始化 state["_print_outputs"] / state["_operations_count"]
    
    第 3 幕: ⭐ 包装 final_answer →
             def final_answer(*args): raise FinalAnswerException(原final(*args))
    
    第 4 幕: ⭐⭐ 遍历 AST 节点
             for node in expression.body:
                 evaluate_ast(node, ...)
                 ├─ 30+ evaluate_xxx 函数（按节点类型分发）
                 ├─ 每个 evaluator 检查 3 层防御（Day 6 §3）
                 │   层 1: 白名单 import
                 │   层 2: 危险 builtins 拦截
                 │   层 3: 资源限制（timeout / MAX_OPERATIONS）
                 └─ tool 调用 → 进 Day 2 Tool.__call__ 框架包装层
    
    第 5 幕: 捕获 FinalAnswerException → return (value, True)
             或捕获 Exception → 包装 InterpreterError 抛
             或正常结束 → return (last_result, False)
  
  return CodeOutput(output, logs, is_final_answer)
```

---

## 6. 零件层：Tool / Model / Memory 怎么被调（Day 1-3）

### Tool 调用链（Day 2）

无论 ToolCallingAgent 还是 CodeAgent，最终都汇到：

```
Tool.__call__(**args, sanitize_inputs_outputs=True)   ← Day 2 ② 框架包装层
   ↓ lazy setup / 输入清洗
Tool.forward(**args)                                  ← 用户写的业务逻辑
   ↓
工具返回值（可能是 AgentImage / AgentAudio → 进 state，呼应 Day 5 02 番外 3）
```

**两子类的差异不在 Tool 本身**，在"谁解析参数 + 谁触发调用"（[tools-are-python-callables](../../02-concepts/tools-are-python-callables.md)）。

### Model 调用链（Day 3）

```
agent → Model.generate(messages, stop, tools_to_call_from, ...)
        ↓
        Model._prepare_completion_kwargs (Day 3 ②):
          ① 清洗 messages（含 role 转换 + 连续合并）
          ② 写 specific 参数（HTTP tools 字段 ← Day 2 §5 闭环）
          ③ caller kwargs
          ④ self.kwargs 压舱石 + REMOVE_PARAMETER 哨兵
          ⑤ 返回 completion_kwargs
        ↓
        子类（InferenceClientModel / OpenAIModel / ...）:
          ① pre-check 协议兼容
          ② 拼 body
          ③ rate_limit 节流
          ④ retry 包裹下真发请求
          ⑤ 解析 + stop fallback strip + 包 ChatMessage
        ↓
        返回 ChatMessage（含 content / tool_calls / token_usage）
```

呼应 [Day 3 inference-client-model-impl](../day3-models/inference-client-model-impl.md)。

### Memory 数据流（Day 1）

```
TaskStep        ← run() 第 7 件事 写入 memory.steps[0]
SystemPromptStep ← initialize_system_prompt 写入（reset 时）
ActionStep × N  ← 每步内循环结束 _run_stream finally 块 append
PlanningStep    ← 周期触发（planning_interval 公式 1, 1+N, 1+2N）
FinalAnswerStep ← 任务终结 yield（⭐ 事件，不入 memory.steps）

write_memory_to_messages():     ← Day 4 ⑤ 翻译机制总入口
  for step in memory.steps:
      messages.extend(step.to_messages(summary_mode))
                       ↑ Day 1 多态契约
```

---

## 7. 事件流：8 种 yield 事件全景（Day 4 ③''）

整个 `agent.run(stream=True)` 期间，外部 consumer 可能收到的 8 种事件：

| 事件 | 哪一层 yield | 何时 |
|---|---|---|
| `ChatMessageStreamDelta` | _step_stream 第 ② 幕 | LLM 每 token |
| `ChatMessageToolCall` | LLM API 服务器返回（不算 yield，是 ChatMessage 字段）| 第 ② 幕末 |
| `ToolCall` | _step_stream 第 ④ 幕 | 执行前预告 |
| `ToolOutput` | ToolCallingAgent 独有 第 ④ 幕 | 执行后反馈 |
| `ActionOutput` | _step_stream 第 ⑤ 幕 | 步内部收尾 |
| `PlanningStep` | _generate_planning_step | 周期触发 |
| `ActionStep` | _run_stream finally 块 | 每步结束档案 |
| `FinalAnswerStep` | _run_stream 收尾 | 任务终结 |

**消费者** 用 `isinstance` 派发处理（[Day 4 ③''' stream-modes](../day4-agents/03d-run-stream-modes.md)）。

---

## 8. 一个完整剧本：compare_agents.py CodeAgent 跑"3 城市最高温" 全程

```
[t=0]  user: agent.run("Find temp of Beijing/Tokyo/Singapore, max → Fahrenheit")
[t=0+] run() 9 件事:
       memory.steps = [SystemPromptStep, TaskStep(task=...)]
       
[t=1]  进入 _run_stream → while loop iteration 1
       action_step = ActionStep(step_number=1, ...)
       
[t=1.1] 进入 _step_stream:
        ① write_memory_to_messages → [SYS, USER]
           memory_step.model_input_messages = [SYS, USER]
        ② model.generate(messages, stop=[..., "</code>"], 不传 tools)
           ↓ Model._prepare_completion_kwargs → HTTP body
           ↓ HTTP POST → HF Inference → Qwen2.5-72B
           ↓ ChatMessage(content="...<code>temps=[...]; final_answer(...)</code>", tool_calls=None)
           memory_step.model_output = "代码字符串"
        ③ parse_code_blobs → code_action = "temps=...; final_answer(...)"
           fix_final_answer_code(code_action) → 无变化
           memory_step.code_action = code_action
           合成 tool_call = ToolCall("python_interpreter", code_action, id="call_2")
           yield tool_call
        ④ python_executor(code_action):
           evaluate_python_code(...):
             第 1 幕: ast.parse → AST 树
             第 2 幕: state["_print_outputs"] = PrintContainer()
             第 3 幕: final_answer 被替换为 raise FinalAnswerException
             第 4 幕: for node in AST.body:
                       evaluate_ast(Assign1) → 调 get_temperature("Beijing") → 25.0
                                              调 get_temperature("Tokyo")   → 30.0
                                              调 get_temperature("Singapore") → 28.0
                                              state["temps"] = [25.0, 30.0, 28.0]
                       evaluate_ast(Assign2) → max([25,30,28]) = 30.0
                                              state["max_temp"] = 30.0
                       evaluate_ast(Expr)    → final_answer(30*1.8+32)
                                              → final_answer(86.0)
                                              → raise FinalAnswerException(86.0)
             第 5 幕: 捕获 → return (86.0, True)
           return CodeOutput(output=86.0, logs="", is_final_answer=True)
           
           memory_step.observations = "Execution logs:\n\nLast output: 86.0"
           memory_step.action_output = 86.0
        ⑤ yield ActionOutput(output=86.0, is_final_answer=True)

[t=1.99] _step_stream generator 终止
[t=2]    _run_stream:
         returned_final_answer = True
         finally: _finalize_step → memory.steps.append(action_step) → yield action_step
         step_number = 2 (但 while 条件不满足，退出)

[t=2.1]  yield FinalAnswerStep(86.0)
         return RunResult(content=86.0, state=..., messages=..., ...)
         
[t=2.2]  user 拿到结果：86.0
```

**LLM 调用总次数 = 1**（CodeAgent 一段代码塞所有逻辑），耗时主要在沙箱执行（毫秒级）+ LLM 调用（秒级）。

对比 ToolCallingAgent 同任务 = 4 步 4 次 LLM 调用（[Day 5 03 §10 实测](../day5-step-stream/03-impl-diff-deep-dive.md)）。

---

## 9. Week 2 知识地图（笔记如何拼成完整图景）

```
┌─ 入口（Day 4 ④）────────────────────────────────────────────────────┐
│ agent.run() 9 件事 ── multi-step-agent-role-overview + init-setup-flow │
└──────────────────────────────────────────────────────────────────────┘
                              ↓ list(self._run_stream(...))
┌─ 外循环（Day 4 ③ ③' ③'' ③''' ③''''）───────────────────────────────┐
│ _run_stream → while loop + step build + try/except/finally           │
│ run-mental-model + run-walkthrough-leopard-demo                       │
│ stream-event-types + stream-event-design-philosophy + stream-modes    │
└──────────────────────────────────────────────────────────────────────┘
                              ↓ for output in _step_stream(action_step)
┌─ 内循环 ★（Day 5 00-04）──────────────────────────────────────────────┐
│ _step_stream 5 步骨架 → ToolCalling vs CodeAgent 演出版 + 9 维度对比 │
│ step-stream-role-overview + toolcalling-walkthrough + codeagent-...   │
│ impl-diff-deep-dive + debugging-walkthrough                           │
└──────────────────────────────────────────────────────────────────────┘
                              ↓ ① ② → Day 3 ② / Day 4 ⑤
                              ↓ ③ → utils.py / model.parse_tool_calls
                              ↓ ④ → process_tool_calls / python_executor
                              ↓ ⑤ → ActionOutput yield
┌─ 沙箱（Day 6 00-01）────────────────────────────────────────────────┐
│ python_executor → evaluate_python_code 5 幕 + 3 层防御              │
│ sandbox-role-overview + evaluate-python-code-walkthrough            │
└──────────────────────────────────────────────────────────────────────┘
                              ↓ 内部调
┌─ 零件层 ─────────────────────────────────────────────────────────────┐
│ Day 1 memory.py: AgentMemory + 7 Step + to_messages 多态契约         │
│ Day 2 tools.py: Tool 类 + 4 渲染 + 出厂/上岗 2 次质检                 │
│ Day 3 models.py: Model + _prepare_completion_kwargs + InferenceClient │
└──────────────────────────────────────────────────────────────────────┘
```

**6 天源码 + 1 天综合 = 1 张图**。

---

## 10. 这张图的"必须能默画"程度（Day 7 验收）

LEARNING_PLAN Day 7 要求：「能默画出调用链，**每个箭头都能指出对应哪个文件、哪个函数、哪一行**」。

具体自检：

- [ ] `agent.run` 入口在哪个文件哪行？（`agents.py:436 MultiStepAgent.run`）
- [ ] `_run_stream` 在哪？（`agents.py:540`）
- [ ] `_step_stream` 基类 / ToolCalling / CodeAgent 各在哪？（`772 / 1276 / 1639`）
- [ ] `evaluate_python_code` 在哪？（`local_python_executor.py:1583`）
- [ ] `write_memory_to_messages` 在哪？（`agents.py:760` 附近 / Day 4 ⑤）
- [ ] Model 基类 `generate` 抽象在哪？（`models.py:?` 软约束）
- [ ] `_prepare_completion_kwargs` 在哪？（`models.py:540` 附近）
- [ ] Tool 类基础在哪？（`tools.py:144` 附近）
- [ ] memory 7 个 Step 类在哪？（`memory.py` 全文 316 行）

能答出 7 个以上 = Day 7 通过。

---

## 关联阅读

- 上游 Day 1-6 全部笔记
- LEARNING_PLAN 末尾 "Week 2 学习总结"（认知层面的提炼）
- 下游 Week 3 自定义 Tool + 改造 example
- 下游 Week 4 多 agent / MCP / 沙箱进阶
