"""Coating Lab: what a model brings (an FBX from any source): its meshes, their material slots, triangles and bounds,
so a coating spec can name its slots. Positions in the file's own units as Blender reads them (metres for most FBX).

    blender -b --factory-startup -P describe_model.py -- <model.fbx> <out.json>"""
import json
import sys

import bpy

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src)
res = {"meshes": {}, "slots": {}}
for o in bpy.context.scene.objects:
    if o.type != 'MESH':
        continue
    me = o.data
    pts = [o.matrix_world @ v.co for v in me.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    res["meshes"][o.name] = {"triangles": sum(len(p.vertices) - 2 for p in me.polygons), "vertices": len(me.vertices),
                             "bounds_m": [lo, hi], "has_col": me.color_attributes.get("Col") is not None}
    for p in me.polygons:
        name = me.materials[p.material_index].name if me.materials else "-"
        res["slots"][name] = res["slots"].get(name, 0) + 1
json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
print("COATINGLAB DESCRIBE %d meshes, slots %s" % (len(res["meshes"]), sorted(res["slots"])))
