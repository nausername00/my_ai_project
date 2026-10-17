"""M5b · 反差萌剧本引擎——被夸奖时的三拍演出。

得意炫耀 → 说漏嘴 → 害羞狡辩（手舞足蹈）。
每拍带 mood（对接 character 情绪枚举：开心/惊喜/害羞）与 expression（立绘表情提示），
支持注入 M5a 形象提案的设计思路（style/idea），让炫耀内容真实指向当前造型。

纯表现层引擎：不改变任何执行 / 授权逻辑。
"""

from __future__ import annotations

import json
import sys
from typing import Any

# 三拍剧本模板（用户点名的可爱场景：自夸→说漏嘴→害羞狡辩）
_PRAISE_BEATS: list[dict[str, str]] = [
    {
        "beat": "proud",
        "mood": "开心",
        "expression": "proud",
        "text": "哼哼~这可是结合「{style}」的风格，自然的褶皱向外扩散，营造出活泼感——",
    },
    {
        "beat": "slip",
        "mood": "惊喜",
        "expression": "surprised",
        "text": "说不定……在诱惑你呢~",
    },
    {
        "beat": "shy",
        "mood": "害羞",
        "expression": "shy",
        "text": "啊——！才、才不是那样！我、我说的是设计思路啦！（手舞足蹈地狡辩）…总之不许乱想！",
    },
]

_TRIGGER_CUES = ("夸", "好看", "漂亮", "可爱", "厉害", "棒", "喜欢", "pride", "praise")


def detect_praise(message: str) -> bool:
    """轻量触发检测：消息里出现夸奖词即命中（默认关的被动触发，不抢话）。"""
    return any(cue in message for cue in _TRIGGER_CUES)


class PraiseScript:
    """反差萌剧本：按触发场景返回三拍演出序列，支持注入设计思路。"""

    def __init__(self, beats: list[dict[str, str]] | None = None) -> None:
        self._beats = beats or _PRAISE_BEATS

    def play(self, style: str = "青花云纹", idea: str = "") -> list[dict[str, Any]]:
        """完整三拍：proud → slip → shy。style 注入当前造型名，idea 附设计思路。"""
        script = []
        for beat in self._beats:
            text = beat["text"].format(style=style)
            if beat["beat"] == "proud" and idea:
                text = f"{text}{idea}"
            script.append({**beat, "text": text})
        return script

    def play_beat(self, index: int, style: str = "青花云纹", idea: str = "") -> dict[str, Any]:
        if not 0 <= index < len(self._beats):
            raise IndexError(f"剧本拍数越界: {index}")
        return self.play(style=style, idea=idea)[index]

    def mood_sequence(self) -> list[str]:
        return [b["mood"] for b in self._beats]

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.play(**kwargs), ensure_ascii=False, indent=2)


def main(argv: list[str]) -> int:
    """CLI：--play [--style 造型名] [--idea 设计思路] | --moods | --detect <消息>"""
    script = PraiseScript()
    if "--moods" in argv:
        print(", ".join(script.mood_sequence()))
        return 0
    if "--detect" in argv:
        msg = argv[argv.index("--detect") + 1]
        print(f"detect_praise={detect_praise(msg)}")
        return 0
    if "--play" in argv:
        style = "青花云纹"
        if "--style" in argv:
            style = argv[argv.index("--style") + 1]
        idea = ""
        if "--idea" in argv:
            idea = argv[argv.index("--idea") + 1]
        print(script.to_json(style=style, idea=idea))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
