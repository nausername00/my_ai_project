"""K1 ComfyUI 冒烟测试：连接本地服务，用 Counterfeit 底模 + LCM-LoRA 生成一张测试图。"""

from __future__ import annotations

import sys
import time

from comfyui_client import ComfyUIClient, ComfyUIError, make_txt2img_workflow

OUT_PATH = r"D:\ComfyUI\smoke_test.png"


def main() -> int:
    client = ComfyUIClient("http://127.0.0.1:8188")
    workflow = make_txt2img_workflow(
        checkpoint="Counterfeit-V2.5_pruned.safetensors",
        positive="1girl, white long hair, gentle smile, upper body, simple plain background, clean lineart, high quality",
        negative="lowres, bad anatomy, bad hands, watermark, text, blurry",
        width=512,
        height=768,
        lora="lcm-lora-sdv1-5.safetensors",
        steps=8,
        cfg=1.5,
    )
    print("queueing prompt...", flush=True)
    prompt_id = client.queue_prompt(workflow)
    print(f"prompt_id={prompt_id}", flush=True)
    deadline = time.time() + 300
    while True:
        entry = client.wait_prompt(prompt_id, poll_interval=5)
        status = entry.get("status", {})
        if status.get("completed"):
            break
        if time.time() > deadline:
            print("TIMEOUT waiting for generation", flush=True)
            return 2
        print("waiting...", flush=True)
    images = client.output_images(entry)
    if not images:
        print("NO IMAGES in output", flush=True)
        return 3
    data = client.fetch_image(images[0])
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    print(f"OK saved {OUT_PATH} ({len(data)} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
