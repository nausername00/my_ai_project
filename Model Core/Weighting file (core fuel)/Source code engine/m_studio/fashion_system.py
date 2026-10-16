"""A · 时装 / 换装系统：部件库 → 组合 → 保存/加载 → 渲染接驳。

时装 = 贴图（--texture）+ 应用部件（--target）；色调 = 未贴图部件底色（--base-color）。
本模块只做纯 Python 逻辑（库读取 / 组合解析 / 状态保存），
渲染实际调用 m2_bpy_render.py（Blender 无界面）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "fashion_registry.json")
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
RENDER_SCRIPT = os.path.join(HERE, "m2_bpy_render.py")


class FashionError(RuntimeError):
    """时装系统错误：未知名 / 未知色调 / 缺素材等。"""


class FashionSystem:
    def __init__(self, registry_path: str = REGISTRY_PATH, state_dir: str | None = None) -> None:
        self._registry_path = registry_path
        self._state_dir = state_dir or HERE
        self._data = self._load_registry(registry_path)
        self._state: dict = {}
        self.load_state()

    # ------------------------------------------------------------------ 库
    @staticmethod
    def _load_registry(path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("outfits"), list) or not isinstance(data.get("tones"), dict):
            raise FashionError("时装注册表格式错误：outfits/tones 缺失")
        return data

    def list_outfits(self) -> list[dict]:
        return [dict(o) for o in self._data["outfits"]]

    def list_tones(self) -> list[str]:
        return list(self._data["tones"].keys())

    def get_outfit(self, outfit_id: str) -> dict:
        for o in self._data["outfits"]:
            if o["id"] == outfit_id:
                return dict(o)
        raise FashionError(f"未知名时装: {outfit_id}")

    def get_tone(self, tone_id: str) -> list[float]:
        tone = self._data["tones"].get(tone_id)
        if tone is None:
            raise FashionError(f"未知色调: {tone_id}")
        return list(tone)

    # ------------------------------------------------------------------ 组合
    def compose(self, outfit_id: str, tone_id: str, res: str = "960,540") -> dict:
        """返回可直接喂给 m2_bpy_render.py 的参数集。"""
        outfit = self.get_outfit(outfit_id)
        tone = self.get_tone(tone_id)
        texture_path = os.path.join(HERE, outfit["texture"])
        if not os.path.isfile(texture_path):
            raise FashionError(f"时装贴图缺失: {texture_path}")
        return {
            "outfit_id": outfit_id,
            "tone_id": tone_id,
            "target": outfit["target"],
            "texture": texture_path,
            "base_color": ",".join(f"{c:.2f}" for c in tone),
            "res": res,
        }

    # ------------------------------------------------------------------ 渲染
    def render(self, params: dict, out_path: str) -> dict:
        """调用 Blender 无界面渲染，返回 {rc, log_tail, out}。"""
        args = [
            BLENDER_EXE, "--background", "--python", RENDER_SCRIPT, "--",
            "--target", params["target"],
            "--texture", params["texture"],
            "--base-color", params["base_color"],
            "--res", params["res"],
            "--out", out_path,
        ]
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-200:]
        return {"rc": proc.returncode, "log_tail": tail, "out": out_path}

    # ------------------------------------------------------------------ 状态
    def save_state(self, outfit_id: str, tone_id: str, res: str = "960,540") -> None:
        self._state = {"outfit_id": outfit_id, "tone_id": tone_id, "res": res}
        with open(os.path.join(self._state_dir, self._data["state_path"]), "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def load_state(self) -> dict:
        path = os.path.join(self._state_dir, self._data["state_path"])
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._state = json.load(f)
            except (OSError, ValueError):
                self._state = {}
        else:
            self._state = {}
        return dict(self._state)

    def current(self) -> dict:
        return dict(self._state)


def main(argv: list[str]) -> int:
    """CLI：--list | --tones | --compose <outfit> <tone> [--res WxH] | --render <outfit> <tone> --out <png>"""
    fs = FashionSystem()
    if "--list" in argv:
        print("时装库：")
        for o in fs.list_outfits():
            print(f"  - {o['id']}: {o['name']}（{o['desc']}）")
        print("色调库：", ", ".join(fs.list_tones()))
        return 0
    if "--tones" in argv:
        print(", ".join(fs.list_tones()))
        return 0
    if "--compose" in argv:
        i = argv.index("--compose")
        outfit_id, tone_id = argv[i + 1], argv[i + 2]
        res = "960,540"
        if "--res" in argv:
            res = argv[argv.index("--res") + 1]
        print(json.dumps(fs.compose(outfit_id, tone_id, res), ensure_ascii=False, indent=2))
        return 0
    if "--render" in argv:
        i = argv.index("--render")
        outfit_id, tone_id = argv[i + 1], argv[i + 2]
        out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, f"fashion_{outfit_id}_{tone_id}.png")
        res = "960,540"
        if "--res" in argv:
            res = argv[argv.index("--res") + 1]
        params = fs.compose(outfit_id, tone_id, res)
        result = fs.render(params, out)
        fs.save_state(outfit_id, tone_id, res)
        print(f"[fashion] rc={result['rc']} out={result['out']}")
        print(result["log_tail"].strip()[-300:])
        return result["rc"]
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
