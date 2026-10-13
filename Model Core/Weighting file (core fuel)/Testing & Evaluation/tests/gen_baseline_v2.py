"""K1 v2 基准立绘：星空蓝紫眸 / 翠绿宝石眸 两版对比。

修正点：
- 眼睛：starlight blue-violet / emerald gem
- 服装：黑底 + 红蓝撞色 + 金色徽章、帅气夹克感，明确禁止女仆装
- 腿部：标准 euler 采样 + 20 步提高质量；负面词加腿部防护
"""

from __future__ import annotations

import sys
from pathlib import Path

from comfyui_client import ComfyUIClient, make_txt2img_workflow

PROJECT_ROOT = Path(r"D:\Coding\code program\test\This is mine\my_ai_project")
ASSET_DIR = PROJECT_ROOT / "Model Core" / "Weighting file (core fuel)" / "Character" / "K1 Portrait"

CHECKPOINT = "Counterfeit-V2.5_pruned.safetensors"
LORA = "lcm-lora-sdv1-5.safetensors"

EYE_VARIANTS = {
    "star": "(deep blue-violet starry eyes with white starlight sparkle highlights:1.4)",
    "emerald": "(bright emerald green jewel-like sparkling eyes:1.4)",
}

SHARED = (
    "masterpiece, best quality, anime illustration, "
    "elegant gothic dark fantasy style, "
    "1girl, white cat ears, (silver white long flowing hair:1.2), "
    "%EYES%, calm mysterious confident expression, "
    "(black gothic military long coat:1.3), black coat with (blue accents:1.1) and (red accents:1.1), "
    "gold insignia and epaulettes, high collar, white inner shirt, "
    "black stockings, black and gold high heel boots, "
    "standing on two legs, human legs, half body, facing viewer directly, "
    "both arms relaxed at sides, symmetrical frontal pose, "
    "simple plain white background, clean lineart, detailed"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, watermark, text, signature, "
    "blurry, jpeg artifacts, deformed, "
    "bad legs, deformed legs, extra legs, malformed feet, "
    "maid outfit, apron, lace dress, frilly skirt, "
    "gun, weapon, firearm, rifle, sword, "
    "mermaid, fish tail, tail, animal tail, "
    "purple dress, white dress, green dress, green coat"
)


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient("http://127.0.0.1:8188")
    for key, eye_text in EYE_VARIANTS.items():
        if only and key != only:
            continue
        positive = SHARED.replace("%EYES%", eye_text)
        workflow = make_txt2img_workflow(
            checkpoint=CHECKPOINT,
            positive=positive,
            negative=NEGATIVE,
            width=1024,
            height=1536,
            seed=20261012,
            steps=20,
            cfg=7.0,
            lora=None,
        )
        print(f"[{key}] submitting...", flush=True)
        images = client.generate(workflow, timeout_seconds=600)
        if not images:
            print(f"[{key}] NO IMAGES", flush=True)
            continue
        data = client.fetch_image(images[0])
        raw_path = ASSET_DIR / f"baseline_v2_{key}_raw.png"
        raw_path.write_bytes(data)
        print(f"[{key}] raw saved: {raw_path} ({len(data)} bytes)", flush=True)

        try:
            from PIL import Image
            from rembg import remove

            img = Image.open(raw_path).convert("RGBA")
            out = remove(img)
            trans_path = ASSET_DIR / f"baseline_v2_{key}_transparent.png"
            out.save(trans_path)
            print(f"[{key}] transparent saved: {trans_path}", flush=True)
        except Exception as error:  # noqa: BLE001
            print(f"[{key}] rembg failed: {error}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
