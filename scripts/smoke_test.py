#!/usr/bin/env python3
"""Standalone smoke test for the Rigyd API client — NO Isaac Sim required.

Exercises the full round-trip the extension relies on (create -> poll ->
download format=usd ZIP -> unzip -> locate .usd) using only the Python stdlib,
so you can validate your API key, credits, and connectivity from any laptop
before touching Isaac Sim.

Usage:
    export RIGYD_API_KEY=rgyd_live_xxx
    python scripts/smoke_test.py --prompt "a wooden dining chair"
    python scripts/smoke_test.py --file /path/to/model.glb [--tris 50000]
    # optional: override the base URL (e.g. a staging API)
    #   export RIGYD_BASE_URL=https://api.rigyd.com/api
"""

import argparse
import os
import sys
import time

# Make the extension package importable without Kit.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "exts", "rigyd.simready"))

from rigyd.simready.api_client import RigydClient, RigydError  # noqa: E402
from rigyd.simready import loader  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="text prompt to generate from")
    ap.add_argument("--file", help="path to a 3D model file")
    ap.add_argument("--tris", type=int, default=None, help="target triangle count")
    args = ap.parse_args()

    api_key = os.environ.get("RIGYD_API_KEY", "")
    base_url = os.environ.get("RIGYD_BASE_URL", "https://api.rigyd.com/api")
    if not api_key:
        print("Set RIGYD_API_KEY first.")
        return 2
    if not args.prompt and not args.file:
        print("Pass --prompt or --file.")
        return 2

    client = RigydClient(base_url, api_key)

    try:
        print(f"Pricing: {client.pricing()}")
        if args.file:
            print(f"Uploading {args.file} …")
            job = client.create_from_file(args.file, args.tris)
        else:
            print(f"Generating: {args.prompt!r} …")
            job = client.generate_from_prompt(args.prompt)

        job_id = job["id"]
        print(f"Job {job_id} created (status={job.get('status')})")

        while True:
            j = client.get_job(job_id)
            print(f"  {j.get('status')} · {j.get('stage')} · {j.get('progress')}%")
            if j.get("status") in ("completed", "failed"):
                break
            time.sleep(3)

        if j.get("status") != "completed":
            print(f"Job failed: {j.get('error')}")
            return 1

        zip_path = os.path.join("/tmp", f"rigyd_{job_id}.zip")
        client.download_result(job_id, zip_path, "usd")
        usd_path = loader.unzip_result(zip_path, job_id)
        print(f"OK — USD ready at: {usd_path}")
        return 0
    except RigydError as exc:
        print(f"API error (status={exc.status}): {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
