"""C 收官命题③月下·霓影月：墨灵自评 v1（姐姐转述渲染 → 妹妹做审美判断）。

反转模式：墨灵写了执行代码（有 4 个 bug），姐姐代笔修复并保留墨灵意图
（月光银白 [215,245,255]、静谧月夜）。渲染完成后转述给墨灵自评。
输出 design_moon_review.json。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import GenerationRequest, OllamaBackend  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_PATH = os.path.join(HERE, "design_moon_code.json")
OUT = os.path.join(HERE, "design_moon_review.json")

SYSTEM = (
    "你是墨灵，一位有自己审美和性格的虚拟时装设计师。"
    "你的执行代码被姐姐修复后做成成品给你看，你会认真自评："
    "先承认做得好的地方，再诚实指出不足，给出具体、可执行的修改意见。"
    "只输出 JSON。"
)

RENDER_DESCRIPTION = (
    "这是你的「霓影月」时装被制作出来后的效果（3D 摆件渲染图）："
    "黑色背景；底部是银灰色八边形台座；主体是**浅灰银白**棱锥状几何体，"
    "顶部有一段深色尖顶（月夜剪影的暗部），锥面散布白色小圆点（星点），"
    "整体银白月光、静谧素雅。你的月光银白主色 [215,245,255] 被忠实呈现，"
    "但可能偏『素净』，月光的柔美层次（月晕光晕、银光流转）在渲染里还不明显。"
)


def main() -> int:
    with open(CODE_PATH, encoding="utf-8") as f:
        design = json.load(f)
    prompt = (
        f"你设计的时装「{design['name']}」（月光银白 [215,245,255]）已经做出来了。\n"
        f"你的设计理念：{design.get('idea')}\n\n"
        f"制作结果（由姐姐转述渲染图）：\n{RENDER_DESCRIPTION}\n\n"
        "请自评，严格 JSON 输出：\n"
        '{"verdict": "一句话总体评价（是否达到你预期的静谧神秘月光氛围）",\n'
        '"praise": "你觉得做得好的 1-2 点",\n'
        '"issues": ["诚实的不足，1-3 条"],\n'
        '"suggestions": ["可执行的修改意见，每条一句话，最多 3 条（可针对月晕光晕/银光层次/星点/云纱/明暗对比）"]}\n'
        "只输出 JSON。"
    )
    backend = OllamaBackend(
        model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        timeout=240.0,
    )
    req = GenerationRequest(prompt=prompt, max_tokens=1200, system_prompt=SYSTEM, json_mode=True)
    text = backend.generate(req)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    review = json.loads(text)
    review["_design"] = design.get("name")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)
    print(json.dumps(review, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
