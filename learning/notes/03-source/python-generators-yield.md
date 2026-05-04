---
created: 2026-05-03
status: active
tags: [python, prereqs, generator, yield, async, syntax, week2-day1]
---

# Python 生成器与 yield：smolagents 实时事件流的实现基石

## 背景 / 动机

读 [agents.py](../../../src/smolagents/agents.py) 时反复见到 `yield` 关键字 + `Generator[X | Y | ...]` 类型注解：

```python
def _run_stream(self, ...) -> Generator[ActionStep | PlanningStep | FinalAnswerStep | ChatMessageStreamDelta]:
    while ...:
        ...
        yield action_step
    yield final_answer_step
```

这是 smolagents **ReAct 循环 + 实时流式输出**的实现基石。如果 `yield` 不熟，Day 5 读 `_step_stream` 时会很吃力。先在这里补齐。

涉及 4 个问题：
1. `yield` 是什么含义？和 `return` 的区别？
2. 为什么调用一个有 `yield` 的函数"什么都没发生"？
3. smolagents 为什么大量用 `yield`？
4. `Generator[X]` 这种类型注解怎么读？

---

## 1. `yield` 一句话定位

> **`yield` ≈ 可暂停的 `return`**：函数遇到 `yield` 时**暂停**，把值"吐"给调用方，等调用方再要时**从暂停处继续**。

带 `yield` 的函数叫**生成器函数**（generator function）。

---

## 2. 最小对比：`return` vs `yield`

### 普通函数（`return`）

```python
def get_numbers():
    print("开始计算")
    return [1, 2, 3]
```

```python
result = get_numbers()
# 输出: 开始计算
# result == [1, 2, 3]
```

**特点**：函数从头跑到 `return`，**一次性**返回所有结果。想拿 3 个数？必须先生成全部 3 个再一起返回。

### 生成器函数（`yield`）

```python
def get_numbers():
    print("开始计算")
    print("吐 1")
    yield 1                  # 暂停，把 1 吐出去
    print("继续，吐 2")
    yield 2                  # 又暂停，把 2 吐出去
    print("继续，吐 3")
    yield 3                  # 再暂停，把 3 吐出去
    print("函数结束")
```

```python
gen = get_numbers()           # ⚠️ 注意：这一行什么都没打印！
print(type(gen))
# 输出: <class 'generator'>

for n in gen:                 # for 循环时函数才真正开始跑
    print(f"拿到 {n}")
# 输出:
# 开始计算
# 吐 1
# 拿到 1
# 继续，吐 2
# 拿到 2
# 继续，吐 3
# 拿到 3
# 函数结束
```

### 两个反直觉的现象

| 现象 | 解释 |
|---|---|
| 第一行 `gen = get_numbers()` 没打印 | 调用生成器函数**不执行函数体**，只创建一个 generator 对象 |
| `for n in gen:` 才打印 "开始计算" | 函数**只在被迭代时**才真正执行 |

> 💡 这是新手最常踩的坑：以为 generator 函数和普通函数一样调用就跑。其实**调用 = 创建对象，迭代 = 执行**。

---

## 3. yield 的执行模型：暂停-恢复

把 generator 想成**带"暂停键"的录像机**：

```
def get_numbers():
    print("开始计算")
    yield 1                    ← ⏸ 第 1 次 next() 在这里暂停
    print("继续")
    yield 2                    ← ⏸ 第 2 次 next() 在这里暂停
    yield 3                    ← ⏸ 第 3 次 next() 在这里暂停
                               ← 第 4 次 next() 时函数走到末尾，抛 StopIteration
```

**每次外部"要下一个"，函数就从上次暂停的地方继续跑**，直到下一个 yield 或函数结束。

### 手动操控 generator（不用 for 循环）

```python
gen = get_numbers()
print(next(gen))   # 输出: 开始计算 → 1
print(next(gen))   # 输出: 继续 → 2
print(next(gen))   # 输出: 3
print(next(gen))   # 💥 StopIteration（没东西可 yield 了）
```

`for` 循环本质就是**自动调 `next()` 直到 StopIteration**。

---

## 4. smolagents 为什么大量用 `yield`？

回到你看到的代码 [agents.py:540-611](../../../src/smolagents/agents.py:540)：

```python
def _run_stream(self, task, max_steps, images) -> Generator[...]:
    self.step_number = 1
    while not returned_final_answer and self.step_number <= max_steps:
        ...
        if planning_triggered:
            for element in self._generate_planning_step(...):
                yield element                      # ⭐ 实时吐 plan 进展
            ...
        for output in self._step_stream(action_step):
            yield output                            # ⭐ 实时吐每步进展
        yield action_step                            # ⭐ 整个 step 完成后吐出
    yield final_answer_step                          # ⭐ 最后吐终止事件
```

**整个 ReAct 循环都在这一个函数里**，`yield` 让框架能：

### 用途 A：实时反馈（流式输出）

```python
agent = CodeAgent(...)
for event in agent.run("查巴黎温度", stream=True):
    if isinstance(event, ChatMessageStreamDelta):
        print(event.content, end="", flush=True)        # token 一个一个显示
    elif isinstance(event, ActionStep):
        print(f"\n✅ 完成步骤 {event.step_number}")
    elif isinstance(event, FinalAnswerStep):
        print(f"\n🎯 最终答案：{event.output}")
```

**没有 yield 的话**：只能等 agent 全部跑完才能拿结果，调用方无法看到中途进度 → Web UI / 命令行进度条全部失效。

### 用途 B：让一个长流程"自然分块"

ReAct 循环里**异步等 LLM**、**等工具执行**，每步几秒到几十秒。yield 的好处：

- 每个步骤完成时把 ActionStep 吐出去
- 调用方可以**中途介入**（取消、可视化、记录）
- 框架内部代码**像同步代码一样写**（不用搞 callback 地狱）

### 用途 C：内存友好（lazy）

如果 agent 跑 50 步，**不用 yield**得攒成 50 个的 list 一次性返回。**用 yield**：每生成一个就能消费一个。

---

## 5. 实战：`run()` 内部怎么用 generator

[agents.py:495-503](../../../src/smolagents/agents.py:495)：

```python
def run(self, task, ..., stream=False):
    ...
    if stream:
        return self._run_stream(task, ...)            # 返回 generator，调用方自己迭代
    else:
        steps = list(self._run_stream(task, ...))     # 内部 list() 把 generator 全消费
        assert isinstance(steps[-1], FinalAnswerStep)
        return steps[-1].output                        # 取最后一个事件的 output
```

**关键**：`list(generator)` 会**触发 generator 全部跑完**，把每个 yield 的值收集到列表。这就是 [final-answer-step.md](final-answer-step.md) 里"`run()` 收集生成器结果取最后一项"的真相。

→ **同一个 generator 函数同时支持流式和非流式**：调用方按 `stream` 参数决定要不要 `list()`。这是 yield 设计的优雅之处。

---

## 6. `Generator[ActionStep | PlanningStep | ...]` 类型注解怎么读？

```python
def _run_stream(self, ...) -> Generator[ActionStep | PlanningStep | FinalAnswerStep | ChatMessageStreamDelta]:
```

**读法**：**"这是一个 generator，每次 yield 出来的值可能是 `ActionStep` / `PlanningStep` / `FinalAnswerStep` / `ChatMessageStreamDelta` 之一"**。

`Generator` 来自 `typing` 模块。完整签名 `Generator[YieldType, SendType, ReturnType]`，但简化只用第一个参数表示 yield 的类型。

→ 这条注解是给 IDE 和读代码的人**提示"这函数是 generator，会吐这几种事件"**。运行时不强制（和 `@dataclass` 的字段注解一样，纯文档性质）。

---

## 7. 三个常见坑

### 坑 1：generator **只能消费一次**

```python
gen = get_numbers()
list(gen)          # [1, 2, 3]
list(gen)          # [] ← 空！gen 已经"用完"了
```

要再迭代，需**重新调用函数生成新的 generator**。

### 坑 2：调用 generator 函数**不执行函数体**

```python
def buggy():
    print("我应该被打印")
    raise ValueError("我应该被抛")
    yield 1

buggy()        # 什么都不会发生！连 print 和 raise 都不触发
```

必须 `next(buggy())` 或 `for _ in buggy():` 才会真正执行。

### 坑 3：yield 函数里的 `return` **不会出现在 yield 流里**

```python
def mixed():
    yield 1
    yield 2
    return 3       # ⚠️ 这个 3 不会出现在 for 循环里！
```

generator 函数里 `return` 的值会被塞到 `StopIteration.value`，**不会被 for 循环看到**。所以 smolagents 用 `yield final_answer_step` 而不是 `return final_answer` —— 这样流式消费时能看到结束信号。

---

## 8. 反向自测：跑一段代码加深印象

```python
def react_loop_simulator(max_steps=3):
    """模拟 smolagents 的 _run_stream"""
    print("ReAct 循环开始")
    for step in range(1, max_steps + 1):
        print(f"内部：跑 step {step}")
        yield f"ActionStep_{step}"      # 每步吐一个事件
        print(f"内部：step {step} 后，准备下一步")
    print("内部：循环退出")
    yield "FinalAnswerStep"             # 最后吐终止事件

# 流式消费
gen = react_loop_simulator()
for event in gen:
    print(f"  调用方收到: {event}")

# 非流式消费
events = list(react_loop_simulator())
print(f"非流式收到: {events}")
```

跑一遍能直观看到**生成器的暂停-恢复节奏** + **流式 vs 非流式调用差异**。

---

## 9. 总结表

| 问题 | 答案 |
|---|---|
| 调用一个 yield 函数会发生什么？ | 创建一个 generator 对象，**不执行函数体** |
| 函数体什么时候才执行？ | 调用 `next(gen)` 或 `for _ in gen` 时 |
| yield 和 return 的核心区别？ | yield 暂停函数继续保留状态；return 终止函数 |
| smolagents 用 yield 的核心收益？ | 实时事件流（流式输出）+ 长流程自然分块 + 调用方决定消费节奏 |
| `Generator[X]` 注解什么意思？ | 这是个 generator，每次 yield 类型是 X |

---

## 10. 迭代协议：`list()` / `for` 怎么消费 generator？

**关键事实**：**`list()` / `for` / `sum()` 等内部都在帮你调 `next()`**。这不是 generator 独占的特性，而是 Python **迭代协议**的标准行为。

简明结论：

```python
steps = list(self._run_stream(...))
# 等价于：反复 next(generator) 直到 StopIteration，收集到列表
```

`list()` / `tuple()` / `set()` / `for` / `sum()` / `max()` / `any()` / 解包 / 推导式 / `"".join()` —— **全部底层都是 `iter()` + 反复 `next()`**。

⭐ **延伸认知**：这其实涉及 **iterable**（可迭代）vs **iterator**（迭代器）的区分。`list` 是 iterable 但**不是** iterator（`next([1,2,3])` 会报错）；generator **既是 iterable 又是 iterator**，所以可以直接 `next(g)`。

→ 这是比 yield 更基础的概念，独立成笔记 **[python-iterables-iterators.md](python-iterables-iterators.md)**。读完那篇就彻底懂了。

---

## 三句话记住

1. **`yield` = 可暂停的 `return`**：函数遇到 yield 暂停并吐值，下次被 next 时从暂停处继续
2. **调用 generator 函数不执行函数体**，只创建一个 generator 对象；真正执行发生在迭代时
3. **smolagents 用 yield 实现"实时事件流"**：让 ReAct 循环既能写成自然的 while/for，又能让调用方实时拿到每步进展

---

## 相关链接

- 源码示例：
  - [agents.py:540](../../../src/smolagents/agents.py:540) `_run_stream` 主 generator
  - [agents.py:495-503](../../../src/smolagents/agents.py:495) `run()` 同时支持流式/非流式
  - [memory.py:96](../../../src/smolagents/memory.py:96) `to_messages` 不是 generator（只是普通函数返回 list）
- 关联笔记：
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) Python 类语法预习（同一系列）
  - [final-answer-step.md](final-answer-step.md) yield 在 FinalAnswerStep 设计中的作用

## 遗留问题

- [ ] `yield from`（如 `yield from self._step_stream(...)`）是什么？和直接 `for x in ...: yield x` 有什么区别？
- [ ] `async def` + `yield`（异步生成器）是什么？smolagents 用了吗？
- [ ] generator 的 `.send(value)` 方法是干嘛的？（用于双向通信，rare）
- [ ] generator expression（`(x for x in ...)`）和 list comprehension 的区别？
