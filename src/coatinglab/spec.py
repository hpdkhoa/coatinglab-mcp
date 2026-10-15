"""A coating spec: which finish on each material slot of a model, in one or more variants, at a wear level; and the
zones the wear comes from. One bake of the model's masks serves every variant: a variant is only the finishes.

{"id": "M4A1",
 "model": {"kind": "modellab", "build": "<Model Lab build folder>"}  or  {"kind": "fbx", "fbx": "<path>", "slots": [...]},
 "substrates": {slot: "aluminium" | "steel" | "metal" | "polymer" | ...},      what each slot is made of
 "zones": {"contacts": [...], "rubs": [...], "carbon": [...]},                 bake_wear.py's zones, gun space cm
 "variants": {"<name>": {"finishes": {slot: finish id}, "wear": "<level>", "about": "..."}}}"""
import json
from pathlib import Path

from . import library as L

# what Model Lab's slots are made of (its AR-15: the receivers, the handguard and the optics are aluminium forgings
# or extrusions; the barrel and the bolt group steel; Detail mixes small steel and aluminium parts)
MODELLAB_SUBSTRATES = {"Upper": "aluminium", "Lower": "aluminium", "Receiver": "aluminium", "Handguard": "aluminium",
                       "Optic": "aluminium", "Barrel": "steel", "Steel": "steel", "Detail": "metal", "Furniture": "polymer",
                       "Magazine": "aluminium", "Rubber": "rubber", "Brass": "brass", "Copper": "copper",
                       "Glass": "glass", "Lens": "glass"}
OPTIONAL = {"Glass", "Lens"}        # the engine keeps its own glass


def fits(finish_substrates, slot_substrate):
    """Whether a finish goes on a slot's material: "any" goes on anything but glass; "metal" is aluminium or steel."""
    subs = set(finish_substrates or [])
    if slot_substrate == "glass":
        return "glass" in subs
    if "any" in subs:
        return True
    if slot_substrate == "metal":
        return bool(subs & {"aluminium", "steel", "metal"})
    return slot_substrate in subs or ("metal" in subs and slot_substrate in ("aluminium", "steel"))


def slots(spec):
    m = spec.get("model", {})
    if m.get("kind") == "modellab":
        facts = json.loads((Path(m["build"]) / "facts.json").read_text(encoding="utf-8"))
        if "slots" not in facts:
            raise ValueError("the Model Lab build has no slots table (Model Lab 0.2 or later writes it)")
        return {s: v for s, v in facts["slots"].items()}
    return {s: {} for s in m.get("slots", [])}


def validate(spec):
    """Every problem with a coating spec, as sentences; empty when it is whole."""
    bad = []
    for k in ("id", "model", "variants"):
        if k not in spec:
            bad.append("missing %r" % k)
    if bad:
        return bad
    try:
        have = slots(spec)
    except (OSError, ValueError, KeyError) as e:
        return ["model: %s" % e]
    subs = {**{s: MODELLAB_SUBSTRATES.get(s) for s in have}, **spec.get("substrates", {})}
    fin, levels = L.finishes(), L.wear_levels()
    if not spec["variants"]:
        bad.append("no variants")
    for vname, v in spec["variants"].items():
        f = v.get("finishes", {})
        for s in have:
            if s not in f and s not in OPTIONAL:
                bad.append("variant %s: slot %s has no finish" % (vname, s))
        for s, fid in f.items():
            if s not in have:
                bad.append("variant %s: slot %s is not in the model" % (vname, s))
            elif fid not in fin:
                bad.append("variant %s, slot %s: no finish %r" % (vname, s, fid))
            elif subs.get(s) and not fits(fin[fid].get("substrates"), subs[s]):
                bad.append("variant %s, slot %s: %s does not go on %s (it goes on %s)" % (vname, s, fid, subs[s], ", ".join(fin[fid].get("substrates", []))))
        if v.get("wear") not in levels:
            bad.append("variant %s: wear must be one of %s" % (vname, sorted(levels)))
    for s, sub in spec.get("substrates", {}).items():
        if sub not in L.SUBSTRATES + ("metal",):
            bad.append("substrate of %s: %r is not one of %s" % (s, sub, L.SUBSTRATES + ("metal",)))
    return bad
