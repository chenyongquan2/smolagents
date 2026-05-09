---
created: 2026-05-08
status: active
tags: [day4, self-check, study-aid, agents, comprehension]
---

# Day 4 自查手册：12 道题 + 详细答案 + 笔记溯源

> **使用方法**：每道题先用纸盖住答案 → 心里答一遍 → 揭开对照 → 答错就点 📖 笔记溯源精读。**不需要一次做完**，Day 5 卡壳时回来补。

> **目的**：验证 Day 4 学习是否到 [LEARNING_PLAN.md:84-90](../../../LEARNING_PLAN.md) 的**层次 3**（"看会 — 让我改/扩展，能动手吗"）。Day 4 是核心循环，必须层次 3。

---

## 题目分布

| # | 类型 | 难度 | 主要考点 | 笔记 |
|---|---|---|---|---|
| 1 | 事实记忆 | ★ | agents.py 内部 9 个类清单 | ⓪ |
| 2 | 事实记忆 | ★ | MultiStepAgent 的 5 类客户 | ① |
| 3 | 概念应用 | ★★ | `_run_stream` 伪代码默写 | ③ |
| 4 | 概念应用 | ★★ | 错误处理 3 层 | ③ |
| 5 | 设计意图 | ★★ | `tools=[]` 为啥有 final_answer | ④ |
| 6 | 跨层闭环 | ★★ | `_step_stream` 既生产又消费 | ②b |
| 7 | 实战应用 | ★★ | `agent.run()` 三种姿势选型 | ③''' |
| 8 | ⭐ 心智模型 | ★★★ | 8 种事件 = 三维度笛卡尔积 | ③'''' |
| 9 | ⭐ 心智模型 | ★★★ | 为何 ActionOutput / ActionStep 不能合并 | ③'''' |
| 10 | 跨笔记闭环 | ★★★ | `write_memory_to_messages()[1:]` 切片 | ⑤ |
| 11 | ⭐⭐ 实证修正 | ★★★ | `MultiStepAgent` 软约束还是硬约束？ | ④ + 实验 |
| 12 | ⭐⭐ 看会层 | ★★★★ | 给 smolagents 加 RAGAgent 需要补什么 | 综合 |

---

## ★ Q1 [事实记忆] agents.py 内部有几个类？怎么分类？

### 题目

agents.py（1814 行）内部除了 `MultiStepAgent` / `CodeAgent` / `ToolCallingAgent` 这 3 个核心类，**还有哪些类**？按 Python 元类型分类。

<details>
<summary>📖 点开看答案</summary>

**总共 11 个类**，按类型分 4 组：

| 类型 | 类 |
|---|---|
| `@dataclass`（3 个）| `ActionOutput` / `ToolOutput` / `RunResult` |
| `TypedDict`（4 个）| `PlanningPromptTemplate` / `ManagedAgentPromptTemplate` / `FinalAnswerPromptTemplate` / `PromptTemplates` |
| `TypeAlias`（1 个）| `StreamEvent` |
| 核心三剑客（1 ABC + 2 子类）| `MultiStepAgent` / `ToolCallingAgent` / `CodeAgent` |

**关键观察**：agents.py 前 265 行**全是数据载体声明**，真正的逻辑从 268 行 MultiStepAgent 开始。

📖 笔记溯源：[⓪ smolagents-package-overview §2](00-package-overview.md)

</details>

---

## ★ Q2 [事实记忆] MultiStepAgent 的 5 类客户角色是什么？

### 题目

MultiStepAgent 面对哪 5 类工作关系？每类对应它的什么入口方法？

<details>
<summary>📖 点开看答案</summary>

| 工作关系 | 谁是对方 | 入口方法 |
|---|---|---|
| **接单**（用户）| 用户脚本 | `run(task)` |
| **带徒弟**（子类）| `CodeAgent` / `ToolCallingAgent` | `_step_stream` 抽象 / `initialize_system_prompt` 抽象 |
| **跟同事协作**（父 agent）| 多 agent 场景的父 agent | `__call__(task)` + `name` + `description` |
| **入档案**（持久化）| 序列化 / HF Hub | `save()` / `to_dict()` / `from_hub()` |
| **被叫停**（中断）| 用户 CTRL-C / Web UI | `interrupt()` |

📖 笔记溯源：[① multi-step-agent-role-overview §1](01-multi-step-agent-role-overview.md)

</details>

---

## ★★ Q3 [概念应用] 默写 `_run_stream` 伪代码

### 题目

合上笔记，默写 `_run_stream` 的核心循环（while 头部 / try-except-finally / 末尾兜底）。**不要求字面一样，关键结构对就行**。

<details>
<summary>📖 点开看答案</summary>

```python
def _run_stream(self, task, max_steps, images):
    self.step_number = 1
    returned_final_answer = False

    while not returned_final_answer and self.step_number <= max_steps:
        if self.interrupt_switch:
            raise AgentError("Agent interrupted.")

        if 该规划吗?(planning_interval, step_number):
            for element in self._generate_planning_step(...):
                yield element
                planning_step = element
            self._finalize_step(planning_step)
            self.memory.steps.append(planning_step)

        action_step = ActionStep(step_number=...)

        try:
            for output in self._step_stream(action_step):
                yield output
                if isinstance(output, ActionOutput) and output.is_final_answer:
                    final_answer = output.output
                    if self.final_answer_checks:
                        self._validate_final_answer(...)
                    returned_final_answer = True
                    action_step.is_final_answer = True

        except AgentGenerationError:
            raise                                       # 实现 bug，立即退出
        except AgentError as e:
            action_step.error = e                       # LLM 错误，记 step 继续
        finally:
            self._finalize_step(action_step)
            self.memory.steps.append(action_step)
            yield action_step
            self.step_number += 1

    # 超时兜底
    if not returned_final_answer and self.step_number == max_steps + 1:
        final_answer = self._handle_max_steps_reached(task)
        yield action_step

    final_answer_step = FinalAnswerStep(handle_agent_output_types(final_answer))
    self._finalize_step(final_answer_step)
    yield final_answer_step
```

📖 笔记溯源：[③ agent-run-mental-model §3](03-run-mental-model.md)

</details>

---

## ★★ Q4 [概念应用] 错误处理 3 层各自的设计意图？

### 题目

`_run_stream` 的 try-except-finally 三层，分别捕什么 / 怎么处理 / 为什么这样设计？

<details>
<summary>📖 点开看答案</summary>

| 层 | 捕什么 | 怎么处理 | 为什么 |
|---|---|---|---|
| `except AgentGenerationError` | **agent 框架自己代码 bug**（实现错误，不是 LLM）| **立即 raise**，整个 run 退出 | 实现 bug 必须 fail-fast，不能掩盖 |
| `except AgentError` | **LLM/解析/工具调用错误**（含 `AgentParsingError` / `AgentToolCallError` 等子类）| 把错误记到 `action_step.error`，**继续下一步** | 让 LLM 自己看到错误，下次循环就修好 —— **错误是反馈信号** |
| `finally` | **不管成败** | 写回 memory + yield + step++ | 保证 step 一定有记录 + 用户一定看得到（错误事件化）+ 不死循环 |

**关键洞察**：错误对外是"事件"不是"异常" —— `finally` 里 `yield action_step` 让 consumer 收到带 `error` 字段的 ActionStep。这呼应 [stream-abstraction-explained §3](../../02-concepts/stream-abstraction-explained.md) "错误传播" 周边概念。

📖 笔记溯源：[③ agent-run-mental-model §4](03-run-mental-model.md)

</details>

---

## ★★ Q5 [设计意图] `tools=[]` 传空列表，为啥 `agent.tools` 里有 `final_answer`？

### 题目

```python
agent = CodeAgent(tools=[], model=...)
print(agent.tools)   # ?
```

会打印什么？为什么？

<details>
<summary>📖 点开看答案</summary>

```python
{'final_answer': <FinalAnswerTool>}    # 还有一个！
```

**机制**：`_setup_tools` 末尾有兜底逻辑（[agents.py:402](../../../../src/smolagents/agents.py#L402)）：

```python
self.tools.setdefault("final_answer", FinalAnswerTool())
```

**为什么必加**：没有 `final_answer` 工具的话，**LLM 没法宣告"我答完了"** → ReAct 循环退不出来 → 必撞 max_steps。

**`setdefault` 的语义**：用户没传同名工具才加。**所以你能传一个自定义的 `final_answer` 工具来覆盖默认行为**。

📖 笔记溯源：[④ agent-init-setup-flow §4 辅助方法 3](04-init-setup-flow.md)

</details>

---

## ★★ Q6 [跨层闭环] 为什么 `_step_stream` "既是生产者又是消费者"？

### 题目

`_step_stream` 在 smolagents 的 stream 体系里**同时扮演两个角色**。具体是哪两个？指向哪两层 stream？

<details>
<summary>📖 点开看答案</summary>

**两个角色**：
1. **L3 步骤流的生产者** —— `_run_stream` 内部 `for output in self._step_stream(...)` 拿到 yield 出来的事件
2. **L2 token 流的消费者** —— `_step_stream` 内部调 `model.generate(stream=True)`，拿到 `ChatMessageStreamDelta` 流（透传给 L3 上层）

**透传机制**：

```python
# _step_stream 内部（伪代码）
for delta in self.model.generate(messages, stream=True):
    yield delta                        # 透传 L2 token 流给 L3 consumer

# 最后还要 yield 自己产的 L3 事件
yield ToolCall(...)
yield ActionOutput(...)
```

> 💡 同一段代码扮演两层 stream 的不同角色（**上层的生产者 = 下层的消费者**），这就是 [stream 嵌套](../../02-concepts/stream-abstraction-explained.md) 的精髓。

📖 笔记溯源：[②b agents-stream-naming-explained §5](02-stream-naming-explained.md)、[stream-abstraction-explained §6](../../02-concepts/stream-abstraction-explained.md)

</details>

---

## ★★ Q7 [实战应用] 3 种 `agent.run()` 姿势的选型

### 题目

下面 3 个场景分别该用哪种 `agent.run()` 姿势？给出参数 + 理由。

1. **场景 A**：写一个 Python 脚本批量跑 100 个 task，把每个 task 的最终答案存到数据库
2. **场景 B**：在 Gradio Web UI 里给用户做实时打字效果
3. **场景 C**：写一个测试，验证某个 task 跑完后总 token 不超过 50000

<details>
<summary>📖 点开看答案</summary>

| 场景 | 姿势 | 代码 |
|---|---|---|
| A 批处理 | `stream=False`（默认）| `result = agent.run(task)` |
| B 实时 UI | `stream=True` + `agent.stream_outputs=True` | `for event in agent.run(task, stream=True): ...` |
| C 测试 token | `return_full_result=True` | `result = agent.run(task, return_full_result=True); assert result.token_usage.input_tokens + ... < 50000` |

**理由**：
- A：批处理 100 个 task，**用户不在线看**，没必要流式 → 默认最简单
- B：Web UI 要"打字效果" → 必须流式 + 打开 token 级流
- C：测试只要总 token，不需要中间事件 → `RunResult` 第 3 种姿势最合适

📖 笔记溯源：[③''' agent-run-stream-modes §2](03d-run-stream-modes.md)

</details>

---

## ★★★ Q8 [⭐ 心智模型] 为什么 smolagents 设计了 8 种事件类型？

### 题目

8 种事件不是"重复设计"。它们是按几个独立维度切分出来的？说出 3 个维度名 + 每个维度的取值。

<details>
<summary>📖 点开看答案</summary>

**3 个独立维度**：

| 维度 | 取值 |
|---|---|
| ① **动作生命周期阶段** | 意图 → 执行 → 结果 → 档案 → 终结 |
| ② **归属 / 责任主体** | LLM / 工具 / 项目经理 |
| ③ **是否进笔记本** | 临时 / 持久化 |

**8 种事件 = 三维度笛卡尔积**。每个事件占独特位置，不可合并。

**关键启示**：这种"事件细粒度暴露"模式不是 smolagents 独创 —— DOM 事件 / Node.js HTTP / Kafka / OpenTelemetry 都是同一套思路。**学一次用一辈子**。

📖 笔记溯源：[③'''' agents-stream-event-design-philosophy §1](03e-stream-event-design-philosophy.md)

</details>

---

## ★★★ Q9 [⭐ 心智模型] 为什么 ActionOutput 和 ActionStep 不能合并？

### 题目

如果合并成一个 BigActionEvent（13 字段），会发生什么问题？两种合并方向（合成胖的 / 合成瘦的）各自代价是什么？

<details>
<summary>📖 点开看答案</summary>

| 合并方向 | 代价 |
|---|---|
| **合成胖 ActionOutput**（13 字段）| `_run_stream` 检查 `is_final_answer` 时**只用 1 个字段**，其他 12 个浪费；且事件**发射时机模糊**（一步执行完就发？还是 finally 才发？）|
| **合成瘦 ActionStep**（2 字段）| **进 memory 时**没地方写 `token_usage` / `error` / `observations` / `model_output` 等字段；LLM 翻笔记本时看不到关键反馈 |

**核心**：拆成两个 = **快信号（极简）+ 完整档案（详细）**，各管各的。

- `ActionOutput` 服务 `_run_stream` 退 while 决策（**单一职责**）
- `ActionStep` 服务"进 memory + 让 LLM 看到反馈"

📖 笔记溯源：[③'''' agents-stream-event-design-philosophy §2 配对 B](03e-stream-event-design-philosophy.md)

</details>

---

## ★★★ Q10 [跨笔记闭环] `provide_final_answer` 的 `[1:]` 切片是什么意思？

### 题目

`provide_final_answer` 里这一行：

```python
messages += self.write_memory_to_messages()[1:]
```

为什么要切片 `[1:]`？切掉的是什么？

<details>
<summary>📖 点开看答案</summary>

**切掉的是 `messages[0]`**，即 `SystemPromptStep` 翻译出的 `role=SYSTEM` 消息。

**为什么要切**：
- `provide_final_answer` 自己**已经拼了一个新的 SYSTEM 消息**（"基于 memory 写最终答案"指令，来自 `prompt_templates["final_answer"]["pre_messages"]`）
- 如果不切，会有**两条 SYSTEM 消息** —— LLM 会困惑听哪条
- 切掉 memory 自带的，**让 LLM 只听新指令**

**最终拼出的 messages 结构**：
```
[
  SYSTEM (final_answer 模板 pre_messages),    ← 新拼的
  USER (task), ASSISTANT (...), ...,         ← 来自 memory[1:]，跳过 SystemPrompt
  USER (post_messages 含 task),              ← 新拼的
]
```

> 💡 **这是 prompt 工程的精髓**：不让旧 system_prompt 干扰新指令。

📖 笔记溯源：[⑤ write-memory-to-messages-deep-dive §4](05-write-memory-to-messages-deep-dive.md)

</details>

---

## ★★★ Q11 [⭐⭐ 实证修正] `MultiStepAgent` 是软约束还是硬约束？

### 题目

老笔记说 `MultiStepAgent` 是"软约束"（理论上能直接实例化，调到 `_step_stream` 才崩）。**实证验证后发现什么**？修正后正确说法是什么？

<details>
<summary>📖 点开看答案</summary>

**实证发现**：直接实例化 `MultiStepAgent(...)` **会立即抛 TypeError**：

```
TypeError: Can't instantiate abstract class MultiStepAgent
           without an implementation for abstract method 'initialize_system_prompt'
```

**原因**：`initialize_system_prompt` **是 `@abstractmethod`**（[agents.py:749](../../../../src/smolagents/agents.py#L749)），不是 `raise NotImplementedError`。

**正确说法**（修正版）：

| 方法 | 约束类型 |
|---|---|
| `initialize_system_prompt` | ⭐ **`@abstractmethod` 硬约束** |
| `_step_stream` | `raise NotImplementedError` 软约束 |

但因为 `initialize_system_prompt` 是硬约束，整个类**实例化阶段就被拦下**。**事实上是混合约束 = 硬约束 + 软约束**。

**设计哲学**：用 `initialize_system_prompt` 当**守门员**（强制硬约束），`_step_stream` 即使是软约束也无所谓 —— 子类已经被守门员强迫继承。

📖 笔记溯源：[实验脚本 abc_soft_constraint_demo.py](../../../scripts/abc_soft_constraint_demo.py)、[① §3 组 C](01-multi-step-agent-role-overview.md)、[④ agent-init-setup-flow §⑧](04-init-setup-flow.md)

</details>

---

## ★★★★ Q12 [⭐⭐ 看会层] 给 smolagents 加一种 RAGAgent 需要补什么？

### 题目

假设你要给 smolagents 加一种新 agent —— `RAGAgent`：它的"动作"不是写代码、不是 JSON tool_calls，而是 **"先调 retriever 取相关文档 → 再让 LLM 基于文档写答案"**。

要让它能跑起来，**至少要补哪些东西**？（结构化作答：哪个父类继承 / 必须实现哪些方法 / 大致逻辑）

<details>
<summary>📖 点开看答案</summary>

**继承 `MultiStepAgent`**（拿到 `_run_stream` 外圈骨架），然后必须补这两块：

### 必须实现的 2 个抽象方法

#### 1. `initialize_system_prompt()`（硬约束 `@abstractmethod`）

写一个 RAG 专用的 system_prompt，告诉 LLM：
- 你的工作流程是 "先 retrieve 再 answer"
- 你需要先输出 retrieve query，工具拿到文档后你再答
- 输出格式（比如 JSON `{"query": "..."} ` 或 markdown 块）

具体读 prompts/ 下的 yaml 模板（参考 CodeAgent / ToolCallingAgent 各自的模板）。

#### 2. `_step_stream(action_step)`（实际"一步内部"逻辑）

需要 yield 这些事件（参考 [③'' event-types](03c-stream-event-types.md)）：

```python
def _step_stream(self, action_step):
    # 1. 翻译 memory 给 LLM
    messages = self.write_memory_to_messages()

    # 2. 调 LLM 拿 retrieve query
    chat_message = self.model.generate(messages)
    action_step.model_output = chat_message.content

    # 3. 解析 query
    query = self._parse_retrieve_query(chat_message.content)
    action_step.tool_calls = [ToolCall(name="retriever", arguments=query)]
    yield ToolCall(name="retriever", arguments=query)

    # 4. 跑 retriever
    docs = self.retriever(query)
    action_step.observations = docs

    # 5. 判断是不是最终答案
    is_final = self._check_final_answer(chat_message.content)
    output = ActionOutput(output=docs if is_final else None, is_final_answer=is_final)
    yield output
```

### 还需要的辅助

- **`__init__`** 重写：加 `retriever` 字段、加载 RAG prompt 模板、调 `super().__init__(...)`
- 解析逻辑（`_parse_retrieve_query` 等私有方法）
- 可能需要的辅助 Tool（retriever 包成 Tool，或者 retriever 自己是另一个 agent）

### 不需要补的（基类已经管）

- ✅ ReAct while 循环、错误处理、超时兜底（`_run_stream`）
- ✅ memory 管理、TaskStep 入笔记本（`run`）
- ✅ 监控 / 回调 / 序列化（基类全套）

> 💡 **设计精髓 = Template Method 模式**：基类定义算法骨架，子类只填变化点。**改 agent 类型只需要改 ~100 行**，整个外圈不用碰。

📖 笔记溯源：[① multi-step-agent-role-overview §3 组 C](01-multi-step-agent-role-overview.md)、[④ agent-init-setup-flow §5](04-init-setup-flow.md)、[③'' agents-stream-event-types §2](03c-stream-event-types.md)

</details>

---

## 🎯 Day 4 完成度自评

按答对题数估算掌握度：

| 答对题数 | 评价 |
|---|---|
| 12 / 12 | 🥇 **大师**：能自己加新 agent 类型，可以进 Day 5 |
| 9-11 | 🥈 **熟练**：核心都懂，Day 5 应该顺利。建议补 Q11+Q12 |
| 6-8 | 🥉 **基本掌握**：进 Day 5 前回头精读错的章节 |
| < 6 | ⚠️ 重读一遍 ③ + ③' + ④ + ⑤ 再来 |

---

## 关键启示（自查后回看）

| 启示 | 含义 |
|---|---|
| **Day 4 = 把 Day 1-3 的零件串起来** | 所有"新概念"几乎都能在前 3 天找到根 |
| **MultiStepAgent 是模板，不是实例** | 你实例化的永远是 CodeAgent / ToolCallingAgent |
| **错误是反馈信号不是终止信号** | finally 块的 yield 让错误事件化 |
| **8 种事件 = 3 维度笛卡尔积** | 单一职责 + 各管各的 |
| **加新 agent 类型只要改 2 个抽象方法** | Template Method 模式的力量 |

---

## 相关链接

- 同系列：[day3-self-check.md](../day3-models/self-check.md)（Day 3 自查 7 道题）
- 全部 Day 4 笔记：见 [README.md Day 4 系列](../../README.md)
- 实验脚本：[abc_soft_constraint_demo.py](../../../scripts/abc_soft_constraint_demo.py)
