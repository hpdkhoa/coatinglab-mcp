"""Coating Lab's look-dev renders, in Blender, on a baked model (its vertex colour "Col": R edge, G handling, B rub,
A dirt): each variant's finishes by slot, worn by the same formula as coat.py and an engine's material, rendered from
the gun's right, its left and a close three-quarter view of the receiver. Look-dev, not a game's view.

    blender -b <baked .blend> -P render_variants.py -- <render_job.json>
job: {"mesh": object name or null, "out": folder, "views": ["right", "left", "close"],
      "variants": {name: {slot: {Color, Metallic, Roughness, WearColor, WearMetallic, WearRoughness,
                                 EdgeWear, HandleWear, RubWear, Dirt, DirtColor}}}}"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

job = json.load(open(sys.argv[sys.argv.index("--") + 1:][0], encoding="utf-8"))
os.makedirs(job["out"], exist_ok=True)
sc = bpy.context.scene
meshes = [o for o in sc.objects if o.type == 'MESH']
mesh = bpy.data.objects.get(job.get("mesh") or "") or max(meshes, key=lambda o: len(o.data.vertices))
for o in meshes:                     # only the gun: the hand's magazine and loose attachments stay out of the pictures
    o.hide_render = o is not mesh and o.parent is not mesh.parent
for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        continue
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
if not [o for o in sc.objects if o.type == 'LIGHT']:
    for lname, energy, rot in (("Key", 3.2, (math.radians(50), 0, math.radians(-35))), ("Fill", 1.1, (math.radians(65), 0, math.radians(140))),
                               ("Rim", 2.2, (math.radians(115), 0, math.radians(-160)))):
        ld = bpy.data.lights.new(lname, 'SUN')
        ld.energy = energy
        lo_ = bpy.data.objects.new(lname, ld)
        lo_.rotation_euler = rot
        sc.collection.objects.link(lo_)
cam = sc.camera or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
if cam.name not in sc.collection.objects:
    sc.collection.objects.link(cam)
sc.camera = cam


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        if k == "operation":
            n.operation = v
        else:
            n.inputs[k].default_value = v
    return n


def math_(nt, op, a, b=None, c=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, x in enumerate((a, b, c)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def mixc(nt, a, b, fac):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = 'RGBA'
    for sock, val in ((6, a), (7, b)):
        if isinstance(val, (tuple, list)):
            n.inputs[sock].default_value = (*val, 1.0)
        else:
            nt.links.new(val, n.inputs[sock])
    nt.links.new(fac, n.inputs[0])
    return n.outputs[2]


def coat_material(name, p):
    """The formula in nodes: wear from the masks above each level's threshold, broken by grunge; dirt where occluded."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    col = nt.nodes.new("ShaderNodeVertexColor")
    col.layer_name = "Col"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(col.outputs["Color"], sep.inputs[0])
    e = math_(nt, 'SUBTRACT', 1.0, sep.outputs[0])
    w_e = math_(nt, 'SUBTRACT', e, 1.0 - p["EdgeWear"])
    w_h = math_(nt, 'SUBTRACT', sep.outputs[1], 1.0 - p["HandleWear"])
    w_r = math_(nt, 'SUBTRACT', sep.outputs[2], 1.0 - p["RubWear"])
    w0 = math_(nt, 'MAXIMUM', math_(nt, 'MAXIMUM', w_e, w_h), w_r)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0          # in object space (m): grains of about 1.5 cm, as the grunge
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    g = math_(nt, 'ADD', 0.4, math_(nt, 'MULTIPLY', noise.outputs["Fac"], 1.2))     # the grunge scales wear, never adds it
    wear = math_(nt, 'DIVIDE', math_(nt, 'MULTIPLY', math_(nt, 'MAXIMUM', w0, 0.0), g), 0.25)
    wear = math_(nt, 'MINIMUM', math_(nt, 'MAXIMUM', wear, 0.0), 1.0)
    alpha = col.outputs["Alpha"]
    dirt = math_(nt, 'MULTIPLY', math_(nt, 'MULTIPLY', alpha, p["Dirt"]), math_(nt, 'SUBTRACT', 1.0, wear))
    base = mixc(nt, tuple(p["Color"]), tuple(p["WearColor"]), wear)
    base = mixc(nt, base, tuple(p["DirtColor"]), math_(nt, 'MULTIPLY', dirt, 0.7))
    nt.links.new(base, bsdf.inputs["Base Color"])
    met = math_(nt, 'ADD', p["Metallic"], math_(nt, 'MULTIPLY', wear, p["WearMetallic"] - p["Metallic"]))
    nt.links.new(math_(nt, 'MULTIPLY', met, math_(nt, 'SUBTRACT', 1.0, dirt)), bsdf.inputs["Metallic"])
    rough = math_(nt, 'ADD', p["Roughness"], math_(nt, 'MULTIPLY', wear, p["WearRoughness"] - p["Roughness"]))
    rough = math_(nt, 'ADD', rough, math_(nt, 'MULTIPLY', dirt, math_(nt, 'SUBTRACT', 0.9, rough)))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    return m


pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
mid, span = (lo + hi) / 2, (hi - lo).length


def aim(d, size, target, persp):
    d = d.normalized()
    cam.data.type = 'PERSP' if persp else 'ORTHO'
    if persp:
        cam.data.lens = 50
        loc = target + d * size * 2.6
    else:
        cam.data.ortho_scale = size
        loc = target + d * span * 2
    f = -d
    r = f.cross(Vector((0, 0, 1)))
    r = r.normalized() if r.length > 1e-6 else Vector((0, -1, 0))
    u = (-f).cross(r).normalized()
    M = Matrix((r, u, -f)).transposed().to_4x4()
    M.translation = loc
    cam.matrix_world = M
    cam.data.clip_end = span * 10


# gun space +X is the gun's left and Blender's +X too: the right side is seen from -X
VIEWS = {"right": (Vector((-1, 0, 0.08)), (hi - lo).y * 1.08, mid, False),
         "left": (Vector((1, 0, 0.08)), (hi - lo).y * 1.08, mid, False),
         "close": (Vector((-0.8, -0.35, 0.45)), 0.16, Vector((0, 0.08, 0.0)), True)}   # the receiver, from the right rear
slots = [s.material.name for s in mesh.material_slots if s.material]
for vname, params in job["variants"].items():
    for i, ms in enumerate(mesh.material_slots):
        sname = slots[i] if i < len(slots) else None
        if sname in params:
            ms.material = coat_material("%s_%s" % (vname, sname), params[sname])
    for view in job.get("views", ["right", "left"]):
        d, size, target, persp = VIEWS[view]
        aim(d, size, target, persp)
        sc.render.filepath = os.path.join(job["out"], "%s_%s.png" % (vname, view))
        bpy.ops.render.render(write_still=True)
    print("COATINGLAB RENDER %s" % vname)
print("COATINGLAB RENDER DONE %d variants" % len(job["variants"]))
