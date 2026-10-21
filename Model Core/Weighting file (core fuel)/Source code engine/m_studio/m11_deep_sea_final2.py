"""C 收官命题①深海：墨灵最终确认（第三轮）。

v3 已按第二轮意见再迭代（底色提亮、海浪/流苏/鱼群更强、气泡珍珠更大更亮、
对比度拉伸）。转述 v3 效果请墨灵拍板；若仍不满意，要求它给出具体的 RGB
数值范围或明确效果，便于一次到位。输出 design_deep_sea_final2.json。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import GenerationRequest, OllamaBackend  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_PATH = os.path.join(HERE, "design_deep_sea_meng.json")
OUT = os.path.join(HERE, "design_deep_sea_final2.json")

SYSTEM = (
    "你是墨灵，一位有自己审美和性格的虚拟时装设计师。"
    "第三版作品已经按你的意见做了，你要认真确认是否定稿。"
    "如果还不满意，必须给出具体、可执行的数值或明确效果，不能再笼统。只输出 JSON。"
)

RENDER_V3_DESCRIPTION = (
    "v3 渲染效果（执行者转述）：黑色背景；灰色八边形台座；主体是**亮蓝色**多棱锥状几何体，"
    "表面有明显反光高光点（气泡与小珍珠反光清晰可见），银色流苏细亮线在棱面上更明显，"
    "整体比前两版更亮、蓝得更鲜活，深海幽冥氛围保持，元素辨识度已很高。"
)


def main() -> int:
    with open(DESIGN_PATH, encoding="utf-8") as f:
        design = json.load(f)
    prompt = (
        f"你的作品「{design['name']}」第三版效果（执行者转述渲染图）：\n"
        f"{RENDER_V3_DESCRIPTION}\n\n"
        "请最终确认，严格 JSON 输出：\n"
        '{"verdict": "总体评价一句话",\n'
        '"satisfied": true 或 false,\n'
        '"reason": "第一人称俏皮口气说明",\n'
        '"next": "若 satisfied=false，给出【具体】修改（如主色 RGB 数值范围、某元素增强比例）；若 true 写 \'定稿！\'"}\n'
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
