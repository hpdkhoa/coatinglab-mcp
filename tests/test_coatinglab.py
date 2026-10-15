"""Coating Lab's own checks. The library and spec checks need nothing; the bake test needs Blender and a Model Lab
build (COATINGLAB_TEST_BUILD), and is skipped without them."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from coatinglab import coat as C, library as L, spec as S  # noqa: E402


def test_the_library_holds_to_the_rules():
    assert L.check_all() == {}
    assert len(L.finishes()) >= 20
    for fid, f in L.finishes().items():
        assert f["sources"], fid


def test_the_rules_catch_what_is_not_physical():
    ok = {"base": {"linear": [0.03, 0.03, 0.03], "metallic": 0.0, "roughness": 0.5}, "sources": ["x"], "substrates": ["steel"]}
    assert L.check("ok", ok) == []
    dark_metal = dict(ok, base={"linear": [0.012, 0.012, 0.014], "metallic": 0.85, "roughness": 0.28})
    assert "a metal must reflect" in " ".join(L.check("dark_metal", dark_metal))
    half = dict(ok, base={"linear": [0.03, 0.03, 0.03], "metallic": 0.45, "roughness": 0.5})
    assert "neither a metal" in " ".join(L.check("half", half))
    assert L.check("layered", dict(half, layered=True)) == []
    white = dict(ok, base={"linear": [0.95, 0.95, 0.95], "metallic": 0.0, "roughness": 0.5})
    assert "sRGB" in " ".join(L.check("white", white))
    assert "no sources" in " ".join(L.check("nosrc", dict(ok, sources=[])))


def test_a_finish_goes_only_on_its_material():
    assert S.fits(["aluminium"], "aluminium") and not S.fits(["aluminium"], "steel")
    assert S.fits(["any"], "polymer") and not S.fits(["any"], "glass")
    assert S.fits(["steel"], "metal") and S.fits(["aluminium"], "metal")


def test_a_spec_is_checked(tmp_path):
    spec = {"id": "X", "model": {"kind": "fbx", "fbx": "x.fbx", "slots": ["Upper", "Barrel", "Furniture"]},
            "variants": {"a": {"finishes": {"Upper": "anodized_black", "Barrel": "phosphate_manganese", "Furniture": "polymer_black"}, "wear": "issued"}}}
    assert S.validate(spec) == []
    bad = json.loads(json.dumps(spec))
    bad["variants"]["a"]["finishes"]["Upper"] = "phosphate_manganese"      # phosphate does not go on aluminium
    del bad["variants"]["a"]["finishes"]["Furniture"]
    bad["variants"]["a"]["wear"] = "shiny"
    text = " ".join(S.validate(bad))
    assert "does not go on aluminium" in text and "Furniture has no finish" in text and "wear must be one of" in text


def test_wear_rises_with_the_level_and_grunge_never_makes_wear():
    lv = L.wear_levels()
    edge = [0.9, 0.0, 0.0, 0.0, 0.0, 1.0, "Upper"]          # a sharp exposed edge, nothing else
    flat = [0.0, 0.0, 0.0, 0.2, 0.0, 1.0, "Upper"]          # flat ground
    ws = [C.wear_of(edge, lv[k])[0] for k in ("new", "issued", "worn", "abused")]
    assert ws == sorted(ws) and ws[0] < ws[-1]
    assert all(C.wear_of(flat, lv[k])[0] == 0.0 for k in lv)


def test_a_ceramic_coat_wears_to_what_is_under_it():
    spec = {"id": "X", "model": {"kind": "fbx", "fbx": "x.fbx", "slots": ["Lower", "Barrel"]},
            "variants": {"a": {"finishes": {"Lower": "ceramic_fde", "Barrel": "ceramic_fde"}, "wear": "worn"}}}
    p = C.engine_params(spec, "a")
    assert p["Lower"]["WearColor"] == L.finish("aluminium_bare")["base"]["linear"]
    assert p["Barrel"]["WearColor"] == L.finish("steel_bare")["base"]["linear"]


@pytest.mark.skipif(not os.environ.get("COATINGLAB_TEST_BUILD"), reason="needs Blender and a Model Lab build (COATINGLAB_TEST_BUILD)")
def test_a_model_lab_build_bakes_and_every_template_variant_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("COATINGLAB_OUT", str(tmp_path))
    spec = C.spec_for_modellab(os.environ["COATINGLAB_TEST_BUILD"])
    r = C.bake(spec)
    res = C.check(r["bake"])
    assert res["pass"], {k: v for k, v in res["variants"].items() if not v["pass"]}
    assert Path(r["fbx"]).exists()
