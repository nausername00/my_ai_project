"""时装 / 换装系统 v2：部件库 → 组合 → 保存/加载 → 渲染接驳（含优化 1/3/4）。

优化清单：
  1. 渲染缓存：参数哈希，同 outfit+tone+res 组合命中缓存直接回图，不重渲 Blender。
  3. 反馈可见化：每次渲染返回 stats（cache_hit / render_ms / 消耗等级），并写 ops_log.json。
  4. 异步后台：render_async() 后台渲染 + wait_render() 轮询，不阻塞主流程。

时装 = 贴图（--texture）+ 应用部件（--target）；色调 = 未贴图部件底色（--base-color）。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from m_studio.lock_utils import FileLock

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "fashion_registry.json")
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
RENDER_SCRIPT = os.path.join(HERE, "m2_bpy_render.py")
DEFAULT_CACHE_DIR = os.path.join(HERE, ".render_cache")
OPS_LOG_PATH = os.path.join(HERE, "ops_log.json")


class FashionError(RuntimeError):
    """时装系统错误：未知名 / 未知色调 / 缺素材等。"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FashionSystem:
    def __init__(self, registry_path: str = REGISTRY_PATH, state_dir: str | None = None,
                 cache_dir: str | None = None) -> None:
        self._registry_path = registry_path
        self._state_dir = state_dir or HERE
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
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

    # ------------------------------------------------------------------ 缓存（优化 1）
    def cache_key(self, params: dict) -> str:
        raw = f"{params['target']}|{os.path.basename(params['texture'])}|{params['base_color']}|{params['res']}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def cache_path(self, key: str) -> str:
        return os.path.join(self._cache_dir, f"{key}.png")

    def cache_hit(self, params: dict) -> str | None:
        """命中返回缓存 PNG 路径，未命中返回 None。"""
        path = self.cache_path(self.cache_key(params))
        return path if os.path.isfile(path) else None

    # ------------------------------------------------------------------ 渲染（优化 3：返回 stats）
    def _run_blender(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def render(self, params: dict, out_path: str | None = None,
               use_cache: bool = True) -> dict:
        """渲染（可命中缓存）。返回 {rc, cache_hit, render_ms, out, log_tail, cost}。"""
        started = time.monotonic()
        cached = self.cache_hit(params) if use_cache else None
        if cached is not None:
            self._log_op(params, cache_hit=True, render_ms=0)
            return {"rc": 0, "cache_hit": True, "render_ms": 0,
                    "out": cached, "log_tail": "[cache hit]", "cost": "轻"}

        out = out_path or os.path.join(HERE, f"fashion_{params['outfit_id']}_{params['tone_id']}.png")
        args = [
            BLENDER_EXE, "--background", "--python", RENDER_SCRIPT, "--",
            "--target", params["target"],
            "--texture", params["texture"],
            "--base-color", params["base_color"],
            "--res", params["res"],
            "--out", out,
        ]
        proc = self._run_blender(args)
        render_ms = int((time.monotonic() - started) * 1000)
        if use_cache and proc.returncode == 0 and os.path.isfile(out):
            self._store_cache(params, out)
        self._log_op(params, cache_hit=False, render_ms=render_ms)
        tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-200:]
        return {"rc": proc.returncode, "cache_hit": False, "render_ms": render_ms,
                "out": out, "log_tail": tail, "cost": "重" if proc.returncode == 0 else "失败"}

    def _store_cache(self, params: dict, out: str) -> None:
        os.makedirs(self._cache_dir, exist_ok=True)
        target = self.cache_path(self.cache_key(params))
        if os.path.abspath(out) != os.path.abspath(target):
            # 复制而非移动：调用方指定的 out 保留为本次交付产物
            import shutil
            shutil.copyfile(out, target)

    # ------------------------------------------------------------------ 异步（优化 4）
    def render_async(self, params: dict, out_path: str | None = None) -> dict:
        """后台渲染，立即返回任务句柄；wait_render() 轮询取结果。"""
        out = out_path or os.path.join(HERE, f"fashion_{params['outfit_id']}_{params['tone_id']}.png")
        args = [
            BLENDER_EXE, "--background", "--python", RENDER_SCRIPT, "--",
            "--target", params["target"],
            "--texture", params["texture"],
            "--base-color", params["base_color"],
            "--res", params["res"],
            "--out", out,
        ]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
        return {"proc": proc, "out": out, "params": params, "started": _utc_now_iso()}

    @staticmethod
    def wait_render(task: dict, timeout: float = 180.0) -> dict:
        """轮询后台渲染任务直至完成，返回与 render() 同构的结果。"""
        proc: subprocess.Popen = task["proc"]
        started = time.monotonic()
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {"rc": -1, "cache_hit": False, "render_ms": int((time.monotonic() - started) * 1000),
                    "out": task["out"], "log_tail": "[async timeout]",
                    "cost": "失败", "error": "渲染超时已终止"}
        render_ms = int((time.monotonic() - started) * 1000)
        tail = (stdout or "")[-400:] + (stderr or "")[-200:]
        return {"rc": proc.returncode, "cache_hit": False, "render_ms": render_ms,
                "out": task["out"], "log_tail": tail,
                "cost": "重" if proc.returncode == 0 else "失败"}

    # ------------------------------------------------------------------ 操作日志（优化 3）
    def _log_op(self, params: dict, cache_hit: bool, render_ms: int) -> None:
        entry = {
            "ts": _utc_now_iso(),
            "outfit_id": params["outfit_id"],
            "tone_id": params["tone_id"],
            "target": params["target"],
            "cache_hit": cache_hit,
            "render_ms": render_ms,
            "cost": "轻" if cache_hit else "重",
        }
        logs: list[dict] = []
        if os.path.isfile(OPS_LOG_PATH):
            try:
                with open(OPS_LOG_PATH, encoding="utf-8") as f:
                    logs = json.load(f)
            except (OSError, ValueError):
                logs = []
        logs.append(entry)
        with FileLock(OPS_LOG_PATH):
            with open(OPS_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(logs[-200:], f, ensure_ascii=False, indent=2)

    def ops_log(self, limit: int = 20) -> list[dict]:
        if not os.path.isfile(OPS_LOG_PATH):
            return []
        with open(OPS_LOG_PATH, encoding="utf-8") as f:
            logs = json.load(f)
        return logs[-limit:]

    # ------------------------------------------------------------------ 状态
    def save_state(self, outfit_id: str, tone_id: str, res: str = "960,540") -> None:
        self._state = {"outfit_id": outfit_id, "tone_id": tone_id, "res": res}
        state_path = os.path.join(self._state_dir, self._data["state_path"])
        with FileLock(state_path):
            with open(state_path, "w", encoding="utf-8") as f:
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
    """CLI：--list | --tones | --compose <o> <t> | --render <o> <t> [--async] [--no-cache] [--out png] | --log"""
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
    if "--log" in argv:
        for entry in fs.ops_log():
            print(f"  {entry['ts']} {entry['outfit_id']}/{entry['tone_id']} "
                  f"cache={entry['cache_hit']} {entry['render_ms']}ms cost={entry['cost']}")
        return 0
    if "--render" in argv:
        i = argv.index("--render")
        outfit_id, tone_id = argv[i + 1], argv[i + 2]
        out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, f"fashion_{outfit_id}_{tone_id}.png")
        res = "960,540"
        if "--res" in argv:
            res = argv[argv.index("--res") + 1]
        params = fs.compose(outfit_id, tone_id, res)
        if "--async" in argv:
            task = fs.render_async(params, out)
            print(f"[fashion] async task started -> {task['out']}")
            result = fs.wait_render(task)
        else:
            result = fs.render(params, out, use_cache="--no-cache" not in argv)
        fs.save_state(outfit_id, tone_id, res)
        print(f"[fashion] rc={result['rc']} cache_hit={result['cache_hit']} "
              f"{result['render_ms']}ms cost={result['cost']} out={result['out']}")
        if result.get("error"):
            print(result["error"])
        return result["rc"]
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
