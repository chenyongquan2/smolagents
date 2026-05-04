---
created: 2026-05-03
status: active
tags: [callback, observer-pattern, mro, extension-point, source-reading, week2-day1]
---

# CallbackRegistry：Step 完成事件总线（Observer 模式实战）

## 背景 / 动机

Day 1 阶段 4。memory.py 最后一节，37 行 3 个方法。是 smolagents 的**主要扩展点** —— 用户**不修改框架代码**就能在每个 step 完成时插入自己的逻辑（日志、监控、写盘、推送、自动停止...）。

源码：[memory.py:280-316](../../../src/smolagents/memory.py:280)

---

## 一、整体结构

```python
class CallbackRegistry:
    """Registry for callbacks that are called at each step of the agent's execution."""

    def __init__(self):
        self._callbacks: dict[Type[MemoryStep], list[Callable]] = {}

    def register(self, step_cls: Type[MemoryStep], callback: Callable):
        """Register a callback for a step class."""
        if step_cls not in self._callbacks:
            self._callbacks[step_cls] = []
        self._callbacks[step_cls].append(callback)

    def callback(self, memory_step, **kwargs):
        """Call callbacks registered for a step type."""
        for cls in memory_step.__class__.__mro__:                       # ⭐ 关键
            for cb in self._callbacks.get(cls, []):
                cb(memory_step) if len(inspect.signature(cb).parameters) == 1 \
                    else cb(memory_step, **kwargs)
```

3 个方法、1 个数据成员。

---

## 二、数据结构（[memory.py:287](../../../src/smolagents/memory.py:287)）

```python
self._callbacks: dict[Type[MemoryStep], list[Callable]] = {}
```

**键**：Step 类（不是实例！是 class 对象，比如 `ActionStep` 这个类本身）
**值**：注册到这个类的回调函数列表

直观示例：

```python
{
    ActionStep:    [update_metrics_callback, log_to_db_callback],
    PlanningStep:  [notify_user_callback],
    MemoryStep:    [universal_callback],            # 基类
}
```

---

## 三、`register()` —— 简单的字典追加（[memory.py:289-298](../../../src/smolagents/memory.py:289)）

```python
if step_cls not in self._callbacks:
    self._callbacks[step_cls] = []
self._callbacks[step_cls].append(callback)
```

没什么花哨。"如果这个类还没注册过，新建空 list；然后把 callback 追加进去"。**一个 step 类可以挂多个 callback**（list 而非单值）。

---

## 四、⭐ `callback()` —— 整个文件最聪明的一行

```python
def callback(self, memory_step, **kwargs):
    for cls in memory_step.__class__.__mro__:                # ⭐⭐⭐
        for cb in self._callbacks.get(cls, []):
            cb(memory_step) if len(inspect.signature(cb).parameters) == 1 \
                else cb(memory_step, **kwargs)
```

### 看点 1：`memory_step.__class__.__mro__` 走继承链

`__mro__` = **Method Resolution Order**，Python 类的"继承链"（从子类到基类的查找顺序）。

例子：当 `memory_step` 是一个 `ActionStep` 实例时，

```python
memory_step.__class__.__mro__
# = (ActionStep, MemoryStep, object)
```

→ for 循环会**依次查找 `ActionStep`、`MemoryStep`、`object` 各自注册的回调全部触发**。

**这意味着什么**？

| 你 register 在哪里 | 触发场景 |
|---|---|
| `register(ActionStep, my_cb)` | 只有 ActionStep 类型的 step 触发 |
| `register(PlanningStep, my_cb)` | 只有 PlanningStep 触发 |
| `register(MemoryStep, my_cb)` | **所有 Step 类型都触发**（因为它们都继承 MemoryStep）|

→ **想监听全部 step**？注册到基类。**只想监听特定类型**？注册到具体子类。**Python 继承的精髓被这一行用足了**。

### 看点 2：`inspect.signature` 的兼容性技巧

```python
cb(memory_step) if len(inspect.signature(cb).parameters) == 1 \
    else cb(memory_step, **kwargs)
```

含义：**先看 callback 接受几个参数**：

- 只 1 个参数 → `cb(memory_step)`（兼容老式 callback）
- 多个参数 → `cb(memory_step, **kwargs)`（新式，可拿到 agent 等额外参数）

源码注释（[memory.py:308-312](../../../src/smolagents/memory.py:308)）也明说：

> "For backwards compatibility, callbacks with a single parameter signature receive only the memory_step, while callbacks with multiple parameters receive both the memory_step and any additional kwargs."

**为什么需要兼容**？这个项目早期 callback 只传 step，后来加了 agent 等 kwargs。如果直接改成 `cb(memory_step, **kwargs)`，**用户的旧 1 参 callback 全部炸**。这种"看签名再决定怎么调"是**库作者保持兼容性的常用招**。

> 💡 这种技巧叫 **introspection**（自省）—— 程序在运行时检查自己的对象（比如函数签名、属性）。`inspect` 是 Python 标准库做这个的工具。

---

## 五、🎬 框架实际怎么用它？

### 注册侧（[agents.py:416-434](../../../src/smolagents/agents.py:416)）

```python
def _setup_step_callbacks(self, step_callbacks):
    self.step_callbacks = CallbackRegistry()
    if step_callbacks:
        if isinstance(step_callbacks, list):
            for callback in step_callbacks:
                self.step_callbacks.register(ActionStep, callback)   # 默认挂在 ActionStep
        elif isinstance(step_callbacks, dict):
            for step_cls, callbacks in step_callbacks.items():
                for callback in callbacks:
                    self.step_callbacks.register(step_cls, callback)
    self.step_callbacks.register(ActionStep, self.monitor.update_metrics)  # ⭐ 框架自带
```

**用户 API**：

```python
# 简单用法：只 hook ActionStep
agent = CodeAgent(
    tools=[...],
    model=...,
    step_callbacks=[my_action_logger],
)

# 进阶：精细 hook 不同 step 类型
agent = CodeAgent(
    ...,
    step_callbacks={
        ActionStep: [log_action, save_to_db],
        PlanningStep: [notify_replan],
        MemoryStep: [universal_metric],     # 任何 step 都触发
    }
)
```

注意 [agents.py:434](../../../src/smolagents/agents.py:434) **框架自己也注册了一个**：`monitor.update_metrics` 挂在 ActionStep 上。这是 smolagents 内置的"每步累积 token 用量、耗时"机制。

→ 用户的 callback 和框架自己的 callback **平起平坐**，都通过同一个 registry 管理。

### 触发侧（[agents.py:622-623](../../../src/smolagents/agents.py:622)）

```python
def _finalize_step(self, memory_step):
    if not isinstance(memory_step, FinalAnswerStep):
        memory_step.timing.end_time = time.time()
    self.step_callbacks.callback(memory_step, agent=self)              # ⭐ 这里
```

每完成一个 step（不管 ActionStep / PlanningStep / FinalAnswerStep），框架就调一次 `step_callbacks.callback(memory_step, agent=self)`。

→ 所有注册的回调函数会**自动收到通知**，可以做任何事：日志、监控、写数据库、推送 Slack、检测异常自动停 agent...

---

## 六、💡 设计精髓 = "**Step 完成事件总线**"

```
        每完成一个 step
              ↓
      _finalize_step(step)
              ↓
   step_callbacks.callback(step, agent=self)
              ↓
    走 step.__class__.__mro__
              ↓
   依次调用注册到每一层的回调
              ↓
   ActionStep callbacks  →  MemoryStep callbacks  →  object callbacks
   （具体类型）              （所有 step 通用）        （所有对象通用，几乎不用）
```

**核心思想**：把 agent 内部的"事件"开放出来，让用户**不修改框架代码**就能扩展功能。这是经典的 **Observer 模式**（观察者模式）。

> 💡 这种"框架预留扩展点 + 用户挂钩子"的模式在 Python 生态广泛存在：Django signals、PyTorch hooks、HuggingFace transformers callbacks 等等。学会一个，识别一片。

---

## 七、⚡ 实战场景举例

```python
# 场景 1：每完成一个 ActionStep 写一行日志
def my_action_logger(action_step):
    """1 参 callback（老式签名）"""
    with open("agent.log", "a") as f:
        f.write(f"Step {action_step.step_number}: {action_step.tool_calls}\n")

# 场景 2：检测总 token 累积，超阈值就停 agent
def cost_alert(memory_step, agent):                     # 多参 callback（新式签名）
    """多参 callback，能拿到 agent 实例"""
    total = sum(s.token_usage.input_tokens + s.token_usage.output_tokens
                for s in agent.memory.steps if s.token_usage)
    if total > 100_000:
        agent.interrupt()                # 触发 agents.py 的中断开关

# 场景 3：每 5 步自动 dump memory 到磁盘（解答 agent-memory-container.md 遗留 Q3）
def auto_dump(memory_step, agent):
    if isinstance(memory_step, ActionStep) and memory_step.step_number % 5 == 0:
        with open(f"memory_step_{memory_step.step_number}.json", "w") as f:
            json.dump(agent.memory.get_full_steps(), f)

agent = CodeAgent(
    ...,
    step_callbacks={
        ActionStep: [my_action_logger, cost_alert, auto_dump],
    }
)
```

→ **不改框架代码**，就实现日志、成本控制、自动备份。这是 Observer 模式的实际威力。

---

## 八、3 个稳定认知（Day 1 阶段 4 收官）

1. **MRO walk 让"在基类注册 = 监听所有子类"** —— 这是 Python 继承被用足的典型，简洁威力大
2. **`inspect.signature` 兼容性技巧** —— 库作者保持向后兼容的常用招，未来你写库也会用到
3. **CallbackRegistry 是 Observer 模式的实战** —— 学会这个就懂 Django signals / PyTorch hooks / HF transformers callbacks 等等

---

## 相关链接

- 源码：
  - [memory.py:280-316](../../../src/smolagents/memory.py:280) CallbackRegistry 定义
  - [agents.py:416-434](../../../src/smolagents/agents.py:416) 框架注册侧（`_setup_step_callbacks`）
  - [agents.py:622-623](../../../src/smolagents/agents.py:622) 框架触发侧（`_finalize_step`）
- 关联笔记：
  - [agent-memory-container.md](agent-memory-container.md) memory.py 的另一个支撑组件
  - [memory-data-structures.md](memory-data-structures.md) Step 家族整体（callback 接收的就是这些 Step 实例）

## 遗留问题

- [ ] callback 抛异常会怎么样？会中断 agent 还是被吞掉？（看 `_finalize_step` 是否有 try/except）
- [ ] 多个 callback 对同一个 step 操作时，**有没有顺序保证**？（看起来按 register 顺序，但有没有依赖关系的话需要小心）
- [ ] 能不能在 callback 里 **修改** memory_step 的字段？（比如打 tag）框架后续是否依赖原值？
- [ ] FinalAnswerStep 也会触发 callback 吗？（参见 [final-answer-step.md](final-answer-step.md) 第二个遗留问题）
