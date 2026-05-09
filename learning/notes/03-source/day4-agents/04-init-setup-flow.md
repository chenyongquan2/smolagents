---
created: 2026-05-08
status: active
tags: [smolagents, agents, init, mental-model, day4]
---

# 项目经理张三入职那天：构造函数全解

> 💡 **本篇定位**：你写 `agent = CodeAgent(tools=[], model=...)` 那一行**到底发生了什么**？9 篇笔记都在讲 `run()` 之后，但没讲实例化时的"入职准备"。本篇补上。

> ⚠️ **必读前置**：[① multi-step-agent-role-overview](01-multi-step-agent-role-overview.md)（5 类客户 + 5 组成员变量）

## 背景 / 动机

新手疑问的 4 个常见点：

1. 我写 `tools=[]` 传空列表，为什么 `agent.tools` 里有 `final_answer`？
2. `prompt_templates=None` 时怎么拼 system_prompt？
3. 配 `step_callbacks` 时，**list 和 dict 行为不同**是怎么回事？
4. 实例化 `CodeAgent(...)` 和 `ToolCallingAgent(...)` 的差异在哪一步？

读完本笔记你会知道：实例化期发生**13 件事**，跟着源码 60 行能讲清。

---

## 1. 一句话本质

> **构造函数（`__init__`）是项目经理"入职那天"的全套准备**：领工具箱、配顾问电话、写工作模板、登记下属、装监控摄像头、初始化笔记本。**入职完成才能接单**（调 `run()`）。

延续 [项目经理比喻](01-multi-step-agent-role-overview.md)：

```
老板招了个项目经理（CodeAgent）→ 入职那天发生：
  1. 领工号牌 (agent_name)
  2. 配顾问电话 (model)
  3. 写工作模板 (prompt_templates)
  4. 配置工作上限 (max_steps / planning_interval / final_answer_checks)
  5. 登记下属 (managed_agents)
  6. 领工具箱 (tools)
  7. 检查工具/下属名字不冲突
  8. 准备空白笔记本 (memory)
  9. 装日志器 (logger)
  10. 装监控摄像头 (monitor)
  11. 注册旁观者 (step_callbacks)
  12. 摆上"接单状态"标志位 (stream_outputs=False)
  13. 入职完成，等老板下单
```

---

## 2. 构造函数的 17 个入参（按职责分类）

[agents.py:294](../../../../src/smolagents/agents.py#L294) 长这样：

```python
def __init__(
    self,
    tools: list[Tool],
    model: Model,
    prompt_templates: PromptTemplates | None = None,
    instructions: str | None = None,
    max_steps: int = 20,
    add_base_tools: bool = False,
    verbosity_level: LogLevel = LogLevel.INFO,
    managed_agents: list | None = None,
    step_callbacks: ... | None = None,
    planning_interval: int | None = None,
    name: str | None = None,
    description: str | None = None,
    provide_run_summary: bool = False,
    final_answer_checks: list[Callable] | None = None,
    return_full_result: bool = False,
    logger: AgentLogger | None = None,
):
```

按"用途"分 4 组：

### 组 1 · 必填（基础配置）

| 入参 | 用途 |
|---|---|
| `tools` | 工具箱（可以传 `[]`，但 `final_answer` 会自动加进去）|
| `model` | LLM 调用渠道（[Day 3](../day3-models/model-class-role-overview.md)）|

### 组 2 · 行为控制（可选，新手常用）

| 入参 | 默认值 | 含义 |
|---|---|---|
| `max_steps` | 20 | 最多反复几轮 |
| `planning_interval` | None | 每隔几步重规划（None = 不规划）|
| `verbosity_level` | INFO | 日志详细度 |
| `add_base_tools` | False | 自动加内置工具集（web_search / wikipedia 等）|
| `instructions` | None | 用户自定义补充指令（拼进 system_prompt）|
| `final_answer_checks` | None | final_answer 的校验函数列表 |
| `return_full_result` | False | 默认返回值 vs 返回 `RunResult` |

### 组 3 · multi-agent 专用

| 入参 | 含义 |
|---|---|
| `managed_agents` | 子 agent 列表 |
| `name` / `description` | **被父 agent 调用时**的标识 |
| `provide_run_summary` | 被调用时是否提供 run summary |

### 组 4 · 高级 / 替换

| 入参 | 含义 |
|---|---|
| `prompt_templates` | 自定义 YAML 模板（默认走 prompts/*.yaml）|
| `step_callbacks` | 用户注册的回调（每步触发）|
| `logger` | 自定义日志器（默认 `AgentLogger`）|

---

## 3. ⭐ 构造函数内做的 13 件事（按顺序）

[agents.py:313-352](../../../../src/smolagents/agents.py#L313)：

### ① agent_name（[:313](../../../../src/smolagents/agents.py#L313)）

```python
self.agent_name = self.__class__.__name__   # "CodeAgent" 或 "ToolCallingAgent"
```

**张三视角**：把工号牌挂上 —— "我是 CodeAgent 经理"。

### ② model（[:314](../../../../src/smolagents/agents.py#L314)）

```python
self.model = model
```

**张三视角**：把顾问电话存到通讯录。

### ③ prompt_templates + 校验（[:315-326](../../../../src/smolagents/agents.py#L315)）⭐

```python
self.prompt_templates = prompt_templates or EMPTY_PROMPT_TEMPLATES
if prompt_templates is not None:
    # 校验用户传的 templates 包含 EMPTY_PROMPT_TEMPLATES 全部 key
    missing_keys = set(EMPTY_PROMPT_TEMPLATES.keys()) - set(prompt_templates.keys())
    assert not missing_keys, f"...缺失: {missing_keys}"
    # 还要检查嵌套 key（planning 下的 initial_plan 等）
    for key, value in EMPTY_PROMPT_TEMPLATES.items():
        if isinstance(value, dict):
            for subkey in value.keys():
                assert key in prompt_templates and subkey in prompt_templates[key]
```

**张三视角**：检查工作模板手册 —— "如果你给了自定义模板，得把所有 key 都填齐，否则报错"。

> 💡 **`EMPTY_PROMPT_TEMPLATES` 不是真空模板**（[agents.py:183](../../../../src/smolagents/agents.py#L183)）—— 它是 4 个嵌套字段的"骨架"（system_prompt / planning / managed_agent / final_answer）。**真正的默认模板**在子类的 [prompts/*.yaml](../../../../src/smolagents/prompts/) 里，由 `from_dict` / 子类 `__init__` 加载。
>
> 这就是为什么 `CodeAgent.__init__` 会先调 `prompt_templates = yaml.safe_load(...)` 再 `super().__init__(prompt_templates=prompt_templates, ...)`。

### ④ 配置项保存（[:328-337](../../../../src/smolagents/agents.py#L328)）

```python
self.max_steps = max_steps
self.step_number = 0                         # 进度计数器初始 0
self.planning_interval = planning_interval
self.state: dict[str, Any] = {}              # 跨步共享变量草稿纸
self.name = self._validate_name(name)        # ← 调辅助方法 1（详见 §4）
self.description = description
self.provide_run_summary = provide_run_summary
self.final_answer_checks = final_answer_checks if final_answer_checks is not None else []
self.return_full_result = return_full_result
self.instructions = instructions
```

**张三视角**：登记基础信息（步数上限 / 规划周期 / 我的名字 / 各种开关）。

### ⑤ `_setup_managed_agents`（[:338](../../../../src/smolagents/agents.py#L338)）

调辅助方法 2（详见 §4）—— 登记下属。

### ⑥ `_setup_tools`（[:339](../../../../src/smolagents/agents.py#L339)）

调辅助方法 3（详见 §4）—— 领工具箱（**关键：会自动加 `final_answer`**）。

### ⑦ `_validate_tools_and_managed_agents`（[:340](../../../../src/smolagents/agents.py#L340)）

调辅助方法 4（详见 §4）—— 检查工具 / 下属 / 自己 名字不冲突。

### ⑧ task / memory（[:342-343](../../../../src/smolagents/agents.py#L342)）⭐

```python
self.task: str | None = None
self.memory = AgentMemory(self.system_prompt)
```

**张三视角**：拿一个空白笔记本，扉页是 system_prompt。

> ⭐ **隐藏的关键操作**：`self.system_prompt` 是 property（[:355](../../../../src/smolagents/agents.py#L355)）—— 它会调 `self.initialize_system_prompt()`（**子类实现的 `@abstractmethod` 硬约束**）。
>
> **这是 `__init__` 里第一次 zoom 进子类逻辑** —— 拼 system_prompt 的具体规则在 CodeAgent / ToolCallingAgent 各自实现。
>
> ⚠️ **直接实例化 `MultiStepAgent(...)` 在这一步前就炸**：因为 `initialize_system_prompt` 是 `@abstractmethod`（[:749](../../../../src/smolagents/agents.py#L749)），Python 的 ABC 元类在**实例化阶段就抛 TypeError**：
> ```
> TypeError: Can't instantiate abstract class MultiStepAgent
>            without an implementation for abstract method 'initialize_system_prompt'
> ```
> 实证验证见 [abc_soft_constraint_demo.py](../../../scripts/abc_soft_constraint_demo.py)。**事实上只能实例化 CodeAgent / ToolCallingAgent**，呼应 ① §3 组 C 的"留给徒弟"硬约束边界。

### ⑨ logger（[:345-348](../../../../src/smolagents/agents.py#L345)）

```python
if logger is None:
    self.logger = AgentLogger(level=verbosity_level)
else:
    self.logger = logger
```

**张三视角**：装日志器。

### ⑩ monitor（[:350](../../../../src/smolagents/agents.py#L350)）

```python
self.monitor = Monitor(self.model, self.logger)
```

**张三视角**：装监控摄像头（累计 token / step 数 / 耗时）。

### ⑪ `_setup_step_callbacks`（[:351](../../../../src/smolagents/agents.py#L351)）

调辅助方法 5（详见 §4）—— 装回调注册表 + **自动把 monitor.update_metrics 注册到 ActionStep**。

### ⑫ stream_outputs（[:352](../../../../src/smolagents/agents.py#L352)）

```python
self.stream_outputs = False
```

**张三视角**：摆上"默认非流式"标志位。

> 💡 **这就是为什么默认 `agent.stream_outputs = False`** —— 你想要 token 级流（[②b stream-naming](02-stream-naming-explained.md)）必须显式翻成 True。

### ⑬ 入职完成

`__init__` 结束。`agent` 实例可用了，等老板调 `run(task)`。

---

## 4. ⭐ 5 个辅助 setup 方法详解

### 辅助方法 1 · `_validate_name(name)`（[:364](../../../../src/smolagents/agents.py#L364)）

```python
def _validate_name(self, name: str | None) -> str | None:
    if name is not None and not is_valid_name(name):
        raise ValueError(f"Agent name '{name}' must be a valid Python identifier and not a reserved keyword.")
    return name
```

**做什么**：如果传了 `name`，校验它是合法 Python 标识符（不能是 `def` / `class` / 中文 / 带空格）。

**为什么要校验**：multi-agent 场景下，父 agent 可能把子 agent 的 name 拼进 prompt 当 Python 标识符用 —— 不合法会让子 agent 没法被调用。

### 辅助方法 2 · `_setup_managed_agents(managed_agents)`（[:369](../../../../src/smolagents/agents.py#L369)）⭐

```python
def _setup_managed_agents(self, managed_agents=None):
    self.managed_agents = {}
    if managed_agents:
        # ⭐ 强制要求每个子 agent 都有 name + description
        assert all(agent.name and agent.description for agent in managed_agents)
        self.managed_agents = {agent.name: agent for agent in managed_agents}
        # ⭐ 给子 agent 自动设 inputs/output_type，让父能像调 Tool 一样调它们
        for agent in self.managed_agents.values():
            agent.inputs = {
                "task": {"type": "string", "description": "Long detailed description of the task."},
                "additional_args": {"type": "object", "description": "...", "nullable": True},
            }
            agent.output_type = "string"
```

**做什么**：把 managed_agents 列表转成 dict + **自动给子 agent 装上"工具皮"**（设 `inputs` / `output_type` 字段）。

**项目经理类比**：登记下属时**自动给他们办张"我也是工具"的工作证** —— 这样父 agent 调子 agent 时，可以走和调 Tool 完全一样的流程。

> 💡 **如果传 `managed_agents=None`**（普通单 agent 场景）：`self.managed_agents = {}`，跳过整个块。**最常见用法**。

### 辅助方法 3 · `_setup_tools(tools, add_base_tools)`（[:389](../../../../src/smolagents/agents.py#L389)）⭐⭐

```python
def _setup_tools(self, tools, add_base_tools):
    assert all(isinstance(tool, BaseTool) for tool in tools)
    self.tools = {tool.name: tool for tool in tools}
    if add_base_tools:
        # 加内置工具集（web_search / wikipedia / python_interpreter 等）
        self.tools.update({
            name: cls()
            for name, cls in TOOL_MAPPING.items()
            if name != "python_interpreter" or self.__class__.__name__ == "ToolCallingAgent"
            #  ⭐ 关键：CodeAgent 不能加 python_interpreter，因为它本身就是跑代码的
        })
    self.tools.setdefault("final_answer", FinalAnswerTool())
    #  ⭐⭐ 关键：不管你传不传，final_answer 一定有
```

**做什么**：3 件事 ——
1. 校验所有元素都是 `BaseTool` 实例
2. 转成 dict（key 是 tool.name）
3. 如果 `add_base_tools=True`，加内置工具（**CodeAgent 跳过 python_interpreter**）
4. **必加 `final_answer`**（用 `setdefault` —— 用户没传才加）

**这就回答了你的疑问**：

> ❓ "我写 `tools=[]` 传空列表，为什么 `agent.tools` 里有 `final_answer`？"
>
> ✅ 答：第 4 步 `self.tools.setdefault("final_answer", FinalAnswerTool())` 兜底加的。**没有 final_answer 的话 LLM 没法宣告"我答完了"，整个 ReAct 循环退不出来**。

> 💡 **CodeAgent 跳过 python_interpreter 的设计**：因为 CodeAgent 的"动作"就是 LLM 写 Python 代码，整个 step 都在 Python 沙箱里跑 —— 它**不需要**"调 python_interpreter 工具"这种 tool_calls 抽象。ToolCallingAgent 不一样，它需要把 python 当一个工具调。

### 辅助方法 4 · `_validate_tools_and_managed_agents(...)`（[:404](../../../../src/smolagents/agents.py#L404)）

```python
def _validate_tools_and_managed_agents(self, tools, managed_agents):
    tool_and_managed_agent_names = [tool.name for tool in tools]
    if managed_agents is not None:
        tool_and_managed_agent_names += [agent.name for agent in managed_agents]
    if self.name:
        tool_and_managed_agent_names.append(self.name)
    if len(tool_and_managed_agent_names) != len(set(tool_and_managed_agent_names)):
        raise ValueError("...重名的：" + ...)
```

**做什么**：把 tools + managed_agents + 自己的 name 全部塞进一个列表，**检查 list vs set 长度** —— 不一致说明有重名。

**为什么要查自己的名字**：multi-agent 场景下，自己作为 tool 的 name 不能和工具列表里的 tool name 撞。

> 💡 这次校验**没查 final_answer**（因为它是 `_setup_tools` 末尾才 setdefault 加的，而这个方法只看用户传进来的列表）。所以你能传一个**叫 `final_answer` 的自定义工具** —— 它会被 setdefault 跳过（用户的优先），但本方法不报错。

### 辅助方法 5 · `_setup_step_callbacks(step_callbacks)`（[:416](../../../../src/smolagents/agents.py#L416)）⭐

```python
def _setup_step_callbacks(self, step_callbacks):
    self.step_callbacks = CallbackRegistry()                # 空注册表
    if step_callbacks:
        if isinstance(step_callbacks, list):
            # 列表：所有回调都注册到 ActionStep（向后兼容）
            for callback in step_callbacks:
                self.step_callbacks.register(ActionStep, callback)
        elif isinstance(step_callbacks, dict):
            # dict：按 step 类别注册（更灵活）
            for step_cls, callbacks in step_callbacks.items():
                if not isinstance(callbacks, list):
                    callbacks = [callbacks]
                for callback in callbacks:
                    self.step_callbacks.register(step_cls, callback)
        else:
            raise ValueError("step_callbacks must be a list or a dict")
    # ⭐ 不管用户传不传，都把 monitor.update_metrics 注册到 ActionStep
    self.step_callbacks.register(ActionStep, self.monitor.update_metrics)
```

**做什么**：根据用户传的格式（list 或 dict）注册回调 + **自动注册 monitor.update_metrics**。

**这就回答了你的疑问**：

> ❓ "配 `step_callbacks` 时，list 和 dict 行为不同是怎么回事？"
>
> ✅ 答：**list = 向后兼容的简化形式**（早期版本 step_callbacks 只能注册到 ActionStep）—— 列表里所有回调全部注册到 ActionStep。**dict = 新式灵活形式** —— `{ActionStep: [...], PlanningStep: [...]}` 可以按 step 类型分别注册。

```python
# 老式（list）—— 等同于 dict 形式 {ActionStep: [my_callback]}
agent = CodeAgent(..., step_callbacks=[my_callback])

# 新式（dict）
agent = CodeAgent(..., step_callbacks={
    ActionStep: my_action_callback,
    PlanningStep: my_planning_callback,
    FinalAnswerStep: my_final_callback,
})
```

> 💡 `monitor.update_metrics` 的自动注册 —— 这就是为什么默认 `agent.monitor` 一直能累计 token 和 step 数：**框架强制注册 monitor，用户没法跳过**。

---

## 5. CodeAgent vs ToolCallingAgent 在构造函数的差异

[CodeAgent 的构造函数](../../../../src/smolagents/agents.py#L1527) / [ToolCallingAgent 的构造函数](../../../../src/smolagents/agents.py#L1231) 都重写了 `__init__`，差异：

| 子类 | 额外做什么 |
|---|---|
| **CodeAgent** | 加载 `code_agent.yaml` prompt 模板 / 创建 `python_executor`（local / docker / e2b / wasm）/ 设 `additional_authorized_imports` 沙箱白名单 |
| **ToolCallingAgent** | 加载 `toolcalling_agent.yaml` prompt 模板 / 没有 python_executor |

**两者最后都调 `super().__init__(...)` 跑基类的 13 件事**。所以基类的 `__init__` 是"共享地基"。

---

## 6. 关键启示

| 启示 | 含义 |
|---|---|
| **`final_answer` 永远在工具箱里** | `_setup_tools` 用 `setdefault` 兜底加，没它退不出 ReAct 循环 |
| **CodeAgent 跳过 python_interpreter** | 它本身就是跑代码的，不需要"调 python 工具"抽象 |
| **`MultiStepAgent` 不能直接实例化** | `initialize_system_prompt` 是 `@abstractmethod` 硬约束，实例化阶段就抛 `TypeError`（[abc 实证](../../../scripts/abc_soft_constraint_demo.py)）|
| **monitor.update_metrics 强制注册** | 用户没法跳过监控 |
| **step_callbacks: list 是 dict 的简写** | list 等同于 `{ActionStep: list}`（向后兼容）|
| **prompt_templates 校验严格** | 自定义就必须把 4 个嵌套 key 全填齐 |

---

## 7. 一图总览：构造函数 13 件事

```
agent = CodeAgent(tools=[], model=..., max_steps=4)
   │
   ▼
CodeAgent.__init__
   ├── 加载 code_agent.yaml prompt 模板
   ├── 创建 python_executor (LocalPythonExecutor / DockerExecutor / ...)
   └── super().__init__(prompt_templates=..., tools=..., model=..., ...)
              │
              ▼
       MultiStepAgent.__init__ 跑 13 件事
       ┌────────────────────────────────────────────┐
       │ ① agent_name = "CodeAgent"                  │
       │ ② self.model = model                        │
       │ ③ self.prompt_templates = ...（含校验）     │
       │ ④ 配置项保存（max_steps / state / name ...） │
       │ ⑤ _setup_managed_agents()  ← 登记下属        │
       │ ⑥ _setup_tools()           ← 装工具+final_answer│
       │ ⑦ _validate_tools_and_managed_agents()      │
       │ ⑧ self.memory = AgentMemory(system_prompt)  │
       │    ⭐ system_prompt 调子类 initialize 拼     │
       │ ⑨ self.logger = AgentLogger(...)            │
       │ ⑩ self.monitor = Monitor(model, logger)     │
       │ ⑪ _setup_step_callbacks() ← 装监控钩子      │
       │ ⑫ self.stream_outputs = False               │
       │ ⑬ 入职完成，等老板下单                      │
       └────────────────────────────────────────────┘
```

---

## 相关链接

- ⚠️ 必读前置：[① multi-step-agent-role-overview.md](01-multi-step-agent-role-overview.md)（5 类客户 + 5 组成员变量）
- 同系列：[③ agent-run-mental-model.md](03-run-mental-model.md)（接单后干啥）
- 上游 Day 1：[agent-memory-container.md](../day1-memory/agent-memory-container.md)（AgentMemory）、[callback-registry.md](../day1-memory/callback-registry.md)（CallbackRegistry）
- 上游 Day 2：[tool-class-role-overview.md](../day2-tools/tool-class-role-overview.md)（BaseTool / FinalAnswerTool）
- 上游 Day 3：[model-class-role-overview.md](../day3-models/model-class-role-overview.md)（Model）
- 源码：[agents.py:294 MultiStepAgent 构造函数](../../../../src/smolagents/agents.py#L294)、[agents.py:1527 CodeAgent 构造函数](../../../../src/smolagents/agents.py#L1527)、[agents.py:1231 ToolCallingAgent 构造函数](../../../../src/smolagents/agents.py#L1231)

## 遗留问题

- [ ] CodeAgent 的 `executor_type` / `executor_kwargs` / `additional_authorized_imports` 详细行为 —— Day 6 看 local_python_executor 时再深挖
- [ ] `provide_run_summary=True` 实际用在哪里？源码没找到调用点 —— Week 4 multi-agent 时验证
