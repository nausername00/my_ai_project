"""狐仙花嫁 Live2D 模型接入验证：引用完整性 + 部件/参数/表情/动画统计。

验证项：
1. model3.json 引用的 Moc / Textures / Physics / DisplayInfo / Expressions 全部存在
2. cdi3.json 部件清单统计（K2 部件库替代品）
3. 表情 exp3 / 动画 motion3 / 物理文件齐全性
4. 纹理图集尺寸与透明通道
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MODEL_DIR = Path(r"D:\Coding\code program\test\This is mine\my_ai_project\Model Core\Weighting file (core fuel)\Character\狐仙花嫁")
MODEL_SUB = MODEL_DIR / "狐仙花嫁"


def main() -> int:
    model3 = json.loads((MODEL_SUB / "狐仙花嫁.model3.json").read_text(encoding="utf-8"))
    refs = model3["FileReferences"]
    print("== model3.json 引用检查 ==", flush=True)
    ok = True
    for key, path in refs.items():
        if key == "Expressions":
            for entry in path:
                p = MODEL_SUB / entry["File"]
                exists = p.exists()
                print(f"  Expressions: {entry['File']} -> {'OK' if exists else '缺失!'}", flush=True)
                ok &= exists
        elif isinstance(path, str):
            p = MODEL_SUB / path
            exists = p.exists()
            size_mb = p.stat().st_size / 1e6 if exists else 0
            print(f"  {key}: {path} -> {'OK' if exists else '缺失!'} ({size_mb:.1f}MB)", flush=True)
            ok &= exists
        elif isinstance(path, list):
            for sub in path:
                p = MODEL_SUB / sub
                exists = p.exists()
                print(f"  {key}[{len(sub)}]: {sub} -> {'OK' if exists else '缺失!'}", flush=True)
                ok &= exists

    # cdi3 部件清单
    cdi = json.loads((MODEL_SUB / "狐仙花嫁.cdi3.json").read_text(encoding="utf-8"))
    params = cdi.get("Parameters", [])
    parts = cdi.get("Parts", [])
    print(f"\n== cdi3 画布信息 == 参数 {len(params)} 个 / 部件 {len(parts)} 个", flush=True)
    print("参数样例:", [p.get("Name") for p in params[:8]], flush=True)
    print("部件样例:", [p.get("Id") for p in parts[:10]], flush=True)

    # 表情 / 动画 / 物理
    exp_files = sorted(MODEL_SUB.glob("*.exp3.json"))
    motion_files = sorted(MODEL_SUB.glob("*.motion3.json"))
    phys_files = sorted(MODEL_SUB.glob("*.physics3.json"))
    print(f"\n== 资产统计 == 表情 {len(exp_files)} 动画 {len(motion_files)} 物理 {len(phys_files)}", flush=True)
    print("表情:", [f.name for f in exp_files], flush=True)
    print("动画:", [f.name for f in motion_files], flush=True)

    # 纹理图集
    from PIL import Image
    tex_dir = MODEL_SUB / "狐仙花嫁.4096"
    texs = sorted(tex_dir.glob("texture_*.png"))
    print(f"\n== 纹理图集 == {len(texs)} 张", flush=True)
    for t in texs:
        img = Image.open(t)
        alpha = img.getchannel("A")
        bbox = alpha.getbbox()
        print(f"  {t.name}: {img.size} mode={img.mode} 内容bbox={bbox}", flush=True)

    print(f"\n=== 总体: {'通过（引用完整）' if ok else '有缺失，需补齐'} ===", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
