"""K1 基准立绘生成：组装结合形象提示词 → ComfyUI 生成 → rembg 透明化 → 保存。

输出：
- Character/K1 Portrait/baseline_raw.png      原始生成图
- Character/K1 Portrait/baseline_transparent.png  透明立绘
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from comfyui_client import ComfyUIClient, make_txt2img_workflow

PROJECT_ROOT = Path(r"D:\Coding\code program\test\This is mine\my_ai_project")
ASSET_DIR = PROJECT_ROOT / "Model Core" / "Weighting file (core fuel)" / "Character" / "K1 Portrait"

CHECKPOINT = "Counterfeit-V2.5_pruned.safetensors"
LORA = "lcm-lora-sdv1-5.safetensors"

POSITIVE = (
    "masterpiece, best quality, anime illustration, "
    "1girl, cat ears, silver white long flowing hair with light green gradient tips, "
    "red eyes, calm mysterious expression, "
    "gothic lolita dress, black and red color scheme with gold trims, white ribbon accents, "
    "half body, neutral standing pose, facing viewer, "
    "simple plain white background, clean lineart, soft shading"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, watermark, text, signature, "
    "blurry, jpeg artifacts, deformed"
)


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient("http://127.0.0.1:8188")
    workflow = make_txt2img_workflow(
        checkpoint=CHECKPOINT,
        positive=POSITIVE,
        negative=NEGATIVE,
        width=1024,
        height=1536,
        seed=20261012,
        steps=8,
        cfg=1.5,
        lora=LORA,
    )
    print("submitting baseline prompt...", flush=True)
    images = client.generate(workflow, timeout_seconds=420)
    if not images:
        print("NO IMAGES returned", flush=True)
        return 2
    data = client.fetch_image(images[0])
    raw_path = ASSET_DIR / "baseline_raw.png"
    raw_path.write_bytes(data)
    print(f"raw saved: {raw_path} ({len(data)} bytes)", flush=True)

    try:
        from PIL import Image
        from rembg import remove

        img = Image.open(raw_path).convert("RGBA")
        out = remove(img)
        trans_path = ASSET_DIR / "baseline_transparent.png"
        out.save(trans_path)
        print(f"transparent saved: {trans_path}", flush=True)
    except Exception as error:  # noqa: BLE001
        print(f"rembg failed: {error}", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
