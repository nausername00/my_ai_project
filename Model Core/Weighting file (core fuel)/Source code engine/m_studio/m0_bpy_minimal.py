"""M0 · Blender 创作工作台最小演示脚本（BPY 程序化路径）。

目标：证明墨灵能在无界面模式下驱动 Blender——
  1) 程序化建模：低多边形底座（圆柱台座 + 锥体主体 + 圆环）
  2) 双色材质（蓝白，呼应角色基准色）
  3) 相机/灯光自动布置
  4) 无界面渲染 PNG 输出（渲染快照回传）

用法（Windows）：
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" --background --python m0_bpy_minimal.py -- --out <path>
"""

import bpy
import os
import sys

# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
def _arg(name: str, default: str) -> str:
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
        for i in range(0, len(args) - 1):
            if args[i] == name:
                return args[i + 1]
    return default

OUT = _arg("--out", os.path.join(os.path.dirname(os.path.abspath(__file__)), "m0_render.png"))
RES_X, RES_Y = 960, 540

# ---------------------------------------------------------------------------
# 场景重置
# ---------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------------------------------------------
# 材质工具
# ---------------------------------------------------------------------------
def make_material(name: str, color: tuple) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.35
    return mat

blue = make_material("moling_blue", (0.18, 0.35, 0.75))
white = make_material("moling_white", (0.92, 0.94, 0.97))
gold = make_material("moling_gold", (0.85, 0.65, 0.25))

# ---------------------------------------------------------------------------
# 低模底座：圆柱台座
# ---------------------------------------------------------------------------
bpy.ops.mesh.primitive_cylinder_add(
    radius=1.6, depth=0.35, vertices=10,
    location=(0, 0, -0.35),
)
base = bpy.context.object
base.name = "m0_pedestal"
base.data.materials.append(blue)

# ---------------------------------------------------------------------------
# 主体：锥体（低多边形）
# ---------------------------------------------------------------------------
bpy.ops.mesh.primitive_cone_add(
    radius1=0.95, depth=1.9, vertices=7,
    location=(0, 0, 0.5),
)
body = bpy.context.object
body.name = "m0_body"
body.data.materials.append(white)

# ---------------------------------------------------------------------------
# 顶饰：圆环
# ---------------------------------------------------------------------------
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.38, minor_radius=0.10, major_segments=8, minor_segments=6,
    location=(0, 0, 1.5),
)
top = bpy.context.object
top.name = "m0_ring"
top.data.materials.append(gold)

# ---------------------------------------------------------------------------
# 相机：3/4 视角
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(4.2, -3.6, 2.6))
cam = bpy.context.object
cam.name = "m0_cam"
bpy.context.scene.camera = cam
cam.rotation_euler = (1.14, 0.0, 0.72)

# ---------------------------------------------------------------------------
# 灯光：主光 + 补光
# ---------------------------------------------------------------------------
bpy.ops.object.light_add(type="SUN", location=(5.0, -4.0, 6.0))
sun = bpy.context.object
sun.data.energy = 3.0
sun.rotation_euler = (0.9, 0.0, 0.6)

bpy.ops.object.light_add(type="AREA", location=(-3.5, 3.0, 3.5))
fill = bpy.context.object
fill.data.energy = 60.0

# ---------------------------------------------------------------------------
# 渲染设置 + 输出
# ---------------------------------------------------------------------------
scene = bpy.context.scene
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.filepath = OUT

# 5.x：EEVEE_NEXT 快；不可用则退回 Cycles
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    scene.render.engine = "CYCLES"

os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.render.render(write_still=True)

print(f"[M0] rendered -> {OUT}")
