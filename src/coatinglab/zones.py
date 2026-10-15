"""Where a gun wears, from what the model knows about itself: the hands' contacts (its grip and support marks, its
controls), the lines its parts slide on, and where it burns powder. For a Model Lab build these come from its facts
(marks, shape bounds, moving parts); any other model gives them in its coating spec.

The radii and weights are estimates from how a rifle is handled (the firing hand wraps the grip and works the
selector and the magazine release; the support hand holds the handguard and pulls the charging handle; a magazine
rubs the well going in and out; a collapsible stock rubs its tube when it is moved; carbon blows out of the muzzle
and the ejection port). They are marked as estimates in every spec they make."""
import json
from pathlib import Path

# (name, mark or shape, radius cm, weight): the hands' work
CONTACTS = [("grip", "mark:grip_r", 5.5, 1.0), ("support", "mark:support_l", 7.0, 0.9), ("charging_handle", "shape:Charging_Wing", 2.0, 1.0),
            ("charging_handle_latch", "shape:Charging_Latch", 1.6, 0.9), ("trigger", "shape:Trigger", 1.2, 0.6),
            ("selector", "shape:Selector_Lever", 1.4, 0.8), ("mag_release", "shape:MagRelease", 1.2, 0.8),
            ("bolt_catch", "shape:BoltCatch", 1.4, 0.6), ("forward_assist", "shape:ForwardAssist", 1.0, 0.4),
            ("stock_lever", "shape:Stock_Lever", 1.3, 0.5), ("magwell_flare", "mark:magwell", 3.5, 0.6),
            ("cheek_weld", "shape:Stock_Body:top_rear", 4.0, 0.4), ("sling_loop", "shape:Stock_SlingLoop", 1.0, 0.5)]
CARBON = [("muzzle", "mark:muzzle", 3.5), ("port", "mark:eject_port", 3.5)]


def _centre(b):
    return [(a + c) / 2.0 for a, c in zip(b[0], b[1])]


def _where(facts, ref):
    kind, _, rest = ref.partition(":")
    if kind == "mark":
        m = facts["marks"].get(rest)
        return m["at"] if m else None
    name, _, part = rest.partition(":")
    b = facts.get("shape_bounds", {}).get(name)
    if not b:
        return None
    if part == "top_rear":                 # a stock's comb, where the cheek rests: its top, a third from the rear
        return [0.0, b[0][1] + (b[1][1] - b[0][1]) * 0.35, b[1][2]]
    return _centre(b)


def from_modellab(build):
    """The zones of a Model Lab build (its folder)."""
    facts = json.loads((Path(build) / "facts.json").read_text(encoding="utf-8"))
    sb = facts.get("shape_bounds", {})
    contacts = []
    for name, ref, r, w in CONTACTS:
        at = _where(facts, ref)
        if at:
            contacts.append({"name": name, "at": [round(x, 3) for x in at], "radius_cm": r, "weight": w})
    rubs = []
    if "Magazine_Body" in sb and "magwell" in facts["marks"]:
        # the magazine rubs only over the depth it sits inside the well: from the well's top to its bottom edge
        lo, hi = sb["Magazine_Body"]
        y = (lo[1] + hi[1]) / 2.0
        top = facts["marks"]["magwell"]["at"][2]
        bottom = sb["Lower_Well"][0][2] if "Lower_Well" in sb else top - 5.0
        rubs.append({"name": "magazine_in_well", "from": [0.0, y, top], "to": [0.0, y, bottom + 0.5], "width_cm": 3.0, "weight": 0.6})
    if "Buffer_Tube" in sb:
        lo, hi = sb["Buffer_Tube"]
        rubs.append({"name": "stock_on_tube", "from": [0.0, lo[1], hi[2]], "to": [0.0, hi[1] - 2.0, hi[2]], "width_cm": 1.2, "weight": 0.7})
    if "Bolt_Carrier" in sb:
        lo, hi = sb["Bolt_Carrier"]
        rubs.append({"name": "bolt_carrier", "from": [0.0, lo[1], 0.0], "to": [0.0, hi[1], 0.0], "width_cm": 1.6, "weight": 0.8})
    carbon = []
    for name, ref, r in CARBON:
        at = _where(facts, ref)
        if at:
            carbon.append({"name": name, "at": [round(x, 3) for x in at], "radius_cm": r})
    return {"contacts": contacts, "rubs": rubs, "carbon": carbon,
            "source": "estimates from how a rifle is handled, placed on the build's own marks and parts (coatinglab.zones)"}
