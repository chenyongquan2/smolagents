---
created: 2026-05-04
status: active
tags: [python, prereqs, metaclass, oop, hooks, syntax]
---

# Python 类语法预习：`__init_subclass__` 钩子

## 背景 / 动机

Day 2 要读 [tools.py](../../../../src/smolagents/tools.py) 的 Tool 基类，第一个新概念就是 `__init_subclass__`：

```python
# tools.py:140
class Tool(BaseTool):
    ...
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        validate_after_init(cls)
```

涉及 4 个问题：

1. `__init_subclass__` 是什么？什么时候触发？跟 `__init__` / `__new__` 啥关系？
2. 它和 `@dataclass`、`abc.ABC`、metaclass 是什么关系？为什么不能用那些代替？
3. 不用这个钩子能不能实现同样效果？
4. smolagents 用它做了什么？

> 💡 提前剧透：Day 2 plan 我说过 "`__init_subclass__` 在导入时校验 name/description"，**这个说法不完全准确**。源码里这个钩子只做了"wrap 一下子类的 `__init__`"，真正的 schema 校验跑在**实例化时**。这篇会讲清楚区别。

---

## 1. 触发时机：子类被定义的那一刻

### 三个时机的对照

```python
class Foo:
    def __init_subclass__(cls):
        print(f"[subclass hook] {cls.__name__} 被定义了")

    def __new__(cls):
        print(f"[new] 创建 {cls.__name__} 的一个实例")
        return super().__new__(cls)

    def __init__(self):
        print(f"[init] 初始化 {type(self).__name__} 的实例")


print("--- 定义子类 Bar ---")
class Bar(Foo):
    pass

print("--- 实例化 Bar ---")
b = Bar()
```

输出：

```
--- 定义子类 Bar ---
[subclass hook] Bar 被定义了        ← __init_subclass__ 在这里就跑了
--- 实例化 Bar ---
[new] 创建 Bar 的一个实例           ← __new__ 创建对象
[init] 初始化 Bar 的实例            ← __init__ 初始化字段
```

**三个时机**：

| 钩子 | 谁是 self/cls | 触发时机 | 目的 |
|---|---|---|---|
| `__init_subclass__(cls)` | **子类对象** (cls) | 子类被 **定义** 时（import 阶段） | 改造子类本身 |
| `__new__(cls)` | 子类对象 (cls) | 实例化时，**创建对象**前 | 控制对象怎么造（很少改） |
| `__init__(self)` | **实例对象** (self) | 实例化时，对象造好后 | 给实例字段赋值 |

> 💡 我的理解：`__init_subclass__` 是个 **"每当有人继承我，就让我先看看新子类长啥样" 的钩子**。
> 对应 Java 没有等价物（Java 的字节码注入 / annotation processor 是编译期的，更重）。
> 比较接近的类比：JavaScript 的 `class A extends B {}` 时 B 没法插手。Python 给了你这个机会。

### 它在 `class Bar(Foo):` 这一行就跑

很重要的一点：**子类一被定义，钩子就触发**。不需要等实例化、不需要 import 完。所以如果钩子里抛错，**导入这个模块就直接崩**。

```python
class Foo:
    def __init_subclass__(cls):
        if not hasattr(cls, "name"):
            raise TypeError(f"{cls.__name__} must define class attribute 'name'")

# 定义子类时就崩，不用等实例化
class Bar(Foo):
    pass
# 💥 TypeError: Bar must define class attribute 'name'
```

这就是 "**校验前置到导入阶段**" 的能力 —— 让错误**早暴露、早失败**。

---

## 2. ⭐ 用 vs 不用 的对比

### 不用 `__init_subclass__`（手工校验）

```python
class Tool:
    name: str
    description: str

    def __init__(self):
        # 每次实例化都要再写一遍这堆校验
        if not hasattr(self, "name"):
            raise TypeError("missing name")
        if not hasattr(self, "description"):
            raise TypeError("missing description")
        ...

class WeatherTool(Tool):
    name = "weather"
    description = "Get weather"

    def __init__(self):
        super().__init__()   # ← 必须显式调，否则跳过校验
```

**两个痛点**：
- 每个子类必须记得调 `super().__init__()`，**忘了就跳过校验**
- 校验逻辑跟 `__init__` 绑死，不灵活

### 用 `__init_subclass__`

```python
class Tool:
    name: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "name"):
            raise TypeError(f"{cls.__name__} must define 'name'")

class WeatherTool(Tool):     # ← 一行写完，没 name 直接在这行崩
    pass
```

**好处**：
- 子类**不需要写任何代码**，钩子自动跑
- 校验时机在 import，**bug 早一刻暴露**
- 子类的 `__init__` 想怎么写就怎么写，互不干扰

> 💡 原则：**导入时能校验的，不要拖到实例化；实例化时能校验的，不要拖到调用时**。错误越早暴露，调试越省事。

---

## 3. ⭐ smolagents 实际怎么用：只 wrap、不校验

打开 [tools.py:140](../../../../src/smolagents/tools.py#L140)：

```python
def __init_subclass__(cls, **kwargs):
    super().__init_subclass__(**kwargs)
    validate_after_init(cls)
```

`validate_after_init` 在 [tools.py:70](../../../../src/smolagents/tools.py#L70)：

```python
def validate_after_init(cls):
    original_init = cls.__init__

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.validate_arguments()        # ← 真正的校验在这里

    cls.__init__ = new_init
    return cls
```

### 把这两段合起来读 —— 它做的事是 "**装一根挂钩**"

| 时机 | 真正发生了什么 |
|---|---|
| **导入子类时**（`class WeatherTool(Tool):` 这一行） | `__init_subclass__` 跑 → 调 `validate_after_init` → 把子类的 `__init__` 偷偷换成 `new_init` |
| **实例化时**（`WeatherTool()`） | `new_init` 跑 → 先调用户原本的 `__init__` → 再调 `self.validate_arguments()`（这才是真校验，[tools.py:144](../../../../src/smolagents/tools.py#L144)） |

> 💡 **修正 Day 2 plan 的措辞**：导入阶段做的事**仅是 wrap，不是校验**。所以如果你在 `WeatherTool` 里把 `name = "weather"` 写错成 `nmae = "weather"`，
> - import 这一刻**不会崩**（`__init_subclass__` 不知道你想让谁叫 name）
> - 等到 `WeatherTool()` 这一刻才会崩（在 `validate_arguments` 里 `getattr(self, "name", None)` 拿到 `None`）
>
> 这是个很微妙但很常见的设计：**有些校验天然依赖实例数据（比如 `self.inputs.items()`），导入期还没数据可校；所以推迟到实例化但通过 wrap 让用户无感**。

### 为什么这么绕？直接重写 `__init__` 不行吗？

你可能会想：为什么不直接在 `Tool.__init__` 里加 `self.validate_arguments()`？

```python
# 假设的简化版
class Tool:
    def __init__(self):
        self.is_initialized = False
        self.validate_arguments()  # ← 直接在基类调

class WeatherTool(Tool):
    def __init__(self):
        # 用户必须记得调 super().__init__()
        # 否则校验被跳过！
        super().__init__()
```

**问题就是**：用户子类的 `__init__` 必须记得显式调 `super().__init__()`。**忘了就跳过校验**。

`validate_after_init` 的解法是 monkey-patch 子类的 `__init__`：

```python
cls.__init__ = new_init   # ← 覆盖子类自己的 __init__
```

这样**不管子类 `__init__` 怎么写、调没调 super**，外面看到的入口都已经是 `new_init` 了 —— 用户必然在写完 `__init__` 之后被自动接上一句 `self.validate_arguments()`。**强制、无法绕过、用户无感**。

---

## 4. 与 `abc.ABC`、`@dataclass`、metaclass 的对比

### 4.1 vs `abc.ABC`（抽象基类）

`abc.ABC` 能做：标记某些方法为抽象，子类必须实现。

```python
from abc import ABC, abstractmethod

class Tool(ABC):
    @abstractmethod
    def forward(self): ...

class WeatherTool(Tool):
    pass

WeatherTool()
# 💥 TypeError: Can't instantiate abstract class WeatherTool with abstract method forward
```

但**只能查抽象方法**。查不了 "类属性 `name` 必须存在且为 str"。

`__init_subclass__` 更通用，**校验逻辑随便写**。

### 4.2 vs `@dataclass`

完全不同的事：
- `@dataclass`：**生成代码**（自动写 `__init__`）
- `__init_subclass__`：**注入逻辑**（在子类上做手脚）

它俩可以叠用 —— Day 1 笔记 [python-class-and-dataclass.md](python-class-and-dataclass.md) 提过 "`abc.ABC + @dataclass` 有元类冲突"，但 `__init_subclass__ + @dataclass` 没冲突，因为前者不引入新元类。

### 4.3 vs metaclass

`__init_subclass__` 是 **Python 3.6 (PEP 487) 后**为了 "**避免大家写 metaclass**" 引入的**轻量替代**。

```python
# metaclass 写法（重武器）
class ToolMeta(type):
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        # ... 校验
        return cls

class Tool(metaclass=ToolMeta):
    pass

# __init_subclass__ 写法（轻量）
class Tool:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # ... 校验
```

绝大多数 "**子类被定义时做点事**" 的场景，`__init_subclass__` 已经够用，**不需要碰 metaclass**。

> 💡 经验法则：能用 `__init_subclass__` 解决就别上 metaclass。metaclass 元类冲突是 Python 出名的坑（Day 1 已经遇到过 ABC + dataclass 那个）。

---

## 5. `super().__init_subclass__(**kwargs)` 这行

源码这一行：

```python
def __init_subclass__(cls, **kwargs):
    super().__init_subclass__(**kwargs)   # ← 为什么写这行？
    validate_after_init(cls)
```

**理由：合作式继承**。如果 `Tool` 还有别的基类（或者将来加上），它们各自的 `__init_subclass__` 都得跑到。`super().__init_subclass__(**kwargs)` 把链条传下去，避免吃掉别人的钩子。

**写不写的差别**：

```python
# 不写 super 的版本
class A:
    def __init_subclass__(cls, **kwargs):
        print("A hook")

class B:
    def __init_subclass__(cls, **kwargs):
        print("B hook")

class C(A, B):
    def __init_subclass__(cls, **kwargs):
        print("C hook")
        # ← 没调 super().__init_subclass__()
```

```python
class D(C): pass
# 输出：C hook
# A hook 和 B hook 都没跑！
```

加上 `super().__init_subclass__(**kwargs)` 后会沿 MRO 链一路向上调用。

> 💡 这是 Python "MRO walk" 模式，Day 1 的 [callback-registry.md](../day1-memory/callback-registry.md) 见过：CallbackRegistry 也用 `__mro__` 遍历父类。**任何"插钩子"型的设计，都要考虑链式传递的问题**。

---

## 6. 总结表

| 问题 | 答案 |
|---|---|
| `__init_subclass__` 何时触发？ | 子类被**定义**时（class 语句执行那一刻），不是实例化时 |
| 它的入参是啥？ | `cls` = 新定义的子类（不是 self） |
| 它和 `__init__` 关系？ | 完全不同时机：subclass = 定义时（一次），init = 实例化时（每个实例一次） |
| smolagents 用它做什么？ | **仅 wrap 子类 `__init__`**，让实例化时自动跑 `validate_arguments()` |
| 为什么不直接在基类 `__init__` 校验？ | 子类可能忘调 `super().__init__()`，校验被跳过；wrap 的写法强制无法绕过 |
| 和 metaclass 的关系？ | PEP 487 引入的轻量替代，绝大多数场景够用，不要上 metaclass |
| `super().__init_subclass__(**kwargs)` 必须写吗？ | **强烈建议**，否则会吃掉多继承场景下别的基类的钩子 |

---

## 7. 反向自测题

```python
class Tool:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        print(f"hook for {cls.__name__}")
        cls.tag = "registered"


print("--- import 阶段 ---")
class WeatherTool(Tool):
    def __init__(self):
        print("WeatherTool.__init__ 跑了")


print("--- 实例化 ---")
t = WeatherTool()

print("--- 检查 tag ---")
print(WeatherTool.tag)
print(t.tag)
```

**预测输出，再跑代码对照**：

<details>
<summary>答案</summary>

```
--- import 阶段 ---
hook for WeatherTool         ← 注意：还没实例化就打印了
--- 实例化 ---
WeatherTool.__init__ 跑了
--- 检查 tag ---
registered                   ← 类属性，钩子在子类对象上挂的
registered                   ← 实例查不到时会向上找类属性
```

**关键观察**：`hook for WeatherTool` 在 `--- 实例化 ---` 之前就打印了，证明 `__init_subclass__` 触发于子类**定义**时。
</details>

---

## 相关链接

- 源码：[src/smolagents/tools.py](../../../../src/smolagents/tools.py)（特别是 [line 70](../../../../src/smolagents/tools.py#L70)、[line 140](../../../../src/smolagents/tools.py#L140)、[line 144](../../../../src/smolagents/tools.py#L144)）
- Day 1 类似主题笔记：
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) — `@dataclass` / `self` / 抽象方法
  - [callback-registry.md](../day1-memory/callback-registry.md) — 同样用了 MRO walk 模式
- 学习计划：[../../LEARNING_PLAN.md](../../../LEARNING_PLAN.md)
- 外部参考：
  - [PEP 487 — Simpler customisation of class creation](https://peps.python.org/pep-0487/)

## 遗留问题

- [ ] `metaclass` 在哪些场景**不得不**用（`__init_subclass__` 替代不了）？
- [ ] `validate_after_init` 用了 `functools.wraps` 保留元信息，没用 `wraps` 会有什么问题？
- [ ] Day 1 的 user_profile 待解释清单里还有 `*args` / `**kwargs`、`@classmethod` / `@staticmethod` / `@property`，下次遇到时再补
