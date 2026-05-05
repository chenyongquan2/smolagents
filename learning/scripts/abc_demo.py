"""
Day 2 配套实验：abc.ABC 抽象基类手感练习

配套笔记：learning/notes/03-source/python-abc-abstract-base-class.md

跑法：
  python learning/scripts/abc_demo.py

建议调试姿势：
  1. 先整体跑一遍，观察哪些类是"实例化时崩"、哪些是"调用时崩"
  2. 重点感受 demo_2 —— 同一份 API 用两种写法，错误暴露时机的差异
  3. 重点感受 demo_4 —— smolagents 真实代码里两种写法**同时使用**的设计意图

每个 demo 是独立的，可以注释掉别的、单独跑某一个。
"""

import sys
from abc import ABC, abstractmethod

# Windows 默认控制台是 GBK，强制 UTF-8 才能正常打印中文 + emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# Demo 1: ABC 最基本行为 —— 抽象类不能被直接实例化
# ----- 对应笔记第 1 节
# ============================================================
def demo_1_cant_instantiate():
    print("\n" + "=" * 60)
    print("Demo 1: ABC 抽象类的基本行为")
    print("=" * 60)

    class Animal(ABC):
        @abstractmethod
        def speak(self):
            pass

    print("--- 试图直接实例化 Animal（抽象类）---")
    try:
        Animal()
    except TypeError as e:
        print(f"    💥 如预期崩了：{e}")

    print("\n--- 子类 Cat 没实现 speak ---")
    class Cat(Animal):
        pass

    try:
        Cat()
    except TypeError as e:
        print(f"    💥 如预期崩了：{e}")

    print("\n--- 子类 Dog 实现了 speak ---")
    class Dog(Animal):
        def speak(self):
            return "Woof"

    d = Dog()
    print(f"    ✅ Dog 实例化成功，d.speak() = {d.speak()!r}")

    print("\n💡 关键观察：错误在**实例化那一刻**暴露，不用等调用 speak()")


# ============================================================
# Demo 2: ⭐ 硬约束 vs 软约束 —— 错误暴露时机的差异
# ----- 对应笔记第 2 节
# ============================================================
def demo_2_hard_vs_soft():
    print("\n" + "=" * 60)
    print("Demo 2: @abstractmethod (硬) vs raise NotImplementedError (软)")
    print("=" * 60)

    # ---- 写法 A：raise NotImplementedError（软约束） ----
    class SoftAnimal:
        def speak(self):
            raise NotImplementedError("subclass must implement")

    print("--- 写法 A：raise NotImplementedError ---")
    a = SoftAnimal()  # ← 这一行能过
    print(f"    ⚠️  SoftAnimal() 实例化成功了 —— 软约束让你能拿到一个空壳")
    try:
        a.speak()
    except NotImplementedError as e:
        print(f"    💥 真正调用 speak() 才崩：NotImplementedError: {e}")

    # ---- 写法 B：abc.ABC + @abstractmethod（硬约束） ----
    class HardAnimal(ABC):
        @abstractmethod
        def speak(self):
            pass

    print("\n--- 写法 B：ABC + @abstractmethod ---")
    try:
        b = HardAnimal()  # ← 这一行就过不去
    except TypeError as e:
        print(f"    💥 实例化那一刻就崩：TypeError")
        print(f"       不需要等到调用 speak() —— 错误更早暴露")

    print("\n💡 关键认知：")
    print("   软约束：实例能造、**调用时**才崩")
    print("   硬约束：连**实例都造不出来**（实例化时崩）")
    print("   错误越早暴露，调试越省事 —— 这就是 ABC 比 raise NotImplementedError 严格的地方")


# ============================================================
# Demo 3: 部分实现 —— ABC 检查的是"覆盖"，不检查"内容"
# ----- 对应笔记第 8 节自测题 Q3 的延伸
# ============================================================
def demo_3_partial_implementation():
    print("\n" + "=" * 60)
    print("Demo 3: ABC 检查\"是否覆盖\"，不检查方法体的内容")
    print("=" * 60)

    class Tool(ABC):
        @abstractmethod
        def __call__(self):
            pass

    # ---- 场景 A：完整实现 ----
    class GoodTool(Tool):
        def __call__(self):
            return "result"

    print("--- GoodTool（完整实现）---")
    g = GoodTool()
    print(f"    ✅ 实例化成功，调用结果 = {g()!r}")

    # ---- 场景 B：覆盖了名字，但方法体抛错 ----
    class HalfBakedTool(Tool):
        def __call__(self):
            raise NotImplementedError("我故意空着")

    print("\n--- HalfBakedTool（覆盖了 __call__，但方法体抛错）---")
    h = HalfBakedTool()
    print(f"    ✅ 实例化成功（ABC 不管方法体写啥）")
    try:
        h()
    except NotImplementedError as e:
        print(f"    💥 调用时才崩：{e}")

    print("\n💡 关键认知：")
    print("   ABC 检查的是 '子类有没有覆盖那个方法名'，**不检查方法体**")
    print("   所以 ABC + raise NotImplementedError **可以同时用**当双保险")


# ============================================================
# Demo 4: ⭐ smolagents 真实模式 —— BaseTool 用 ABC、Tool.forward 用 NotImplementedError
# ----- 对应笔记第 4 节，最重要的一段
# ============================================================
def demo_4_smolagents_pattern():
    print("\n" + "=" * 60)
    print("Demo 4: smolagents 模式：硬约束 + 软约束 同时存在")
    print("=" * 60)

    # ---- 完全模仿 tools.py:98 的 BaseTool ----
    class BaseTool(ABC):
        name: str

        @abstractmethod
        def __call__(self, *args, **kwargs):
            """框架必经入口，硬约束 —— 没实现连实例都造不出来"""
            pass

    # ---- 完全模仿 tools.py:106 的 Tool ----
    class Tool(BaseTool):
        name = "tool"

        def forward(self, *args, **kwargs):
            """业务逻辑层，软约束 —— wrapper 子类可以绕过 forward"""
            raise NotImplementedError("Write this method in your subclass of `Tool`.")

        def __call__(self, *args, **kwargs):
            # 框架包装层：调用 forward
            return self.forward(*args, **kwargs)

    # ---- 用法 1：标准子类（覆盖 forward，间接经过 __call__）----
    class WeatherTool(Tool):
        name = "weather"

        def forward(self, city):
            return f"The weather in {city} is sunny"

    print("--- 用法 1：WeatherTool 覆盖 forward（标准用法）---")
    w = WeatherTool()
    print(f"    ✅ 实例化成功（forward 已覆盖）")
    print(f"    调用：w('Beijing') = {w('Beijing')!r}")

    # ---- 用法 2：wrapper 子类（绕过 forward，直接覆盖 __call__）----
    # 模拟 PipelineTool / SpaceToolWrapper 这种场景
    class LangChainToolWrapper(Tool):
        name = "lc_wrapper"

        def __init__(self, langchain_tool):
            self.lc_tool = langchain_tool

        def __call__(self, *args, **kwargs):
            # 直接走 __call__，不经过 forward
            return f"[wrapped] {self.lc_tool(*args, **kwargs)}"

    print("\n--- 用法 2：LangChainToolWrapper 绕过 forward 直接覆盖 __call__ ---")
    fake_lc_tool = lambda x: f"lc_result({x})"
    lcw = LangChainToolWrapper(fake_lc_tool)
    print(f"    ✅ 实例化成功（即使没覆盖 forward）")
    print(f"    调用：lcw('hi') = {lcw('hi')!r}")

    # ---- 反证：如果 forward 也用 @abstractmethod 会怎样？----
    print("\n--- 反证：假设 forward 也用 @abstractmethod ---")

    class StrictTool(BaseTool):
        @abstractmethod
        def forward(self):
            pass

        def __call__(self):
            return self.forward()

    class StrictWrapper(StrictTool):
        # 也想绕过 forward 直接实现 __call__
        def __call__(self):
            return "wrapped result"

    try:
        sw = StrictWrapper()
    except TypeError as e:
        print(f"    💥 实例化失败：{e}")
        print(f"    —— 即使覆盖了 __call__，因为没覆盖 forward，照样被 ABC 拦下")

    print("\n💡 关键认知：")
    print("   - BaseTool.__call__ 用硬约束：框架必经之路，没它不行")
    print("   - Tool.forward 用软约束：要给 wrapper 子类留绕过的口子")
    print("   - 这就是 smolagents 同一个文件两种写法都有的设计意图")


# ============================================================
# Demo 5: ABC 与 dataclass 的"温和摩擦"
# ----- 对应笔记第 3 节
# ============================================================
def demo_5_dataclass_friction():
    print("\n" + "=" * 60)
    print("Demo 5: ABC 和 @dataclass 一起用的情况")
    print("=" * 60)

    from dataclasses import dataclass

    # ---- 现代 Python (3.10+) 其实能跑 ----
    @dataclass
    class Step(ABC):
        name: str

        @abstractmethod
        def to_messages(self):
            pass

    print("--- 定义 @dataclass + ABC 的基类 Step ---")
    print(f"    ✅ 类定义成功（Python 3.10+ 改进过）")

    # ---- 子类没实现抽象方法 ----
    @dataclass
    class TaskStep(Step):
        task: str

    print("\n--- 子类 TaskStep 没实现 to_messages ---")
    try:
        TaskStep(name="task", task="hi")
    except TypeError as e:
        print(f"    💥 实例化失败：{e}")
        print(f"    （ABC 的硬约束依然生效）")

    # ---- 子类完整实现 ----
    @dataclass
    class GoodStep(Step):
        task: str

        def to_messages(self):
            return [{"role": "user", "content": self.task}]

    print("\n--- 子类 GoodStep 完整实现 ---")
    g = GoodStep(name="task1", task="hello")
    print(f"    ✅ 实例化成功：{g}")
    print(f"    调用 to_messages() = {g.to_messages()}")

    print("\n💡 关键认知：")
    print("   现代 Python 里 @dataclass + ABC 能跑，但 memory.py 选了软约束路线")
    print("   理由：dataclass 子类继承时字段顺序、默认值传递等限制容易和 ABC 互相拉扯")
    print("   —— 数据容器为主的场景，软约束 + 约定 比硬约束 + 修补更好")


# ============================================================
# Demo 6: 反向自测题（笔记第 8 节）
# ============================================================
def demo_6_self_test():
    print("\n" + "=" * 60)
    print("Demo 6: 自测题")
    print("=" * 60)

    class Tool(ABC):
        name: str  # 类属性注解，不是 abstract

        @abstractmethod
        def __call__(self):
            pass

    # ---- Q1：直接实例化 Tool ----
    print("--- Q1: 直接实例化抽象类 Tool ---")
    try:
        t = Tool()
    except Exception as e:
        print(f"    {type(e).__name__}: {e}")

    # ---- Q2：子类没实现 __call__ ----
    print("\n--- Q2: 子类 IncompleteTool 没实现 __call__ ---")
    class IncompleteTool(Tool):
        name = "incomplete"

    try:
        t2 = IncompleteTool()
    except Exception as e:
        print(f"    {type(e).__name__}: {e}")

    # ---- Q3：覆盖了 __call__ 但方法体抛错 ----
    print("\n--- Q3: HalfBakedTool 覆盖了 __call__ 但方法体抛错 ---")
    class HalfBakedTool(Tool):
        name = "halfbaked"

        def __call__(self):
            raise NotImplementedError("我故意空着")

    t3 = HalfBakedTool()
    print(f"    实例化{'成功' if t3 else '失败'}（ABC 不管方法体内容）")
    try:
        t3()
    except Exception as e:
        print(f"    调用时：{type(e).__name__}: {e}")

    print("\n💡 关键观察：")
    print("   Q3 证明 ABC 的硬约束**只到\"有这个方法\"那一步**，方法里写啥它管不着")
    print("   所以现实代码里 ABC + raise NotImplementedError 经常同时出现 —— 双保险")


if __name__ == "__main__":
    demo_1_cant_instantiate()
    demo_2_hard_vs_soft()
    demo_3_partial_implementation()
    demo_4_smolagents_pattern()
    demo_5_dataclass_friction()
    demo_6_self_test()

    print("\n" + "=" * 60)
    print("✅ 全部 demo 跑完。")
    print("建议下一步：")
    print("  1. 在 tools.py:98 设断点，看 BaseTool 类被定义的瞬间 —— 它是 ABCMeta 元类的实例")
    print("  2. 试试 from smolagents import Tool; Tool() —— 看 Tool 实例化时被 wrap 的校验拦截")
    print("=" * 60)
