"""
Day 2 配套实验：__init_subclass__ 钩子手感练习

配套笔记：learning/notes/03-source/python-init-subclass.md

跑法：
  python learning/scripts/init_subclass_demo.py

建议调试姿势：
  1. 先整体跑一遍，看输出顺序
  2. 在每个 demo 函数开头设断点，单步走
  3. 重点观察 "[HOOK]" 打印出现的时机 —— 是不是真的早于 "[INIT]"

每个 demo 是独立的，可以注释掉别的、单独跑某一个。
"""

import sys

# Windows 默认控制台是 GBK，强制 UTF-8 才能正常打印中文 + emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# Demo 1: 三个钩子的触发时机对比
# ----- 对应笔记第 1 节"触发时机：子类被定义的那一刻"
# ============================================================
def demo_1_timing():
    print("\n" + "=" * 60)
    print("Demo 1: __init_subclass__ vs __new__ vs __init__ 时机")
    print("=" * 60)

    class Foo:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            print(f"[HOOK]  __init_subclass__ 跑了，cls = {cls.__name__}")

        def __new__(cls, *args, **kwargs):
            print(f"[NEW]   __new__ 跑了，正在创建 {cls.__name__} 的实例")
            return super().__new__(cls)

        def __init__(self):
            print(f"[INIT]  __init__ 跑了，self 是 {type(self).__name__} 的实例")

    print("--- 准备定义子类 Bar（注意下一行就会触发钩子） ---")
    class Bar(Foo):
        pass
    print("--- 子类 Bar 已定义 ---")

    print("--- 准备实例化 Bar ---")
    b = Bar()
    print("--- 实例 b 已创建 ---")

    print("--- 再造一个实例 ---")
    b2 = Bar()
    # 注意：__init_subclass__ 不会再跑（钩子只在子类**定义**时触发，不在实例化时）


# ============================================================
# Demo 2: 校验前置到导入阶段
# ----- 对应笔记 1.2 节"hasattr name 检查"
# ============================================================
def demo_2_early_fail():
    print("\n" + "=" * 60)
    print("Demo 2: 钩子里抛错 → 子类定义那一刻就崩")
    print("=" * 60)

    class Tool:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            if not hasattr(cls, "name"):
                raise TypeError(f"{cls.__name__} 必须定义类属性 'name'")

    # 正常情况
    print("--- 定义 GoodTool（有 name） ---")
    class GoodTool(Tool):
        name = "good"
    print("    ✅ GoodTool 定义成功")

    # 异常情况：故意不写 name
    print("--- 定义 BadTool（没 name），预期崩 ---")
    try:
        class BadTool(Tool):
            pass
    except TypeError as e:
        print(f"    💥 如预期崩了：{e}")

    print("\n💡 关键观察：BadTool 没有被实例化，仅仅是定义就崩了")
    print("   —— 这就是 '错误早一刻暴露' 的能力")


# ============================================================
# Demo 3: 不用 vs 用 __init_subclass__ 的对比
# ----- 对应笔记第 2 节
# ============================================================
def demo_3_compare_with_without():
    print("\n" + "=" * 60)
    print("Demo 3: 不用 __init_subclass__ 时校验容易被绕过")
    print("=" * 60)

    # ---- 写法 A：基类 __init__ 校验，子类必须显式调 super().__init__() ----
    class ToolA:
        def __init__(self):
            if not hasattr(self, "name"):
                raise TypeError("missing name")

    class ForgetfulTool(ToolA):
        # 注意：故意不调 super().__init__()
        def __init__(self):
            pass  # 跳过校验

    print("--- 写法 A：用基类 __init__ 校验 ---")
    t = ForgetfulTool()  # 没崩！校验被绕过了
    print(f"    ⚠️  ForgetfulTool 实例化成功了（没 name 也没崩）—— 校验被绕过")

    # ---- 写法 B：用 __init_subclass__ 校验，无法绕过 ----
    class ToolB:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            if not hasattr(cls, "name"):
                raise TypeError(f"{cls.__name__} 必须定义 'name'")

    print("--- 写法 B：用 __init_subclass__ 校验 ---")
    try:
        class ForgetfulToolB(ToolB):
            def __init__(self):
                pass  # 你想绕也绕不开 —— 钩子在你写 __init__ 之前就跑过了
    except TypeError as e:
        print(f"    💥 如预期崩：{e}")
    print("    ✅ ForgetfulToolB 根本没机会被定义出来")


# ============================================================
# Demo 4: smolagents 的实际模式 —— wrap __init__
# ----- 对应笔记第 3 节，最重要的一段，对照 tools.py:70 看
# ============================================================
def demo_4_smolagents_pattern():
    print("\n" + "=" * 60)
    print("Demo 4: smolagents 模式：钩子 wrap 子类 __init__")
    print("=" * 60)

    from functools import wraps

    # 完全模仿 tools.py:70 的 validate_after_init
    def validate_after_init(cls):
        original_init = cls.__init__
        print(f"    [WRAP] 准备给 {cls.__name__} 装挂钩，原 __init__ = {original_init}")

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            print(f"    [NEW_INIT] 跑 {type(self).__name__} 的 __init__ 包装层")
            original_init(self, *args, **kwargs)
            print(f"    [NEW_INIT] 用户 __init__ 跑完了，现在自动调 validate_arguments")
            self.validate_arguments()

        cls.__init__ = new_init
        print(f"    [WRAP] {cls.__name__}.__init__ 已被换成 {new_init}")
        return cls

    class Tool:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            print(f"[HOOK] 给 {cls.__name__} 装校验挂钩")
            validate_after_init(cls)

        def validate_arguments(self):
            # 真正的校验在这里跑
            if not hasattr(self, "name"):
                raise TypeError(f"{type(self).__name__} 缺 name")
            print(f"    [VALIDATE] {type(self).__name__} 校验通过，name={self.name}")

    # ---- 场景 A：用户子类老老实实调 super().__init__() ----
    print("\n--- 场景 A：定义 ProperTool（调 super） ---")
    class ProperTool(Tool):
        name = "proper"

        def __init__(self):
            print(f"    [USER_INIT] ProperTool 用户写的 __init__ 跑了")
            super().__init__()  # Tool 没自定义 __init__，但调 super 是好习惯

    print("\n--- 实例化 ProperTool ---")
    t1 = ProperTool()

    # ---- 场景 B：用户子类故意不调 super().__init__() —— 也无法绕过校验！ ----
    print("\n--- 场景 B：定义 SneakyTool（故意不调 super） ---")
    class SneakyTool(Tool):
        name = "sneaky"

        def __init__(self):
            print(f"    [USER_INIT] SneakyTool 用户写的 __init__ 跑了（没调 super）")

    print("\n--- 实例化 SneakyTool ---")
    t2 = SneakyTool()
    # 注意 [VALIDATE] 还是跑了！这就是 wrap 模式的精妙之处

    print("\n💡 关键观察：")
    print("   两种场景下 [VALIDATE] 都跑了。")
    print("   wrap 模式让用户**无论怎么写 __init__**，都会被自动加上校验调用。")


# ============================================================
# Demo 5: super().__init_subclass__() 的链式传递
# ----- 对应笔记第 5 节
# ============================================================
def demo_5_super_chain():
    print("\n" + "=" * 60)
    print("Demo 5: super().__init_subclass__() 链式传递的重要性")
    print("=" * 60)

    class A:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            print(f"    [A's hook] 看到 {cls.__name__}")

    class B:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            print(f"    [B's hook] 看到 {cls.__name__}")

    print("--- 写法 A：调 super（推荐）---")
    class GoodChild(A, B):
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)  # ← 关键
            print(f"    [GoodChild's hook] 看到 {cls.__name__}")

    print("--- 定义 GrandGood(GoodChild) ---")
    class GrandGood(GoodChild):
        pass
    # 应该看到 A、B、GoodChild 三个钩子都打印

    print("\n--- 写法 B：不调 super（错误示范）---")
    class BadChild(A, B):
        def __init_subclass__(cls, **kwargs):
            # 故意不调 super！
            print(f"    [BadChild's hook] 看到 {cls.__name__}")

    print("--- 定义 GrandBad(BadChild) ---")
    class GrandBad(BadChild):
        pass
    # 只会看到 BadChild 一个钩子，A 和 B 的都被吃掉了

    print("\n💡 关键观察：")
    print("   GoodChild 链上 A/B/GoodChild 三个钩子都跑了；")
    print("   BadChild 链上只有 BadChild 自己的跑了，A、B 被吃掉。")
    print("   所以基类的 __init_subclass__ 第一行通常都要 super().__init_subclass__(**kwargs)")


# ============================================================
# Demo 6: 反向自测题（笔记第 7 节）
# ============================================================
def demo_6_self_test():
    print("\n" + "=" * 60)
    print("Demo 6: 自测题 —— 钩子在子类对象上挂属性")
    print("=" * 60)

    class Tool:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            print(f"    hook for {cls.__name__}")
            cls.tag = "registered"  # 在子类对象上挂一个类属性

    print("--- import 阶段 ---")
    class WeatherTool(Tool):
        def __init__(self):
            print("    WeatherTool.__init__ 跑了")

    print("--- 实例化 ---")
    t = WeatherTool()

    print("--- 检查 tag ---")
    print(f"    WeatherTool.tag = {WeatherTool.tag}")  # 类属性
    print(f"    t.tag           = {t.tag}")            # 实例查不到时向上找类属性

    print("\n💡 关键观察：")
    print("   'hook for WeatherTool' 出现在 '--- 实例化 ---' 之前")
    print("   —— 钩子触发于子类**定义**时，不是实例化时")


if __name__ == "__main__":
    demo_1_timing()
    demo_2_early_fail()
    demo_3_compare_with_without()
    demo_4_smolagents_pattern()
    demo_5_super_chain()
    demo_6_self_test()

    print("\n" + "=" * 60)
    print("✅ 全部 demo 跑完。")
    print("建议：现在去 tools.py:70 和 tools.py:140 设断点，")
    print("      跑 learning/scripts/compare_agents.py，单步走 validate_after_init")
    print("      —— 你会看到真实的 Tool 子类被这套机制接管的全过程。")
    print("=" * 60)
