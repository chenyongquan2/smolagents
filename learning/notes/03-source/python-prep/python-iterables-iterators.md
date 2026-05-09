---
created: 2026-05-03
status: active
tags: [python, prereqs, iterator, iterable, iteration-protocol, syntax, week2-day1]
---

# Python 迭代协议：Iterable vs Iterator（很多人写几年都没分清）

## 背景 / 动机

读 [agents.py:495-503](../../../../src/smolagents/agents.py:495) 时看到 `list(self._run_stream(...))`，疑问"没人调 `next()` 啊？"。挖下去触到了 Python 一个**很多人写几年都没分清**的概念：

> **Iterable**（可迭代对象）和 **Iterator**（迭代器）**不是同一个东西**。

涉及的问题：
1. `next()` 是 generator 独占的吗？为什么 `for x in list_y` 也能跑？
2. `list` / `dict` / `str` 在迭代协议里到底扮演什么角色？
3. `iter()` 这个内置函数干嘛用？
4. 为什么 generator **只能迭代一次**而 list 可以反复？

这是 [python-generators-yield.md](python-generators-yield.md) 的**前置概念**，也是它"延伸出"的更基础话题，独立成文。

---

## 1. 一张关键表（核心认知）

| 概念 | 定义 | 必须实现 | 例子 |
|---|---|---|---|
| **Iterable**（可迭代）| 能"产出"一个迭代器的对象 | `__iter__()` | `list`、`dict`、`set`、`tuple`、`str`、generator function 调用结果 |
| **Iterator**（迭代器）| 能"一步步推进"的对象 | `__next__()` + `__iter__()`（返回自己）| `list_iterator`、`dict_keyiterator`、`str_iterator`、**generator object** |

**核心区分**：
- `list` 是 **iterable，不是 iterator**
- `generator` **同时是 iterable 和 iterator**（这是它"特殊"的地方）

---

## 2. 验证：`next([1,2,3])` 会报错

```python
my_list = [1, 2, 3]

next(my_list)
# 💥 TypeError: 'list' object is not an iterator
```

**因为 list 没有 `__next__()` 方法**，它只有 `__iter__()`。

要这样：

```python
my_iter = iter(my_list)         # ⭐ 用 iter() 把 iterable 变成 iterator
print(type(my_iter))            # <class 'list_iterator'>

print(next(my_iter))            # 1
print(next(my_iter))            # 2
print(next(my_iter))            # 3
print(next(my_iter))            # 💥 StopIteration（list 已耗尽）
```

→ **任何 iterable，`iter()` 后都能用 `next()`**。

---

## 3. Generator 的特殊：它已经是 iterator 了

```python
def gen():
    yield 1
    yield 2

g = gen()
print(type(g))                  # <class 'generator'>
print(iter(g) is g)             # True ⭐ generator 自己就是 iterator

# 所以可以直接 next，不用先 iter()
print(next(g))                  # 1
print(next(g))                  # 2
```

**generator 的 `__iter__()` 返回自己**：

```python
class generator:                # 概念示意
    def __iter__(self):
        return self             # ⭐ 自己就是 iterator
    def __next__(self):
        # 推进到下一个 yield
        ...
```

---

## 4. `for x in [1,2,3]` 底层实际发生什么？

```python
# 你写的：
for x in [1, 2, 3]:
    print(x)
```

**Python 实际执行**：

```python
my_list = [1, 2, 3]
iterator = iter(my_list)         # ⭐ 第一步：把 iterable 变 iterator
while True:
    try:
        x = next(iterator)       # ⭐ 第二步：反复 next
    except StopIteration:
        break
    print(x)
```

→ **for 循环对 list 和对 generator 的底层行为一模一样**！都是 `iter()` + 反复 `next()`。

唯一区别：list 经过 `iter()` 得到一个 `list_iterator`；generator 经过 `iter()` **还是它自己**。

---

## 5. 自定义实现迭代协议（鸭子类型实战）

只要你的对象实现了 `__iter__()` 返回一个 iterator（一个有 `__next__()` 的对象），它就能被 for 循环消费。

```python
class CountDown:
    """从 start 倒数到 1 的 iterable"""
    def __init__(self, start):
        self.start = start

    def __iter__(self):
        return CountDownIterator(self.start)    # ⭐ 返回一个独立的 iterator 对象

class CountDownIterator:
    """实际负责推进的 iterator"""
    def __init__(self, start):
        self.current = start

    def __iter__(self):
        return self                              # ⭐ iterator 的 __iter__ 返回自己

    def __next__(self):
        if self.current <= 0:
            raise StopIteration
        value = self.current
        self.current -= 1
        return value

# 测试
for n in CountDown(3):
    print(n)
# 输出: 3, 2, 1

print(list(CountDown(3)))           # [3, 2, 1]
print(sum(CountDown(3)))            # 6
print(max(CountDown(3)))            # 3
```

→ 这就是迭代协议的**鸭子类型**精髓：不管你是 list、generator、还是自定义类，只要实现了协议，所有 iter/next 工具都能消费。

### "iterable + iterator" 拆两个类的好处

CountDown 拆成 2 个类的**关键好处**：**iterable 可以反复迭代**。

```python
cd = CountDown(3)
print(list(cd))   # [3, 2, 1]
print(list(cd))   # [3, 2, 1] ⭐ 还能再来！
# 因为每次 list() 都会调 iter(cd)，得到一个 NEW 的 CountDownIterator
```

如果合成一个类（让 CountDown 自己实现 `__next__`），就只能消费一次（变成纯 iterator，类似 generator）。

---

## 6. 为什么 generator 设计成"自己是自己的 iterator"？

| 设计选择 | 优点 | 缺点 |
|---|---|---|
| ❌ generator function 调用返回 iterable，再 iter() 拿 iterator | 概念分得清 | 多一步操作，每次 `iter(gen())` 烦 |
| ✅ generator object 本身就是 iterator | 调用一次直接能 next | **不能"重新开始"**（耗尽就死） |

→ Python 选了简便。代价是 generator **一次性**（不能重新迭代）—— 这就是 [python-generators-yield.md](python-generators-yield.md) 第 7 节"坑 1"讲的"generator 只能消费一次"的根本原因。

### 一句话：iterable 多次性，iterator 一次性

```python
# list (iterable, 多次性)
my_list = [1, 2, 3]
print(list(my_list))    # [1, 2, 3]
print(list(my_list))    # [1, 2, 3] ⭐ 还在
# 每次 list() 都重新 iter(my_list) 拿新 iterator

# generator (iterator, 一次性)
def gen():
    yield 1; yield 2; yield 3
g = gen()
print(list(g))          # [1, 2, 3]
print(list(g))          # [] ⭐ 空了！同一个 g 不能重来
# 必须 g = gen() 重新调用一次函数
```

---

## 7. 完整对照：list / generator / range / dict 在迭代协议里的角色

```python
import sys

# list
print(hasattr([1,2,3], '__iter__'))    # True
print(hasattr([1,2,3], '__next__'))    # False  ← 不是 iterator
print(type(iter([1,2,3])))              # <class 'list_iterator'>

# generator object
def g(): yield 1
gen = g()
print(hasattr(gen, '__iter__'))         # True
print(hasattr(gen, '__next__'))         # True   ⭐ 既是 iterable 又是 iterator
print(iter(gen) is gen)                 # True

# range（更微妙：是 iterable，但 iter(range) 给出独立 iterator）
print(hasattr(range(3), '__iter__'))    # True
print(hasattr(range(3), '__next__'))    # False  ← 不是 iterator
print(type(iter(range(3))))             # <class 'range_iterator'>

# dict（key 视图）
d = {'a': 1, 'b': 2}
print(hasattr(d, '__iter__'))           # True
print(hasattr(d, '__next__'))           # False
print(type(iter(d)))                    # <class 'dict_keyiterator'>
```

**规律**：内置容器全是"iterable，但不是 iterator"，要 `iter()` 才能拿到一次性的 iterator。**generator 是少数自己就是 iterator 的存在**。

---

## 8. 总结表

| 问题 | 答案 |
|---|---|
| `next()` 是 generator 独占的吗？ | ❌ 任何 iterator 都能用 `next()` |
| 为什么 `next([1,2,3])` 报错？ | list 是 iterable 不是 iterator，先要 `iter()` |
| `for x in list_y` 内部调 next 吗？ | ✅ 调，先 `iter(list_y)` 再反复 `next()` |
| generator 的特殊在哪？ | 它**同时是 iterable 和 iterator**，`iter(g) is g` |
| 为什么 generator 一次性而 list 多次？ | iterable + 独立 iterator 的拆分让 iterable 多次；generator 把两者合一所以一次 |
| 自己写一个能 for 的类，要实现什么？ | iterable: `__iter__` 返回独立 iterator；iterator: `__next__` + `__iter__` 返回自己 |

---

## 9. 三句话记住

1. **iterable ≠ iterator**：list 是 iterable 但不是 iterator；generator 两者都是
2. **`next()` 是给 iterator 用的**，对 iterable 必须先 `iter()` 拿到 iterator
3. **`for` / `list()` / `sum()` 内部都自动 `iter() + next()`** —— 这就是为什么平时不用关心这层。理解后，你能自己写**符合迭代协议**的类

---

## 10. 反向自测：跑这段代码加深印象

```python
# === 实验 1: list 不是 iterator ===
my_list = [1, 2, 3]
try:
    next(my_list)
except TypeError as e:
    print(f"实验 1: next(list) → TypeError: {e}")
print(f"  iter(list): {iter(my_list)}\n")    # 拿到 list_iterator

# === 实验 2: generator 自己是 iterator ===
def gen():
    yield 1; yield 2; yield 3
g = gen()
print(f"实验 2: iter(g) is g → {iter(g) is g}")
print(f"  next(g): {next(g)}\n")             # 1，直接调 next 没问题

# === 实验 3: 手写 for 循环 ===
print("实验 3: 手写 for 循环消费 list")
my_list = [10, 20, 30]
iterator = iter(my_list)
while True:
    try:
        x = next(iterator)
    except StopIteration:
        break
    print(f"  拿到: {x}")

# === 实验 4: list 多次性 vs generator 一次性 ===
print("\n实验 4: 多次性对比")
my_list = [1, 2, 3]
print(f"  list(my_list) 第一次: {list(my_list)}")
print(f"  list(my_list) 第二次: {list(my_list)} ⭐ 还在")

g = gen()
print(f"  list(gen) 第一次: {list(g)}")
print(f"  list(gen) 第二次: {list(g)} ⭐ 空了！")
```

跑完你会**亲眼看到**三个不同对象在迭代协议里的行为差异。

---

## 相关链接

- 关联笔记：
  - [python-generators-yield.md](python-generators-yield.md) Generator / yield 详解（这篇是它的前置概念）
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) Python 类语法预习（同 prereqs 系列）
- 源码相关：
  - [agents.py:495-503](../../../../src/smolagents/agents.py:495) `list(self._run_stream(...))` 触发的迭代协议
  - [memory.py:768](../../../../src/smolagents/memory.py:768) `for memory_step in self.memory.steps:` 用的迭代协议

## 遗留问题

- [ ] `yield from another_iterable` 和直接 `for x in another_iterable: yield x` 有什么区别？
- [ ] `itertools` 模块的 `chain` / `tee` / `islice` 是怎么操作 iterator 的？
- [ ] 异步迭代协议（`__aiter__` / `__anext__` / `async for`）和同步的关系？
- [ ] `iter(callable, sentinel)` 的双参数形式是干嘛用的？
