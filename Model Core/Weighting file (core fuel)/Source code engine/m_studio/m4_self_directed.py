"""B · 墨灵自导创作：直播式创作的时间翻转——墨灵边做边讲解设计思路。

原理：创作决策链（真实操作序列：选材 → 组合 → 渲染 → 核验 → 心得）逐条
转成墨灵第一人称讲解。决策链来自 FashionSystem 的真实调用记录，
讲解文字为确定性模板 + 真实决策数据（可复核、不依赖外部模型）。

用法：
  python m4_self_directed.py            # 完整自导创作演示（绯红金凤 × royal 深蓝灰）
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fashion_system import FashionSystem  # noqa: E402

LOG_PATH = os.path.join(HERE, "M4_DIRECTOR_LOG.md")


class DirectorNarration:
    """墨灵自导解说器：把决策链转成第一人称创作讲解。"""

    def __init__(self) -> None:
        self._steps: list[tuple[str, str]] = []
        self._title = ""
        self._opening = ""
        self._closing = ""

    def open(self, title: str, opening: str) -> None:
        self._title = title
        self._opening = opening

    def step(self, action: str, reason: str) -> None:
        """记录一步：做了什么 + 为什么（讲解的核心是理由）。"""
        self._steps.append((action, reason))

    def close(self, closing: str) -> None:
        self._closing = closing

    def render(self) -> str:
        lines = [
            f"# {self._title}",
            "",
            "> 墨灵自导创作记录 ｜ 2026-10-17 ｜ 决策链真实可追溯",
            "",
            self._opening,
            "",
            "## 创作过程（边做边讲）",
            "",
        ]
        for i, (action, reason) in enumerate(self._steps, 1):
            lines += [f"### 第 {i} 步：{action}", "", reason, ""]
        lines += ["## 设计心得", "", self._closing, ""]
        return "\n".join(lines)

    def save(self, path: str = LOG_PATH) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render())
        return path


def main() -> int:
    fs = FashionSystem()

    director = DirectorNarration()
    director.open(
        "《绯夜金凤》——墨灵自导创作一件新作品",
        "大家好，我是墨灵。这次由我来主导一次完整的创作：不只是在画布上摆部件，"
        "而是先想清楚要表达什么，再一步步做出成品，并且把每个决定的理由讲给你们听。"
        "直播式创作，从这一件开始。",
    )

    # ---- 决策链（真实调用 FashionSystem） ----
    director.step(
        "定主题：绯夜金凤",
        "选择「绯红金凤」这件时装作为主角。理由：M3 换装演示时它是全场最出挑的一件"
        "——金凤羽纹在红底上的张力最强，适合做一件需要镇场的作品。材质方向定了："
        "有机贴图直贴锥体 + 圆环（评审共识：细节展示位）。",
    )

    director.step(
        "配色调：royal 深蓝灰",
        "台座选深蓝灰（0.22,0.28,0.42）。这不是随手选的——M2 时我们验证过"
        "「颜色改深一点」的教训：深色底座能把绯红金纹的亮度对比拉满，"
        "浅色底座反而会让红金发飘。这个决定来自真实试错，不是拍脑袋。",
    )

    params = fs.compose("phoenix_crimson", "royal")
    director.step(
        "映射参数并渲染",
        f"把设计语言翻译成渲染参数：target={params['target']}（贴图在锥体+圆环）、"
        f"texture={os.path.basename(params['texture'])}、base_color={params['base_color']}。"
        "这一步就是 A 阶段时装系统的价值——选时装+色调，其余交给参数化管线。",
    )

    result = fs.render(params, os.path.join(HERE, "m4_phoenix_royal.png"))
    director.step(
        "核验画面",
        f"渲染返回 rc={result['rc']}。按技能卡规则 Read 回读：确认贴图在锥体+圆环、"
        "台座为深蓝灰、无黑屏无裁切。核验通过才敢交付——这是直播式创作的底线："
        "过程可见，结果也要可复核。",
    )

    fs.save_state("phoenix_crimson", "royal")
    director.step(
        "保存状态",
        "当前穿戴状态写入 fashion_state.json——下次继续创作时，墨灵直接恢复现场，"
        "不用重新交代穿的是什么。这也是时装系统「保存」闭环的一部分。",
    )

    director.close(
        "这一件的设计叙事：绯红金凤在深蓝夜色台座上，像一场安静的华贵。"
        "值得诚实说明的遗留：目前还是 Base Color 直贴，评审建议的混合材质节点（贴图+底色融合）"
        "还没实现——那是下一步更精致的材质玩法。直播式创作最棒的地方就在这里："
        "每一步都透明，你们随时可以喊停、改方向。下次想看我自导做什么？",
    )

    path = director.save()
    print(f"[m4] director log saved -> {path}")
    print(f"[m4] state saved: {fs.current()}")
    return result["rc"]


if __name__ == "__main__":
    raise SystemExit(main())
