---
created: 2026-05-06
status: active
tags: [python, sentinel, design-pattern, prerequisite, source-reading]
---

# Python 哨兵模式（Sentinel Pattern）：当 None 不够用时

## 背景 / 动机

读 [models.py:441-449](../../../src/smolagents/models.py#L441) 看到 `REMOVE_PARAMETER`：

```python
class _ParameterRemove:
    """Sentinel value to indicate a parameter should be removed."""
    def __repr__(self):
        return "REMOVE_PARAMETER"

REMOVE_PARAMETER = _ParameterRemove()
```

第一反应可能是："为什么不用 None 表达'删除'？多此一举？"答案是：**当 None 本身就是合法值时，需要再造一个新哨兵**。本笔记拆这个 Python 通用模式。

---

## 1. 哨兵（Sentinel）是什么？

**哨兵值 = 一个特殊值，专门表示"这是一种特殊状态，不是真实数据"**。

最常见的哨兵就是 `None`：

```python
def find(items, target):
    for item in items:
        if item == target:
            return item
    return None   # ← None 是"没找到"的哨兵
```

但 `None` 这一个哨兵不够用 —— 当 **`None` 本身就是合法数据**时，就需要造新哨兵。

---

## 2. ⭐ 为什么 None 不够用？—— 经典三场景

### 场景 ①：函数参数想区分"用户没传"和"用户传了 None"

```python
# ❌ 错误版本
def fetch(url, timeout=None):
    if timeout is None:
        timeout = 30   # 默认值
    ...
```

**问题**：用户**故意传 `None`** 表达"我不要超时"和**用户没传** 都走这个分支，**两种意图无法区分**。

**正确版本**：

```python
_UNSET = object()  # ← 创建一个独一无二的哨兵对象

def fetch(url, timeout=_UNSET):
    if timeout is _UNSET:
        timeout = 30          # 用户没传 → 用默认 30
    elif timeout is None:
        timeout = float("inf") # 用户故意传 None → 不超时
    else:
        timeout = timeout     # 用户传了具体值 → 用它
```

---

### 场景 ②：dict / JSON 里区分"键存在但值是 None"和"键不存在"

```python
# ❌ 错误版本
def update(config, name=None):
    config["name"] = name   # 不管 name 是 None 还是没传，最终都覆盖

# 调用方写：
update(config)              # 用户根本不想动 name
# 但 config["name"] 被设成了 None ← bug！
```

**正确版本**：

```python
_UNSET = object()

def update(config, name=_UNSET):
    if name is not _UNSET:
        config["name"] = name   # 只有用户显式传值才覆盖
```

---

### 场景 ③：让"删除操作"成为一种值（smolagents 用的就是这个）

回顾 `_prepare_completion_kwargs` 步骤 ④（self.kwargs 最高优先级覆盖）：

```python
for kwarg_name, kwarg_value in self.kwargs.items():
    completion_kwargs[kwarg_name] = kwarg_value   # ← 朴素覆盖
```

**问题**：用户想表达"让 body 里**根本没有** stop 这个字段"，怎么办？

#### 尝试 1：传 `None`

```python
model = InferenceClientModel(model_id="o3-mini", stop=None)
# self.kwargs = {"stop": None}
# completion_kwargs["stop"] = None
# 最终 HTTP body: {"stop": null, ...}  ← ⚠️ "stop": null 不等于"没有 stop 字段"！
```

**JSON 协议层面**：
- `"stop": null` = "字段存在，值为空"
- 用户真正想说 = **"字段根本不该存在"**

这两件事在 JSON 协议里**完全不同**。

#### 解决：自造一个"删除"哨兵

```python
class _ParameterRemove:
    def __repr__(self):
        return "REMOVE_PARAMETER"

REMOVE_PARAMETER = _ParameterRemove()
```

```python
for kwarg_name, kwarg_value in self.kwargs.items():
    if kwarg_value is REMOVE_PARAMETER:        # ← 用 is 严格比较单例
        completion_kwargs.pop(kwarg_name, None)  # ← 主动删字段
    else:
        completion_kwargs[kwarg_name] = kwarg_value
```

用户用法：

```python
from smolagents.models import REMOVE_PARAMETER

model = InferenceClientModel(
    model_id="openai/o3-mini",
    stop=REMOVE_PARAMETER,   # ← "永远别在 body 里放 stop 字段"
)
```

> 💡 **设计的精髓**：把"删除操作"伪装成"赋一个特殊值"，复用了"配置覆盖"流程，**零额外 API 表面**。Pythonic 又优雅。

---

## 3. ⭐ 为什么用 `is` 而不是 `==`？

```python
if kwarg_value is REMOVE_PARAMETER:   # ✅ 正确
if kwarg_value == REMOVE_PARAMETER:   # ❌ 不安全
```

**`is` 检查"是不是同一个对象"，`==` 检查"值相等"**。

哨兵必须用 `is` 检查的两个原因：

### 原因 ① 防止伪造

```python
class FakeRemove:
    def __eq__(self, other):
        return True   # 我跟谁比都说自己相等

# 用户传：
model = SomeModel(stop=FakeRemove())
# self.kwargs = {"stop": FakeRemove()}

# 如果用 == 检查：
if kwarg_value == REMOVE_PARAMETER:   # FakeRemove.__eq__ 返回 True
    completion_kwargs.pop("stop")     # ← 误删！

# 用 is 检查：
if kwarg_value is REMOVE_PARAMETER:   # 不是同一个对象 → False
    # 不会误删
```

### 原因 ② 性能 + 准确

`is` 是**指针比较**（O(1)），`==` 可能调用复杂的 `__eq__` 方法。

而且哨兵的核心语义就是**"独一无二的标记对象"** —— 检查"是不是它"比"是不是相等"更贴合本意。

---

## 4. ⭐ Python 标准库里的哨兵实例

哨兵不是 smolagents 独创的怪招，**Python 标准库满地都是**：

| 哨兵 | 来源 | 用途 |
|---|---|---|
| [`dataclasses.MISSING`](https://docs.python.org/3/library/dataclasses.html#dataclasses.MISSING) | `dataclasses` 模块 | 标记"字段没默认值"（不用 None 因为 None 可能是合法默认值）|
| [`inspect.Parameter.empty`](https://docs.python.org/3/library/inspect.html#inspect.Parameter.empty) | `inspect` 模块 | 标记"参数没默认值" |
| `Ellipsis` (`...`) | 内置 | 在 NumPy / typing 里有特殊含义；在 stub 文件里表示"实现省略" |
| `NotImplemented` | 内置 | `__eq__` 等返回它表示"我不知道怎么和它比，让对方试试" |
| `_MISSING_TYPE` (private) | functools / 多处 | 内部使用，区分"没传"和"传了 None" |

**自造哨兵的标准手法**（一行）：

```python
_UNSET = object()
```

`object()` 创建一个最朴素的对象，**没人能造出和它"is 相等"的副本**（因为指针唯一）。

---

## 5. 哨兵 vs 默认值的对比表

| 写法 | 用户传 None | 用户没传 | 用户故意覆盖 |
|---|---|---|---|
| `def f(x=None)` | x = None | x = None | x = 用户值 |
| ↑ 区分？ | ❌ 不能区分"传 None"和"没传" |
| `_UNSET=object(); def f(x=_UNSET)` | x = None | x = `<sentinel>` | x = 用户值 |
| ↑ 区分？ | ✅ 可以区分 |

---

## 6. ⚠️ 哨兵的反模式：别滥用

### 反模式 ① 哨兵漏出 API

```python
# ❌ 错误：让用户能拿到内部哨兵
def get(key):
    return _registry.get(key, _MY_SENTINEL)

result = get("foo")
if result is _MY_SENTINEL:   # 但用户怎么 import _MY_SENTINEL？
    ...
```

**修法**：哨兵留内部，对外用别的方式表达（抛异常 / 返回 None / 返回 `(value, found)` tuple）。

### 反模式 ② 哨兵当真实数据塞进 dict

```python
data = {"key": _UNSET}    # ← 不要把哨兵塞进会被序列化的容器
json.dumps(data)          # 序列化时无法处理 _UNSET 对象
```

**哨兵的存在意义就是"短暂的标记"**，不要让它被持久化或长期保存。

---

## 7. 总结表

| 问题 | 答案 |
|---|---|
| 哨兵是什么？ | 表示特殊状态的特殊值（不是真实数据）|
| 为什么 None 不够用？ | 当 None 本身是合法数据时，需要新哨兵区分"用户传了 None" 和 "特殊状态" |
| 经典三场景？ | ① 区分"没传 vs 传 None" ② 区分"键存在 vs 键不存在" ③ 让"删除"成为一种值（smolagents 用法）|
| 为什么用 `is` 不用 `==`？ | 防止伪造（恶意 `__eq__`）+ 指针比较 O(1) + 语义匹配 |
| 标准库实例？ | `dataclasses.MISSING` / `inspect.Parameter.empty` / `Ellipsis` / `NotImplemented` |
| 自造哨兵最简手法？ | `_UNSET = object()` 一行搞定 |
| 反模式？ | 哨兵漏出 API / 把哨兵塞进会被序列化的容器 |

---

## 相关链接

- 源码：
  - [models.py:441-449](../../../src/smolagents/models.py#L441) — `REMOVE_PARAMETER` 定义
  - [models.py:546-550](../../../src/smolagents/models.py#L546) — `is REMOVE_PARAMETER` 检查 + `pop` 删字段
- 设计上下文：
  - [model-generate-mental-model.md](model-generate-mental-model.md) — 三层优先级合并 + REMOVE_PARAMETER 在步骤 ④
- Python 系列：
  - [python-class-and-dataclass.md](python-class-and-dataclass.md) — `dataclasses.MISSING` 也是哨兵
  - [python-class-vs-instance-attributes.md](python-class-vs-instance-attributes.md) — 单例对象的存储

## 遗留问题

- [ ] PEP 661（Sentinel Values）—— 官方曾讨论给 Python 加内置哨兵语法，目前未通过，仍靠 `object()` 手工造
- [ ] 哨兵 vs Enum：什么时候用 enum 表达"几种特殊状态"更好？—— 一般状态多于 1 个时用 enum
