---
created: 2026-05-05
status: active
tags: [smolagents, tools, decorator, source-reading, week1-verification]
---

# `@tool` 装饰器的源码实现：验证 Week 1 三个结论

## 背景 / 动机

Week 1 [tool-creation-decorator-vs-subclass.md](../02-concepts/tool-creation-decorator-vs-subclass.md) 写过 3 条关于 `@tool` 装饰器的结论：

1. **`@tool` 内部就是动态构造 Tool 子类**，区别只在能不能带 `__init__` 参数
2. **`@tool` 的 forward 是 staticmethod**，所以挂不住实例资源（"重型资源用子类、轻量函数用 @tool"）
3. **装饰后的 `foo` 不再是函数**，而是一个 SimpleTool 的实例

Day 2 段 5 彩蛋 = **打开源码 [tools.py:1061-1168](../../../src/smolagents/tools.py#L1061) 验证这 3 条**。

> 💡 这是 **Week 1 → Week 2 的闭环时刻**：你听过的"为什么"在源码里看到了"怎么做"。

---

## 1. 一句话定义

`@tool` 装饰器 = **接受一个普通 Python 函数 → 动态构造一个 Tool 子类 + 实例化 → 返回这个实例**。

签名（[tools.py:1061](../../../src/smolagents/tools.py#L1061)）：

```python
def tool(tool_function: Callable) -> Tool:
    ...
```

注意返回类型是 **`Tool`**（一个实例），不是 `type[Tool]`（一个类）。这就直接证明了 Week 1 结论 ③：**装饰后 foo 不再是函数，是 SimpleTool 实例**。

---

## 2. ⭐ 验证 Week 1 结论 ①：动态构造 Tool 子类

源码 [tools.py:1080-1088](../../../src/smolagents/tools.py#L1080)：

```python
class SimpleTool(Tool):                            # ① 在函数体内定义子类
    def __init__(self):
        self.is_initialized = True

# Set the class attributes
SimpleTool.name = tool_json_schema["name"]         # ② 在函数体内挂类属性
SimpleTool.description = tool_json_schema["description"]
SimpleTool.inputs = tool_json_schema["parameters"]["properties"]
SimpleTool.output_type = tool_json_schema["return"]["type"]
```

**两个关键观察**：

1. **`class SimpleTool(Tool):` 写在函数内部** —— 每次 `@tool` 装饰一个函数，**都会在内存里造出一个新的 SimpleTool 类**（不同的类对象，不是同一个）
2. **类属性是事后用赋值挂上去的** —— 通过 `get_json_schema(tool_function)` 解析函数的类型注解 + docstring 拼出 `inputs` 字典 → 然后赋值到类对象上

> 💡 联系 [python-class-vs-instance-attributes.md](python-class-vs-instance-attributes.md) §6 —— smolagents 全程把 schema 设计成**类属性**，连动态构造时也是直接挂在 `SimpleTool.xxx` 上而不是在 `__init__` 里 `self.xxx`。一致性贯彻得很彻底。

**verbatim 验证 Week 1 结论 ①** ✅

---

## 3. ⭐ 验证 Week 1 结论 ②：forward 是 staticmethod

源码 [tools.py:1096-1101](../../../src/smolagents/tools.py#L1096)：

```python
@wraps(tool_function)
def wrapped_function(*args, **kwargs):
    return tool_function(*args, **kwargs)

# Bind the copied function to the forward method
SimpleTool.forward = staticmethod(wrapped_function)   # ⭐ 关键
```

**`SimpleTool.forward = staticmethod(wrapped_function)` 这一行**就是 Week 1 那条"挂不住资源"的根源。

### 为什么 staticmethod 挂不住资源？

普通方法（实例方法）签名是 `def forward(self, ...)`，第一个参数 `self` 让方法能访问实例状态：

```python
class HeavyTool(Tool):
    def __init__(self):
        self.model = load_huge_model()    # 实例属性
    
    def forward(self, x):
        return self.model.predict(x)      # ✅ 通过 self 访问
```

**staticmethod 没有 self**：

```python
@tool
def my_tool(x: str) -> str:
    """..."""
    return x.upper()
# 装饰后 my_tool 是 SimpleTool 实例
# my_tool.forward 是 staticmethod 包装的 wrapped_function
# 调用时 wrapped_function(x) —— 没有 self 参数

# 所以你**不可能**在 @tool 装饰的函数体内访问"实例状态"
# 因为根本没有"实例"概念
```

### 实际后果

```python
# ❌ 用 @tool 不行（没法 init 模型）：
@tool
def predict(text: str) -> str:
    """..."""
    return model.predict(text)   # model 从哪来？没法在装饰器场景下注入

# ✅ 用 Tool 子类才行：
class PredictTool(Tool):
    name = "predict"
    description = "..."
    inputs = {"text": {"type": "string", "description": "..."}}
    output_type = "string"
    
    def __init__(self):
        super().__init__()
        self.model = load_huge_model()    # 实例化时一次性加载
    
    def forward(self, text):
        return self.model.predict(text)   # 通过 self 访问，运行多次复用
```

**这就是 Week 1 那张决策表 "重型资源用子类，轻量函数用 @tool" 的源码层依据** ✅

---

## 4. ⭐ 验证 Week 1 结论 ③：装饰后 foo 是实例不是函数

源码末尾 [tools.py:1167-1168](../../../src/smolagents/tools.py#L1167)：

```python
simple_tool = SimpleTool()       # ① 实例化
return simple_tool                # ② 返回实例
```

所以：

```python
@tool
def get_temperature(city: str) -> float:
    """..."""
    return 25.0

# 装饰之后：
type(get_temperature)            # <class 'smolagents.tools.SimpleTool'>
                                  # ↑ 不是 function，是 SimpleTool 实例！
get_temperature.name             # "get_temperature"
get_temperature.description      # ...
get_temperature("Beijing")       # 25.0  ← 走 __call__ → forward
```

**`get_temperature` 已经不是原来的函数了，是个 SimpleTool 实例**。Python 装饰器的本质就是 `get_temperature = tool(get_temperature)` —— 名字保留，对象被替换。

**verbatim 验证 Week 1 结论 ③** ✅

---

## 5. 延伸洞察：你没见过的 2 个细节

读源码顺手发现 2 个 Week 1 没讲的细节：

### 5.1 schema 是从函数本身解析出来的

源码 [tools.py:1071](../../../src/smolagents/tools.py#L1071)：

```python
tool_json_schema = get_json_schema(tool_function)["function"]
```

**`get_json_schema` 是 transformers 的工具函数**（smolagents 复用），它通过：
- 函数的**类型注解** → 推导 `inputs` 各字段的 type
- 函数的 **docstring `Args:` 段** → 推导 `description`

也就是说，写 `@tool` 时**必须给类型注解 + docstring 的 Args 段**，否则 schema 推导失败。

```python
# ❌ 这样会崩
@tool
def bad_tool(x):                 # ← 没类型注解
    return x

# ✅ 这样才行
@tool
def good_tool(x: str) -> str:
    """Description here.
    
    Args:
        x: The input string.     ← 必须有 Args 段
    """
    return x
```

> 💡 这就是为什么 Week 1 写的 `@tool` demo 里 docstring 看起来"非常正式"。**不是为了好看，是协议要求**。

### 5.2 `SimpleTool` 也保留了源码字符串

源码 [tools.py:1162-1165](../../../src/smolagents/tools.py#L1162)：

```python
SimpleTool.__source__ = class_source
SimpleTool.forward.__source__ = forward_method_source
```

装饰器**反向重建**了一份"如果你手写 Tool 子类会怎么写"的源码字符串，挂在 `__source__` 属性上。

**用途**：`to_dict()` 序列化（[tool-schema-rendering-mental-model.md](tool-schema-rendering-mental-model.md) §7.4 提到的 SimpleTool 分支）需要这份源码字符串才能 push_to_hub —— 你装饰一个函数，最后能上传到 HF Hub 当一个完整的 Tool 子类。

> 💡 这条揭示了 **`@tool` 装饰器并不是"轻量替代品"**，而是真的把函数变成了一个等价的 Tool 子类（连源码字符串都帮你生成好），只是少了 `__init__` 参数和实例状态而已。

---

## 6. 总结表

| Week 1 结论 | 源码验证位置 | 状态 |
|---|---|---|
| ① `@tool` 内部就是动态构造 Tool 子类 | [tools.py:1080](../../../src/smolagents/tools.py#L1080) `class SimpleTool(Tool):` 写在函数内 | ✅ 验证 |
| ② forward 是 staticmethod，挂不住资源 | [tools.py:1101](../../../src/smolagents/tools.py#L1101) `SimpleTool.forward = staticmethod(...)` | ✅ 验证 |
| ③ 装饰后 foo 是实例不是函数 | [tools.py:1167-1168](../../../src/smolagents/tools.py#L1167) `return simple_tool` | ✅ 验证 |

**延伸洞察**：

| 洞察 | 含义 |
|---|---|
| schema 来自类型注解 + docstring Args 段 | `@tool` 对函数签名的"严格要求"是协议层的，不是约定 |
| `__source__` 字符串反向重建 | `@tool` 不是替代品，是等价转换；连 push_to_hub 都能用 |

---

## 7. Week 1 → Week 2 闭环

把今天的发现连起来：

```
Week 1 概念：       @tool 是动态子类（猜想）
                          │
                          ▼
Week 2 段 5 彩蛋：  打开源码看到 class SimpleTool(Tool) 真的写在函数内
                          │
                          ▼
未来 Week 3：       自己写 @tool 时知道要给完整 docstring，
                  并且知道什么场景下应该改用 Tool 子类（重资源场景）
```

**这就是源码阅读的真正价值** —— 不是为了背代码，是为了**让 Week 1 的"为什么"和 Week 3 的"怎么用"在脑子里联通**。

---

## 相关链接

- 源码：[tools.py:1061-1168](../../../src/smolagents/tools.py#L1061) — `@tool` 装饰器实现
- Week 1 概念笔记：[tool-creation-decorator-vs-subclass.md](../02-concepts/tool-creation-decorator-vs-subclass.md) — 三个结论的原始出处
- 横向关联：
  - [python-class-vs-instance-attributes.md](python-class-vs-instance-attributes.md) — 为什么 `@tool` 也用类属性挂 schema
  - [tool-schema-rendering-mental-model.md](tool-schema-rendering-mental-model.md) §7.4 — `to_dict` 在 SimpleTool 分支用 `__source__` 序列化

## 遗留问题

- [ ] `get_json_schema` 内部怎么从类型注解 + docstring 推 schema 的？（[_function_type_hints_utils.py:97](../../../src/smolagents/_function_type_hints_utils.py#L97) 有完整实现，碰到再读）
- [ ] `inspect.signature.replace()` 加 self 的技巧（[tools.py:1106-1108](../../../src/smolagents/tools.py#L1106)） —— Python 反射进阶用法
