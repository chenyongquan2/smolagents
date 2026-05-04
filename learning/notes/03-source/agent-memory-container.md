---
created: 2026-05-03
status: active
tags: [memory, container, source-reading, week2-day1]
---

# AgentMemory 容器：所有 Step 的"家"

## 背景 / 动机

Day 1 阶段 3。把 [memory.py:214-277](../../../src/smolagents/memory.py:214) 的 `AgentMemory` 类单独成文。这是 Step 家族的**收纳盒**，前面读完的 6 个 Step 类都通过它管理。

源码共 64 行，2 个数据成员 + 5 个工具方法。

---

## 一、整体结构

```python
class AgentMemory:
    """Memory for the agent, containing the system prompt and all steps taken by the agent."""

    def __init__(self, system_prompt: str):
        self.system_prompt: SystemPromptStep = SystemPromptStep(system_prompt=system_prompt)
        self.steps: list[TaskStep | ActionStep | PlanningStep] = []

    def reset(self): ...
    def get_succinct_steps(self) -> list[dict]: ...
    def get_full_steps(self) -> list[dict]: ...
    def replay(self, logger, detailed=False): ...
    def return_full_code(self) -> str: ...
```

两个数据成员 + 5 个工具方法。其他全部交给 Step 子类自己负责（`to_messages` / `dict` / `is_final_answer` 等）。

---

## 二、两个数据成员（[memory.py:228-230](../../../src/smolagents/memory.py:228)）

```python
def __init__(self, system_prompt: str):
    self.system_prompt: SystemPromptStep = SystemPromptStep(system_prompt=system_prompt)
    self.steps: list[TaskStep | ActionStep | PlanningStep] = []
```

### 看点

#### ① `system_prompt` 独立挂载，不进 `steps[]`

为什么？因为 `reset()` 时**要保留它**（见下文）。如果把 system_prompt 也塞进 steps，reset 时就丢了。

→ **结构上分开 = 语义上的耦合解开**。

#### ② `__init__` 接收 `str` 但内部存 `SystemPromptStep`

入参方便用户（直接传字符串），存储统一格式（包成 Step 对象，享受 `to_messages()` 多态）。

→ 这是经典的**接口适配器模式**：对外是字符串，对内是统一 Step。

#### ③ ⭐ `steps` 类型注解里**没有 `FinalAnswerStep`**！

```python
self.steps: list[TaskStep | ActionStep | PlanningStep] = []
```

注意 union 里**只有 3 种**：TaskStep / ActionStep / PlanningStep。**没有 FinalAnswerStep**。

→ 这正是 [final-answer-step.md](final-answer-step.md) 讲的"FinalAnswerStep 走事件通道不走持久化通道"的**类型层证据**。框架在类型注解里就**显式排除**了它。

> 💡 **设计精髓**：当类型注解都明确写出"FinalAnswerStep 不可能出现在这里"时，**这个设计是显式的、有意识的**，不是偶然没写。

---

## 三、5 个工具方法

### 1. `reset()` ([memory.py:232-234](../../../src/smolagents/memory.py:232))

```python
def reset(self):
    self.steps = []        # 只清 steps，不动 system_prompt
```

**用途**：同一个 agent 实例跑多次 task 时，希望每次"忘掉上次的过程"但**保留人设/约束**。

```python
agent.run("第一个 task")
# memory.steps 现在有 5 个 step
agent.memory.reset()
agent.run("第二个 task")
# 第二次跑时不会被第一次的痕迹污染
```

回忆 [action-step-anatomy.md](action-step-anatomy.md) Q1 答案：**不 reset 的话，第二次 run 会带着第一次的 memory.steps**。这就是 reset 存在的意义。

### 2. `get_succinct_steps()` vs 3. `get_full_steps()` ([memory.py:236-246](../../../src/smolagents/memory.py:236))

```python
def get_succinct_steps(self) -> list[dict]:
    return [
        {key: value for key, value in step.dict().items() if key != "model_input_messages"}
        for step in self.steps
    ]

def get_full_steps(self) -> list[dict]:
    if len(self.steps) == 0:
        return []
    return [step.dict() for step in self.steps]
```

**对比**：

| 方法 | 含 `model_input_messages`？ | 用途 |
|---|---|---|
| `get_full_steps()` | ✅ 含 | 完整 dump，存盘/回放 |
| `get_succinct_steps()` | ❌ 砍掉 | 控制台调试、UI 显示，避免被巨大的 messages 历史淹没 |

**为什么 `model_input_messages` 是大头**？回忆 [action-step-anatomy.md](action-step-anatomy.md)：每个 ActionStep 都存了"这次发给 LLM 的完整 messages 历史"。第 10 步时，messages 历史已累积前 9 步内容 —— 单这一个字段就可能 KB 级。

→ `succinct` = "去掉发给 LLM 的输入历史"，让输出可读。

### 4. `replay(logger, detailed=False)` ([memory.py:248-271](../../../src/smolagents/memory.py:248))

调试利器。源码用 `isinstance` 分发：每种 Step 用不同格式打印（典型多态分支）。

```python
agent.run("查巴黎天气")
agent.memory.replay(agent.logger, detailed=False)    # 漂亮打印整个执行历史
```

**3 个看点**：
- 用 `isinstance` 分发：每种 Step 不同格式（TaskStep / ActionStep / PlanningStep 各打印不同样）
- `detailed=False` 是默认 —— **故意藏起 model_input_messages**（同 succinct 思路）
- 注释提醒（[memory.py:254](../../../src/smolagents/memory.py:254)）：`detailed=True` 会让日志**指数级膨胀**，仅调试用

### 5. `return_full_code()` ([memory.py:273-277](../../../src/smolagents/memory.py:273))

```python
def return_full_code(self) -> str:
    return "\n\n".join(
        [step.code_action for step in self.steps
         if isinstance(step, ActionStep) and step.code_action is not None]
    )
```

**只对 CodeAgent 有意义**（filter 条件要求 `code_action is not None`，而 ToolCallingAgent 的 ActionStep 没有 `code_action`）。

**用途**：跑完一个 CodeAgent 任务后，把所有"思考产生的代码"拼成一段完整 Python 脚本。可以：

- **重现**：脱离 agent 单独跑这段脚本验证逻辑
- **学习**：看 LLM 写出的代码风格
- **导出**：作为最终 deliverable（你要的不是答案，而是实现答案的代码）

> 💡 这是 CodeAgent 独有的"代码考古"能力，ToolCallingAgent 没有等价物（它只有 tool_calls 没有完整代码）。

---

## 四、3 个关键设计洞察

1. **`system_prompt` 独立挂载** —— `reset()` 想保留它，所以不能塞进 steps[]。**结构分开 = 语义解耦**
2. **类型注解显式排除 FinalAnswerStep** —— 印证 [final-answer-step.md](final-answer-step.md) "事件 vs 记录"是显式设计
3. **succinct/full/detailed 三档输出** —— 不同场景需要不同详略。`model_input_messages` 是"调试黄金 + 输出炸弹"，所以三档都有它的开关

---

## 五、AgentMemory 在 Day 1 全图谱里的位置

```
agent: MultiStepAgent
└─ memory: AgentMemory ⭐
   ├─ system_prompt: SystemPromptStep      (独立挂载)
   ├─ steps: list[TaskStep|ActionStep|PlanningStep]
   │   ├─ TaskStep                          (任务)
   │   ├─ PlanningStep (可选)               (计划)
   │   ├─ ActionStep                        (一步行动)
   │   ├─ ...
   │   └─ ActionStep(is_final=T)            (最后一步)
   │   ⚠️ FinalAnswerStep 不在这里            (走事件通道)
   │
   ├─ reset()                                (清 steps 保留 system_prompt)
   ├─ get_full_steps() / succinct_steps()    (dump 整个内容，控制详略)
   ├─ replay(logger)                         (漂亮打印调试)
   └─ return_full_code()                     (CodeAgent 专用：导出全部代码)
```

---

## 相关链接

- 源码：[memory.py:214-277](../../../src/smolagents/memory.py:214)
- 关联笔记：
  - [memory-data-structures.md](memory-data-structures.md) Step 家族整体（AgentMemory 是它的容器）
  - [final-answer-step.md](final-answer-step.md) 解释为什么 FinalAnswerStep 不在 `steps[]` 类型里
  - [callback-registry.md](callback-registry.md) memory.py 另一个支撑组件，与 AgentMemory 配合工作
  - [action-step-anatomy.md](action-step-anatomy.md) `model_input_messages` 字段为什么大、`code_action` 字段从哪来

## 遗留问题

- [ ] `replay(detailed=True)` 时第 5 步的 `model_input_messages` 会重复打印前 4 步的内容 —— 这暗示了什么内存问题？是否值得加去重逻辑？
- [ ] 为什么 `return_full_code()` 用 `\n\n` 而不是单换行？多空行的目的？
- [ ] 如果想实现"max_history=10"（只保留最近 10 个 ActionStep），最简单的实现方式是什么？（提示：用 [callback-registry.md](callback-registry.md) 在每步触发后清理）
