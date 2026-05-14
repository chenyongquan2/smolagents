---
created: 2026-05-09
status: active
tags: [smolagents, agents, step-stream, mental-model, role-overview, day5, source-reading]
---

# `_step_stream` Role Overview：一步内部的 5 个固定动作

> ⚠️ **必读前置**（按重要性排序）：
> - Day 4 ③ [agent-run-mental-model.md §6](../day4-agents/03-run-mental-model.md#6--一步内部_step_stream-调用前后做了什么day-5-边界) — "一步内部"调用前后已经讲过
> - Day 4 ⑤ [write-memory-to-messages-deep-dive.md](../day4-agents/05-write-memory-to-messages-deep-dive.md) — 动作 1 翻译机制
> - Day 3 ② [model-generate-mental-model.md](../day3-models/model-generate-mental-model.md) — 动作 2 调 LLM
> - Day 1 ⭐ [action-step-anatomy.md](../day1-memory/action-step-anatomy.md) — 13 字段被就地写
> - Week 1 ⭐ [codeagent-vs-toolcallingagent.md](../../02-concepts/codeagent-vs-toolcallingagent.md) — 概念层差异（Day 5 看实现层）
> - Week 1 ⭐⭐ [codeagent-how-it-works.md](../../02-concepts/codeagent-how-it-works.md) — Day 5 之前的最后认知拼图
> - 💡 **延伸阅读** [tools-are-python-callables.md](../../02-concepts/tools-are-python-callables.md) — 两种 agent 调用的工具本质都是 Python callable，差异只在"谁解析参数 + 谁触发调用"。看完 §3-5 两个分歧点回来读这篇，闭环更紧

---

## 1. 一句话定调

`_step_stream(action_step)` 是 **ReAct 一步的实际承担者**：子类（`CodeAgent` / `ToolCallingAgent`）必须实现它，按 **5 个固定动作**把"思考-行动-观察"做完，**就地修改** `action_step` 各字段，然后 yield 一系列事件给 Day 4 外层 `_run_stream` 消费。

> 💡 **Day 4 看的是"老板让谁干、什么时候干、干完怎么收尾"**（外层骨架）；
> **Day 5 看的是"被指派的人到底怎么干这一步"**（内部实现）。
> Day 5 是仓库的"心脏" —— LEARNING_PLAN 里说的就是这一刻。

---

## 2. 谁在调用 / 谁在被调用

**调用方**（Day 4 已知）：

```python
# agents.py:121 (Day 4 ③ §6)
for output in self._step_stream(action_step):  # ← 外层 for 循环消费 yield
    if isinstance(output, ActionOutput) and output.is_final_answer:
        returned_final_answer = True
    yield output  # 透传给最外层 consumer
```

**被调用方**（Day 5 重点）：

| 类 | agents.py 行号 | 实现状态 | 行数 |
|---|---|---|---|
| `MultiStepAgent._step_stream` | [772](../../../../src/smolagents/agents.py#L772) | 软约束 `raise NotImplementedError` | ~10 |
| `ToolCallingAgent._step_stream` | [1276](../../../../src/smolagents/agents.py#L1276) | 完整实现 | ~84 |
| `CodeAgent._step_stream` | [1639](../../../../src/smolagents/agents.py#L1639) | 完整实现 | ~127 |

> ⚠️ **基类是软约束（`raise NotImplementedError`）不是 `@abstractmethod`**。但 Day 4 self-check Q11 实证 `MultiStepAgent.initialize_system_prompt` 是 `@abstractmethod` —— 整个类先在实例化关被硬约束挡住，**根本走不到 `_step_stream`**。两层防御嵌套设计。

---

## 3. ⭐⭐ 5 个固定动作（共同骨架）

两子类**几乎一模一样地走这 5 步**，只在动作 3 和动作 4 有差异：

```
┌────────────────────────────────────────────────────────────────┐
│  ① read messages    (Day 4 ⑤)                                  │
│     write_memory_to_messages() → input_messages                │
│     memory_step.model_input_messages = input_messages          │
├────────────────────────────────────────────────────────────────┤
│  ② call LLM         (Day 3)                                     │
│     model.generate(input, stop=["Observation:", ...], **kw)    │
│     yield ChatMessageStreamDelta × N  (if stream_outputs)       │
│     memory_step.model_output / output_message / token_usage    │
├────────────────────────────────────────────────────────────────┤
│  ③ parse output     ⭐ 分歧点 1                                 │
│     从 LLM 文字输出抠出"动作"                                  │
├────────────────────────────────────────────────────────────────┤
│  ④ execute action   ⭐ 分歧点 2                                 │
│     真的把动作跑一遍                                            │
│     yield ToolCall  (执行前预告)                                 │
│     yield ToolOutput (执行后反馈)                                │
├────────────────────────────────────────────────────────────────┤
│  ⑤ write back + yield                                            │
│     memory_step.tool_calls / observations / action_output      │
│     yield ActionOutput(output, is_final_answer)                  │
└────────────────────────────────────────────────────────────────┘
```

**两子类共享的不止这 5 步骨架**，还有：
- 异常包装：动作 2 的 `try/except` → `AgentGenerationError`；动作 3 的 `try/except` → `AgentParsingError`；动作 4 的 → `AgentExecutionError`（CodeAgent）/ `AgentToolExecutionError`（ToolCallingAgent）
- yield 顺序固定：先 token deltas → 再 ToolCall → 再 ToolOutput → 最后 ActionOutput（ActionStep / FinalAnswerStep 由 Day 4 外层 yield，不在这层）

---

## 4. ⭐ 分歧点 1：动作 3 怎么解析输出

| 子类 | 解析方法 | 输入 | 产出 |
|---|---|---|---|
| **ToolCallingAgent** ([1327-1334](../../../../src/smolagents/agents.py#L1327)) | 优先取 `chat_message.tool_calls`（HTTP `tool_calls` 字段，LLM API 服务器已解析）；空时 fallback `model.parse_tool_calls()` 从文本 regex 抠 | `ChatMessage` | `list[ChatMessageToolCall]` |
| **CodeAgent** ([1703-1714](../../../../src/smolagents/agents.py#L1703)) | structured 模式：`json.loads(output)["code"]`；普通模式：`parse_code_blobs(output_text, code_block_tags)` 从 markdown ` ```python ... ``` ` 抠；最后 `fix_final_answer_code` 容错修补 | `output_text` (str) | `code_action` (str) |

> 💡 **本质区别**：
> - ToolCallingAgent 拿的是**结构化数据**（服务器替你解析过的 JSON），失败时退回文本 regex
> - CodeAgent 拿的是**纯文本中的代码块**（永远要自己解析）
>
> 这印证 Week 1 [codeagent-vs-toolcallingagent.md](../../02-concepts/codeagent-vs-toolcallingagent.md) 的"动作格式不同"。

---

## 5. ⭐ 分歧点 2：动作 4 怎么执行动作

| 子类 | 执行方法 | 单次 vs 并行 | 接口 |
|---|---|---|---|
| **ToolCallingAgent** ([1336 → process_tool_calls](../../../../src/smolagents/agents.py#L1336)) | `execute_tool_call(name, args)` → `tool(**args)` Python 函数调用 | **多 tool call 时 `ThreadPoolExecutor` 并行**（agents.py:1426） | Day 2 的 Tool 类 `__call__` |
| **CodeAgent** ([1727](../../../../src/smolagents/agents.py#L1727)) | `self.python_executor(code_action)` —— 沙箱执行整段代码 | 一段代码一次跑（沙箱内部可能调多个 tool） | Day 6 `local_python_executor` |

**两子类对 final_answer 的判定也不同**：

- ToolCallingAgent：检测 `tool_name == "final_answer"`（agents.py:1406）
- CodeAgent：执行器返回 `code_output.is_final_answer`（沙箱内部 detect `final_answer(...)` 调用）

---

## 6. action_step 13 字段中哪些被 `_step_stream` 就地写

呼应 Day 1 [action-step-anatomy.md](../day1-memory/action-step-anatomy.md) 的 13 字段：

| 字段 | 写入时机 | 谁写 |
|---|---|---|
| `model_input_messages` | 动作 1 末尾 | 两子类共享 |
| `model_output_message` | 动作 2 末尾 | 两子类共享 |
| `model_output` | 动作 2 末尾 | 两子类共享 |
| `token_usage` | 动作 2 末尾 | 两子类共享 |
| `tool_calls` | 动作 5 | 两子类（CodeAgent 合成 1 个 `python_interpreter` ToolCall）|
| `observations` | 动作 5 | 两子类（ToolCallingAgent 拼 ToolOutput.observation；CodeAgent 用 execution logs）|
| `action_output` | 动作 5 | 两子类（CodeAgent 是 `code_output.output`）|
| `code_action` | 动作 3 末尾 | 仅 CodeAgent |
| `error` | 异常时 | finally 里写（Day 4 ③ 已讲）|
| `is_final_answer` | 动作 5 yield | 不写字段，是 `ActionOutput.is_final_answer` |
| `step_number` | 创建时 | Day 4 外层写 |
| `timing` | 进入时创建 + `_finalize_step` 写 end_time | Day 4 外层 |
| `images` | 进入前由调用者塞入 | 用户/外层 |

> 💡 **`_step_stream` 不返回 ActionStep —— 它就地修改传进来的 `action_step` 对象引用**（Day 4 ③ §6 已讲）。这是 Python 对象引用机制，不是魔法。

---

## 7. yield 出去什么（Day 4 ③'' 8 种事件回收）

按 Day 4 [agents-stream-event-types.md](../day4-agents/03c-stream-event-types.md) 的 8 种事件，`_step_stream` 这层只产生其中 4 种：

| 事件类型 | 何时 yield | 谁 yield | 必发吗 |
|---|---|---|---|
| `ChatMessageStreamDelta` | 动作 2 LLM 流式输出每 token | 两子类 | 仅 `stream_outputs=True` |
| `ToolCall` | 动作 4 执行**前**（预告） | 两子类（CodeAgent 合成）| 总会 |
| `ToolOutput` | 动作 4 执行**后**（反馈） | 仅 ToolCallingAgent | 总会（ToolCallingAgent）|
| `ActionOutput` | 动作 5 收尾 | 两子类 | 总会（最后一个 yield）|

> ⚠️ **`ActionStep` 和 `FinalAnswerStep` 不在这层 yield**！它们由 Day 4 外层 `_run_stream` 在每步结束 / 任务终结时 yield。Day 4 ③'''' [设计哲学笔记](../day4-agents/03e-stream-event-design-philosophy.md)讲过事件主体归属：临时事件 vs 持久化档案。

---

## 8. 跟 Day 1-4 的闭环回收清单

| Day | 笔记 | 闭环点 |
|---|---|---|
| **Week 1** | [codeagent-vs-toolcallingagent](../../02-concepts/codeagent-vs-toolcallingagent.md) | 概念层"动作格式不同"→ Day 5 实现层逐字逐行印证 |
| **Week 1** | [codeagent-how-it-works](../../02-concepts/codeagent-how-it-works.md) | Q1-Q4 工具传递路径 / LLM 编排 / 3 Layer 限制 → 全部在 CodeAgent.\_step\_stream 里看到 |
| **Day 1** | [action-step-anatomy](../day1-memory/action-step-anatomy.md) | 13 字段中 9 个被就地写（见 §6） |
| **Day 2** | [tool-schema-rendering](../day2-tools/tool-schema-rendering-mental-model.md) | 4 种渲染中的 2 种被这里使用：HTTP `tools` JSON（ToolCallingAgent 的 `tools_to_call_from`）+ prompt 文字（CodeAgent 的系统提示词）|
| **Day 3** | [model-generate-mental-model](../day3-models/model-generate-mental-model.md) | 动作 2 入口；CodeAgent 还多用 `code_block_tags[1]` 进 stop_sequences |
| **Day 4 ③** | [agent-run-mental-model §6](../day4-agents/03-run-mental-model.md#6--一步内部_step_stream-调用前后做了什么day-5-边界) | 调用前后约定（引用就地修改 / yield 类型）|
| **Day 4 ⑤** | [write-memory-to-messages-deep-dive](../day4-agents/05-write-memory-to-messages-deep-dive.md) | 动作 1 全机制 |
| **Day 4 ③''** | [stream-event-types](../day4-agents/03c-stream-event-types.md) | yield 的 4 种事件归属 |

---

## 9. 一图压缩 Day 5 的"心脏"

```
                    Day 4 _run_stream
                          │
                          ▼  for output in self._step_stream(action_step):
            ┌─────────────────────────────────┐
            │  _step_stream（子类实现）       │
            │  ────────────────────────────   │
            │  ① read messages                │ ← Day 4 ⑤
            │  ② call LLM ──── yield delta    │ ← Day 3
            │  ③ parse output  ★ 分歧点 1     │
            │  ④ execute       ★ 分歧点 2     │
            │     yield ToolCall              │
            │     yield ToolOutput            │
            │  ⑤ write back ─ yield ActionOut │
            └─────────────────────────────────┘
                          │
                          ▼
                外层透传给 consumer (Day 4 ③''')
```

---

## 10. Day 5 接下来怎么读

| 笔记 | 范围 | 学完应能 |
|---|---|---|
| **00 本笔记** | mental model 骨架 | 默写 5 步 + 2 个分歧点 |
| **01-toolcalling-step-stream-impl.md** | agents.py:1276-1502（含 process_tool_calls / execute_tool_call）| 看穿 ToolCallingAgent 84 行 |
| **02-codeagent-step-stream-impl.md** | agents.py:1639-1765 | 看穿 CodeAgent 127 行 + 沙箱接口预告 |
| **03-impl-diff-deep-dive.md** | 两子类逐环节 5 维差异 | 不看代码也能默画分歧点 |
| **04-debugging-walkthrough.md** | `compare_agents.py` 单步调试 | 兑现 LEARNING_PLAN Day 5 验收③ |
| **self-check.md** | 12+ 题自查 | 闭合 Day 5 |

---

## 11. 给 Day 5 学习者的 3 条提醒

1. **CodeAgent 的"沙箱执行"先存疑**：动作 4 调 `python_executor(code)` 本笔记不展开，留给 Day 6。**这一层 Day 5 只看接口，不深入沙箱内部**。
2. **`process_tool_calls` 是 ToolCallingAgent 的重头戏**：1336-1442 共 107 行，比 `_step_stream` 主体（84 行）还长。Day 5 笔记 01 必须分独立一节讲它（含并行执行 + final_answer 特判）。
3. **不要混淆"`tool_calls` 字段"在两个语境**：
   - **`memory_step.tool_calls`**（Day 1）= 持久化的 ToolCall list，记 step 历史
   - **`chat_message.tool_calls`**（Day 3）= 一次 LLM 响应里的 tool_calls 字段，临时态
   - 动作 5 的"写回 memory"就是把后者**规范化后**写进前者。CodeAgent 没有后者（不传 `tools_to_call_from`），所以**合成**了一个 ToolCall 写进前者（让两种 agent 的 log/replay 统一 —— Day 1 ⭐ 已揭示）

---

## 关联阅读

- 上游 Day 4 ③ [agent-run-mental-model §6](../day4-agents/03-run-mental-model.md#6--一步内部_step_stream-调用前后做了什么day-5-边界) — `_step_stream` 的边界已经划好
- 上游 Day 4 ③'' [stream-event-types](../day4-agents/03c-stream-event-types.md) — 8 种事件的位置定位
- Week 1 [codeagent-how-it-works](../../02-concepts/codeagent-how-it-works.md) — Q3 LLM 能写哪些代码（CodeAgent 沙箱预告）
- 下游 Day 6 [local_python_executor.py](../../../../src/smolagents/local_python_executor.py)（待读）— CodeAgent 动作 4 的去处

---

## 自检（学完本笔记应能）

- [ ] 默写 `_step_stream` 的 5 个固定动作（不看本笔记）
- [ ] 一句话说出动作 3 的两子类分歧（提示：结构化数据 vs 纯文本代码块）
- [ ] 一句话说出动作 4 的两子类分歧（提示：函数调用 vs 沙箱执行）
- [ ] 列出 `_step_stream` 这一层 yield 的 4 种事件类型，解释为什么 ActionStep 不在
- [ ] 解释 `memory_step.tool_calls` vs `chat_message.tool_calls` 的差异
