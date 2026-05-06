---
created: 2026-05-05
status: active
tags: [python, syntax, args, kwargs, prerequisite, source-reading]
---

# Python `*args` 与 `**kwargs`：含义、区别、smolagents 怎么用

## 背景 / 动机

读 [models.py:484](../../../src/smolagents/models.py#L484) 的 `Model.__init__`：

```python
def __init__(self, flatten_messages_as_text=False, ..., model_id=None, **kwargs):
    ...
    self.kwargs = kwargs
```

会看到 `**kwargs` 兜底，并且最后**最高优先级**地覆盖到 HTTP body。理解这一招的前提是先搞清楚：

1. `kwargs` 是什么？
2. `*args` 和 `**kwargs` 有什么区别？
3. 为什么这里选 `**kwargs` 不选 `*args`？

---

## 1. 名字溯源

| 写法 | 全称 | 含义 |
|---|---|---|
| `*args` | **arg**ument**s** | "剩余的位置参数" |
| `**kwargs` | **k**ey**w**ord **arg**ument**s** | "剩余的关键字参数" |

⚠️ **`args` / `kwargs` 这两个名字不是 Python 关键字，是社区铁打的命名约定**。语法关键字是那两个 `*` 号。技术上你可以写 `**foobar`，但**别这么干** —— 所有人看到 `**kwargs` 立刻知道含义。

---

## 2. ⭐ 核心区别 = **传参方式不同**

Python 函数调用有两种传参方式：

| 传参方式 | 调用写法 | 谁兜底 | 收集成 |
|---|---|---|---|
| 位置参数（按顺序对位）| `foo(1, 2, 3)` | `*args` | **tuple** |
| 关键字参数（按名字赋值）| `foo(x=1, y=2)` | `**kwargs` | **dict** |

```python
def f(*args, **kwargs):
    print("args  =", args, type(args).__name__)
    print("kwargs=", kwargs, type(kwargs).__name__)

f(1, 2, 3, x=10, y=20)
# args   = (1, 2, 3) tuple        ← 没名字的，按位置进 tuple
# kwargs = {'x': 10, 'y': 20} dict ← 带名字的，进 dict
```

**记忆口诀**：
- 一颗星 `*` → 一层结构 → **tuple**（线性序列）
- 两颗星 `**` → 两层结构 → **dict**（key-value）

> 💡 **关键差异是"信息量"**：tuple 只记得"第几个"，dict 记得"叫什么"。`**kwargs` 表达力更强 —— 它知道每个值对应哪个参数名。

### 不同调用方式自动分流

```python
f(1, 2, x=3)    # args=(1, 2)   kwargs={'x': 3}
f(1, 2)         # args=(1, 2)   kwargs={}
f(x=3, y=4)     # args=()       kwargs={'x': 3, 'y': 4}
f()             # args=()       kwargs={}
```

不管怎么传，Python 帮你按"有没有 `=` 号"自动分流。

---

## 3. `**` 在两端含义对称（打包 ↔ 拆包）

```python
# 定义端：把多余 keyword 参数 **打包**成 dict
def foo(a, b, **kwargs): ...

# 调用端：把 dict **拆包**成 keyword 参数喂进去
foo(**{"a": 1, "b": 2, "x": 10})
# 等价于 foo(a=1, b=2, x=10)
# 函数内部：a=1, b=2, kwargs={"x": 10}
```

`*` 也一样对称：

```python
def f(*args): print(args)
f(*[1, 2, 3])    # args=(1, 2, 3)，等价 f(1, 2, 3)
```

---

## 4. ⭐ 为什么 `Model.__init__` 用 `**kwargs` 不用 `*args`？

**核心原因**：LLM 配置参数**全都是带名字的**（`temperature=0.7` 而不是裸 `0.7`），位置参数表达不了这种语义。

### 反例：如果用 `*args`

```python
def __init__(self, flatten_messages_as_text=False, model_id=None, *args):
    self.args = args

# 用户必须按位置传：温度 / top_p / max_tokens
model = SomeModel(False, "Qwen/...", 0.7, 0.9, 1024)
#                                    ↑    ↑    ↑
#                       三个数分别对应啥协议字段？没人知道
# self.args = (0.7, 0.9, 1024)
```

后面 `_prepare_completion_kwargs` 要拼 HTTP body：

```json
{"temperature": 0.7, "top_p": 0.9, "max_tokens": 1024}
```

JSON 的 **key 从哪来**？只能从 `**kwargs` 的 dict key 里来。tuple **没有 key**，拼不出 JSON body。

### 正解：`**kwargs` 完美匹配语义

```python
def __init__(self, flatten_messages_as_text=False, model_id=None, **kwargs):
    self.kwargs = kwargs

model = SomeModel(model_id="Qwen/...", temperature=0.7, top_p=0.9, max_tokens=1024)
# self.kwargs = {"temperature": 0.7, "top_p": 0.9, "max_tokens": 1024}
#                ↑ key 和 OpenAI 协议字段名一一对应
```

之后一行合并：

```python
completion_kwargs.update(self.kwargs)   # dict 的 key/value 直接合进最终 body
```

> 💡 **设计精髓**：Model 基类**不需要预先列举**每个 LLM provider 的所有参数。OpenAI 有 `temperature` / Anthropic 有 `top_k` / vLLM 有 `repetition_penalty` …… 全靠 `**kwargs` 兜底，**Model 基类不用每加一家 provider 就改形参列表**。这是"开放扩展、封闭修改"的开闭原则在参数层的体现。

---

## 5. 经验法则：怎么选？

| 你的场景 | 选哪个 |
|---|---|
| 收集"一组同类型、按顺序排列"的值（`max(1,2,3)` / `sum([1,2,3])` 内部）| `*args` |
| 收集"一组带名字的配置项"（LLM 参数 / HTTP headers / 装饰器透传选项）| `**kwargs` |
| 完全不知道用户会传什么（写通用装饰器/wrapper）| **两个都要**：`def wrapper(*args, **kwargs)` |

---

## 6. 装饰器为什么常写 `def wrapper(*args, **kwargs)`？

最通用的"什么都收、原样转发"姿势：

```python
def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("调用前")
        result = func(*args, **kwargs)   # 原样转发
        print("调用后")
        return result
    return wrapper

@my_decorator
def hello(name, greeting="Hi"):
    print(f"{greeting}, {name}")

hello("Alice", greeting="Hello")
# wrapper 收到 args=("Alice",), kwargs={"greeting": "Hello"}
# 转发：hello(*("Alice",), **{"greeting": "Hello"}) = hello("Alice", greeting="Hello")
```

wrapper **不知道** `func` 的签名 —— 所以位置/关键字两个口子都开着，原样接管原样转发。这是装饰器能装饰**任何**函数的根本原因。

详见 [python-decorators-explained.md](python-decorators-explained.md)。

---

## 7. 在 smolagents 源码里的几处典型用法

| 位置 | 写法 | 用途 |
|---|---|---|
| [models.py:484 `Model.__init__`](../../../src/smolagents/models.py#L484) | `**kwargs` 存到 `self.kwargs` | 保存"非核心、不可预知" LLM 配置参数；最高优先级覆盖 HTTP body |
| [models.py:502 `_prepare_completion_kwargs`](../../../src/smolagents/models.py#L502) | `**kwargs` | 单次调用临时参数（中间优先级） |
| [models.py:553 `Model.generate`](../../../src/smolagents/models.py#L553) | `**kwargs` | 透传到子类实现 |
| [models.py:580 `Model.__call__`](../../../src/smolagents/models.py#L580) | `*args, **kwargs` | 装饰器式转发到 `generate` |
| [tools.py 各 `__call__`](../../../src/smolagents/tools.py) | `*args, **kwargs` | wrapper 包装层 |

> 💡 **`Model` 三层优先级合并**就靠 `**kwargs` 实现：
> 1. specific 参数（stop_sequences / response_format / tools …）— 显式形参
> 2. 调用时 kwargs（`generate(..., temperature=0.5)`）— 单次临时
> 3. `self.kwargs`（实例化时存的默认）— 最高优先级覆盖
>
> 三层都用 dict.update 合并，最后用 `REMOVE_PARAMETER` 哨兵删字段。详见 [model-class-role-overview.md §3](model-class-role-overview.md)。

---

## 8. 总结表

| 问题 | 答案 |
|---|---|
| `kwargs` 是什么类型？ | `dict` |
| `args` 是什么类型？ | `tuple` |
| 一颗星 vs 两颗星？ | `*` 收位置参数 → tuple；`**` 收关键字参数 → dict |
| `**` 在定义和调用两端含义？ | 对称：定义时打包，调用时拆包 |
| Model 为什么用 `**kwargs`？ | LLM 配置项天然有名字（`temperature=`），需要 key 才能拼 HTTP body；tuple 没 key |
| `def wrapper(*args, **kwargs)` 含义？ | "什么都接，原样转发"，装饰器的标准姿势 |
| `args`/`kwargs` 是关键字吗？ | 不是，关键字是 `*`/`**`；名字是社区约定 |

---

## 相关链接

- 同系列 Python 预习：
  - [python-decorators-explained.md](python-decorators-explained.md) — 装饰器本质，频繁配合 `*args, **kwargs` 使用
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) — `@dataclass` 自动生成 `__init__`
  - [python-class-vs-instance-attributes.md](python-class-vs-instance-attributes.md) — 为什么 `self.kwargs = kwargs` 是实例属性
- 源码上下文：
  - [model-class-role-overview.md](model-class-role-overview.md) — Model 基类角色 + `self.kwargs` 三层优先级机制
  - [models.py:484](../../../src/smolagents/models.py#L484) — `Model.__init__` 的 `**kwargs`
  - [models.py:502](../../../src/smolagents/models.py#L502) — `_prepare_completion_kwargs` 的合并逻辑
