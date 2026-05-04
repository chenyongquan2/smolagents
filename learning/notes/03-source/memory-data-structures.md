---
created: 2026-05-02
status: active
tags: [memory, step, dataclass, source-reading, week2-day1]
---

# memory.py 源码笔记：Step 家族与 AgentMemory 容器

## 背景 / 动机

Week 2 Day 1 阅读 [memory.py](../../../src/smolagents/memory.py)（316 行）。这是 smolagents 最简单的源文件，也是整个 ReAct 循环的"数据层基石"。

本文覆盖**鸟瞰 + 4 个简单 Step 类**：MemoryStep / SystemPromptStep / TaskStep / ToolCall。
其余拆分到独立笔记：
- PlanningStep 见 [planning-mechanics.md](planning-mechanics.md)（机制比较深，单独成文）
- ⭐ ActionStep 见 [action-step-anatomy.md](action-step-anatomy.md)（13 字段核心硬菜，单独成文）
- ⭐ FinalAnswerStep 见 [final-answer-step.md](final-answer-step.md)（"事件 vs 记录"的关键概念）
- `AgentMemory` 容器见 [agent-memory-container.md](agent-memory-container.md)
- `CallbackRegistry` 见 [callback-registry.md](callback-registry.md)（Observer 模式 + MRO walk）

## 一、文件鸟瞰

memory.py 共 **8 个类 + 1 辅助 dataclass**，分 3 组：

```
memory.py
│
├─ 📦 数据载体组（Step 家族，7 个，全是 @dataclass）
│   ├─ MemoryStep            ← 抽象基类（接口契约）
│   ├─ ToolCall              ← 辅助 dataclass（被 ActionStep 引用，不是 Step）
│   ├─ SystemPromptStep      ← 系统提示词
│   ├─ TaskStep              ← 用户任务
│   ├─ PlanningStep          ← 中途规划（见独立笔记）
│   ├─ ActionStep ⭐         ← ReAct 一轮的完整记录（待读）
│   └─ FinalAnswerStep       ← 最终答案（待读）
│
├─ 📂 容器组（1 个）
│   └─ AgentMemory           ← system_prompt + steps[] 持有者
│
└─ 🪝 钩子组（1 个）
    └─ CallbackRegistry      ← 给特定 step 类型注册回调
```

> 💡 **一句话本质**：`AgentMemory` 是个收纳盒。每跑一步 agent，往盒子里塞一个 Step 对象。要跟 LLM 对话时，把所有 Step 调 `to_messages()` 翻译回 messages 重新喂给 LLM。
> 这就是 Week 1 悟到的"LLM 无状态靠 messages 重发"在数据层的实现侧。

---

## 二、`MemoryStep` 抽象基类（[memory.py:41-47](../../../src/smolagents/memory.py:41)）

```python
@dataclass
class MemoryStep:
    def dict(self):
        return asdict(self)

    def to_messages(self, summary_mode: bool = False) -> list[ChatMessage]:
        raise NotImplementedError
```

### 三个值得品的设计

| 设计选择 | 理由 |
|---|---|
| `@dataclass` 但没字段 | 让基类挂上"我是 dataclass"户口，子类用 `asdict(self)` 才不会报错 |
| `raise NotImplementedError` 而非 `abc.ABC` | `abc.ABCMeta` 和 `@dataclass` 一起用会有元类冲突，作者选了更轻量的"软抽象"做法 |
| `summary_mode: bool = False` 预留参数 | 留给"精简回放/总结"使用 —— 子类自己决定该不该出场 |

### 💡 核心契约

> 整个 Step 家族必须满足 2 条铁律：
> ① **能变成字典**（`dict()` —— 用于序列化、调试）
> ② **能变成 messages**（`to_messages()` —— 用于喂给 LLM）
>
> 这就是 Week 1 "messages 重发"机制的实现基础。

---

## 三、`SystemPromptStep` 系统提示词（[memory.py:199-206](../../../src/smolagents/memory.py:199)）

```python
@dataclass
class SystemPromptStep(MemoryStep):
    system_prompt: str

    def to_messages(self, summary_mode: bool = False) -> list[ChatMessage]:
        if summary_mode:
            return []                    # ⭐ 精简模式下隐身
        return [ChatMessage(
            role=MessageRole.SYSTEM,
            content=[{"type": "text", "text": self.system_prompt}]
        )]
```

### 看点

- 字段只 1 个：`system_prompt: str`
- `to_messages()` 产出 1 条 `SYSTEM` 消息
- ⭐ **`summary_mode=True` 时返回空** —— 这是 [基类预留参数](../../../src/smolagents/memory.py:46) 第一次发挥作用
- **存放位置特殊**：`AgentMemory.__init__` 直接挂在 `self.system_prompt`，**不进** `self.steps[]`

> 💡 **设计思想**：system 消息独立存放是因为 `reset()` 时要保留它。同时 summary 模式下隐身是因为 replay 不需要 system。

---

## 四、`TaskStep` 用户任务（[memory.py:186-196](../../../src/smolagents/memory.py:186)）

```python
@dataclass
class TaskStep(MemoryStep):
    task: str
    task_images: list["PIL.Image.Image"] | None = None

    def to_messages(self, summary_mode: bool = False) -> list[ChatMessage]:
        content = [{"type": "text", "text": f"New task:\n{self.task}"}]
        if self.task_images:
            content.extend([{"type": "image", "image": image} for image in self.task_images])
        return [ChatMessage(role=MessageRole.USER, content=content)]
```

### 看点

- 字段 2 个：文本 + **可选图片列表**（多模态从这里开始）
- `to_messages()` 产出 1 条 `USER` 消息，content 是**混合列表**（文本 + 图）
- 文本前缀 `"New task:\n"` —— 给 LLM 的暗示，相当于"任务来了"的剧本提示词
- ⚠️ **不响应** `summary_mode` —— 任务永远是必要上下文

> 💡 **TaskStep 是真人最后一次出场的载体**。
> 真人在 `agent.run("...")` 那一刻贡献了**唯一一条**真实 user 消息。
> 之后所有 user 角色消息都是 agent 框架伪造的（详见 [chat-message-roles.md](../02-concepts/chat-message-roles.md)）。

---

## 五、`ToolCall` 辅助 dataclass（[memory.py:24-38](../../../src/smolagents/memory.py:24)）

```python
@dataclass
class ToolCall:                # ⚠️ 没继承 MemoryStep！
    name: str
    arguments: Any
    id: str

    def dict(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": make_json_serializable(self.arguments),
            },
        }
```

### 三个看点

**① ⚠️ 它不是 Step**：没继承 `MemoryStep`，没有 `to_messages()`。它只是个**辅助容器**，被 `ActionStep.tool_calls: list[ToolCall]` 引用。

**② Python 新语法 `Any`**：来自 `typing` 模块。"什么类型都行，不约束"。因为不同工具参数千差万别，`get_weather` 要 `{"location": ...}`，`calculator` 要 `{"expression": ...}`，类型系统约束不了，所以用 `Any` 放飞。

**③ `dict()` 输出 = OpenAI 协议官方格式**：

```json
{
  "id": "call_abc123",
  "type": "function",
  "function": {
    "name": "get_weather",
    "arguments": "{\"location\": \"Paris\"}"
  }
}
```

这是行业**标准 tool_call 格式**，OpenAI / Anthropic / 兼容厂商都用这个结构。

> 💡 **概念区分**：
> - **Step** = "agent 跑过的一步"（出现在 `memory.steps[]` 里）
> - **ToolCall** = "一步里调用的具体工具"（嵌套在 `ActionStep` 内部）
> - 一步可能调 0 / 1 / 多个工具，所以 `ActionStep.tool_calls` 是 list

---

## 六、关键洞察总结（4 条）

1. **多态契约**：基类的 `to_messages()` 用 `raise NotImplementedError` 强制每个子类必须实现 —— 这是整个 Step 家族能"统一翻译成 messages"的根基
2. **`@dataclass` 是代码生成器**：把"一堆字段+样板方法"的写法压缩成"几行注解"，这是 memory.py 能用 316 行容纳 8 个类的关键。详见 [python-class-and-dataclass.md](python-class-and-dataclass.md)
3. **子类可以重写 `dict()`**：当默认 `asdict()` 处理不了嵌套复杂对象时，子类自己实现序列化逻辑（PlanningStep 是第一例，详见 [planning-mechanics.md](planning-mechanics.md)）
4. **不是所有 dataclass 都是 Step**：ToolCall 是辅助容器，挂在 ActionStep 内部。Step 家族 = 出现在 `memory.steps[]` 里的、有 `to_messages()` 的；辅助 dataclass = 只是数据载体

---

## 相关链接

- 源码：[src/smolagents/memory.py](../../../src/smolagents/memory.py)
- Python 语法预习：[python-class-and-dataclass.md](python-class-and-dataclass.md)
- PlanningStep 深入：[planning-mechanics.md](planning-mechanics.md)
- Chat 消息 role 概念：[../02-concepts/chat-message-roles.md](../02-concepts/chat-message-roles.md)
- 学习计划：[../../LEARNING_PLAN.md](../../LEARNING_PLAN.md)（Week 2 Day 1）

## 遗留问题

- [x] ✅ ActionStep 13 个字段的逐一含义？→ 见 [action-step-anatomy.md](action-step-anatomy.md)
- [x] ✅ FinalAnswerStep 为什么不进 `memory.steps[]`？→ 因为它是**事件而非记录**，走 generator yield 通道而非 memory 持久化通道。详见 [final-answer-step.md](final-answer-step.md)
- [x] ✅ `AgentMemory.replay()` 实际怎么用？→ 见 [agent-memory-container.md](agent-memory-container.md) 第三节
- [x] ✅ `CallbackRegistry` 在 agent 框架里有哪些常见用法？→ 见 [callback-registry.md](callback-registry.md) 第五节 + 第七节实战
