"""Turn a downloaded Rigyd result ZIP into a prim on the current stage.

The ``format=usd`` result ZIP is self-contained — ``usd/{base}/{model}.usd`` plus
``usd/{base}/textures/*.png`` with the texture paths the USD references relative
to itself. So we unzip locally and reference the *local* ``.usd``; textures then
resolve correctly (the bare CDN URL would not, since its sibling textures live
at unrelated hashed paths).
"""

import os
import shutil
import tempfile
import zipfile
from typing import Optional

import carb

_USD_EXTS = (".usd", ".usda", ".usdc", ".usdz")


def cache_dir_for(job_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), "rigyd_assets", job_id)


def unzip_result(zip_path: str, job_id: str) -> str:
    """Extract the result ZIP into a per-job cache dir; return the .usd path."""
    dest = cache_dir_for(job_id)
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)

    usd_path = _find_usd(dest)
    if not usd_path:
        raise RuntimeError(f"No .usd file found in result for job {job_id}")
    return usd_path


def _find_usd(root: str) -> Optional[str]:
    # Prefer a top-level .usd/.usda/.usdc; fall back to any match (skip usdz packs).
    candidates = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(_USD_EXTS):
                candidates.append(os.path.join(dirpath, name))
    if not candidates:
        return None
    # Shallowest path wins (the asset root .usd, not a nested payload).
    candidates.sort(key=lambda p: (p.count(os.sep), len(p)))
    return candidates[0]


def add_usd_to_stage(usd_path: str, label: str = "RigydAsset") -> str:
    """Reference ``usd_path`` onto the current stage under /World; return prim path."""
    import omni.usd
    from pxr import Sdf, UsdGeom

    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if stage is None:
        ctx.new_stage()
        stage = ctx.get_stage()

    # Ensure a /World root and make it the default prim (Isaac convention).
    world = stage.GetPrimAtPath("/World")
    if not world or not world.IsValid():
        world = UsdGeom.Xform.Define(stage, Sdf.Path("/World")).GetPrim()
    if not stage.GetDefaultPrim() or not stage.GetDefaultPrim().IsValid():
        stage.SetDefaultPrim(world)

    safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in label) or "RigydAsset"
    prim_path = omni.usd.get_stage_next_free_path(stage, f"/World/{safe}", False)

    prim = stage.DefinePrim(prim_path, "Xform")
    prim.GetReferences().AddReference(usd_path)
    carb.log_info(f"[rigyd.simready] referenced {usd_path} at {prim_path}")
    return prim_path
