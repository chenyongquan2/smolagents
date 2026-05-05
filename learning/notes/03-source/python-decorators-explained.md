---
created: 2026-05-05
status: active
tags: [python, prereqs, decorator, syntax, oop]
---

# Python 类语法预习：装饰器（`@xxx`）的本质

## 背景 / 动机

读 [`@tool` 装饰器源码](tool-decorator-implementation.md) 时遇到的疑问：

> `@tool` 是 Python 关键字吗？它怎么能把一个函数变成 Tool 子类的实例？

更早在 Day 1 [python-class-and-dataclass.md](python-class-and-dataclass.md) 也见过 `@dataclass`，当时只说"它是装饰器"没深入。

**装饰器是 Python 中级语法的核心**，后面读 [models.py](../../../src/smolagents/models.py) / [agents.py](../../../src/smolagents/agents.py) 还会遇到 `@property` / `@classmethod` / `@cached_property` / 各种自定义装饰器 —— 现在系统性搞懂，后续回查方便。

读完能回答：

1. `@xxx` 这种语法是 Python 关键字吗？跟 `@dataclass` / `@tool` / `@property` 是什么关系？
2. 装饰器内部到底做了什么？为什么 `@tool` 能让函数"变成"实例？
3. 带参数的装饰器 `@xxx(arg)` 又是什么？
4. 装饰器叠加时（多个 `@`）执行顺序是怎样的？

---

## 1. 一句话定义

**`@xxx` 是 Python 提供的"语法糖"**，把"调用 xxx 包装一个对象"这件事写得更顺眼。

**`xxx` 不是关键字** —— 它是任何"接受一个对象、返回一个新对象"的**可调用对象**（函数 / 类 / 实例都行）。

---

## 2. ⭐ 核心认知：`@xxx` 等价于一行赋值

```python
@xxx
def foo(...):
    ...
```

⬇️ Python 解释器看到这段代码时实际做的事 ⬇️

```python
def foo(...):
    ...
foo = xxx(foo)        # ← 装饰器全部含义就这一行
```

**两段代码完全等价**。**这是装饰器最重要的认知**。

### 一段最小代码验证

```python
def shout(func):
    print(f"shout 被调用了，收到: {func.__name__}")
    return func          # 这里就直接返回原函数，没改它

@shout
def hello():
    return "hi"

# 等价于：
def hello():
    return "hi"
hello = shout(hello)     # 跟 @shout 一回事
```

两种写法运行时**完全一样**：都会打印 "shout 被调用了，收到: hello"。

---

## 3. `@` 是 Python 内置语法，不是关键字

```python
import keyword
print(keyword.kwlist)
# ['False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
#  'break', 'class', 'continue', 'def', 'del', 'elif', 'else', ...]
# ↑ 没有 @、没有 tool、没有 dataclass
```

**Python 关键字（保留字）只有 `def` / `class` / `return` / `if` 这几十个**。`@` 是**符号语法**（不是关键字），跟 `+` / `-` / `:` 一类。

而 `tool` / `dataclass` / `property` 这些 **都是普通名字** —— 它们碰巧被定义为可调用对象，可以放在 `@` 后面。

| 名字 | 来源 | 是关键字吗？|
|---|---|---|
| `@property` | Python builtin | ❌（builtin 函数）|
| `@staticmethod` | Python builtin | ❌（builtin 类）|
| `@dataclass` | 标准库 `dataclasses` 模块 | ❌（普通函数）|
| `@functools.lru_cache` | 标准库 `functools` | ❌（普通函数）|
| `@tool` | smolagents 库 | ❌（普通函数）|

---

## 4. 装饰器可以返回什么？—— 不一定是函数

很多人以为"装饰器装饰函数 → 还是函数"。**错**。装饰器可以返回**任何东西**：原函数、新函数、类、实例、`None` —— 都合法。

### 4.1 返回原函数（最常见）

```python
def log(func):
    print(f"装饰中: {func.__name__}")
    return func          # 原样返回

@log
def f(): pass
type(f)                  # <class 'function'> ← 还是函数
```

### 4.2 返回新函数（"包装层"模式）

```python
def cached(func):
    cache = {}
    def wrapper(x):      # ← 新定义一个函数
        if x not in cache:
            cache[x] = func(x)
        return cache[x]
    return wrapper       # ← 返回新函数

@cached
def slow(x):
    return x * 2

type(slow)               # <class 'function'> ← 还是函数（但不是原来那个）
slow.__name__            # "wrapper" ← 名字也变了
```

### 4.3 返回类（不常见但合法）

```python
def make_class(func):
    class Foo:           # ← 在装饰器里定义类
        pass
    return Foo           # ← 返回类对象

@make_class
def whatever(): pass

type(whatever)           # <class 'type'> ← whatever 现在是个**类**
isinstance(whatever, type)  # True
```

### 4.4 ⭐ 返回实例（这就是 `@tool` 的玩法）

```python
def make_instance(func):
    class Wrapper:
        def __call__(self, *args, **kwargs):
            return func(*args, **kwargs)
    return Wrapper()     # ← 返回实例（注意是 Wrapper() 不是 Wrapper）

@make_instance
def hello(name):
    return f"Hi {name}"

type(hello)              # <class '...Wrapper'> ← hello 现在是个**实例**
hello("Alice")           # "Hi Alice" ← 通过 __call__ 触发
```

> 💡 **`@tool` 装饰器就是用 4.4 这种"返回实例"模式** —— 在装饰器内部定义 `class SimpleTool(Tool):`、实例化、返回实例（详见 [tool-decorator-implementation.md](tool-decorator-implementation.md)）。

---

## 5. 装饰器叠加 —— 从下往上

```python
@A
@B
@C
def foo(): ...
```

⬇️ 等价于 ⬇️

```python
def foo(): ...
foo = A(B(C(foo)))    # ← 从下往上嵌套
```

**执行顺序**：先 `C(foo)` 产出新对象 → 再 `B(...)` 包一层 → 最后 `A(...)` 包最外层。

> 💡 想成"洋葱包装"：最靠近 def 的装饰器（C）最贴近原函数，最上面的（A）在最外层。这跟 stack（栈）的 LIFO 规则一致。

---

## 6. 带参数的装饰器：`@xxx(arg)`

有时候我们见到这种写法：

```python
@functools.lru_cache(maxsize=128)
def slow_func(x): ...
```

`@xxx(arg)` 跟 `@xxx` 不同 —— **`@` 后面的是表达式 `xxx(arg)` 的求值结果，不是 `xxx` 本身**。

### 等价展开

```python
@xxx(arg)
def foo(): ...
```

⬇️ 等价于 ⬇️

```python
def foo(): ...
foo = xxx(arg)(foo)    # ← 注意括号嵌套
```

**两步调用**：
1. `xxx(arg)` 返回一个**装饰器函数**（叫 `decorator_with_arg`）
2. `decorator_with_arg(foo)` 才是真正的装饰

### 实现示例

```python
def repeat(n):                       # ① 第一层：接受参数
    def decorator(func):              # ② 第二层：接受函数
        def wrapper(*args, **kwargs): # ③ 第三层：包装调用
            for _ in range(n):
                result = func(*args, **kwargs)
            return result
        return wrapper
    return decorator                  # 返回真正的装饰器

@repeat(3)
def say_hi():
    print("hi")

say_hi()
# hi
# hi
# hi  ← 跑了 3 次
```

> 💡 **辨认技巧**：
> - `@xxx` → xxx 是装饰器
> - `@xxx(arg)` → xxx 是"装饰器工厂"，调用后**返回**装饰器

---

## 7. ⭐ 回到 `@tool` —— 用上面所有知识解释

打开 [tools.py:1061-1168](../../../src/smolagents/tools.py#L1061)：

```python
def tool(tool_function: Callable) -> Tool:
    # 解析 schema
    tool_json_schema = get_json_schema(tool_function)["function"]
    
    # 在函数体内动态造类（§4.3 + §4.4 的玩法）
    class SimpleTool(Tool):
        def __init__(self):
            self.is_initialized = True
    
    # 给新类挂类属性（schema）
    SimpleTool.name = tool_json_schema["name"]
    SimpleTool.description = tool_json_schema["description"]
    ...
    
    # 把原始函数挂到 forward
    SimpleTool.forward = staticmethod(wrapped_function)
    
    # ⭐ 实例化 + 返回实例
    return SimpleTool()
```

**用本笔记的概念解释**：

| 步骤 | 对应本笔记节 |
|---|---|
| `tool` 是普通 Python 函数（不是关键字）| §3 |
| `tool(tool_function)` 接受一个函数对象作为参数 | §2 |
| 内部 `class SimpleTool(Tool):` 在函数体内定义类 | §4.3（class 是语句，可写在任何地方）|
| 最后 `return SimpleTool()` 返回**实例** | §4.4 |
| 用户的 `my_tool` 这个名字**指向这个实例**，不再是原函数 | §2 等价赋值 |

`@tool` 的"魔法"完全可以用本笔记 5 个概念组合解释。**不是魔法，是 Python 语法的标准用法**。

---

## 8. 总结表

| 问题 | 答案 |
|---|---|
| `@` 是关键字吗？ | **不是**。是 Python 内置的装饰器**语法符号**（同 `+` / `-`）|
| `@xxx` 等价于什么？ | `foo = xxx(foo)` —— 一行赋值 |
| `xxx` 必须是函数吗？ | 不必。任何可调用对象（函数/类/实例）都行 |
| 装饰器返回值必须是函数吗？ | **不必**。可以是函数/类/实例/None —— `@tool` 返回的是实例 |
| `@xxx(arg)` 跟 `@xxx` 区别？ | `xxx(arg)` 先求值得到装饰器函数，再装饰 → 两步调用 |
| 装饰器叠加 `@A @B @C` 顺序？ | **从下往上**：`A(B(C(foo)))` |
| 装饰器在什么时候执行？ | 函数（或类）**定义时**，不是调用时 |
| `@tool` 的核心机制？ | 在函数体内动态造 `SimpleTool(Tool)` 类 + 返回实例 |

---

## 9. 反向自测题

### 题 1

```python
def add_attr(func):
    func.tag = "decorated"
    return func

@add_attr
def hello():
    return "hi"

print(hello.tag)        # ?
print(hello())           # ?
print(type(hello))       # ?
```

<details>
<summary>答案</summary>

```
decorated
hi
<class 'function'>
```

装饰器只是给函数挂了个属性，没改函数本体。`hello` 还是原函数。
</details>

### 题 2

```python
def make_counter(func):
    count = 0
    def wrapper(*args, **kwargs):
        nonlocal count
        count += 1
        print(f"第 {count} 次调用")
        return func(*args, **kwargs)
    return wrapper

@make_counter
def greet(name):
    return f"hello {name}"

greet("a")
greet("b")
greet("c")
```

预测输出？

<details>
<summary>答案</summary>

```
第 1 次调用
第 2 次调用
第 3 次调用
```

`count` 是 `make_counter` 的局部变量，被 `wrapper` 闭包捕获 → 每次调 `greet` 都是同一个 `wrapper`，共享 `count`。
</details>

### 题 3 ⭐

```python
def to_class(func):
    class Foo:
        x = 100
    return Foo

@to_class
def whatever():
    return "this never runs"

print(whatever)          # ?
print(whatever.x)        # ?
print(whatever())        # 会报错吗？
```

<details>
<summary>答案</summary>

```
<class '__main__.to_class.<locals>.Foo'>
100
TypeError: Foo() takes no arguments  ← 实际：会成功，因为没传参也合法
                                       但这调用的是 Foo() —— 实例化！
```

实际运行 `whatever()` 是**实例化** `Foo` —— 因为 `whatever` 不再是函数而是类。`whatever()` 创建一个 `Foo` 实例。`return "this never runs"` 永远不会执行（原函数体被丢弃了）。

**这就是 `@tool` 玩法的同模式**。
</details>

### 题 4

```python
def A(func):
    print("A 装饰")
    return func

def B(func):
    print("B 装饰")
    return func

@A
@B
def hello():
    print("hello 跑了")

# 加载这段代码时打印什么？
# hello() 调用时打印什么？
```

<details>
<summary>答案</summary>

加载时打印（**注意顺序**）：
```
B 装饰
A 装饰
```

调用 `hello()` 时打印：
```
hello 跑了
```

装饰器从下往上执行：先 B 装饰 → 再 A 装饰。
</details>

---

## 10. 与 Java / TypeScript / JS 对比

| 语言 | 装饰器语法 | 关键字 / 库 |
|---|---|---|
| Python | `@xxx` 函数前 | 内置语法符号 + 普通函数名 |
| Java | `@Annotation` | 内置语法 + 必须是注解类（处理逻辑由编译器/运行时框架接收）|
| TypeScript | `@xxx` 类/方法前 | 实验性特性，需 `experimentalDecorators: true` |
| JavaScript | `@xxx` (Stage 3 提案) | 通过 Babel/TS 转译，浏览器原生支持还在路上 |

**Python 装饰器最大的优势**：**`xxx` 是普通函数，不需要任何特殊语法或元数据**。任何"接受函数、返回新对象"的可调用对象都能用作装饰器。这让装饰器**异常灵活**，是 Python 元编程的基石之一。

> 💡 类比：Java 注解是**声明式标记**（编译器/框架解读其语义），Python 装饰器是**主动改造**（装饰器自己执行 + 改变绑定）。本质完全不同。

---

## 相关链接

- 源码：[tools.py:1061](../../../src/smolagents/tools.py#L1061) — `@tool` 装饰器实现，本笔记的核心实战例子
- 相关笔记：
  - [tool-decorator-implementation.md](tool-decorator-implementation.md) — `@tool` 装饰器源码逐行解读（Day 2 段 5 彩蛋）
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) — `@dataclass` 装饰器初次接触（Day 1）
  - [python-class-vs-instance-attributes.md](python-class-vs-instance-attributes.md) — 装饰器内部 `class Foo:` 写法的合法性依据
- Python 官方文档：
  - [PEP 318 — Decorators for Functions and Methods](https://peps.python.org/pep-0318/)
  - [PEP 3129 — Class Decorators](https://peps.python.org/pep-3129/)（也能装饰类）

## 遗留问题

- [ ] `@functools.wraps` —— 让装饰器保留被装饰函数的元数据（`__name__` / `__doc__` 等），常见好习惯
- [ ] 类装饰器（`@dataclass` 装饰类，不是函数）—— 同样的语法糖适用于 class
- [ ] 用类作为装饰器（`__call__` 实现） —— 进阶玩法，碰到再说
