"""C 收官命题②鎏金：墨灵自评 v1（姐姐转述渲染 → 妹妹做审美判断）。

qwen2.5:3b 为文本模型，无法直接看图；执行者（主 AI）将渲染结果转为
客观文字描述喂给墨灵，由墨灵基于自己的设计稿做自评并给出可执行修改意见。
输出 JSON 落盘 design_gold_review.json。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import GenerationRequest, OllamaBackend  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_PATH = os.path.join(HERE, "design_gold_meng.json")
OUT = os.path.join(HERE, "design_gold_review.json")

SYSTEM = (
    "你是墨灵，一位有自己审美和性格的虚拟时装设计师。"
    "当你的设计稿第一版被制作出来给你看时，你会认真自评："
    "先承认做得好的地方，再诚实指出不足，给出具体、可执行的修改意见。"
    "只输出 JSON。"
)

RENDER_DESCRIPTION = (
    "这是你的「鎏金幻影」时装被制作出来后的效果（3D 摆件渲染图）："
    "画面为黑色背景；底部是浅棕色八边形台座；主体是一个浅棕/古铜色棱锥状几何体，"
    "你的鎏金贴图贴合在主体表面，表面散布白色小圆点光斑（对应金箔碎屑反光）。"
    "整体观感：古铜质感有了，但偏『浅棕』，鎏金该有的『熔金暖亮、晚霞镀金』的华丽感还差一些，"
    "金箔亮点多但主体不够金亮。"
)


def main() -> int:
    with open(DESIGN_PATH, encoding="utf-8") as f:
        design = json.load(f)
    prompt = (
        f"你设计的第一版时装「{design['name']}」已经做出来了。\n"
        f"你的设计稿：\n{json.dumps(design, ensure_ascii=False, indent=2)}\n\n"
        f"制作结果（由执行者转述渲染图）：\n{RENDER_DESCRIPTION}\n\n"
        "请自评，严格 JSON 输出：\n"
        '{"verdict": "一句话总体评价（是否达到你预期的晚霞镀金鎏金氛围）",\n'
        '"praise": "你觉得做得好的 1-2 点",\n'
        '"issues": ["诚实的不足，1-3 条"],\n'
        '"suggestions": ["可执行的修改意见，每条一句话，最多 3 条（可针对金色饱和度/明度/浮雕层次/金箔分布/暖光）"]}\n'
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
