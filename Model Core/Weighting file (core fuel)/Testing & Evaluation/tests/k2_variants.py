"""K2 变体生成：背景纯净化 + 闭眼/开口变体（img2img 低噪重绘）。

流程：
1. 把定稿拷入 ComfyUI input 目录（LoadImage 只读那里）
2. img2img denoise≈0.35：背景修成纯白（去掉灰白线条/兜帽/飘带/烟雾残留）
3. 基于净化版再生成 闭眼 / 开口 两个变体（denoise≈0.4，保持其余不变）

用法：python k2_variants.py
输出：baseline_v5_0_clean.png / baseline_v5_0_closed_eyes.png / baseline_v5_0_open_mouth.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from comfyui_client import ComfyUIClient, make_img2img_workflow
from portrait_prompts import NEGATIVE_TEMPLATE, PORTRAIT_BASELINE

PROJECT_ROOT = Path(r"D:\Coding\code program\test\This is mine\my_ai_project")
ASSET_DIR = PROJECT_ROOT / "Model Core" / "Weighting file (core fuel)" / "Character" / "K1 Portrait"
COMFY_INPUT = Path(r"D:\ComfyUI\ComfyUI_windows_portable\ComfyUI\input")

CHECKPOINT = "Counterfeit-V2.5_pruned.safetensors"
INPUT_NAME = "moling_k2_baseline.png"

CLEAN_PROMPT = (
    "identical image, exactly the same girl, same character, same outfit, same red eyes, "
    "same white cat ears, same silver white hair, same pose, same composition, "
    "only remove the background decoration and make the background plain pure white, "
    "no red lines, no cape, no hood, no smoke, no floating elements, "
    "no rabbit, no plush toy, no extra object, no new elements, "
    "clean lineart, detailed"
)
CLEAN_PROMPT_LOW = (
    "identical image, exactly the same girl, same character, same outfit, same red eyes, "
    "same white cat ears, same silver white hair, same pose, same composition, "
    "plain pure white background, no background pattern, no extra object, no new elements, "
    "clean lineart, detailed"
)
CLOSED_EYES_PROMPT = (
    "same girl, same character, same outfit, same white cat ears, same silver white hair, "
    "eyes closed, sleeping calm expression, plain pure white background, "
    "clean lineart, detailed"
)
OPEN_MOUTH_PROMPT = (
    "identical image, exactly the same girl, same character, same outfit, same red eyes, "
    "same white cat ears, same silver white hair, same pose, same composition, "
    "mouth slightly open, gentle speaking expression, "
    "plain pure white background, no background pattern, "
    "no extra object, no shadow figure, no ghost, no broken limb, no body part, "
    "clean lineart, detailed"
)


def _copy_to_input(raw_path: Path) -> None:
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    target = COMFY_INPUT / INPUT_NAME
    target.write_bytes(raw_path.read_bytes())
    print(f"已拷入 ComfyUI input: {target}", flush=True)


def _generate(client: ComfyUIClient, prompt: str, seed: int, denoise: float, out_name: str) -> None:
    workflow = make_img2img_workflow(
        checkpoint=CHECKPOINT,
        positive=prompt,
        negative=NEGATIVE_TEMPLATE,
        input_image=INPUT_NAME,
        seed=seed,
        steps=20,
        cfg=7.0,
        denoise=denoise,
    )
    images = client.generate(workflow, timeout_seconds=600)
    if not images:
        raise RuntimeError(f"{out_name}: ComfyUI 未返回图片")
    data = client.fetch_image(images[0])
    out_path = ASSET_DIR / out_name
    out_path.write_bytes(data)
    print(f"已生成: {out_path} ({len(data)} bytes)", flush=True)


def main() -> int:
    raw_path = ASSET_DIR / "baseline_v5_0_raw.png"
    if not raw_path.exists():
        print("找不到定稿 raw，请先完成 K1", file=sys.stderr)
        return 1
    _copy_to_input(raw_path)

    client = ComfyUIClient("http://127.0.0.1:8188")
    # 1) 背景纯净化（denoise 低，只改背景装饰）
    _generate(client, CLEAN_PROMPT_LOW, seed=20261031, denoise=0.22, out_name="baseline_v5_0_clean.png")
    # 2) 闭眼变体：以净化版为基础，替换 input 后重绘
    clean_path = ASSET_DIR / "baseline_v5_0_clean.png"
    _copy_to_input(clean_path)
    _generate(client, CLOSED_EYES_PROMPT, seed=20261012 + 101, denoise=0.42, out_name="baseline_v5_0_closed_eyes.png")
    # 3) 开口变体（denoise 降低，禁止残影/人形轮廓）
    _generate(client, OPEN_MOUTH_PROMPT, seed=20261012 + 107, denoise=0.32, out_name="baseline_v5_0_open_mouth.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
