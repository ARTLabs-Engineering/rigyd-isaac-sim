#!/usr/bin/env python3
"""Headless Isaac Sim test for the stage-loader — the one bit smoke_test can't cover.

Boots Isaac Sim headless (no GUI streaming needed), then exercises
``loader.add_usd_to_stage`` and asserts the reference composed with its prims.
Either point it at a local ``.usd`` (e.g. the one ``smoke_test.py`` produced) or
let it run the full Rigyd pipeline first.

Run it with Isaac Sim's bundled Python, NOT system python:
    # Isaac Sim 4.x / 5.x install dir:
    ./python.sh /path/to/scripts/isaac_test.py --usd /tmp/.../wooden_chair.usd
    # or full pipeline (needs RIGYD_API_KEY):
    ./python.sh /path/to/scripts/isaac_test.py --prompt "a wooden dining chair"
    # optionally write the composed stage out to inspect later:
    #   ... --save /tmp/rigyd_stage.usd
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "exts", "rigyd.simready"))


def _boot_headless():
    """Start Kit headless. Must happen before importing omni.usd/pxr."""
    try:
        from isaacsim import SimulationApp  # Isaac Sim 4.5+/5.x
    except ImportError:
        from omni.isaac.kit import SimulationApp  # older layout
    return SimulationApp({"headless": True})


def _resolve_usd(args) -> str:
    if args.usd:
        if not os.path.isfile(args.usd):
            raise SystemExit(f"--usd not found: {args.usd}")
        return args.usd

    import time
    from rigyd.simready.api_client import RigydClient
    from rigyd.simready import loader

    key = os.environ.get("RIGYD_API_KEY", "")
    base = os.environ.get("RIGYD_BASE_URL", "https://api.rigyd.com/api")
    if not key:
        raise SystemExit("Set RIGYD_API_KEY or pass --usd.")
    client = RigydClient(base, key)
    job = (
        client.create_from_file(args.file, args.tris)
        if args.file else client.generate_from_prompt(args.prompt)
    )
    job_id = job["id"]
    print(f"Job {job_id} created; polling…")
    while True:
        j = client.get_job(job_id)
        print(f"  {j.get('status')} · {j.get('stage')} · {j.get('progress')}%")
        if j.get("status") in ("completed", "failed"):
            break
        time.sleep(3)
    if j.get("status") != "completed":
        raise SystemExit(f"Job failed: {j.get('error')}")
    zip_path = os.path.join("/tmp", f"rigyd_{job_id}.zip")
    client.download_result(job_id, zip_path, "usd")
    return loader.unzip_result(zip_path, job_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", help="local .usd to load (skips the API call)")
    ap.add_argument("--prompt", help="run the text pipeline first")
    ap.add_argument("--file", help="run the 3D-file pipeline first")
    ap.add_argument("--tris", type=int, default=None)
    ap.add_argument("--save", help="write the composed stage to this path")
    ap.add_argument("--hold", action="store_true",
                    help="keep the app + livestream running after load (Ctrl-C to exit)")
    args = ap.parse_args()
    if not (args.usd or args.prompt or args.file):
        raise SystemExit("Pass --usd, --prompt, or --file.")

    app = _boot_headless()
    try:
        usd_path = _resolve_usd(args)
        print(f"Loading: {usd_path}")

        import omni.usd
        from rigyd.simready import loader

        # Fresh stage so the test is deterministic.
        omni.usd.get_context().new_stage()
        prim_path = loader.add_usd_to_stage(usd_path, "TestAsset")

        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        assert prim and prim.IsValid(), f"prim missing at {prim_path}"
        assert prim.HasAuthoredReferences(), "reference not authored"
        descendants = list(prim.GetAllChildren())
        assert descendants, "reference composed to an empty prim (did it resolve?)"

        # Count gprims (meshes) to confirm geometry actually came through.
        from pxr import UsdGeom
        meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
        print(f"PASS — prim {prim_path}, {len(descendants)} direct children, "
              f"{len(meshes)} mesh(es) in stage")

        if args.save:
            stage.GetRootLayer().Export(args.save)
            print(f"Saved composed stage to {args.save}")

        if args.hold:
            # Select + frame the asset, then keep the app (and livestream) alive
            # so you can actually orbit it in the /viewer tab.
            omni.usd.get_context().get_selection().set_selected_prim_paths(
                [prim_path], True
            )
            try:
                import omni.kit.viewport.utility as vpu

                vpu.frame_viewport_prims(vpu.get_active_viewport(), prims=[prim_path])
            except Exception as exc:  # noqa: BLE001 — framing is best-effort
                print(f"(could not auto-frame; press F in the viewport: {exc})")
            print("Holding — view it in the /viewer tab. Ctrl-C here to exit.")
            while app.is_running():
                app.update()
        return 0
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
