"""M9 · 3D 创作深化：扩展形体 + 混合材质 + 动画序列帧（Blender 端）。

在 M2 参数化渲染器基础上深化三处（对应 SKILL_CARD 已知限制）：
1. 新形体：--target 扩展 gem(宝石) / star(星) / full(全装配场景)；
2. 混合材质：--blend 0..1 把贴图与底色按系数融合（MixRGB），不再纯直贴；
3. 动画：--animate <帧数> 绕 Z 旋转 + 上下漂浮，输出 PNG 序列到 --out-dir，
   供 m9_make_gif.py 合成 GIF（Blender 自带 Python 无 PIL，合成放系统 py）。

参数（Blender 经 ``--`` 传递）：
  --target      pedestal|body|ring|body_ring|gem|star|full（默认 body_ring）
  --base-color  "R,G,B" 0-1 浮点（默认 0.92,0.94,0.97）
  --texture     贴图路径（默认 m1_texture_organic.jpg）
  --blend       贴图与底色混合系数 0..1（默认 0.0 = 纯贴图；1.0 = 纯底色）
  --out         静帧输出 PNG 路径（默认 m9_still.png；--animate 时忽略）
  --out-dir     --animate 时序列帧输出目录（默认 m9_frames/）
  --res         "宽,高"（默认 960,540；动画建议 640,360 提速）
  --animate     帧数 N>0 时渲染 N 帧动画序列；缺省 0 = 静帧

用法示例：
  blender.exe --background --python m9_bpy_render.py -- --target gem --blend 0.35 --out m9_gem.png
  blender.exe --background --python m9_bpy_render.py -- --target full --animate 24 --res "640,360" --out-dir m9_frames
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
BLEND = float(_arg("--blend", "0.0"))
OUT = _arg("--out", os.path.join(HERE, "m9_still.png"))
OUT_DIR = _arg("--out-dir", os.path.join(HERE, "m9_frames"))
RES_RAW = _arg("--res", "960,540")
ANIMATE = int(_arg("--animate", "0"))

BASE_COLOR = tuple(float(x) for x in BASE_COLOR_RAW.split(","))
RES_X, RES_Y = (int(x) for x in RES_RAW.split(","))

TARGETS = {"pedestal", "body", "ring", "body_ring", "gem", "star", "full"}
if TARGET not in TARGETS:
    raise SystemExit(f"[M9] unknown --target {TARGET!r}; expected {sorted(TARGETS)}")
if not (0.0 <= BLEND <= 1.0):
    raise SystemExit("[M9] --blend must be within 0..1")


def make_material(name: str, color: tuple) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.35
    return mat


def mixed_material(name: str, image_path: str, color: tuple, blend: float) -> bpy.types.Material:
    """贴图与底色按系数混合（解决 M2 纯直贴限制）。blend=0 纯贴图，1 纯底色。"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF")
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    tex.image.colorspace_settings.name = "sRGB"
    mix = tree.nodes.new("ShaderNodeMixRGB")
    mix.inputs["Fac"].default_value = blend
    mix.inputs["Color1"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    tree.links.new(tex.outputs["Color"], mix.inputs["Color2"])
    tree.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# ---------------------------------------------------------------------------
# 建模（target 决定装配；材质按目标分配）
# ---------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)

plain = make_material("moling_plain", BASE_COLOR)
textured = mixed_material("moling_mixed", TEXTURE, BASE_COLOR, BLEND)


def attach(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def add_cylinder(name: str, radius: float, depth: float, z: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=10, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    return obj


def add_cone(name: str, radius: float, depth: float, z: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(radius1=radius, depth=depth, vertices=7, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    return obj


def add_torus(name: str, major: float, minor: float, z: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor, major_segments=8, minor_segments=6,
        location=(0, 0, z),
    )
    obj = bpy.context.object
    obj.name = name
    return obj


def add_gem(name: str, z: float) -> bpy.types.Object:
    """程序化宝石：六棱锥上下对拼 + 缩放成宝石轮廓。"""
    bpy.ops.mesh.primitive_cone_add(radius1=0.55, depth=0.9, vertices=6, location=(0, 0, z + 0.45))
    crown = bpy.context.object
    crown.name = f"{name}_crown"
    crown.scale = (1.0, 1.0, 1.15)
    bpy.ops.mesh.primitive_cone_add(radius1=0.55, depth=0.9, vertices=6, location=(0, 0, z - 0.45))
    pavilion = bpy.context.object
    pavilion.name = f"{name}_pavilion"
    pavilion.scale = (1.0, 1.0, 1.15)
    pavilion.rotation_euler = (3.14159, 0.0, 0.0)
    return crown


def add_star(name: str, z: float) -> bpy.types.Object:
    """程序化五角星：圆环 + 顶点缩放成星形轮廓后挤出。"""
    bpy.ops.mesh.primitive_cylinder_add(
        radius=1.0, depth=0.12, vertices=5, location=(0, 0, z)
    )
    star = bpy.context.object
    star.name = name
    # 顶点沿径向按 0.45 系数缩放（奇偶交替）→ 五角星轮廓
    mesh = star.data
    for v in mesh.vertices:
        import math
        angle = math.atan2(v.co.y, v.co.x)
        idx_odd = int(round(angle / (math.pi * 2 / 5))) % 2
        # 用角位置粗略判别：落在奇数扇区的顶点内缩
        half = math.pi / 5
        sector = (angle % (math.pi * 2 / 5)) - half
        if abs(sector) < half * 0.35:
            v.co.x *= 0.45
            v.co.y *= 0.45
    mesh.update()
    return star


parts: dict[str, bpy.types.Object] = {}
if TARGET in ("pedestal", "body_ring", "full", "gem", "star"):
    parts["pedestal"] = add_cylinder("m9_pedestal", 1.6, 0.35, -0.35)
if TARGET in ("body", "body_ring", "full"):
    parts["body"] = add_cone("m9_body", 0.95, 1.9, 0.5)
if TARGET in ("ring", "body_ring", "full"):
    parts["ring"] = add_torus("m9_ring", 0.38, 0.10, 1.5)
if TARGET in ("gem", "full"):
    gem_z = 0.95 if TARGET == "gem" else 2.2  # 单独展示立在台座上；full 时置于锥体+圆环之上
    parts["gem"] = add_gem("m9_gem", gem_z)
if TARGET in ("star", "full"):
    star_z = 1.55 if TARGET == "star" else 3.0
    parts["star"] = add_star("m9_star", star_z)

# 材质分配：台座/锥体/圆环/星 → 混合材质（贴图）；宝石 → 纯底色（高光感）
for name in ("pedestal", "body", "ring", "star"):
    if name in parts:
        attach(parts[name], textured)
if "gem" in parts:
    attach(parts["gem"], plain)
    parts["gem"].data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.12
    parts["gem"].data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.4

# ---------------------------------------------------------------------------
# 相机 / 灯光 / 渲染
# ---------------------------------------------------------------------------
bpy.ops.object.camera_add(location=(4.2, -3.6, 2.6))
cam = bpy.context.object
cam.name = "m9_cam"
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
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    scene.render.engine = "CYCLES"

os.makedirs(os.path.dirname(OUT), exist_ok=True)


def render_still() -> None:
    scene.render.filepath = OUT
    bpy.ops.render.render(write_still=True)
    print(f"[M9] still target={TARGET} blend={BLEND} rendered -> {OUT}")


def render_animation(frames: int) -> str:
    """绕 Z 旋转 + 上下漂浮；渲染 frames 张 PNG 序列，返回目录。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    rotors = [obj for obj in bpy.data.objects if obj.name.startswith("m9_") and obj.type == "MESH"]
    for f in range(frames):
        t = f / max(frames - 1, 1)
        for obj in rotors:
            obj.rotation_euler = (0.0, 0.0, t * 6.28318)
            obj.location.z += 0.12 * (0.5 - abs(t - 0.5))  # 漂浮起伏
        frame_path = os.path.join(OUT_DIR, f"m9_{f:04d}.png")
        scene.render.filepath = frame_path
        bpy.ops.render.render(write_still=True)
    print(f"[M9] anim target={TARGET} frames={frames} -> {OUT_DIR}")
    return OUT_DIR


if ANIMATE > 0:
    render_animation(ANIMATE)
else:
    render_still()
