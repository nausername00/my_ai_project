"""ComfyUI 本地生成客户端（K1）。

职责：向本地 ComfyUI（默认 http://127.0.0.1:8188）提交文生图工作流、
轮询执行结果、取回输出图片。零新依赖（仅标准库 urllib）。
K1 阶段只做“生成立绘底图”，透明化由 rembg 在 portrait_pipeline 中完成。

边界：
- 只连接本机 ComfyUI，不允许远程地址；base_url 非 127.0.0.1/localhost 时直接拒绝。
- 提交前不校验提示词内容为“安全”；提示词由 portrait_pipeline 组装并在
  用户确认特征表后才会提交。
- 所有结果图片仅来自本地 ComfyUI 输出目录，不回传任何数据。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class ComfyUIError(RuntimeError):
    """ComfyUI 调用失败（未启动 / 执行失败 / 超时）。"""


def _assert_local(base_url: str) -> tuple[str, int]:
    from urllib.parse import urlsplit

    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ComfyUIError(f"只允许连接本机 ComfyUI，拒绝远程地址：{base_url}")
    scheme = parts.scheme or "http"
    if scheme not in {"http", "https"}:
        raise ComfyUIError(f"不支持的协议：{scheme}")
    port = parts.port or (443 if scheme == "https" else 8188)
    return f"{scheme}://{host}:{port}", port


class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 15.0) -> None:
        self.base_url, _ = _assert_local(base_url)
        self.timeout = timeout

    def _request_json(self, method: str, path: str, payload: Any = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            raise ComfyUIError(
                f"ComfyUI 拒绝了请求（HTTP {error.code}）：{body[:800]}"
            ) from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            raise ComfyUIError(
                f"无法连接本机 ComfyUI（{reason}）。请先启动 ComfyUI（run_nvidia_gpu.bat），"
                "确认 http://127.0.0.1:8188 可访问后再试。"
            ) from error
        except json.JSONDecodeError as error:
            raise ComfyUIError(f"ComfyUI 返回了无法解析的响应：{error}") from error

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """提交工作流，返回 prompt_id。"""
        result = self._request_json("POST", "/prompt", {"prompt": workflow})
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"ComfyUI 未返回 prompt_id：{result}")
        return prompt_id

    def wait_prompt(
        self, prompt_id: str, timeout_seconds: float = 300.0, poll_interval: float = 1.0
    ) -> dict[str, Any]:
        """轮询 /history 直到该 prompt 完成；返回 history 条目。超时抛错。"""
        deadline = time.monotonic() + timeout_seconds
        last_status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            history = self._request_json("GET", "/history")
            entry = history.get(prompt_id)
            if entry is not None:
                last_status = entry
                status = entry.get("status", {})
                if status.get("completed") or status.get("status_str") == "success":
                    return entry
                if status.get("status_str") in {"error", "failed"}:
                    raise ComfyUIError(f"ComfyUI 执行失败：{json.dumps(status, ensure_ascii=False)}")
            time.sleep(poll_interval)
        raise ComfyUIError(
            f"ComfyUI 执行超过 {int(timeout_seconds)} 秒未完成（prompt_id={prompt_id[:8]}）。"
        )

    def output_images(self, entry: dict[str, Any]) -> list[dict[str, str]]:
        """从 history 条目提取输出图片引用列表。"""
        images: list[dict[str, str]] = []
        for node_output in (entry.get("outputs") or {}).values():
            for image in node_output.get("images", []):
                if image.get("type") == "output":
                    images.append(
                        {
                            "filename": image["filename"],
                            "subfolder": image.get("subfolder", ""),
                            "type": image.get("type", "output"),
                        }
                    )
        return images

    def fetch_image(self, ref: dict[str, str]) -> bytes:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "filename": ref["filename"],
                "subfolder": ref.get("subfolder", ""),
                "type": ref.get("type", "output"),
            }
        )
        url = f"{self.base_url}/view?{query}"
        request = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            raise ComfyUIError(f"取回输出图片失败（{reason}）：{ref}") from error

    def generate(
        self,
        workflow: dict[str, Any],
        timeout_seconds: float = 300.0,
    ) -> list[dict[str, str]]:
        """提交并等待；返回输出图片引用。"""
        prompt_id = self.queue_prompt(workflow)
        entry = self.wait_prompt(prompt_id, timeout_seconds=timeout_seconds)
        return self.output_images(entry)


def make_txt2img_workflow(
    *,
    checkpoint: str,
    positive: str,
    negative: str,
    width: int = 1024,
    height: int = 1536,
    seed: int = 0,
    steps: int = 20,
    cfg: float = 7.0,
    sampler: str = "euler_ancestral",
    scheduler: str = "normal",
    lora: str | None = None,
) -> dict[str, Any]:
    """构造 SD1.5 文生图工作流（K1 立绘底图用）。

    竖版画布：宽 1024 × 高 1536（约 2:3），符合立绘比例；人物落点由提示词
    与后续 ControlNet（K1 迭代）共同约束。
    """
    nodes: dict[str, dict[str, Any]] = {}

    def add(node_id: str, class_type: str, inputs: dict[str, Any]) -> None:
        nodes[node_id] = {"class_type": class_type, "inputs": inputs}

    add("4", "CheckpointLoaderSimple", {"ckpt_name": checkpoint})
    model_ref = ["4", 0]
    if lora:
        add("10", "LoraLoader", {
            "lora_name": lora,
            "strength_model": 1.0,
            "strength_clip": 1.0,
            "model": ["4", 0],
            "clip": ["4", 1],
        })
        model_ref = ["10", 0]
    add("6", "CLIPTextEncode", {"text": positive, "clip": [model_ref[0], 1]})
    add("7", "CLIPTextEncode", {"text": negative, "clip": [model_ref[0], 1]})
    add("3", "KSampler", {
        "seed": seed,
        "steps": steps,
        "cfg": cfg,
        "sampler_name": sampler,
        "scheduler": scheduler,
        "denoise": 1.0,
        "model": [model_ref[0], 0],
        "positive": ["6", 0],
        "negative": ["7", 0],
        "latent_image": ["5", 0],
    })
    add("5", "EmptyLatentImage", {"width": width, "height": height, "batch_size": 1})
    add("8", "VAEDecode", {"samples": ["3", 0], "vae": ["4", 2]})
    add("9", "SaveImage", {"filename_prefix": "moling_portrait", "images": ["8", 0]})
    return nodes


def make_img2img_workflow(
    *,
    checkpoint: str,
    positive: str,
    negative: str,
    input_image: str,
    seed: int = 0,
    steps: int = 20,
    cfg: float = 7.0,
    denoise: float = 0.4,
    sampler: str = "euler_ancestral",
    scheduler: str = "normal",
) -> dict[str, Any]:
    """构造 SD1.5 图生图工作流（K2 变体生成用：闭眼 / 开口等局部重绘）。

    input_image 必须是 ComfyUI 输入目录（ComfyUI/input/）内的文件名；
    denoise 越小越贴近原图（0.35–0.5 适合"改局部、保持整体"）。
    """
    nodes: dict[str, dict[str, Any]] = {}

    def add(node_id: str, class_type: str, inputs: dict[str, Any]) -> None:
        nodes[node_id] = {"class_type": class_type, "inputs": inputs}

    add("4", "CheckpointLoaderSimple", {"ckpt_name": checkpoint})
    add("11", "LoadImage", {"image": input_image})
    add("12", "VAEEncode", {"pixels": ["11", 0], "vae": ["4", 2]})
    add("6", "CLIPTextEncode", {"text": positive, "clip": ["4", 1]})
    add("7", "CLIPTextEncode", {"text": negative, "clip": ["4", 1]})
    add("3", "KSampler", {
        "seed": seed,
        "steps": steps,
        "cfg": cfg,
        "sampler_name": sampler,
        "scheduler": scheduler,
        "denoise": denoise,
        "model": ["4", 0],
        "positive": ["6", 0],
        "negative": ["7", 0],
        "latent_image": ["12", 0],
    })
    add("8", "VAEDecode", {"samples": ["3", 0], "vae": ["4", 2]})
    add("9", "SaveImage", {"filename_prefix": "moling_variant", "images": ["8", 0]})
    return nodes
