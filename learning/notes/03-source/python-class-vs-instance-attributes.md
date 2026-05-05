---
created: 2026-05-05
status: active
tags: [python, prereqs, oop, class-attribute, instance-attribute, syntax]
---

# Python 类语法预习：类属性 vs 实例属性

## 背景 / 动机

Day 2 看 [tools.py:131-135](../../../src/smolagents/tools.py#L131) 时遇到的疑问：

```python
class Tool(BaseTool):
    name: str
    description: str
    inputs: dict[...]
    output_type: str
    output_schema: dict[str, Any] | None = None
```

用户子类是这样写的：

```python
class WeatherTool(Tool):
    name = "get_temperature"        # ← 这一行写在 class 体里
    description = "..."
    inputs = {...}
    output_type = "number"
    def forward(self, city): ...
```

**问题**：`tool.name` 看起来像在访问 "对象属性"，但 `name` 写在 class 体里、不在 `__init__`，**到底是类属性还是实例属性**？

涉及 4 个问题：

1. 类属性 / 实例属性 怎么区分？写法上有什么差异？
2. `tool.name` 这种访问是怎么"找到"值的？
3. 改类属性 vs 改实例属性，影响范围有什么差异？
4. smolagents 为什么把 `name` / `description` / `inputs` / `output_type` 设计成类属性而不是 `__init__` 参数？

> 💡 **直接答案**：Tool 子类里这 4 个**全是类属性**。所有实例**共享同一份**。下面会讲清楚为什么。

---

## 1. 一句话定义

| 概念 | 写法 | 挂在哪 |
|---|---|---|
| **类属性** | 写在 `class` 体里直接赋值（`name = "x"`） | **类对象**上 |
| **实例属性** | `__init__` 里 `self.x = ...` 赋值 | **实例对象**上 |

> 💡 **关键直觉**：Python 里"赋值"的本质是"挂属性"。`Foo.x = 1` 是给类对象挂属性，`f.x = 1` 是给实例对象挂属性。**两个不同的对象**，挂在哪取决于**赋值时左边是谁**。

---

## 2. 一段代码看清差异

```python
class Foo:
    shared = "hello"            # 类属性 —— 写在 class 体里

f1 = Foo()
f2 = Foo()

print(f1.shared, f2.shared)     # hello hello —— 都来自类
print(Foo.shared)                # hello

# 改类属性 → 所有实例都看到新值
Foo.shared = "world"
print(f1.shared, f2.shared)     # world world ← 都变了

# 给某个实例挂同名属性 → "遮蔽"了类属性
f1.shared = "私货"
print(f1.shared)                 # 私货 ← 实例自己的
print(f2.shared)                 # world ← 还是类的
print(Foo.shared)                # world ← 类的没变
```

> 💡 **"遮蔽"是个重要概念**：实例属性可以和类属性同名，访问时**实例优先**（详见 §4 的查找机制）。

---

## 3. 用 `__dict__` 看实际存储位置

每个 Python 对象（包括类对象）都有一个 `__dict__` 属性，存它身上挂的属性。**眼见为实**：

```python
class Foo:
    shared = "hello"            # 类属性

    def __init__(self):
        self.private = "hi"     # 实例属性

f = Foo()

print(Foo.__dict__)
# {'shared': 'hello', '__init__': <function ...>, ...}
#  ↑ shared 在类对象的 __dict__ 里

print(f.__dict__)
# {'private': 'hi'}
#  ↑ 只有 private，没有 shared
```

**结论**：
- `shared` 物理上**只存在于** `Foo.__dict__`
- `private` 物理上**只存在于** `f.__dict__`
- 你写 `f.shared` 能取到值，是因为 Python 找不到时会**自动向类查**（见下节）

---

## 4. ⭐ Python 的属性查找机制（attribute lookup）

当你写 `f.x` 时，Python 按这个顺序找：

```
1. 查 f.__dict__              ← 实例自己有吗？
   ├─ 有 → 返回
   └─ 没有 ↓
2. 查 type(f).__dict__         ← 实例的类有吗？
   ├─ 有 → 返回
   └─ 没有 ↓
3. 沿 MRO 查父类的 __dict__    ← 父类、祖父类...
   ├─ 找到 → 返回
   └─ 没有 → 抛 AttributeError
```

回到 `tool.name` 的例子：

```python
tool = WeatherTool()
tool.name    # ← 这个表达式怎么求值？

# 第 1 步：查 tool.__dict__ → {"is_initialized": False}，没有 name
# 第 2 步：查 WeatherTool.__dict__ → 有 {"name": "get_temperature"}，命中！
# 返回 "get_temperature"
```

> 💡 **重点**：`tool.name` 在**语法上**像访问对象属性，**实际上**值是从类对象上拿的。这是 Python 的"自动向类回退"机制让访问看起来透明。

---

## 5. 类比已知（其他语言对照）

### 类比 Java 的 `static` 字段

```java
class Foo {
    static String shared = "hello";   // 类属性（Java 用 static 关键字）
    String private_;                   // 实例属性（默认）
}
```

| Python | Java |
|---|---|
| 类属性（class 体里赋值） | `static` 字段 |
| 实例属性（`self.x =`） | 普通字段 |
| `Foo.shared` | `Foo.shared`（一样） |
| `f.shared` 也能取到（向类回退） | `f.shared` ⚠️ Java 编译器会警告，建议 `Foo.shared` |

> 💡 Python 不区分 `static` —— 写在 class 体里的赋值**自动**就是类属性。Java 必须显式用 `static` 关键字。

### 类比 JavaScript 的 class fields

```javascript
class Foo {
    static shared = "hello";    // 类属性
    private_;                    // 实例属性（ES2022+）
    
    constructor() {
        this.private_ = "hi";   // 也是实例属性
    }
}
```

JavaScript 的 `static` 关键字明确标记类属性 —— 跟 Java 类似，比 Python 更显式。

---

## 6. ⭐ 回到 Tool —— 为什么 smolagents 这样设计

打开 [tools.py:131-135](../../../src/smolagents/tools.py#L131)：

```python
class Tool(BaseTool):
    name: str                                # ← 仅类型注解，无赋值
    description: str
    inputs: dict[...]
    output_type: str
    output_schema: dict[str, Any] | None = None    # ← 有赋值，类属性
```

**Tool 基类**：前 4 个**只是类型注解，没赋值**。所以**什么属性都没创建**（Day 1 [python-class-and-dataclass.md](python-class-and-dataclass.md) §4 讲过）。注解只给 IDE / mypy / 装饰器读，**不创建属性**。

**用户子类必须在 class 体里赋值**：

```python
class WeatherTool(Tool):
    name = "get_temperature"     # 类属性
    description = "..."           # 类属性
    inputs = {...}                # 类属性
    output_type = "number"        # 类属性

    def forward(self, city): ...
```

这就是为什么 `validate_arguments`（[tools.py:144](../../../src/smolagents/tools.py#L144)）要用 `getattr(self, "name", None)` 而不是直接 `self.name` —— **如果用户子类忘了赋值，`self.name` 会因为找不到而抛 AttributeError**，错误信息不友好。`getattr(..., None)` 拿不到时返回 None，让代码可以打印 "You must set an attribute name." 这种友好错误。

### 为什么不写在 `__init__` 里？

假设的反例：

```python
class WeatherTool(Tool):
    def __init__(self):
        self.name = "weather"        # 实例属性
        self.description = "..."     # 实例属性
        ...
```

**这样写也能 work，但有 4 个问题**：

1. **每次 `WeatherTool()` 都重新赋值一次** —— 浪费 CPU
2. **每个实例独立一份 `inputs` 字典副本** —— 浪费内存（100 个实例 = 100 份 dict）
3. **schema 不再有"类级别"稳定性** —— 让人误以为 schema 可以在实例间不同（实际不应该）
4. ⭐ **`__init_subclass__` 校验时拿不到值** —— `__init_subclass__` 在子类定义时跑（实例都还没创建），那时只能查类属性。如果 schema 写在 `__init__` 里，校验只能推迟到实例化以后

> 💡 **设计原则**：**类属性表达"这种东西的固有性质"，实例属性表达"这个具体东西的当前状态"**。Tool 的 schema 是"固有性质"（这种工具本质上长这样），所以选类属性。`is_initialized` 是"当前状态"（这个具体实例有没有 setup 过），所以选实例属性。

---

## 7. 实际验证 Tool 的属性归属

```python
from smolagents import Tool

class WeatherTool(Tool):
    name = "weather"
    description = "test"
    inputs = {}
    output_type = "string"
    def forward(self): pass

t1 = WeatherTool()
t2 = WeatherTool()

# 实例自己的 __dict__ 只有 is_initialized
print(t1.__dict__)
# {'is_initialized': False}     ← 这才是实例属性

# name / description 都在类对象上
print(WeatherTool.__dict__["name"])         # "weather"
print(WeatherTool.__dict__["description"])  # "test"

# 改类属性，两个实例都受影响
WeatherTool.name = "weather_v2"
print(t1.name, t2.name)                     # weather_v2 weather_v2

# 给单个实例打私货 —— 遮蔽类属性
t1.name = "私货"
print(t1.name, t2.name)                     # 私货 weather_v2
print(WeatherTool.name)                     # weather_v2 ← 类的没变
```

---

## 8. 常见踩坑

### 坑 1：可变类属性被多个实例共享改坏

```python
class Foo:
    items = []                  # ⚠️ 类属性，所有实例共享

f1 = Foo()
f2 = Foo()
f1.items.append("hello")        # 注意：是 .append 不是 .items =
print(f2.items)                 # ['hello']  ← f2 也受影响了！
```

**原因**：`f1.items.append(...)` **没有给 f1 挂新属性**，是在**类的 `items` 列表对象**上调用方法。f1 和 f2 通过查找机制看到的是同一个 list 对象。

**正解**：可变默认值用实例属性：

```python
class Foo:
    def __init__(self):
        self.items = []         # 每个实例独立的 list
```

### 坑 2：以为类属性赋值 = 改类属性

```python
class Foo:
    shared = "hello"

f = Foo()
f.shared = "world"              # ← 这不是改类属性！
                                # ← 是给 f 挂了一个名为 shared 的实例属性
print(f.shared)                 # world ← 实例自己的
print(Foo.shared)               # hello ← 类的没动
```

**Python 赋值规则**：`f.x = ...` 永远是给 `f` 挂属性，不会"穿透"到类。要改类属性必须 `Foo.x = ...`。

### 坑 3：类属性是不可变值时，看起来"被改了"

```python
class Foo:
    count = 0

f1 = Foo()
f1.count += 1                   # ← 这是 f1.count = f1.count + 1
                                #   读取走查找（拿到类的 0）
                                #   赋值给 f1 自己挂 count = 1
print(f1.count)                 # 1
print(Foo.count)                # 0 ← 没变
```

`+=` 在不可变类型上**实际上是创建新值再赋值**，所以不会改类属性。

---

## 9. 总结表

| 问题 | 答案 |
|---|---|
| 类属性怎么写？ | class 体里直接赋值 `name = "x"` |
| 实例属性怎么写？ | `__init__` 里 `self.x = ...` |
| 物理存哪？ | 类属性在 `Cls.__dict__`、实例属性在 `obj.__dict__` |
| `obj.x` 怎么找到值？ | 先查实例 → 没有再查类 → 还没有沿 MRO 查父类 |
| 改类属性影响谁？ | 所有实例（除非有同名实例属性遮蔽） |
| 改实例属性影响谁？ | 只影响那个实例 |
| Tool 的 name/description 是哪种？ | **类属性**（用户子类在 class 体里赋值） |
| 为什么 smolagents 选类属性而不是 `__init__`？ | 1) schema 是固有性质 2) 省内存 3) 让 `__init_subclass__` 能在子类定义时校验 |
| Tool 的 is_initialized 是哪种？ | **实例属性**（在 `__init__` 里 `self.is_initialized = False`）|

---

## 10. 反向自测题

```python
class Counter:
    total = 0

    def __init__(self):
        self.local = 0

    def inc(self):
        self.local += 1
        Counter.total += 1


a = Counter()
b = Counter()
a.inc()
a.inc()
b.inc()

# 预测下面 4 个值
print(a.local)         # ?
print(b.local)         # ?
print(Counter.total)   # ?
print(a.total)         # ?
```

<details>
<summary>答案</summary>

```
a.local        = 2     ← a 自己的实例属性，独立计数
b.local        = 1     ← b 自己的实例属性，独立计数
Counter.total  = 3     ← 类属性，所有实例共享
a.total        = 3     ← 实例 a 没有 total 属性，向类回退找到 3
```

**关键观察**：`Counter.total += 1` 显式改类属性 → 全局生效；`self.local += 1` 改实例属性 → 各自独立。如果错写成 `self.total += 1`，会发生坑 3：a 自己挂一个 total=1，类的 total 没变。
</details>

---

## 相关链接

- 源码：
  - [tools.py:131-135](../../../src/smolagents/tools.py#L131) — Tool 基类的 4 个类型注解
  - [tools.py:138](../../../src/smolagents/tools.py#L138) — `is_initialized = False`（唯一真正的实例属性）
  - [tools.py:144](../../../src/smolagents/tools.py#L144) — `validate_arguments` 用 `getattr(self, attr, None)` 友好处理缺失属性
- 相关笔记：
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) — 与 dataclass 的关系（§4 "Python 没有字段声明"）
  - [python-init-subclass.md](python-init-subclass.md) — `__init_subclass__` 在子类定义时跑，那时只能查类属性
  - [tool-class-role-overview.md](tool-class-role-overview.md) — Tool 的 4 个类属性 + 1 个实例属性总览

## 遗留问题

- [ ] `@property` / `@classmethod` / `@staticmethod` 装饰器（user_profile 待解释清单里还有这些）
- [ ] `__slots__` —— 限制实例属性、节省内存的进阶技巧（碰到再说）
- [ ] 描述符协议（`__get__` / `__set__`） —— 类属性更深层的机制，进阶话题
