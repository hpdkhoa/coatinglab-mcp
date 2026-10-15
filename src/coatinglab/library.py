"""The finish library: real gun finishes as physically based values (linear colour, metallic, roughness), each with
what shows when it wears through and where its numbers come from (data/finishes.json; COATINGLAB_LIBRARY merges a
project's own over it). check() holds every finish to the rules physically based rendering rests on: a non-metal's
colour stays inside the range real materials reflect, a metal reflects at least as much as the darkest real metal,
metallic is a material's nature (0 or 1) unless the finish says why it is a layer between."""
import json
import os
from pathlib import Path

from .config import DATA

SUBSTRATES = ("aluminium", "steel", "polymer", "rubber", "brass", "copper", "lead", "wood", "glass")


def _srgb(c):
    """Linear to sRGB 0..255 (the sRGB transfer function)."""
    c = max(0.0, min(1.0, c))
    return 255.0 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig")) if Path(p).exists() else {}


def library():
    """{"finishes": {...}, "rules": {...}, "wear_levels": {...}}: the built-in library with the project's over it."""
    lib = _load(DATA / "finishes.json")
    extra = os.environ.get("COATINGLAB_LIBRARY")
    if extra:
        mine = _load(extra)
        lib.setdefault("finishes", {}).update(mine.get("finishes", {}))
        lib.setdefault("wear_levels", {}).update(mine.get("wear_levels", {}))
    return lib


def finishes():
    return library().get("finishes", {})


def finish(fid):
    f = finishes().get(fid)
    if f is None:
        raise KeyError("no finish %r (list_finishes names them)" % fid)
    return f


def wear_levels():
    return library().get("wear_levels", {})


def check(fid, f=None, rules=None):
    """Every problem with a finish, as sentences; empty when it holds to the rules."""
    f = f or finish(fid)
    rules = rules or library().get("rules", {})
    lo, hi = rules.get("dielectric_albedo_srgb", [30, 240])
    f0 = rules.get("metal_f0_min_linear", 0.5)
    bad = []
    b = f.get("base", {})
    lin, met, rough = b.get("linear"), b.get("metallic"), b.get("roughness")
    if not (isinstance(lin, list) and len(lin) == 3 and all(isinstance(x, (int, float)) for x in lin)):
        return ["%s: base.linear must be [r, g, b] in 0..1" % fid]
    if not isinstance(met, (int, float)) or not 0 <= met <= 1:
        bad.append("%s: metallic must be 0..1" % fid)
        met = 0.0
    if not isinstance(rough, (int, float)) or not 0.02 <= rough <= 1:
        bad.append("%s: roughness must be 0.02..1" % fid)
    srgb = [_srgb(c) for c in lin]
    if met <= 0.2:
        if max(srgb) > hi or max(srgb) < lo:
            bad.append("%s: a non-metal's colour must keep its brightest channel within sRGB %d..%d, it is %d" % (fid, lo, hi, round(max(srgb))))
    elif met >= 0.8:
        if max(lin) < f0:
            bad.append("%s: a metal must reflect at least linear %.2f in its brightest channel, it reflects %.3f" % (fid, f0, max(lin)))
    elif not f.get("layered"):
        bad.append("%s: metallic %.2f is neither a metal nor a non-metal: mark the finish layered and say why" % (fid, met))
    if f.get("worn_to") and f["worn_to"] not in finishes():
        bad.append("%s: worn_to %r is not in the library" % (fid, f["worn_to"]))
    if not f.get("sources"):
        bad.append("%s: no sources (where the numbers come from)" % fid)
    for s in f.get("substrates", []):
        if s not in SUBSTRATES and s != "any":
            bad.append("%s: substrate %r is not one of %s" % (fid, s, SUBSTRATES))
    return bad


def check_all():
    """The library against its rules: {finish id: [problems]} for the finishes that break one."""
    lib = library()
    return {fid: b for fid, f in lib.get("finishes", {}).items() for b in [check(fid, f, lib.get("rules"))] if b}


def summary():
    """Each finish in a line: name, process, colour as sRGB hex, metallic, roughness, worn_to, measured or estimated."""
    out = {}
    for fid, f in finishes().items():
        b = f.get("base", {})
        hexc = "#%02x%02x%02x" % tuple(int(round(_srgb(c))) for c in b.get("linear", [0, 0, 0]))
        out[fid] = {"name": f.get("name"), "process": f.get("process"), "srgb": hexc, "metallic": b.get("metallic"),
                    "roughness": b.get("roughness"), "worn_to": f.get("worn_to"), "substrates": f.get("substrates"),
                    "estimate": f.get("estimate", False)}
    return out
