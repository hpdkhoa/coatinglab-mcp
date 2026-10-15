"""Coating Lab over MCP. Run: coatinglab-mcp (or python -m coatinglab serve)."""
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from . import __version__, coat as C, library as L, spec as S
from .config import Busy

mcp = MCPServer("coatinglab", title="Coating Lab", version=__version__, instructions=(
    "Coating Lab gives game gun models real surface finishes: anodized aluminium, phosphate and blued steel, ceramic "
    "coatings, polymer, brass, each a physically based value with its sources. A coating spec puts a finish on each "
    "material slot of a model, in variants (a two-tone rifle, a worn one) at a wear level (new, issued, worn, "
    "abused). Wear is baked once into the model's vertex colours from where use wears a gun: exposed edges, where the "
    "hands work it, where parts slide, and dirt where it is occluded. Every variant reads the same masks. The checks "
    "hold each finish to physical rules and each variant's wear to its level. Model Lab builds give their own slots, "
    "marks and parts; spec_for_modellab makes a spec from one. Look at the renders: a passing number can hide a wrong "
    "look."))


def _err(f, *a, **k):
    try:
        return f(*a, **k)
    except (Busy, RuntimeError, ValueError, FileNotFoundError, KeyError) as e:
        raise ToolError(str(e))


@mcp.tool()
def list_finishes() -> dict:
    """Every finish: name, process, colour (sRGB hex), metallic, roughness, what it wears to, measured or estimated."""
    return L.summary()


@mcp.tool()
def read_finish(finish: str) -> dict:
    """One finish in full, with its notes and sources."""
    return _err(L.finish, finish)


@mcp.tool()
def check_library() -> dict:
    """The library against the physical rules: the finishes that break one, and why (empty: all hold)."""
    return L.check_all()


@mcp.tool()
def check_finish(finish: Annotated[dict, Field(description="a finish: {name, substrates, base {linear, metallic, roughness}, worn_to, sources}")],
                 finish_id: str = "candidate") -> list:
    """A finish of your own against the rules before you add it."""
    return L.check(finish_id, finish)


@mcp.tool()
def list_wear_levels() -> dict:
    """The wear levels (new, issued, worn, abused): each mask's threshold and what the level looks like."""
    return L.wear_levels()


@mcp.tool()
def list_templates() -> dict:
    """The ready variant sets (e.g. ar15: issued, new_black, fde_two_tone, odg_ceramic, tungsten_stainless, abused_parkerized)."""
    return C.templates()


@mcp.tool()
def spec_for_modellab(build: Annotated[str, Field(description="a Model Lab build folder")], template: str = "ar15",
                      variants: list[str] | None = None) -> dict:
    """A coating spec for a Model Lab build: a template's variants on the slots it has, the wear zones from its marks."""
    return _err(C.spec_for_modellab, build, template, variants)


@mcp.tool()
def describe_model(fbx: str) -> dict:
    """Any model's meshes and material slots (an FBX), to write a coating spec for a model Model Lab did not make."""
    return _err(C.describe, fbx)


@mcp.tool()
def validate_spec(spec: dict) -> list:
    """Every problem with a coating spec: a slot without a finish, a finish that does not go on its material."""
    return _err(S.validate, spec)


@mcp.tool()
def bake(spec: dict, name: str | None = None) -> dict:
    """Bakes the wear masks into a copy of the model (FBX for an engine, .blend for renders): about a minute."""
    return _err(C.bake, spec, name)


@mcp.tool()
def check_coating(bake_folder: str) -> dict:
    """Each variant against its wear level's band, wear kept out of corners, every finish physical."""
    return _err(C.check, bake_folder)


@mcp.tool()
def render_variants(bake_folder: str, variants: list[str] | None = None,
                    views: Annotated[list[str] | None, Field(description="right, left, close")] = None) -> dict:
    """Look-dev renders of the variants (labelled: not a game's view) and a sheet of them."""
    return _err(C.render, bake_folder, variants, tuple(views or ("right", "close")))


@mcp.tool()
def engine_params(spec: dict, variant: str) -> dict:
    """A variant's values by slot for an engine material that follows the shared wear formula."""
    return _err(C.engine_params, spec, variant)


def main():
    mcp.run()
