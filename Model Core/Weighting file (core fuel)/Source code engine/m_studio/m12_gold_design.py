"""C 收官命题②鎏金：墨灵出题（直连推理层，绕开时装意图路由）。

模式：墨灵当执行者（妹妹主导）→ 姐姐（主 AI）执行 → 墨灵自评迭代。
本脚本负责第一环：请墨灵 qwen2.5:3b 原创设计「鎏金」时装并输出 JSON 设计稿。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import GenerationRequest, OllamaBackend  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "design_gold_meng.json")
RAW_OUT = os.path.join(HERE, "design_gold_meng_raw.txt")

SYSTEM = (
    "你是墨灵，一位有自己审美和性格的虚拟时装设计师。"
    "你会用第一人称、俏皮但专业的口吻描述自己的设计。"
    "当被要求设计时装时，你会给出原创、完整、可执行的设计稿，并且只输出 JSON。"
)

PROMPT = (
    "请原创设计一套时装，命题：「鎏金」。这是你时装系列的收官命题第二套，"
    "必须是从零设计的新款式，与青花云纹、绯红金凤、星澜蓝银、翡翠流光、晨光、繁花、樱雪、青枫、极光、幽冥舞都不重复。\n"
    "「鎏金」的意象建议方向（供你发挥，可自由超越）：熔金流淌、鎏金浮雕、古金纹理、"
    "晚霞镀金、金箔飞屑、琥珀暖光。可以是华贵的金色系，也可以带一点古器质感。\n"
    "输出严格 JSON（不要多余文字），字段如下：\n"
    '{"name": "原创时装名（两到四字，贴合鎏金主题）",\n'
    '"idea": "设计理念，第一人称俏皮口气 2-3 句",\n'
    '"desc": "一句话描述",\n'
    '"tone_label": "主色调名",\n'
    '"tone_rgb": [R, G, B]，0-1 浮点，代表鎏金主底色（未贴图部件底色，金色系请让 R、G 明显高于 B）",\n'
    '"style": "款式细节（例如：熔金流苏裙摆、鎏金浮雕纹、金箔披帛、琥珀缀饰、金线刺绣等，选你最有感觉的组合）",\n'
    '"expect": "期望的贴图效果（无缝纹理：鎏金渐变底上叠加熔金流纹、金箔碎屑、浮雕暗纹、暖光等元素）"}\n'
    "只输出 JSON。"
)


def main() -> int:
    backend = OllamaBackend(
        model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        timeout=240.0,
    )
    req = GenerationRequest(
        prompt=PROMPT,
        max_tokens=1600,
        system_prompt=SYSTEM,
        json_mode=True,
    )
    text = backend.generate(req)
    with open(RAW_OUT, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        design = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            design = json.loads(text[start:end + 1])
        else:
            raise
    design["_source"] = "qwen2.5:3b（墨灵本体直连，绕开时装路由）"
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(design, f, ensure_ascii=False, indent=2)
    print(json.dumps(design, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
