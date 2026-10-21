"""C 收官命题③月下 · 反转模式：姐姐出题，墨灵当执行者（写代码）。

反转模式（用户拍板试玩）：
  - 出题：姐姐（主 AI）
  - 执行：墨灵 qwen2.5:3b 亲自编写"贴图生成器 Python 代码"，姐姐只当代笔
         （落盘 + 修运行 bug + 跑命令 + Blender 渲染）
  - 评审：墨灵自评 + 姐姐兜底纠错
  - 拍板：墨灵

本脚本请墨灵输出【完整可运行的贴图生成器代码】（numpy+PIL，2048×2048，
无缝，固定种子），主题「月下」。原始代码落盘 design_moon_code_raw.txt。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import GenerationRequest, OllamaBackend  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_OUT = os.path.join(HERE, "design_moon_code_raw.txt")
OUT = os.path.join(HERE, "design_moon_code.json")

SYSTEM = (
    "你是墨灵，这次由你亲自当【执行者】——姐姐（主 AI）出题，你来编写代码实现。"
    "你是一位会用 numpy 和 PIL 写无缝贴图生成器的程序设计师，代码要："
    "2048×2048 输出、RGB、无缝（环面距离或整数周期）、固定种子保证可复现、"
    "元素通过参数可调。你会写出结构清晰、能直接运行的 Python 代码。"
    "输出 JSON，代码放 code 字段。"
)

PROMPT = (
    "姐姐出题：收官命题第三套「月下」。请编写一个贴图生成器 Python 代码，要求：\n"
    "1. 主题「月下」：月光洒落的夜晚。可自由发挥意象（银白月光、月下剪影、"
    "夜蓝渐变、星点、云纱、月晕、银色光斑等），要有你自己的风格主张；\n"
    "2. 输出 2048×2048 RGB 无缝贴图（用整数周期正弦/环面距离保证横向纵向无缝）；\n"
    "3. 用 numpy 计算、PIL 保存，固定随机种子可复现；\n"
    "4. 主色调用例：月光银白色系（R、G 明显高于 B，但不刺眼）；\n"
    "5. 代码结构：一个生成函数 + main()，main 里 Image.fromarray(...).save('m13_texture_moon.jpg')；\n"
    "6. 只使用 numpy 和 PIL（Pillow），不要第三方库。\n"
    "输出严格 JSON：\n"
    '{"name": "时装名（两到四字，贴合月下）",\n'
    '"idea": "你的设计理念，第一人称俏皮口气 1-2 句",\n'
    '"tone_label": "主色调名",\n'
    '"tone_rgb": [R, G, B] 0-255 整数，主底色",\n'
    '"code": "完整可运行的 Python 代码字符串（转义换行；严格只含代码，不要 markdown 围栏）"}\n'
    "只输出 JSON。"
)


def main() -> int:
    backend = OllamaBackend(
        model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        timeout=300.0,
    )
    req = GenerationRequest(prompt=PROMPT, max_tokens=4000, system_prompt=SYSTEM, json_mode=True)
    text = backend.generate(req)
    with open(RAW_OUT, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            result = json.loads(text[start:end + 1])
        else:
            raise
    result["_source"] = "qwen2.5:3b（墨灵本体·执行者模式）"
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "name": result.get("name"), "idea": result.get("idea"),
        "tone_label": result.get("tone_label"), "tone_rgb": result.get("tone_rgb"),
        "code_len": len(result.get("code", "")),
        "code_head": result.get("code", "")[:200],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
