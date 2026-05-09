---
created: 2026-05-04
status: active
tags: [python, prereqs, abc, oop, abstract-class, syntax]
---

# Python 类语法预习：`abc.ABC` 抽象基类

## 背景 / 动机

Day 2 看 [tools.py:98](../../../../src/smolagents/tools.py#L98)：

```python
class BaseTool(ABC):
    name: str

    @abstractmethod
    def __call__(self, *args, **kwargs) -> Any:
        pass
```

**两个新东西**：
- 父类位置写了个 `ABC`
- 方法上挂了 `@abstractmethod`

涉及 4 个问题：

1. `ABC` 是什么？为什么继承它？
2. `@abstractmethod` 跟 Day 1 见过的 `raise NotImplementedError` 有啥区别？
3. 既然有 `ABC` 这套机制，[memory.py](../../../../src/smolagents/memory.py) 的 7 个 Step 类为什么没用、而是用 `raise NotImplementedError`？
4. smolagents 同一个文件里两种写法都有（[BaseTool](../../../../src/smolagents/tools.py#L98) 用 ABC，[Tool.forward](../../../../src/smolagents/tools.py#L228) 用 NotImplementedError），矛盾吗？

> 💡 提前剧透：**两种写法不矛盾，是有意的混用**。一种"硬"（连实例都造不出来）一种"软"（实例能造，调用才崩）。下面会讲清楚什么时候用哪个。

---

## 1. ABC 是什么？

**ABC = Abstract Base Class**（抽象基类）。来自 Python 标准库的 `abc` 模块。

它的核心作用一句话：**让一个类"不能被实例化"，必须被继承+实现后才能用**。

```python
from abc import ABC, abstractmethod

class Animal(ABC):                    # 继承 ABC = "我是抽象类"
    @abstractmethod                   # 这个方法必须被子类实现
    def speak(self):
        pass

# 试试直接实例化 ——
a = Animal()
# 💥 TypeError: Can't instantiate abstract class Animal
#    without an implementation for abstract method 'speak'
```

子类必须实现所有 `@abstractmethod` 方法，才能被实例化：

```python
class Dog(Animal):
    def speak(self):
        return "Woof"

d = Dog()           # ✅ OK
print(d.speak())    # Woof
```

如果子类只实现了一部分：

```python
class Cat(Animal):
    pass            # 没实现 speak

c = Cat()
# 💥 TypeError: Can't instantiate abstract class Cat
#    without an implementation for abstract method 'speak'
```

> 💡 **ABC 是契约**："我承诺有 `speak` 方法，但具体怎么叫由子类定。**没实现的子类 Python 拒绝放出来用**。"

---

## 2. ⭐ vs `raise NotImplementedError`：硬约束 vs 软约束

Day 1 [python-class-and-dataclass.md](python-class-and-dataclass.md) 提到过 `raise NotImplementedError`，那是**轻量抽象方法**。

```python
# 写法 A：raise NotImplementedError（轻量）
class Animal:
    def speak(self):
        raise NotImplementedError("subclass must implement")

# 写法 B：abc.ABC + @abstractmethod（正式）
class Animal(ABC):
    @abstractmethod
    def speak(self):
        pass
```

两种写法都能让子类**调用 `speak()` 时崩**，但有一个**关键差异 —— 实例化时机**：

| 行为 | `raise NotImplementedError` | `ABC + @abstractmethod` |
|---|---|---|
| 实例化基类 `Animal()` | ✅ **能实例化**（一个空壳实例） | ❌ TypeError |
| 实例化没实现的子类 | ✅ 能实例化 | ❌ TypeError |
| 调用没实现的方法 | ❌ NotImplementedError | ❌ NotImplementedError |

### 用代码验证

```python
# ---- 写法 A ----
class A:
    def speak(self):
        raise NotImplementedError

a = A()                # ✅ 没崩，得到一个壳
a.speak()              # 💥 现在才崩

# ---- 写法 B ----
from abc import ABC, abstractmethod

class B(ABC):
    @abstractmethod
    def speak(self):
        pass

b = B()                # 💥 立刻崩，连实例都造不出来
```

> 💡 **关键认知**：`@abstractmethod` 把"错误暴露时机" 从**调用时**提前到了**实例化时**。这跟 [python-init-subclass.md](python-init-subclass.md) 那条 "**错误越早暴露越好**" 的原则一脉相承。

### 为什么 ABC 能做到这点？

`abc.ABC` 用了 **metaclass**（元类，比 `__init_subclass__` 更深的钩子）。它的元类在你写 `B()` 时检查 "**有没有未实现的 `@abstractmethod`**"，有就拒绝放出实例。

**这也是 [python-init-subclass.md](python-init-subclass.md) 第 4.3 节说"绝大多数场景能用 `__init_subclass__` 替代 metaclass"** 的反例：ABC 这种"控制实例化"的能力，就**只能用 metaclass 实现**。

---

## 3. 既然 ABC 这么好，为什么 [memory.py](../../../../src/smolagents/memory.py) 不用？

打开 [memory.py:1-3](../../../../src/smolagents/memory.py#L1)：

```python
import inspect
from dataclasses import asdict, dataclass
from logging import getLogger
```

**没有 import `abc`**。然后 7 个 Step 类全部用 `raise NotImplementedError` 风格。

**理由：和 `@dataclass` 元类冲突**。

### 冲突演示

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Step(ABC):
    name: str

    @abstractmethod
    def to_messages(self):
        pass
```

这段代码**能跑**（Python 3.10+ 改进过）—— 但在某些场景下：

```python
@dataclass
class Step(ABC):
    @abstractmethod
    def to_messages(self):
        pass

@dataclass
class TaskStep(Step):
    task: str
    # 忘了实现 to_messages
```

```python
TaskStep(task="hi")
# 💥 TypeError: Can't instantiate abstract class TaskStep
```

**问题**：dataclass 子类如果想覆盖 `@abstractmethod`，**必须显式覆盖**，但 dataclass 有继承字段顺序、默认值传递的种种限制，`@dataclass + ABC` 一组合写起来就**容易踩坑** —— 特别是要保留 dataclass 自动生成的 `__init__`、又要满足 ABC 的实例化检查。

> 💡 **memory.py 的折中**：**Step 类是数据容器**（重 dataclass、轻继承），所以选 `raise NotImplementedError` 这条软约束路线。代价：基类 `MemoryStep` 能被实例化（一个空壳），但实践中没人会去实例化基类，**契约靠约定不靠强制**。

---

## 4. ⭐ smolagents 里两种写法**同时存在**：[BaseTool](../../../../src/smolagents/tools.py#L98) vs [Tool.forward](../../../../src/smolagents/tools.py#L228)

来对比：

### BaseTool（line 98）—— 用 `ABC`

```python
class BaseTool(ABC):
    name: str

    @abstractmethod
    def __call__(self, *args, **kwargs) -> Any:
        pass
```

`__call__` 是**框架入口契约**：smolagents 框架内部所有调 tool 的地方都是 `tool(...)`（即触发 `__call__`）。这个方法**必须有**，**没实现就不准放出来**。

### Tool（line 228）—— 用 `raise NotImplementedError`

```python
def forward(self, *args, **kwargs):
    raise NotImplementedError("Write this method in your subclass of `Tool`.")
```

`forward` 是**业务逻辑层**，用户子类应该覆盖。但 smolagents 还有一些**不需要 `forward` 的子类**（[PipelineTool](../../../../src/smolagents/tools.py#L1171)、`SpaceToolWrapper`、`LangChainToolWrapper`）—— 它们直接覆盖 `__call__`。

如果 `forward` 也用 `@abstractmethod`，**这些 wrapper 子类就实例化不出来了**。所以 `forward` 的"不实现就崩"必须留到**调用时**。

### 一句话总结

| 方法 | 写法 | 严格度 | 为什么这样选 |
|---|---|---|---|
| `BaseTool.__call__` | `@abstractmethod` | **硬**（实例化时崩）| 框架入口契约，没它框架根本不能调 |
| `Tool.forward` | `raise NotImplementedError` | **软**（调用时崩）| 留口子让 wrapper 子类绕过 forward 直接实现 __call__ |

> 💡 **设计模式对照**：硬约束适合"**必经之路**"，软约束适合"**有替代方案的可选路径**"。这是写库的一条经验法则。

---

## 5. 实战：试着自己跑一下

```python
from abc import ABC, abstractmethod

# ---- 实验 A：能不能实例化 ABC 基类？----
class Tool(ABC):
    @abstractmethod
    def __call__(self): ...

try:
    Tool()
except TypeError as e:
    print(f"A: {e}")
# A: Can't instantiate abstract class Tool without an implementation for abstract method '__call__'


# ---- 实验 B：子类不实现也不行 ----
class IncompleteTool(Tool):
    pass

try:
    IncompleteTool()
except TypeError as e:
    print(f"B: {e}")
# B: Can't instantiate abstract class IncompleteTool ...


# ---- 实验 C：实现了就能用 ----
class WeatherTool(Tool):
    def __call__(self):
        return "sunny"

w = WeatherTool()
print(f"C: {w()}")
# C: sunny


# ---- 实验 D：ABC 也能多个 abstractmethod ----
class Animal(ABC):
    @abstractmethod
    def name(self): ...
    @abstractmethod
    def sound(self): ...

class Dog(Animal):
    def name(self): return "dog"
    # 故意只实现了 name，没实现 sound

try:
    Dog()
except TypeError as e:
    print(f"D: {e}")
# D: Can't instantiate abstract class Dog without an implementation for abstract method 'sound'
```

> 💡 跑一遍这 4 个实验，"硬约束"的感觉就出来了。

---

## 6. ABC 还有什么别的能力？（顺便扩展）

除了 `@abstractmethod`，`abc` 模块还有一些不太常用但偶尔遇到的标记：

| 装饰器 | 含义 |
|---|---|
| `@abstractmethod` | 抽象方法（用得最多） |
| `@abstractproperty` | 抽象属性（已弃用，改用 `@property + @abstractmethod`） |
| `@abstractclassmethod` | 抽象类方法（同上，改用 `@classmethod + @abstractmethod`） |
| `@abstractstaticmethod` | 抽象静态方法（同上） |

第一遍**只需要记 `@abstractmethod`**，其它等碰到再说。

### 还有：`ABC` 和 `ABCMeta` 的关系

源码里偶尔会看到：

```python
class MyClass(metaclass=ABCMeta):
    pass
```

vs 

```python
class MyClass(ABC):
    pass
```

**等价**。`ABC` 就是 `class ABC(metaclass=ABCMeta): pass` 的便捷封装（PEP 3119）。**写 `ABC` 更简单**，所以现代代码都用前者。

---

## 7. 总结表

| 问题 | 答案 |
|---|---|
| ABC 是什么？ | Abstract Base Class，让类不能直接实例化，强制子类实现指定方法 |
| `@abstractmethod` 怎么用？ | 挂在方法上，子类没实现就**实例化时**崩 |
| 与 `raise NotImplementedError` 的差异？ | ABC 是硬约束（实例化时崩），后者是软约束（调用时崩） |
| 哪个错误暴露更早？ | ABC 更早 —— 实例化时 |
| ABC 怎么实现"实例化拦截"？ | 用 metaclass（`ABCMeta`），比 `__init_subclass__` 更深的钩子 |
| 为什么 memory.py 不用 ABC？ | `@dataclass` 和 ABC 一起用容易踩元类冲突坑，选了软约束路线 |
| BaseTool vs Tool.forward 为什么用法不同？ | 硬约束适合必经之路，软约束适合可绕过的可选路径 |
| `ABC` 和 `ABCMeta` 关系？ | `ABC` 是带 `ABCMeta` 元类的便捷基类，等价 |

---

## 8. 反向自测题

```python
from abc import ABC, abstractmethod

class Tool(ABC):
    name: str  # 类属性注解，不是 abstract

    @abstractmethod
    def __call__(self):
        pass


# 问题 1：下面这行会发生什么？
try:
    t = Tool()
except Exception as e:
    print(f"Q1: {type(e).__name__}: {e}")


# 问题 2：下面这个子类能实例化吗？
class IncompleteTool(Tool):
    name = "incomplete"
    # 没实现 __call__

try:
    t2 = IncompleteTool()
except Exception as e:
    print(f"Q2: {type(e).__name__}: {e}")


# 问题 3：下面这个能实例化但调用会怎样？
class HalfBakedTool(Tool):
    name = "halfbaked"

    def __call__(self):
        raise NotImplementedError("我故意空着")

t3 = HalfBakedTool()  # 这一行能不能过？
print(f"Q3: 实例化{'成功' if t3 else '失败'}")
try:
    t3()
except Exception as e:
    print(f"Q3 调用: {type(e).__name__}: {e}")
```

<details>
<summary>预测答案</summary>

```
Q1: TypeError: Can't instantiate abstract class Tool ...
Q2: TypeError: Can't instantiate abstract class IncompleteTool ...
Q3: 实例化成功                       ← 因为 __call__ 已被覆盖（虽然方法体抛错）
Q3 调用: NotImplementedError: 我故意空着
```

**关键观察**：Q3 证明 ABC 检查的是 "**子类有没有覆盖那个名字**"，**不检查覆盖后方法体的内容**。所以 ABC 的硬约束**只到"有这个方法"那一步**，方法里写啥它管不着。这也是为什么 ABC + `raise NotImplementedError` 有时会同时出现 —— 双保险。

</details>

---

## 相关链接

- 源码：
  - BaseTool: [src/smolagents/tools.py:98](../../../../src/smolagents/tools.py#L98)
  - Tool.forward: [src/smolagents/tools.py:228](../../../../src/smolagents/tools.py#L228)
  - memory.py 全部用 raise NotImplementedError 的 Step 类：[src/smolagents/memory.py](../../../../src/smolagents/memory.py)
- 相关笔记：
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) — `@dataclass` 与 `raise NotImplementedError` 的初次相遇
  - [python-init-subclass.md](python-init-subclass.md) — 比 ABC 更轻量的子类钩子机制
- 外部参考：
  - [Python docs: abc module](https://docs.python.org/3/library/abc.html)
  - [PEP 3119 — Introducing Abstract Base Classes](https://peps.python.org/pep-3119/)

## 遗留问题

- [ ] `metaclass` 的完整机制（不限于 ABCMeta）—— 第一遍不深究，碰到再说
- [ ] `@abstractmethod` + `@property` 如何叠加（碰到再补）
- [ ] `isinstance(x, Tool)` 在 ABC 场景下的行为（virtual subclass 机制）—— 进阶话题
