"""C 收官命题②鎏金：墨灵最终确认（第二轮回评）。

执行者已按墨灵第一轮意见完成 v2 迭代，转述新渲染效果，请墨灵拍板。
输出 JSON 落盘 design_gold_final.json。
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
REVIEW_PATH = os.path.join(HERE, "design_gold_review.json")
OUT = os.path.join(HERE, "design_gold_final.json")

SYSTEM = (
    "你是墨灵，一位有自己审美和性格的虚拟时装设计师。"
    "当你的修改意见被执行后看到新效果，你会认真确认是否满意，"
    "满意就果断拍板，不满意就继续给出下一步意见。只输出 JSON。"
)

RENDER_V2_DESCRIPTION = (
    "执行者已按你的 3 条意见完成 v2 迭代：古铜色偏暖饱和、增加明度亮度、"
    "金箔网格化均匀分布。新的 3D 摆件渲染效果：黑色背景；主体是**金色**棱锥状几何体"
    "（不再是浅棕，现在是明显鎏金金），锥面均匀散布亮白色光点（金箔碎屑），"
    "锥顶有一小片深色阴影增加立体感，整体华贵暖金、晚霞镀金的感觉出来了。"
)


def main() -> int:
    with open(DESIGN_PATH, encoding="utf-8") as f:
        design = json.load(f)
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)
    prompt = (
        f"你的作品「{design['name']}」迭代后的效果（执行者转述渲染图）：\n"
        f"{RENDER_V2_DESCRIPTION}\n\n"
        f"你的第一轮自评意见：{json.dumps(review.get('suggestions'), ensure_ascii=False)}\n\n"
        "请最终确认，严格 JSON 输出：\n"
        '{"verdict": "总体评价一句话",\n'
        '"satisfied": true 或 false（是否满意、可以定稿）,\n'
        '"reason": "拍板或继续的原因，第一人称俏皮口气",\n'
        '"next": "若 satisfied=false 给出下一条可执行意见；若 true 则写 \'定稿！\'"}\n'
        "只输出 JSON。"
    )
    backend = OllamaBackend(
        model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        timeout=240.0,
    )
    req = GenerationRequest(prompt=prompt, max_tokens=800, system_prompt=SYSTEM, json_mode=True)
    text = backend.generate(req)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    final = json.loads(text)
    final["_design"] = design.get("name")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(json.dumps(final, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
