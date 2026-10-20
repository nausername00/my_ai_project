"""M9 · 序列帧 → GIF 合成器（系统 Python，需 PIL/imageio；Blender 自带 Python 无 PIL）。

用法：
  py -3 m9_make_gif.py <帧目录> <输出gif> [--fps 12] [--duration_ms 0]

与 m9_bpy_render.py --animate N 配套：把 m9_frames/ 下的 m9_0000.png..m9_%04d.png
按帧序合成循环 GIF（无 ffmpeg 依赖）。
"""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="序列帧合成 GIF（PIL/imageio）")
    parser.add_argument("frames_dir", help="PNG 序列目录（m9_0000.png 命名）")
    parser.add_argument("out_gif", help="输出 GIF 路径")
    parser.add_argument("--fps", type=int, default=12, help="帧率（默认 12）")
    parser.add_argument("--duration-ms", type=int, default=0, help="每帧时长毫秒（默认由 fps 推导）")
    args = parser.parse_args()

    frames = sorted(
        p for p in os.listdir(args.frames_dir)
        if p.startswith("m9_") and p.endswith(".png")
    )
    if not frames:
        print(f"[M9GIF] no m9_*.png frames under {args.frames_dir}", file=sys.stderr)
        return 1

    try:
        from PIL import Image
    except ImportError:
        try:
            import imageio.v2 as imageio
        except ImportError:
            print("[M9GIF] need PIL or imageio", file=sys.stderr)
            return 2
        images = [imageio.imread(os.path.join(args.frames_dir, f)) for f in frames]
        duration_ms = args.duration_ms or max(50, int(1000 / args.fps))
        imageio.mimsave(args.out_gif, images, duration=duration_ms, loop=0)
    else:
        images = [Image.open(os.path.join(args.frames_dir, f)).convert("RGB") for f in frames]
        duration_ms = args.duration_ms or max(50, int(1000 / args.fps))
        images[0].save(
            args.out_gif,
            save_all=True,
            append_images=images[1:],
            duration=duration_ms,
            loop=0,
        )

    print(f"[M9GIF] {len(frames)} frames -> {args.out_gif}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
