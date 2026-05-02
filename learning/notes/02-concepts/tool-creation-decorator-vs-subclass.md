---
created: 2026-05-02
status: done
tags: [concept, tool, week-1, week-2-preview]
---

# 创建工具：`@tool` 装饰器 vs `Tool` 子类 —— 区别和如何选

> 本笔记回答**一个**问题：smolagents 提供两种创建工具的写法，差在哪？什么时候用哪个？
>
> 前置：[codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md)
> 来源：[guided_tour.md § 创建一个新工具](../../../docs/source/zh/guided_tour.md)、[tools.py 源码](../../../src/smolagents/tools.py)

---

## 1. 一句话区别

> **`@tool` 装饰器在底层就是动态构造一个 `Tool` 子类**。两者本质相同，但 `Tool` 子类是父集 —— 能做 `@tool` 做的所有事，还多了 `__init__` 参数和实例状态。

## 2. 源码证据：`@tool` = "动态构造的 Tool 子类"

[tools.py:1061-1101](../../../src/smolagents/tools.py)：

```python
def tool(tool_function: Callable) -> Tool:
    """Convert a function into an instance of a dynamically created Tool subclass."""
    tool_json_schema = get_json_schema(tool_function)["function"]   # ← 从 type hints + docstring 抽 schema

    class SimpleTool(Tool):                # ← 动态构造一个匿名 Tool 子类
        def __init__(self):
            self.is_initialized = True     # ← 写死的，不接受任何参数

    SimpleTool.name = tool_json_schema["name"]
    SimpleTool.description = tool_json_schema["description"]
    SimpleTool.inputs = tool_json_schema["parameters"]["properties"]
    SimpleTool.output_type = tool_json_schema["return"]["type"]
    SimpleTool.forward = staticmethod(wrapped_function)  # ← 把你写的函数挂成 forward

    return SimpleTool()                    # 返回这个匿名子类的实例
```

> 💡 **关键观察**：`SimpleTool.__init__(self)` 写死了，**不接受任何参数**。这就是 `@tool` 的所有限制的根源。

## 3. 唯一的功能差异

| 能力 | `@tool` | `Tool` 子类 |
|---|---|---|
| 写起来便利 | ✅ 一个装饰器 | ❌ 要写 5 个类属性 + forward |
| Schema 来源 | 自动从 type hints + docstring 抽 | 手动写 `inputs` 字典 |
| `__init__` 接受参数（API key、endpoint、配置） | ❌ | ✅ |
| 维护实例状态（`self.cache` / `self.client` / `self.counter`） | ❌ | ✅ |
| 预加载重型资源（模型、数据库连接） | ❌ | ✅ |
| 同一个工具多个实例不同配置 | ❌ | ✅ |
| 工具间继承复用 | ❌ | ✅ |

> 💡 **本质**：`@tool` 用便利性换灵活性。**LLM 看到的工具描述完全一样**（同一份 JSON schema），所以**对模型行为零影响**，只影响开发体验。

## 4. 决策表（直接抄）

```
有 __init__ 参数？     → Tool 子类
要预加载重型资源？      → Tool 子类
要维护实例状态？        → Tool 子类
要在多个工具间继承？    → Tool 子类
否则                  → @tool 装饰器（更简洁）
```

## 5. 三个具体例子

### 例 1：纯函数工具 → `@tool`（小工具的最佳选择）

```python
@tool
def get_temperature(city: str) -> float:
    """Get current temperature in Celsius for a city.
    Args:
        city: City name in English.
    """
    fake_data = {"Beijing": 25.0, "Tokyo": 30.0, "Singapore": 28.0}
    return fake_data.get(city, 20.0)
```

无状态、无配置、纯计算 —— 用 `@tool` 最合适。**强行写成 Tool 子类是过度工程**。

### 例 2：需要 API key 的工具 → 必须 `Tool` 子类

```python
class WeatherAPITool(Tool):
    name = "get_weather"
    description = "Get real weather from API"
    inputs = {"city": {"type": "string", "description": "City name"}}
    output_type = "string"

    def __init__(self, api_key: str, base_url: str = "https://api.weather.com"):
        super().__init__()
        self.api_key = api_key           # ← @tool 做不到
        self.base_url = base_url
        self.client = httpx.Client()     # ← 复用 HTTP 连接

    def forward(self, city: str) -> str:
        resp = self.client.get(f"{self.base_url}/...", headers={"X-API-Key": self.api_key})
        return resp.text

# 用法
agent = ToolCallingAgent(
    tools=[WeatherAPITool(api_key=os.getenv("WEATHER_KEY"))],
    model=model,
)
```

如果硬用 `@tool` 写，只能把 `api_key` 写成全局变量 / 模块级变量，难看且不可测。

### 例 3：预加载重型资源的工具 → 必须 `Tool` 子类

```python
class ImageClassifyTool(Tool):
    name = "classify_image"
    description = "Classify image content"
    inputs = {"path": {"type": "string", "description": "Image path"}}
    output_type = "string"

    def __init__(self):
        super().__init__()
        from transformers import pipeline
        self.classifier = pipeline("image-classification")  # ← 创建实例时加载一次

    def forward(self, path: str) -> str:
        return self.classifier(path)[0]["label"]            # ← 后续每次调用直接复用
```

## 6. 什么是"预加载重型资源"

指**在 Tool 实例化（`__init__`）时一次性加载昂贵资源，后续每次 `forward()` 直接复用**。

### "重型"指什么

通常是**加载一次要几秒到几分钟**的东西：

| 资源 | 加载耗时 | 内存占用 |
|---|---|---|
| Transformers 模型（pipeline / AutoModel） | 5~30 秒 | 数百 MB ~ GB |
| Embedding 模型 + 向量索引（ChromaDB / FAISS） | 10~60 秒 | GB 级 |
| 数据库连接池（Postgres / Redis） | 1~3 秒 | 小但建立慢 |
| 大词典 / 知识图谱（GB 级 JSON） | 10~30 秒 | GB 级 |
| 本地 LLM（vLLM / Ollama 加载到显存） | 30 秒~几分钟 | 显存占大 |

### 为什么 `@tool` 做不到

[tools.py:1080-1082](../../../src/smolagents/tools.py)：

```python
class SimpleTool(Tool):
    def __init__(self):
        self.is_initialized = True   # ← 写死的，没法塞自定义代码
```

被装饰的函数被绑成 `staticmethod`（每次调用都从函数顶部开始执行），所以**唯一的"加载位置"只能是函数体里**：

```python
@tool
def classify_image(path: str) -> str:
    """..."""
    from transformers import pipeline
    classifier = pipeline("image-classification")  # ❌ 每次调用都加载
    return classifier(path)[0]["label"]
```

工具被调 10 次，加载就发生 10 次。Tool 子类把 `pipeline(...)` 放在 `__init__` 里，**整个 agent 生命周期只加载 1 次**，10 次调用总耗时省 9× 加载时间。

> 💡 **"重型" = 加载贵 + 可复用**。Tool 子类的 `__init__` 是这种资源的"安家之处"，让它只加载一次。`@tool` 没有这个落脚点。

### 为什么 `__init__` 只跑一次？—— 实例化 vs 调用的区分

> 这是初学时最容易混淆的点：**"我每次调工具不也得调 `__init__` 吗？"** 答案是**不会**。`__init__` 只在 `MyTool()` 那一行（实例化时）跑，之后被 agent 持有的整个生命周期里**不会再跑**。

#### 工具的生命周期

```
脚本启动
   ↓
GetTemperatureTool()           ← __init__ 调用 1 次（30 秒加载模型）
   ↓
agent = ToolCallingAgent(tools=[那个实例])
   ↓
agent.run("查...")
   ├─ LLM 第 1 次决定调工具
   │     framework: tool = self.tools["get_temperature"]   ← 从字典拿现有实例
   │     framework: tool(**arguments)                       ← 调 __call__ → forward
   │     forward 内部: self.classifier(...)                 ← 用 __init__ 时加载的模型
   │
   ├─ LLM 第 2 次决定调工具
   │     framework: tool = self.tools["get_temperature"]   ← 同一个实例
   │     forward 内部: self.classifier(...)                 ← 还是那个加载好的模型
   │
   └─ ... LLM 调 N 次同理 ...
```

**`__init__` 只在你写 `()` 那一行执行一次。后面 N 次 LLM 调用，调的都是同一个实例的 `forward()`，不会重新触发 `__init__`。**

#### 源码证据

**实例化只在你写 `()` 时发生**（[compare_agents.py:68](../../scripts/compare_agents.py)）：
```python
tools=[GetTemperatureTool()]   # ← 整个脚本里 __init__ 只在这里跑 1 次
```

**Agent 把实例存进字典**（[agents.py:393](../../../src/smolagents/agents.py)）：
```python
self.tools = {tool.name: tool for tool in tools}
#                       ^^^^ 存的是实例本身（不是类）
```

**调工具时从字典查现成实例**（[agents.py:1471, 1486](../../../src/smolagents/agents.py)）：
```python
tool = available_tools[tool_name]      # ← 拿已存在的实例
return tool(**arguments, ...)          # ← 调 __call__ → forward()，没有重新 GetTemperatureTool()
```

#### Python OOP 视角

```python
class MyTool:
    def __init__(self):         # 实例化时跑（一次性的"出厂设置"）
        self.x = "loaded"

    def forward(self, ...):      # 每次调用跑（一次性使用的"动作"）
        return self.x

t = MyTool()    # ← __init__ 跑一次，self.x 从此存活在 t 上
t.forward(...)  # ← 用 self.x（不重新加载）
t.forward(...)  # ← 还是用 self.x
```

> 💡 **`__init__` 是"出厂"，`forward` 是"使用"**。出厂只跑一次，使用可以跑 N 次。Tool 子类靠 `self.xxx` 把"出厂"时加载的资源**挂在实例上**，后续每次"使用"都直接复用。

#### `@tool` 为什么挂不住 —— `staticmethod` 的限制

[tools.py:1101](../../../src/smolagents/tools.py)：
```python
SimpleTool.forward = staticmethod(wrapped_function)
```

`@tool` 把你的函数包装成 **`staticmethod`** —— 静态方法**没有 `self`**。函数体每次进来都是从顶部执行，没办法访问"前一次调用结束时的状态"。即使你硬把 `pipeline(...)` 写在函数体里，每次调用都是冷启动：

```python
@tool
def classify(path: str) -> str:
    """..."""
    classifier = pipeline("...")    # ❌ 每次进入函数都是从这一行开始 —— 重新加载
    return classifier(path)
```

vs

```python
class ClassifyTool(Tool):
    def __init__(self):
        self.classifier = pipeline("...")   # ✅ 只跑一次，挂在 self 上
    def forward(self, path: str) -> str:
        return self.classifier(path)         # ✅ 复用 self.classifier
```

#### 类比帮你记住

> 💡 **想象你买一辆车**：
> - **`__init__`** = 出厂组装（装发动机、装空调） —— 只发生一次
> - **`forward`** = 每次开车（点火、踩油门） —— 发生 N 次
>
> 你不会每次开车都拆装一次发动机。`Tool` 子类的 `self.classifier` 就是那辆车里"装好的发动机"，开车时直接用。
>
> `@tool` 的写法相当于"每次开车都得现造一辆车" —— 因为它没有"车"这个持久存在的容器，只有一次性的开车动作。

## 7. 一个有用的类比

> 💡 **`@tool` 之于 `Tool` 子类，类似 Python 的 `@dataclass` 之于手写类**：
> - 简单数据类（只有几个字段、没有自定义逻辑）→ `@dataclass` 一行搞定
> - 需要自定义 `__init__` / 复杂方法 / 继承 / 状态 → 老老实实写类
>
> 同理：
> - 简单纯函数工具 → `@tool` 一行搞定
> - 需要参数 / 状态 / 重型资源 → 老老实实写 `Tool` 子类

## 8. 实战建议

1. **学习阶段**：用 `@tool`。你的 [compare_agents.py](../../scripts/compare_agents.py) 的 `get_temperature` 就是合适场景。
2. **真做项目**：90% 的工具用 `@tool` 够了；10% 需要 API key / 模型加载的用 `Tool` 子类。
3. **判断标准**：写工具前先问自己**"这玩意儿要不要带状态 / 加载东西"**，答案是"要"就上子类。

## 关键认知清单

学完这一节，你应该能回答：

- [x] `@tool` 装饰器内部就是动态构造 Tool 子类（[tools.py:1080](../../../src/smolagents/tools.py)）
- [x] 两者**对 LLM 完全等价**（同一份 JSON schema），差异只在开发体验
- [x] `@tool` 的限制根源：`SimpleTool.__init__(self)` 不接受参数
- [x] "预加载重型资源"是什么：实例化时一次性加载昂贵资源，后续复用
- [x] **`__init__` 只跑一次**（在 `MyTool()` 实例化时），forward 跑 N 次（每次 LLM 调用）
- [x] **agent 把工具实例存进 `self.tools` 字典复用**（[agents.py:393](../../../src/smolagents/agents.py)），不会重新 new
- [x] **`@tool` 把函数包成 `staticmethod`**（[tools.py:1101](../../../src/smolagents/tools.py)），没 `self`，所以挂不住状态
- [x] 决策树：要状态/参数/重型资源 → 子类；否则 → `@tool`

## 相关链接

- [codeagent-vs-toolcallingagent.md](codeagent-vs-toolcallingagent.md) — 两种 agent 的对比
- 源码：
  - [tools.py:106 `class Tool`](../../../src/smolagents/tools.py) — Tool 基类
  - [tools.py:1061 `def tool`](../../../src/smolagents/tools.py) — `@tool` 装饰器实现
- 文档：
  - [guided_tour.md § 创建一个新工具](../../../docs/source/zh/guided_tour.md)
  - [tutorials/tools.md](../../../docs/source/zh/tutorials/tools.md) — 工具的进阶教程
- demo：
  - [compare_agents.py](../../scripts/compare_agents.py) — 已包含两种写法对比（`@tool def get_temperature` vs `class GetTemperatureTool`）

## 遗留问题

- [ ] Tool 子类的 `setup()` 方法是干嘛的？（搜 [tools.py](../../../src/smolagents/tools.py) `def setup`）
- [ ] `is_initialized` 字段在框架里被谁读？（[tools.py:1082](../../../src/smolagents/tools.py)）
- [ ] 如何把工具上传到 HuggingFace Hub 复用？（[tutorials/tools.md](../../../docs/source/zh/tutorials/tools.md)）
