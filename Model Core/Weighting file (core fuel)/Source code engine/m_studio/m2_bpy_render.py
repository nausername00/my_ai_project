"""M2 · 参数化渲染器：一次建模、按参数出图（直播式创作交互回路底座）。

参数（Blender 无界面，经 ``--`` 传递）：
  --target      贴图应用部件：pedestal(台座) | body(锥体) | ring(圆环) | body_ring(锥体+圆环，默认)
  --base-color  未贴图部件的底色："R,G,B"（0-1 浮点，默认台座/锥体白）
  --texture     贴图路径（默认 m1_texture_organic.jpg）
  --out         输出 PNG 路径（默认 m2_render.png）
  --res         "宽,高"（默认 960,540）

用法示例：
  blender.exe --background --python m2_bpy_render.py -- --target ring --base-color "0.25,0.3,0.45" --out m2_ring.png
"""

import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEXTURE = os.path.join(HERE, "m1_texture_organic.jpg")


def _arg(name: str, default: str) -> str:
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
        for i in range(0, len(args) - 1):
            if args[i] == name:
                return args[i + 1]
    return default


TARGET = _arg("--target", "body_ring")
BASE_COLOR_RAW = _arg("--base-color", "0.92,0.94,0.97")
TEXTURE = _arg("--texture", DEFAULT_TEXTURE)
OUT = _arg("--out", os.path.join(HERE, "m2_render.png"))
RES_RAW = _arg("--res", "960,540")

BASE_COLOR = tuple(float(x) for x in BASE_COLOR_RAW.split(","))
RES_X, RES_Y = (int(x) for x in RES_RAW.split(","))

PARTS = {"pedestal", "body", "ring", "body_ring"}
if TARGET not in PARTS:
    raise SystemExit(f"[M2] unknown --target {TARGET!r}; expected {sorted(PARTS)}")


def make_material(name: str, color: tuple) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.35
    return mat


def textured_material(name: str, image_path: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF")
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    tex.image.colorspace_settings.name = "sRGB"
    bsdf.inputs["Roughness"].default_value = 0.45
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# ---------------------------------------------------------------------------
# 建模（结构固定，仅材质分配随参数变化）
# ---------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)

plain = make_material("moling_plain", BASE_COLOR)
textured = textured_material("moling_organic", TEXTURE)


def attach(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


bpy.ops.mesh.primitive_cylinder_add(radius=1.6, depth=0.35, vertices=10, location=(0, 0, -0.35))
base = bpy.context.object
base.name = "m2_pedestal"

bpy.ops.mesh.primitive_cone_add(radius1=0.95, depth=1.9, vertices=7, location=(0, 0, 0.5))
body = bpy.context.object
body.name = "m2_body"

bpy.ops.mesh.primitive_torus_add(
    major_radius=0.38, minor_radius=0.10, major_segments=8, minor_segments=6, location=(0, 0, 1.5)
)
ring = bpy.context.object
ring.name = "m2_ring"

# 按 --target 分配材质（先装配后贴图，遵循评审共识）
attach(base, textured if TARGET == "pedestal" else plain)
attach(body, textured if TARGET in ("body", "body_ring") else plain)
attach(ring, textured if TARGET in ("ring", "body_ring") else plain)

# ---------------------------------------------------------------------------
# 相机 / 灯光 / 渲染
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(4.2, -3.6, 2.6))
cam = bpy.context.object
cam.name = "m2_cam"
bpy.context.scene.camera = cam
cam.rotation_euler = (1.14, 0.0, 0.72)

bpy.ops.object.light_add(type="SUN", location=(5.0, -4.0, 6.0))
sun = bpy.context.object
sun.data.energy = 3.0
sun.rotation_euler = (0.9, 0.0, 0.6)

bpy.ops.object.light_add(type="AREA", location=(-3.5, 3.0, 3.5))
fill = bpy.context.object
fill.data.energy = 60.0

scene = bpy.context.scene
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.filepath = OUT

try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    scene.render.engine = "CYCLES"

os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.render.render(write_still=True)
print(f"[M2] target={TARGET} base={BASE_COLOR} rendered -> {OUT}")
