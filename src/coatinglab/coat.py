"""Coating a model: bake its wear masks once (blender/bake_wear.py), then for each variant the finishes and the wear
level become surface values the same way everywhere: these checks, the look-dev renders (blender/render_variants.py)
and an engine's material (engine_params; ToangTown's M_GunCoat). The formula, per vertex:

  e = 1 - R (edge), h = G (handling), r = B (rub), d = A (dirt); levels Le, Lh, Lr, Ld from the wear level
  w0   = max(e - (1 - Le), h - (1 - Lh), r - (1 - Lr))      a level is how weak a mask already wears through
  wear = saturate(w0 * (0.4 + 1.2 * g) / 0.25)              g: a grunge texture (0.5 where there is none): it
                                                            breaks up wear that is there, it never makes wear
  dirt = d * Ld * (1 - wear)
  colour    = lerp(lerp(finish, worn, wear), DIRT, 0.7 * dirt)
  metallic  = lerp(lerp(finish, worn, wear), 0, dirt)
  roughness = lerp(lerp(finish, worn, wear), 0.9, dirt)"""
import json
import shutil
import time
from pathlib import Path

from . import library as L
from . import spec as S
from . import zones as Z
from .config import out, run_blender

DIRT = (0.020, 0.018, 0.015)      # linear: carbon and grime, near black (an estimate: soot reflects about 2 to 4 %)
# the share of a slot's area worn through at each level: estimates of a rifle's look (new from the box, an issued
# rifle a few years in service, a worn one, an abused one); the checks hold a variant's whole gun to its band
WORN_BANDS = {"new": (0.0, 0.01), "issued": (0.003, 0.06), "worn": (0.02, 0.15), "abused": (0.06, 0.35)}
CAVITY_WEAR_MAX = 0.02            # wear inside corners: nothing reaches there (at most 2 % of the corners' area)


def wear_of(v, lv):
    """wear and dirt at one vertex sample [edge, handling, rub, dirt, cavity, area, slot] for a level, no grunge."""
    e, h, r, d = v[0], v[1], v[2], v[3]
    w0 = max(e - (1 - lv["edge"]), h - (1 - lv["handling"]), r - (1 - lv["rub"]))
    wear = min(1.0, max(0.0, w0 / 0.25))
    return wear, d * lv["dirt"] * (1.0 - wear)


def zones_for(spec):
    if spec.get("zones"):
        return spec["zones"]
    m = spec["model"]
    if m.get("kind") == "modellab":
        return Z.from_modellab(m["build"])
    return {"contacts": [], "rubs": [], "carbon": []}


def bake(spec, name=None):
    """The model's wear masks into a copy of it (FBX for the engine, .blend for renders) and the stats the checks read.
    Returns the bake folder and its files."""
    bad = S.validate(spec)
    if bad:
        raise ValueError("the coating spec is not whole: " + "; ".join(bad))
    folder = out("bakes", "%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), name or spec["id"]))
    m = spec["model"]
    zones = zones_for(spec)
    job = {"zones": zones, "stats": str(folder / "stats.json"), "out_fbx": str(folder / ("SK_%s_Coated.fbx" % spec["id"])),
           "out_blend": str(folder / ("%s_coated.blend" % spec["id"])), "space": "modellab"}
    blend = None
    if m.get("kind") == "modellab":
        facts = json.loads((Path(m["build"]) / "facts.json").read_text(encoding="utf-8"))
        blend = facts["files"]["blend"]
        job["mesh"] = "SK_%s_Rig_Mesh" % facts["name"]
    else:
        job["fbx"] = m["fbx"]
        job["space"] = m.get("space", "modellab")
    (folder / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    (folder / "spec.json").write_text(json.dumps(dict(spec, zones=zones), indent=1), encoding="utf-8")
    log = run_blender("bake_wear.py", [folder / "job.json"], blend=blend)
    return {"bake": str(folder), "fbx": job["out_fbx"], "blend": job["out_blend"], "log": log}


def check(bake_folder):
    """Each variant against the evidence: the share of the gun worn through within its level's band, no wear inside
    corners, every finish holding to the library's rules. Rows a gate can judge (coating.* metrics)."""
    folder = Path(bake_folder)
    spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    st = json.loads((folder / "stats.json").read_text(encoding="utf-8"))
    levels = L.wear_levels()
    pv = st["per_vertex"]
    out_ = {}
    for vname, var in spec["variants"].items():
        lv = levels[var["wear"]]
        params = engine_params(spec, vname)
        # only a finish that wears through to something else counts (rubber, brass, a moulded colour wear to themselves)
        coated = {s for s, p_ in params.items() if p_["WearColor"] != p_["Color"] or p_["WearMetallic"] != p_["Metallic"]}
        pvv = [v for v in pv if v[6] in coated]
        total = sum(v[5] for v in pvv) or 1.0
        cav_area = sum(v[5] for v in pvv if v[4] > 0.6) or 1.0
        worn = cav = 0.0
        by_slot = {}
        for v in pvv:
            w, _d = wear_of(v, lv)
            if w > 0.5:
                worn += v[5]
                by_slot[v[6]] = by_slot.get(v[6], 0.0) + v[5]
                if v[4] > 0.6:
                    cav += v[5]
        share = worn / total
        lo, hi = WORN_BANDS.get(var["wear"], (0.0, 1.0))
        pbr = {fid: L.check(fid) for fid in set(var["finishes"].values())}
        pbr_bad = sorted(b for bs in pbr.values() for b in bs)
        slot_area = {s: d["area_cm2"] for s, d in st["slots"].items()}
        out_[vname] = {"wear": var["wear"], "worn_share": round(share, 4), "band": [lo, hi], "worn_in_band": lo <= share <= hi,
                       "cavity_wear_share": round(cav / cav_area, 4), "cavity_ok": cav / cav_area <= CAVITY_WEAR_MAX,
                       "pbr_problems": pbr_bad, "worn_by_slot": {s: round(a / max(slot_area.get(s, 1e-9), 1e-9), 4) for s, a in sorted(by_slot.items())},
                       "pass": lo <= share <= hi and cav / cav_area <= CAVITY_WEAR_MAX and not pbr_bad}
    return {"bake": str(folder), "variants": out_, "masks": st["slots"], "pass": all(v["pass"] for v in out_.values())}


def rows(result, weapon):
    """check()'s result as rows for a gate (weapon, action "idle", metric coating.*: one set per variant)."""
    r = []
    for vname, v in result["variants"].items():
        w = "%s@%s" % (weapon, vname)
        r += [{"weapon": w, "action": "idle", "metric": "coating.worn_share", "value": v["worn_share"]},
              {"weapon": w, "action": "idle", "metric": "coating.worn_in_band", "value": 1 if v["worn_in_band"] else 0},
              {"weapon": w, "action": "idle", "metric": "coating.cavity_wear_share", "value": v["cavity_wear_share"]},
              {"weapon": w, "action": "idle", "metric": "coating.pbr_problems", "value": len(v["pbr_problems"])}]
    return r


def engine_params(spec, variant):
    """A variant's values by slot for an engine material that follows the formula above."""
    var = spec["variants"][variant]
    lv = L.wear_levels()[var["wear"]]
    out_ = {}
    subs = {**S.MODELLAB_SUBSTRATES, **spec.get("substrates", {})}
    for slot, fid in var["finishes"].items():
        f = L.finish(fid)
        under = f.get("worn_to") or (f.get("worn_to_by_substrate") or {}).get(subs.get(slot))
        w = L.finish(under) if under else f          # worn through to what is under it; a solid colour wears to itself
        out_[slot] = {"finish": fid, "Color": f["base"]["linear"], "Metallic": f["base"]["metallic"], "Roughness": f["base"]["roughness"],
                      "WearColor": w["base"]["linear"], "WearMetallic": w["base"]["metallic"], "WearRoughness": w["base"]["roughness"],
                      "EdgeWear": lv["edge"], "HandleWear": lv["handling"], "RubWear": lv["rub"], "Dirt": lv["dirt"], "DirtColor": list(DIRT)}
    return out_


def render(bake_folder, variants=None, views=("right", "left")):
    """Look-dev renders of each variant on the baked model (not a game's view: labelled so). Returns the sheet."""
    folder = Path(bake_folder)
    spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    names = variants or list(spec["variants"])
    rjob = {"mesh": job.get("mesh"), "out": str(folder / "renders"), "views": list(views),
            "variants": {n: engine_params(spec, n) for n in names}}
    (folder / "render_job.json").write_text(json.dumps(rjob, indent=1), encoding="utf-8")
    run_blender("render_variants.py", [folder / "render_job.json"], blend=job["out_blend"], timeout=3600)
    return {"sheet": str(_sheet(folder / "renders", names, views)), "renders": str(folder / "renders")}


def _sheet(d, names, views):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    tiles = []
    for n in names:
        for v in views:
            p = d / ("%s_%s.png" % (n, v))
            if p.exists():
                im = Image.open(p).convert("RGB")
                im.thumbnail((800, 450))
                c = Image.new("RGB", (800, 485), (18, 18, 18))
                c.paste(im, (0, 35))
                ImageDraw.Draw(c).text((8, 6), "%s, %s (look-dev render, not the game view)" % (n, v), fill=(150, 230, 150), font=font)
                tiles.append(c)
    cols = len(views)
    rows_ = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (800 * cols, 485 * max(rows_, 1)), (0, 0, 0))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 800, (i // cols) * 485))
    p = d / "sheet.png"
    sheet.save(p)
    return p


def templates():
    from .config import DATA
    return {p.stem: json.loads(p.read_text(encoding="utf-8")).get("about") for p in sorted((DATA / "templates").glob("*.json"))}


def spec_for_modellab(build, template="ar15", variants=None, sid=None):
    """A coating spec for a Model Lab build from a template's variants, kept to the slots the build has (an optic's
    slot only with an optic), the zones from the build's marks and parts."""
    from .config import DATA
    t = json.loads((DATA / "templates" / (template + ".json")).read_text(encoding="utf-8"))
    facts = json.loads((Path(build) / "facts.json").read_text(encoding="utf-8"))
    have = set(facts.get("slots", {}))
    vs = {}
    for name, v in t["variants"].items():
        if variants and name not in variants:
            continue
        vs[name] = dict(v, finishes={s: f for s, f in v["finishes"].items() if s in have})
    return {"id": sid or facts["name"], "model": {"kind": "modellab", "build": str(Path(build))}, "variants": vs,
            "zones": Z.from_modellab(build), "template": template}


def describe(fbx):
    """A model's meshes and material slots (any FBX), for a coating spec of a model Model Lab did not make."""
    o = out("describe", time.strftime("%Y%m%d-%H%M%S"))
    run_blender("describe_model.py", [fbx, o / "model.json"])
    return json.loads((o / "model.json").read_text(encoding="utf-8"))
