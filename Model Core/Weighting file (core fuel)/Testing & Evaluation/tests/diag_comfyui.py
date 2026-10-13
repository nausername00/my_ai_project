"""诊断 ComfyUI 400 错误详情。"""

import json
import urllib.error
import urllib.request

from comfyui_client import make_txt2img_workflow

wf = make_txt2img_workflow(
    checkpoint="Counterfeit-V2.5_pruned.safetensors",
    positive="1girl",
    negative="bad",
    width=512,
    height=768,
    lora="lcm-lora-sdv1-5.safetensors",
    steps=8,
    cfg=1.5,
)
req = urllib.request.Request(
    "http://127.0.0.1:8188/prompt",
    data=json.dumps({"prompt": wf}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    r = urllib.request.urlopen(req, timeout=15)
    print("OK", r.read()[:500])
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "replace")[:3000])
