"""coatinglab <command>
  serve                                  the MCP server (also: coatinglab-mcp)
  finishes                               the library, a line a finish
  check-library                          the library against the physical rules
  spec <modellab build> [template]       a coating spec for a Model Lab build (printed as JSON)
  bake <spec.json>                       bake the wear masks
  check <bake folder>                    the variants against their wear levels
  render <bake folder> [variant ...]     look-dev renders and a sheet"""
import json
import sys


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if a[0] == "serve":
        from .server import main as serve
        serve()
        return 0
    from . import coat as C, library as L
    if a[0] == "finishes":
        out = L.summary()
    elif a[0] == "check-library":
        out = L.check_all()
    elif a[0] == "spec":
        out = C.spec_for_modellab(a[1], a[2] if len(a) > 2 else "ar15")
    elif a[0] == "bake":
        out = C.bake(json.load(open(a[1], encoding="utf-8")))
    elif a[0] == "check":
        out = C.check(a[1])
    elif a[0] == "render":
        out = C.render(a[1], a[2:] or None)
    else:
        raise SystemExit(__doc__)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
