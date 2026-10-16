"""M1b · 按评审团共识迭代：有机贴图应用到锥体表面 + 圆环顶饰（台座保持白色）。

评审共识（m1_collaboration_result.json）：锥体与圆环更能展示有机贴图细节；
代码伙伴建议 Base Color 直贴 + 标准 UV；先装配后贴图。本版据此调整。
"""

import bpy
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEXTURE_PATH = os.path.join(HERE, "m1_texture_organic.jpg")
OUT = os.path.join(HERE, "m1b_render.png")
RES_X, RES_Y = 960, 540


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


bpy.ops.wm.read_factory_settings(use_empty=True)

white = make_material("moling_white", (0.92, 0.94, 0.97))
textured = textured_material("moling_organic", TEXTURE_PATH)

# 台座：白色（简洁底）
bpy.ops.mesh.primitive_cylinder_add(radius=1.6, depth=0.35, vertices=10, location=(0, 0, -0.35))
base = bpy.context.object
base.name = "m1b_pedestal"
base.data.materials.append(white)

# 锥体主体：有机贴图（评审共识主位）
bpy.ops.mesh.primitive_cone_add(radius1=0.95, depth=1.9, vertices=7, location=(0, 0, 0.5))
body = bpy.context.object
body.name = "m1b_body"
body.data.materials.append(textured)

# 圆环顶饰：有机贴图（评审共识次位）
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.38, minor_radius=0.10, major_segments=8, minor_segments=6, location=(0, 0, 1.5)
)
top = bpy.context.object
top.name = "m1b_ring"
top.data.materials.append(textured)

bpy.ops.object.camera_add(location=(4.2, -3.6, 2.6))
cam = bpy.context.object
cam.name = "m1b_cam"
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
print(f"[M1b] rendered -> {OUT}")
