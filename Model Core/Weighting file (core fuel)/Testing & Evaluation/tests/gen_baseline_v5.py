"""K1 v5：回归第一版基底（红眸/白猫耳/银白长发）+ 黑白主色蓝红点缀服装 + 多 seed 挑选腿部。

策略：一次生成 3 个 seed 的 raw 图（不透明化），由人工挑选腿部/裙摆正常的一张后再透明化。
"""

from __future__ import annotations

import sys
from pathlib import Path

from comfyui_client import ComfyUIClient, make_txt2img_workflow

PROJECT_ROOT = Path(r"D:\Coding\code program\test\This is mine\my_ai_project")
ASSET_DIR = PROJECT_ROOT / "Model Core" / "Weighting file (core fuel)" / "Character" / "K1 Portrait"

CHECKPOINT = "Counterfeit-V2.5_pruned.safetensors"
LORA = "lcm-lora-sdv1-5.safetensors"

SEEDS = [20261031]

POSITIVE = (
    "masterpiece, best quality, anime illustration, "
    "elegant gothic dark fantasy style, "
    "1girl, solo, single character, (white cat ears:1.1), (silver white long flowing hair:1.2), "
    "(bright red eyes:1.3), calm mysterious gentle expression, "
    "(black and white elegant outfit:1.2), white shirt with black high collar jacket, "
    "(blue accents:1.0) and (red accents:1.0) trims, gold insignia, "
    "black skirt with red and blue trim, black stockings, black boots, "
    "standing on two legs, normal legs, half body, facing viewer directly, "
    "both arms relaxed at sides, symmetrical frontal pose, "
    "plain pure white background, clean lineart, detailed"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, watermark, text, signature, "
    "blurry, jpeg artifacts, deformed, "
    "bad legs, deformed legs, extra legs, three legs, triple legs, fused legs, "
    "malformed feet, skirt overlap, clipping, "
    "maid outfit, apron, lace dress, frilly skirt, "
    "gun, weapon, firearm, rifle, sword, "
    "mermaid, fish tail, tail, animal tail, "
    "purple cape, green dress, green coat, "
    "garbage bag, plastic bag, trash bag, holding bag, "
    "flower petals, petals, mist, fog, smoke, "
    "twin tails, twin-tail hair, double ponytail, pigtails, "
    "two girls, multiple people, second person, duo"
)


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient("http://127.0.0.1:8188")
    for i, seed in enumerate(SEEDS):
        workflow = make_txt2img_workflow(
            checkpoint=CHECKPOINT,
            positive=POSITIVE,
            negative=NEGATIVE,
            width=1024,
            height=1536,
            seed=seed,
            steps=20,
            cfg=7.0,
            lora=None,
        )
        print(f"[seed {seed}] submitting...", flush=True)
        images = client.generate(workflow, timeout_seconds=600)
        if not images:
            print(f"[seed {seed}] NO IMAGES", flush=True)
            continue
        data = client.fetch_image(images[0])
        raw_path = ASSET_DIR / f"baseline_v5_{i}_raw.png"
        raw_path.write_bytes(data)
        print(f"[seed {seed}] saved: {raw_path} ({len(data)} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
