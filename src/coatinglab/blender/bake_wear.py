"""Coating Lab's wear bake, in Blender: where a gun's finish wears and where dirt sits, from evidence, into the vertex
colour "Col" of every mesh of the gun (no UVs needed; every coating variant reads the same masks):
  R  edge      1 on flat ground, 0 on a sharp exposed edge (the model's own edge measure when it has one)
  G  handling  1 where hands work the gun (the grip, the support hand, the charging handle, the controls)
  B  rub       1 along the lines parts slide on (a magazine in its well, a stock on its tube)
  A  dirt      1 where it is occluded (corners, the inside of the gun) and round the muzzle and the port (carbon)
Positions are the gun's space in cm (+X left, +Y forward, +Z up), as Model Lab writes them. The main mesh (the rig's)
gives the stats; the others (attachments, sights) are baked by the same zones where they stand; a mesh that does not
stand on the gun (the hand's spare magazine at the origin) gets its edges and its dirt only.

    blender -b <model.blend | --factory-startup> -P bake_wear.py -- <job.json>
job: {"blend": path or null, "fbx": path or null, "mesh": the main object's name or null (the largest mesh),
      "out_fbx": path, "out_blend": path or null, "stats": path, "space": "modellab" or "blender_cm",
      "zones": {"contacts": [{"name", "at", "radius_cm", "weight"}], "rubs": [{"name", "from", "to", "width_cm",
                "weight"}], "carbon": [{"name", "at", "radius_cm"}]}, "loose": [names of meshes not on the gun]}"""
import json
import math
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

job = json.load(open(sys.argv[sys.argv.index("--") + 1:][0], encoding="utf-8"))
if job.get("fbx"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=job["fbx"])
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and len(o.data.polygons)
          and not o.name.startswith(("UCX_", "UBX_", "USP_", "UCP_"))]       # an engine's collision shapes are not the gun
main = bpy.data.objects.get(job.get("mesh") or "") or max(meshes, key=lambda o: len(o.data.vertices))
STEP = 0.015      # m: no edge longer than 1.5 cm (as Model Lab's own edge measure), so a flat face has vertices of its own


def prepare(ob):
    """A model from elsewhere: its transform applied (an FBX in cm comes with a 0.01 scale: the rays and the areas are
    metres here), and, when it has no edge measure of its own, its long edges split, so edge wear stays at the edge
    instead of spreading over whole faces. A rigged mesh keeps its armature; only a loose mesh is moved."""
    if ob.parent is None and ob.matrix_world != ob.matrix_world.Identity(4):
        ob.data.transform(ob.matrix_world)
        ob.matrix_world.identity()
    if ob.data.color_attributes.get("Col") is None:
        # which edges the artist shaded sharp: where the two faces' normals at a corner differ. A low-poly cylinder's
        # facets are smooth-shaded: a curve, not an edge
        me_ = ob.data
        try:
            cn = [c.vector.copy() for c in me_.corner_normals]
        except AttributeError:                        # before Blender 4.1
            me_.calc_normals_split()
            cn = [l.normal.copy() for l in me_.loops]
        at = {}
        for p in me_.polygons:
            for li in p.loop_indices:
                at[(p.index, me_.loops[li].vertex_index)] = cn[li]
        faces_of = {}
        for p in me_.polygons:
            for ek in p.edge_keys:
                faces_of.setdefault(ek, []).append(p.index)
        sharp_keys = set()
        for ek, fs in faces_of.items():
            if len(fs) == 2 and at[(fs[0], ek[0])].angle(at[(fs[1], ek[0])], 0.0) > math.radians(10):
                sharp_keys.add(ek)
        bm = bmesh.new()
        bm.from_mesh(me_)
        for e in bm.edges:
            e.smooth = tuple(sorted(v.index for v in e.verts)) not in sharp_keys
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
        for _ in range(8):
            long_edges = [e for e in bm.edges if e.calc_length() > STEP]
            if not long_edges:
                break
            bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=True)
            bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
        bm.to_mesh(ob.data)
        bm.free()


if job.get("fbx"):
    for m in meshes:
        prepare(m)
SOFT, SHARP = math.radians(20), math.radians(75)
N_RAYS, REACH = 32, 0.02
golden = math.pi * (3 - math.sqrt(5))
DIRS = []
for k in range(N_RAYS):   # cosine-weighted (an even disk lifted onto the hemisphere), as ambient occlusion is measured:
    r = math.sqrt((k + 0.5) / N_RAYS)        # a ray skimming the surface counts little, one straight out counts most
    DIRS.append(Vector((math.cos(golden * k) * r, math.sin(golden * k) * r, math.sqrt(max(0.0, 1 - r * r)))))
Z = job.get("zones", {})
CONTACTS = [(Vector(c["at"]), float(c.get("radius_cm", 4.0)), float(c.get("weight", 1.0))) for c in Z.get("contacts", [])]
RUBS = [(Vector(r["from"]), Vector(r["to"]), float(r.get("width_cm", 1.0)), float(r.get("weight", 1.0))) for r in Z.get("rubs", [])]
CARBON = [(Vector(c["at"]), float(c.get("radius_cm", 3.0))) for c in Z.get("carbon", [])]
LOOSE = set(job.get("loose", []))


def falloff(d, r):
    """1 inside 40 % of the radius, down to 0 at the radius: worn ground fades out, it has no hard line."""
    if r <= 0:
        return 0.0
    t = min(1.0, max(0.0, (d - 0.4 * r) / (0.6 * r)))
    return 1.0 - t * t * (3 - 2 * t)


def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-9)))
    return (p - (a + ab * t)).length


def bake(mesh, zones_on):
    me = mesh.data
    W = mesh.matrix_world
    modellab = job.get("space", "modellab") == "modellab"

    def gun(co):
        p = W @ co
        return Vector((p.x * 100.0, -p.y * 100.0, p.z * 100.0)) if modellab else p

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    shaded = bool(job.get("fbx"))     # a model from elsewhere: its shading says which edges are edges (prepare)
    convex = []
    for v in bm.verts:
        hi = max((e.calc_face_angle_signed(0.0) for e in v.link_edges if len(e.link_faces) == 2 and not (shaded and e.smooth)), default=0.0)
        convex.append(min(1.0, max(0.0, (hi - SOFT) / (SHARP - SOFT))))
    bm.free()
    col = me.color_attributes.get("Col")
    had_edge = col is not None and col.domain == 'POINT'
    if not had_edge:
        if col is not None:
            me.color_attributes.remove(col)
        col = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    edge = [col.data[i].color[0] if had_edge else 1.0 - convex[i] for i in range(len(me.vertices))]
    # how exposed each vertex is: the share of short rays (2 cm, cosine-weighted) out of its surface that meet nothing.
    # Wear starts on prominent edges and corners (the collectors' guides): a sharp edge inside the gun or in a corner
    # is not reached; what the rays cannot leave is where grime sits. The rays meet this mesh and, for a part on the
    # gun, the gun's main mesh too
    trees = [BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])]
    if mesh is not main and zones_on:
        inv = W.inverted() @ main.matrix_world
        trees.append(BVHTree.FromPolygons([inv @ v.co for v in main.data.vertices], [tuple(p.vertices) for p in main.data.polygons]))
    exposure = []
    for v in me.vertices:
        nrm = v.normal.normalized()
        q = nrm.to_track_quat('Z', 'Y')
        o = v.co + nrm * 0.0005
        free = sum(1 for d in DIRS if all(t.ray_cast(o, q @ d, REACH)[0] is None for t in trees))
        exposure.append(free / N_RAYS)
    occl = [1.0 - x for x in exposure]
    edge = [1.0 - (1.0 - edge[i]) * exposure[i] ** 2 for i in range(len(me.vertices))]   # a half-hidden edge wears little
    G, B, A = [], [], []
    for i, v in enumerate(me.vertices):
        p = gun(v.co)
        exposed = exposure[i] ** 2                       # a hand or a part does not reach into a corner
        h = max((w * falloff((p - c).length, r) for c, r, w in CONTACTS), default=0.0) if zones_on else 0.0
        G.append(min(1.0, h * exposed * (0.6 + 0.4 * (1.0 - edge[i]))))
        rb = max((w * falloff(seg_dist(p, a, b), wd) for a, b, wd, w in RUBS), default=0.0) if zones_on else 0.0
        B.append(min(1.0, rb * exposed))
        cb = max((falloff((p - c).length, r) for c, r in CARBON), default=0.0) if zones_on else 0.0
        A.append(min(1.0, max(0.9 * occl[i], cb)))
    for i in range(len(me.vertices)):
        col.data[i].color = (edge[i], G[i], B[i], A[i])
    me.color_attributes.active_color = col
    try:
        me.color_attributes.render_color_index = me.color_attributes.find("Col")
    except AttributeError:
        pass
    return edge, G, B, A, occl, had_edge


baked = {}
for m in meshes:
    on = m.name not in LOOSE and not (m is not main and m.name.startswith("SM_") and m.name.endswith("_Magazine"))
    baked[m.name] = bake(m, on)
edge, G, B, A, occl, had_edge = baked[main.name]
me = main.data

# the stats of the main mesh: by material slot, each channel's area-weighted mean and the share over 0.5
area = [0.0] * len(me.vertices)
slot_of_v = ["-"] * len(me.vertices)
for poly in me.polygons:
    s = me.materials[poly.material_index].name if me.materials else "-"
    for vi in poly.vertices:
        area[vi] += poly.area / len(poly.vertices)
        slot_of_v[vi] = s
stats = {}
for i in range(len(me.vertices)):
    st = stats.setdefault(slot_of_v[i], {"area_cm2": 0.0, **{k: [0.0, 0.0] for k in ("edge", "handling", "rub", "dirt", "cavity")}})
    a = area[i] * 1e4
    st["area_cm2"] += a
    for k, v in (("edge", 1.0 - edge[i]), ("handling", G[i]), ("rub", B[i]), ("dirt", A[i]), ("cavity", occl[i])):
        st[k][0] += v * a
        st[k][1] += a if v > 0.5 else 0.0
out = {}
for s, st in stats.items():
    tot = max(st["area_cm2"], 1e-9)
    out[s] = {"area_cm2": round(st["area_cm2"], 1)}
    for k in ("edge", "handling", "rub", "dirt", "cavity"):
        out[s][k] = {"mean": round(st[k][0] / tot, 4), "share_over_half": round(st[k][1] / tot, 4)}
sample = [[round(1.0 - edge[i], 3), round(G[i], 3), round(B[i], 3), round(A[i], 3), round(occl[i], 3), round(area[i] * 1e4, 4), slot_of_v[i]]
          for i in range(len(me.vertices))]
json.dump({"mesh": main.name, "vertices": len(me.vertices), "kept_edge": had_edge, "slots": out, "per_vertex": sample,
           "also_baked": sorted(n for n in baked if n != main.name)}, open(job["stats"], "w", encoding="utf-8"))

if job.get("out_blend"):
    bpy.ops.wm.save_as_mainfile(filepath=job["out_blend"])
if job.get("out_fbx"):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    main.select_set(True)
    arm = main.parent if main.parent and main.parent.type == 'ARMATURE' else None
    if arm:
        arm.select_set(True)
    bpy.ops.export_scene.fbx(filepath=job["out_fbx"], use_selection=True, object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False,
                             bake_anim=False, mesh_smooth_type='FACE', colors_type='LINEAR')
print("COATINGLAB BAKE %s: %d vertices, edge kept %s, slots %s, also %d meshes" % (main.name, len(me.vertices), had_edge, sorted(out), len(baked) - 1))
