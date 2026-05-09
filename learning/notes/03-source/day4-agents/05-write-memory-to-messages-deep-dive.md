---
created: 2026-05-08
status: active
tags: [smolagents, agents, memory, messages, day4]
---

# `write_memory_to_messages()` 深挖：把笔记本翻译给顾问看

> 💡 **本篇定位**：原 Day 4 学习计划重点之一 —— **memory → messages 翻译器的总入口**。9 篇笔记里反复提到，但没有专门讲解。本篇补齐。

> ⚠️ **必读前置**：[Day 1 action-step-anatomy](../day1-memory/action-step-anatomy.md)（13 字段 + 5 分支 to_messages）+ [Day 1 final-answer-step](../day1-memory/final-answer-step.md)（事件不入 memory）+ [③ agent-run-mental-model](03-run-mental-model.md)

## 背景 / 动机

[③ mental-model](03-run-mental-model.md) §6 说：

> "每一步内部要先 `write_memory_to_messages()` 把笔记本翻译给顾问看"

但**这一行内部具体在做什么**？为什么 `provide_final_answer` 用 `[1:]` 切片它？为什么有 `summary_mode` 参数？

本笔记一次讲清这个**只有 13 行代码却横跨 Day 1-4 的关键方法**。

---

## 1. 一句话本质

> **`write_memory_to_messages()` 是 Day 1 `to_messages()` 多态契约的总入口** —— 遍历笔记本里所有 Step，调每个 Step 的 `to_messages()` 把它翻译成 ChatMessage，最后拼成给顾问看的"对话历史"。

**项目经理类比**：

```
张三的笔记本（AgentMemory）                       翻译给顾问看的 messages
─────────────────────────                         ─────────────────────
system_prompt 字段:                               [
  SystemPromptStep("...")        ──翻译──►          ChatMessage(role=SYSTEM, ...),    ← messages[0]

steps 字段（list）:                                  ChatMessage(role=USER, "查北京天气"), ← messages[1]
  [0] TaskStep("查北京天气")     ──翻译──►          ChatMessage(role=ASSISTANT, "思考..."),
  [1] ActionStep(step 1, ...)    ──翻译──►          ChatMessage(role=USER, "Observation: ..."),
  [2] ActionStep(step 2, ...)    ──翻译──►          ChatMessage(role=ASSISTANT, "思考..."),
  [3] PlanningStep(...)          ──翻译──►          ...
                                                  ]
```

> ⚠️ **关键澄清**：`SystemPromptStep` **不在 `memory.steps` 列表里**。它是 `AgentMemory` 的**独立字段** `system_prompt`（[memory.py:229](../../../../src/smolagents/memory.py#L229)）。`memory.steps[0]` 永远是 `TaskStep`（如果有 task 的话）。

**翻译机制 = 多态**：每种 Step 的 `to_messages()` 实现不同（[Day 1](../day1-memory/action-step-anatomy.md)），但**调用方式统一**。

---

## 2. 看源码：13 行讲清

[agents.py:758](../../../../src/smolagents/agents.py#L758)：

```python
def write_memory_to_messages(
    self,
    summary_mode: bool = False,
) -> list[ChatMessage]:
    """
    Reads past llm_outputs, actions, and observations or errors from the memory into a series of messages
    that can be used as input to the LLM. Adds a number of keywords (such as PLAN, error, etc) to help
    the LLM.
    """
    messages = self.memory.system_prompt.to_messages(summary_mode=summary_mode)
    for memory_step in self.memory.steps:
        messages.extend(memory_step.to_messages(summary_mode=summary_mode))
    return messages
```

**就这 4 行核心**：

```python
messages = self.memory.system_prompt.to_messages(summary_mode=summary_mode)   # ① 先把 system_prompt 翻译进去
for memory_step in self.memory.steps:                                          # ② 遍历笔记本所有 step
    messages.extend(memory_step.to_messages(summary_mode=summary_mode))        # ③ 调每个 step 的 to_messages 拼接
return messages                                                                 # ④ 返回完整 messages 列表
```

> 💡 **优雅之处** = 完全靠 `to_messages` 多态。`write_memory_to_messages` **不知道每种 Step 怎么翻译** —— 它只负责"按顺序遍历 + 调多态方法"。具体翻译规则全在 Step 子类里（Day 1 学过）。

---

## 3. ⭐ `summary_mode` 参数：什么时候为 True

回顾 Day 1 的设计（[planning-mechanics.md §summary_mode](../day1-memory/planning-mechanics.md)）：

| `summary_mode` | 行为 |
|---|---|
| `False`（默认）| 完整模式 —— 翻译 model_output（"想法"）+ tool_calls + observations + error |
| `True` | 摘要模式 —— 隐藏 model_output（"想法"），只保留 observations / tool_calls（"事实"）|

**`summary_mode=True` 的实际触发场景**：

[agents.py:_generate_planning_step](../../../../src/smolagents/agents.py#L639) 内部，**重规划时**调 `write_memory_to_messages(summary_mode=True)`。

**为什么重规划时要藏起"想法"**：让 LLM 重新规划时**只基于已发生的事实**（observation），不被旧的"我之前想错了"思考路径带偏。

> 💡 **`summary_mode` 是 Day 1 [final-answer-step §summary_mode](../day1-memory/final-answer-step.md) + [action-step-anatomy §summary_mode](../day1-memory/action-step-anatomy.md) 的总开关在这里**。

---

## 4. ⭐ 为什么 `provide_final_answer` 用 `[1:]` 切片

[agents.py:810-845](../../../../src/smolagents/agents.py#L810)：

```python
def provide_final_answer(self, task: str) -> ChatMessage:
    messages = [
        ChatMessage(role=MessageRole.SYSTEM,
                    content=[{"type": "text",
                              "text": self.prompt_templates["final_answer"]["pre_messages"]}])
    ]
    messages += self.write_memory_to_messages()[1:]    # ⭐ 这里 [1:] 切片
    messages.append(
        ChatMessage(role=MessageRole.USER,
                    content=[{"type": "text",
                              "text": populate_template(
                                  self.prompt_templates["final_answer"]["post_messages"],
                                  variables={"task": task})}])
    )
    chat_message = self.model.generate(messages)
    return chat_message
```

**为什么 `[1:]` 切片**：

```
write_memory_to_messages() 返回的列表：
[
  ChatMessage(SYSTEM, system_prompt),      ← messages[0]
  ChatMessage(USER, task),
  ChatMessage(ASSISTANT, ...),
  ...
]
```

`provide_final_answer` 想自己**用 final_answer 模板的 SYSTEM**（"基于 memory 写一个总结答案"），所以**跳过 memory 自带的 SYSTEM**（即 `messages[0]`）。

**最终拼出的 messages**：

```
[
  ChatMessage(SYSTEM, "Based on memory, give final answer..."),  ← 自己拼的
  ChatMessage(USER, task),                                         ← 来自 [1:]
  ChatMessage(ASSISTANT, ...),                                     ← 来自 [1:]
  ...
  ChatMessage(USER, "Now please give final answer for: {task}"),  ← 自己拼的
]
```

> 💡 **这是 max_steps 兜底场景**（用户超时强制让 LLM 写答案）。设计精髓：**不让 memory 自带的 system_prompt 干扰"现在我要你写最终答案"的指令**。

---

## 5. 跟其他笔记的闭环

### 闭环 1 · Day 1 多态契约的兑现

[Day 1 action-step-anatomy.md](../day1-memory/action-step-anatomy.md) 讲：每种 Step 必须实现 `to_messages()`。

**`write_memory_to_messages` 就是这个契约的唯一调用方**。它**信任**每种 Step 都能正确翻译，自己不操心实现。

### 闭环 2 · ③ mental-model §3 _step_stream 第 1 步

```
_step_stream 内部:
  ├─ ⭐ write_memory_to_messages()    ← 这里！把笔记本翻译给顾问
  ├─ self.model.generate(...)
  ├─ 解析输出
  ├─ 执行动作
  └─ 写回 action_step
```

每一步都重新翻译完整笔记本 —— 这就是为什么 LLM 永远能"看到全部历史"，[Week 1 chat-message-roles](../../02-concepts/chat-message-roles.md) 提过的"LLM 是无状态的"在这里得到具体实现。

### 闭环 3 · ②a stream-abstraction §6 layer 2

[②a stream-abstraction](../../02-concepts/stream-abstraction-explained.md) 讲过 **smolagents 3 层 stream 嵌套**：
- Layer 3：agent 步骤流（`_run_stream` yield 的事件）
- Layer 2：LLM token 流（`Model.generate(stream=True)` 透传的 ChatMessageStreamDelta）
- Layer 1：TCP 字节流

**`write_memory_to_messages` 是 Layer 2 的"上料"**：每次 `_step_stream` 调它生成 messages，然后调 `model.generate(messages, stream=True)` —— 这一调就触发了 Layer 2 的 token 流。

---

## 6. 不变量观察

> 💡 **先分清两个数组**：
> - `memory.steps` —— 笔记本里的 Step 对象列表（不含 system_prompt）
> - `messages` —— `write_memory_to_messages()` 翻译后的 ChatMessage 列表
>
> 同一个序号在两个数组里**指向不同对象**。

### 不变量 1 · `messages[0]` 是 SYSTEM 角色（默认情况下）

`memory.system_prompt`（独立字段，**不在 `memory.steps` 里**）在 `__init__` 里被赋值（[agent-init-setup-flow §⑧](04-init-setup-flow.md)），且 `run()` 每次重置时也会重新设（[③ §2 run() 9 件事](03-run-mental-model.md)）。`SystemPromptStep.to_messages()` 默认返回一条 SYSTEM 消息。

所以 `messages[0]` 是 SYSTEM 角色。

> ⚠️ **例外**：`summary_mode=True` 时 `SystemPromptStep.to_messages()` 返回空 list `[]`（[memory.py:204](../../../../src/smolagents/memory.py#L204)），此时 `messages[0]` 不再是 SYSTEM —— 而是 TaskStep 翻译的 USER 消息。**重规划场景**会触发这种情况。

### 不变量 2 · `memory.steps[0]` 是 TaskStep，对应 `messages[1]`

`run()` 第 7 步把 TaskStep append 到 `memory.steps`（[③ §2](03-run-mental-model.md)），且 `memory.reset()` 会清空 `memory.steps` 后才 append —— 所以 **TaskStep 永远在 `memory.steps` 列表的开头**（即 `memory.steps[0]`）。

翻译后的对应位置（默认 `summary_mode=False`）：

```
memory.steps[0] = TaskStep("查北京天气")
                       │
                       │ TaskStep.to_messages() 返回 1 条 USER 消息
                       ▼
messages[1] = ChatMessage(role=USER, content="New task: 查北京天气")
```

`messages[0]` 被 SYSTEM 占了（不变量 1），所以 task 落到 `messages[1]`。

### 不变量 3 · FinalAnswerStep 永远不在 `memory.steps` 里

[Day 1 final-answer-step.md](../day1-memory/final-answer-step.md) 的核心设计：**FinalAnswerStep 是事件不是档案**。

所以 `write_memory_to_messages` **永远不会翻译 FinalAnswerStep**（因为它根本不在 `memory.steps` 里）。

---

## 7. 4 个新手疑问

### Q1：每次 `_step_stream` 都重新翻译全部笔记本，token 不会爆吗？

会。这是 ReAct 的固有代价（[Week 1 codeagent-vs-toolcallingagent](../../02-concepts/codeagent-vs-toolcallingagent.md) 提过）。**Prompt caching 是部分解药**（[Week 1 §prompt-caching](../../02-concepts/codeagent-vs-toolcallingagent.md)）—— 重发的 prefix 走 KV cache。

### Q2：能跳过某些 step 不翻译吗？

可以但要自己改源码。当前实现是无脑翻译全部 —— 这是简洁性的代价。

> 💡 例外：`vision_web_browser.py` 在外部清理 `observations_images = None`，相当于"翻译时不带图"（[③'' event-types §5 Consumer E](03c-stream-event-types.md)）。这是清理 step 字段而不是跳过 step 的策略。

### Q3：能预览翻译结果吗？

可以！直接调：

```python
messages = agent.write_memory_to_messages()
for msg in messages:
    print(f"[{msg.role}] {msg.content}")
```

这是单步调试时**最有价值的一行代码**之一 —— 看 LLM 实际收到什么。

### Q4：`memory_step.to_messages` 返回空列表怎么办？

会发生 —— `summary_mode=True` 时 PlanningStep 的 to_messages **直接 return []**（[Day 1 planning-mechanics §summary_mode](../day1-memory/planning-mechanics.md)）。

`messages.extend([])` 是 no-op，没问题。**翻译可以"主动消失"**。

---

## 8. 关键启示

| 启示 | 含义 |
|---|---|
| **13 行核心代码 = Day 1-4 闭环点** | 多态调用 `to_messages` + 顺序遍历 |
| **完全不知道具体翻译规则** | 全交给 Step 子类（多态契约的兑现）|
| **summary_mode 是"隐藏想法保留事实"的总开关** | 重规划时用 |
| **`provide_final_answer` 切片 `[1:]` 是 prompt 工程** | 替换 system_prompt 让 LLM 听新指令 |
| **3 个不变量** | `messages[0]`=SYSTEM（默认）/ `memory.steps[0]`=TaskStep（对应 `messages[1]`）/ FinalAnswerStep 永不进 `memory.steps` |

---

## 9. 一图：write_memory_to_messages 在整个系统的位置

```
┌──────── 用户调 agent.run("...") ────────┐
│                                        │
│  ┌─ run() 准备阶段 ─┐                   │
│  │ memory.reset()  │ ← 笔记本翻新页    │
│  │ TaskStep 入笔记本│                   │
│  └────────┬────────┘                   │
│           ▼                             │
│  ┌─ _run_stream while ─────────────┐   │
│  │   ┌─ _step_stream ────────┐     │   │
│  │   │ ⭐ write_memory_to_   │     │   │
│  │   │   messages()         │     │   │
│  │   │   ├─ system_prompt    │     │   │
│  │   │   │   .to_messages()  │     │   │
│  │   │   ├─ for step in      │     │   │
│  │   │   │   memory.steps:   │     │   │
│  │   │   │     step.to_msgs()│     │   │
│  │   │   └─ return messages  │     │   │
│  │   │                       │     │   │
│  │   │ model.generate(msgs)  │     │   │
│  │   │ 解析 / 执行 / 写回    │     │   │
│  │   └───────────────────────┘     │   │
│  │   memory.append(action_step)    │   │
│  │   ⭐ 笔记本变长 → 下次翻译会包括它│   │
│  └─────────────────────────────────┘   │
│                                        │
│  超时兜底: provide_final_answer        │
│           └─ write_memory_to_messages()│
│              [1:] ⭐ 切片              │
└────────────────────────────────────────┘
```

---

## 相关链接

- ⚠️ 必读前置：[Day 1 action-step-anatomy.md](../day1-memory/action-step-anatomy.md)、[Day 1 final-answer-step.md](../day1-memory/final-answer-step.md)、[③ agent-run-mental-model.md](03-run-mental-model.md)
- 同系列：[④ agent-init-setup-flow.md](04-init-setup-flow.md)（memory 在 `__init__` 怎么建）
- 上游 Day 1：[planning-mechanics.md](../day1-memory/planning-mechanics.md)（summary_mode 触发场景）、[agent-memory-container.md](../day1-memory/agent-memory-container.md)（AgentMemory 容器）
- 上游 Week 1：[chat-message-roles.md](../../02-concepts/chat-message-roles.md)、[codeagent-vs-toolcallingagent.md](../../02-concepts/codeagent-vs-toolcallingagent.md)（messages 重发机制）
- 源码：[agents.py:758 write_memory_to_messages](../../../../src/smolagents/agents.py#L758)、[agents.py:810 provide_final_answer](../../../../src/smolagents/agents.py#L810)

## 遗留问题

- [ ] `to_messages` 在所有 6 种 MemoryStep 子类的具体实现差异 —— Day 1 各篇笔记零散覆盖，可以做一张对照表
- [ ] Prompt caching 在重发完整 messages 时的命中率到底多高？测一下 —— Week 3 实战
