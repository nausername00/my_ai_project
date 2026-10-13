"""补全狐仙花嫁 model3.json 的 Motions 与 Expressions 注册（项目副本）。

原文件 Motions 为空、Expressions 只注册 3 个；把 17 个表情、2 个动画全部注册，
供 pixi-live2d-display 运行时按名调用。表情名称剥离数字前缀（如 "1星星眼" -> "星星眼"）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MODEL3 = Path(r"D:\Coding\code program\test\This is mine\my_ai_project\Model Core\Weighting file (core fuel)\Character\狐仙花嫁\狐仙花嫁\狐仙花嫁.model3.json")


def clean_expression_name(raw_name: str) -> str:
    """去掉文件名的 .exp3.json 后缀与数字前缀，保留语义名。"""
    return re.sub(r"^\d+", "", raw_name.removesuffix(".exp3.json"))


def main() -> int:
    data = json.loads(MODEL3.read_text(encoding="utf-8"))
    model_dir = MODEL3.parent

    motions = {}
    for m in sorted(model_dir.glob("*.motion3.json")):
        name = m.name.removesuffix(".motion3.json")
        group = "Idle" if "待机" in name else "Sleep"
        motions.setdefault(group, []).append({"File": m.name, "Name": name})
    data["FileReferences"]["Motions"] = motions

    expressions = []
    for e in sorted(model_dir.glob("*.exp3.json")):
        expressions.append({"Name": clean_expression_name(e.name), "File": e.name})
    data["FileReferences"]["Expressions"] = expressions

    MODEL3.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    groups = {g: len(v) for g, v in motions.items()}
    print(f"Motions 注册: {groups}", flush=True)
    print(f"Expressions 注册: {len(expressions)} 个", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
