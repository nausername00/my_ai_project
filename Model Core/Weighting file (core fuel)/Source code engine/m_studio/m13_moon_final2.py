"""C 收官命题③月下·霓影月：墨灵最终确认（第三轮）。

v3 已按墨灵明示数值（星点 800）迭代。转述 v3 效果请墨灵拍板。
输出 design_moon_final2.json。
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
OUT = os.path.join(HERE, "design_moon_final2.json")

SYSTEM = (
    "你是墨灵，一位有自己审美和性格的虚拟时装设计师。"
    "第三版作品已经按你给的数值做了，你要认真确认是否定稿。"
    "如果还不满意，必须给出具体数值或明确效果，不能再笼统。只输出 JSON。"
)

RENDER_V3_DESCRIPTION = (
    "v3 渲染效果（姐姐转述）：黑色背景；主体是浅灰+淡蓝棱锥状几何体，"
    "**锥面星点密度大幅提升（800 颗）**，浅白斑点细密散布如星空，"
    "顶端深色尖顶保留（月夜剪影），月光银白+银光细线依旧，"
    "静谧神秘的星月夜氛围已经很足。"
)


def main() -> int:
    with open(CODE_PATH, encoding="utf-8") as f:
        design = json.load(f)
    prompt = (
        f"你的作品「{design['name']}」第三版效果（姐姐转述渲染图）：\n"
        f"{RENDER_V3_DESCRIPTION}\n\n"
        "请最终确认，严格 JSON 输出：\n"
        '{"verdict": "总体评价一句话",\n'
        '"satisfied": true 或 false,\n'
        '"reason": "第一人称俏皮口气说明",\n'
        '"next": "若 satisfied=false，给出【具体】修改（如星点数量/某元素数值）；若 true 写 \'定稿！\'"}\n'
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
