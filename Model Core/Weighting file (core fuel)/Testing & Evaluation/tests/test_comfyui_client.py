"""K1 ComfyUI 客户端测试：工作流结构、本机约束、请求与错误处理（不连接真实服务）。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from comfyui_client import (
    ComfyUIClient,
    ComfyUIError,
    make_img2img_workflow,
    make_txt2img_workflow,
)


class WorkflowTests(unittest.TestCase):
    def test_workflow_has_expected_nodes(self) -> None:
        workflow = make_txt2img_workflow(
            checkpoint="Counterfeit-V2.5_pruned.safetensors",
            positive="1girl, white hair, calm",
            negative="lowres, bad anatomy",
            width=1024,
            height=1536,
        )
        self.assertIn("4", workflow)
        self.assertEqual(workflow["4"]["inputs"]["ckpt_name"], "Counterfeit-V2.5_pruned.safetensors")
        self.assertEqual(workflow["5"]["inputs"]["width"], 1024)
        self.assertEqual(workflow["5"]["inputs"]["height"], 1536)
        self.assertEqual(workflow["3"]["inputs"]["cfg"], 7.0)
        self.assertEqual(workflow["9"]["class_type"], "SaveImage")

    def test_workflow_with_lora_chains_model(self) -> None:
        workflow = make_txt2img_workflow(
            checkpoint="x.safetensors",
            positive="p",
            negative="n",
            lora="lcm-lora-sdv1-5.safetensors",
        )
        self.assertIn("10", workflow)
        # LoraLoader 必须从底模接过 model/clip 输入，采样器模型指向 LoraLoader 输出
        self.assertEqual(workflow["10"]["inputs"]["model"], ["4", 0])
        self.assertEqual(workflow["10"]["inputs"]["clip"], ["4", 1])
        self.assertEqual(workflow["3"]["inputs"]["model"], ["10", 0])

    def test_remote_base_url_is_rejected(self) -> None:
        with self.assertRaises(ComfyUIError):
            ComfyUIClient("http://192.168.1.5:8188")
        with self.assertRaises(ComfyUIError):
            ComfyUIClient("https://example.com:8188")

    def test_img2img_workflow_loads_input_and_applies_denoise(self) -> None:
        workflow = make_img2img_workflow(
            checkpoint="Counterfeit-V2.5_pruned.safetensors",
            positive="same girl, closed eyes",
            negative="lowres, bad anatomy",
            input_image="moling_baseline.png",
            seed=7,
            denoise=0.4,
        )
        self.assertEqual(workflow["11"]["class_type"], "LoadImage")
        self.assertEqual(workflow["11"]["inputs"]["image"], "moling_baseline.png")
        self.assertEqual(workflow["12"]["class_type"], "VAEEncode")
        # 采样器 latent 来自 VAEEncode，而不是 EmptyLatentImage
        self.assertEqual(workflow["3"]["inputs"]["latent_image"], ["12", 0])
        self.assertEqual(workflow["3"]["inputs"]["denoise"], 0.4)
        self.assertEqual(workflow["3"]["inputs"]["seed"], 7)


class ClientBehaviorTests(unittest.TestCase):
    def test_queue_prompt_parses_prompt_id(self) -> None:
        with patch("urllib.request.urlopen") as fake:
            fake.return_value.__enter__.return_value.read.return_value = (
                b'{"prompt_id": "abc123"}'
            )
            client = ComfyUIClient()
            self.assertEqual(client.queue_prompt({}), "abc123")

    def test_connection_refused_raises_clear_error(self) -> None:
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            client = ComfyUIClient()
            with self.assertRaises(ComfyUIError) as ctx:
                client.queue_prompt({})
        self.assertIn("启动", str(ctx.exception))

    def test_wait_prompt_returns_completed_entry(self) -> None:
        entry = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {
                "9": {
                    "images": [
                        {"filename": "a.png", "subfolder": "", "type": "output"}
                    ]
                }
            },
        }
        with patch("urllib.request.urlopen") as fake:
            fake.return_value.__enter__.return_value.read.return_value = json.dumps(
                {"abc123": entry}
            ).encode("utf-8")
            client = ComfyUIClient()
            result = client.wait_prompt("abc123", poll_interval=0.01)
            self.assertEqual(result["status"]["status_str"], "success")

    def test_output_images_extracts_output_type_only(self) -> None:
        entry = {
            "outputs": {
                "9": {"images": [{"filename": "out.png", "type": "output"}]},
                "99": {"images": [{"filename": "temp.png", "type": "temp"}]},
            }
        }
        client = ComfyUIClient()
        images = client.output_images(entry)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["filename"], "out.png")

    def test_fetch_image_builds_view_request(self) -> None:
        with patch("urllib.request.urlopen") as fake:
            fake.return_value.__enter__.return_value.read.return_value = b"\x89PNG"
            client = ComfyUIClient()
            data = client.fetch_image({"filename": "a.png", "subfolder": "", "type": "output"})
            self.assertEqual(data, b"\x89PNG")
            request = fake.call_args.args[0]
            self.assertIn("/view?", request.full_url)


if __name__ == "__main__":
    unittest.main()
