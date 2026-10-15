"""Where Coating Lab writes, how it finds Blender, and what it waits for.

COATINGLAB_OUT       the only folder Coating Lab writes to (bakes, sheets, engine parameters); ~/.coatinglab by default
COATINGLAB_BLENDER   Blender's executable, if it is not on the PATH or in the usual install folder
COATINGLAB_LIBRARY   optional: a finishes JSON of your own, merged over the built-in library (same shape)
COATINGLAB_WAIT_FOR  optional: process names that hold the machine ("UnrealEditor.exe,blender.exe"); while one runs,
                     a bake refuses to start (one heavy job at a time). Empty by default."""
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
SCRIPTS = PACKAGE / "blender"
DATA = PACKAGE / "data"


def out(*parts):
    p = Path(os.environ.get("COATINGLAB_OUT") or Path.home() / ".coatinglab").joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def blender():
    """Blender: COATINGLAB_BLENDER, the PATH, then the usual install folders."""
    for cand in (os.environ.get("COATINGLAB_BLENDER"), shutil.which("blender")):
        if cand and Path(cand).exists():
            return Path(cand)
    pats = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), r"D:\Blender", r"C:\Blender"):
            pats += [os.path.join(base, "Blender Foundation", "Blender*", "blender.exe"), os.path.join(base, "blender.exe")]
    elif sys.platform == "darwin":
        pats += ["/Applications/Blender.app/Contents/MacOS/Blender"]
    else:
        pats += ["/usr/bin/blender", "/snap/bin/blender", os.path.expanduser("~/blender*/blender")]
    for pat in pats:
        hits = sorted(glob.glob(pat), reverse=True)
        if hits:
            return Path(hits[0])
    raise FileNotFoundError("Blender not found: set COATINGLAB_BLENDER")


class Busy(RuntimeError):
    pass


def busy():
    """The processes named in COATINGLAB_WAIT_FOR that run now."""
    names = {n.strip().lower() for n in os.environ.get("COATINGLAB_WAIT_FOR", "").split(",") if n.strip()}
    if not names:
        return []
    if sys.platform == "win32":
        txt = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout.lower()
        seen = {line.split(",")[0].strip('"') for line in txt.splitlines() if line}
    else:
        txt = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True).stdout.lower()
        seen = {Path(line.strip()).name for line in txt.splitlines() if line.strip()}
    return sorted(seen & names)


def run_blender(script, args, blend=None, timeout=1800, tag="COATINGLAB"):
    """Runs one of the package's Blender scripts; its tagged lines, or an error with the tail of its output."""
    held = busy()
    if held:
        raise Busy("%s running: one heavy job at a time" % ", ".join(held))
    cmd = [str(blender()), "-b"] + ([str(blend)] if blend else ["--factory-startup"]) + ["-P", str(SCRIPTS / script), "--"] + [str(a) for a in args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    lines = [l for l in (p.stdout or "").splitlines() if l.startswith(tag)]
    if p.returncode != 0 or not lines:
        raise RuntimeError("%s failed: %s" % (script, ((p.stderr or "") + (p.stdout or ""))[-1500:]))
    return lines
