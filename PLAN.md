# Track A — Isaac Sim "Rigyd" Kit Extension

> Status: planning → execution. New repo/dir: `isaac-rigyd-ext/` (this folder).
> Goal: install "Rigyd" from inside Isaac Sim, convert a 3D file / text / images into a SimReady asset via the Rigyd API, and load the resulting USD directly onto the active stage — no manual download/drag.

## Why
Rigyd already emits **native SimReady USD** (Z-up, `metersPerUnit=1.0`, physics: mass/CoM/inertia/friction/restitution — `physiq/pipeline/usd_exporter.py`). Isaac Sim loads USD natively. So the extension is a thin **API client + stage loader**, not a format parser. Distribution is solved by the Omniverse **Community Extension Registry** (tag repo `omniverse-kit-extension`, cut a GitHub release).

## Integration contract (from `api.rigyd.com`)
Base: `https://api.rigyd.com/api`. Auth: `Authorization: Bearer rgyd_live_…` (programmatic API key — `src/auth/strategies/api-key.ts`).

| Flow | Call |
|---|---|
| Upload 3D file | `POST /conversions` (multipart; `.glb/.gltf/.fbx/.obj/.stl/.ply/.usd[a/c/z]`; optional `target_triangle_count` 1k–1M) |
| Text → asset | `POST /conversions/generate` (prompt, 2 credits) |
| Images → asset | `POST /conversions/generate` (1–4 images, 3 credits) |
| Simulate | `POST /conversions/:id/simulate` (on a completed job, 0 credits) |
| Poll | `GET /conversions/:id` → `status` (`submitting→preprocessing→queued→running→completed\|failed`), `progress`, `stage`, `output` |
| Result | `GET /conversions/:id/result?format=usd` → ZIP (`usd/{asset}/{asset}.usd` + `textures/*.png`) |
| Pricing | `GET /conversions/pricing` |

⚠️ **Verify before coding** (controller: `src/api/conversion-job/controllers/custom-controller.ts`):
1. Exact `output` shape — does it expose a directly-loadable USD URL, or only the ZIP? (Exploration suggested `output.model.url` + `output.textures[]`, but confirm field names against the controller.)
2. Whether `result` URLs are presigned/public (loadable by `omni.client` directly) or require the Bearer header (→ we download+unzip to a temp dir first).
3. CORS / redirect behavior on the result endpoint.

## Architecture (Python-only extension — no build system)
```
isaac-rigyd-ext/
  config/extension.toml        # metadata, deps, registry keywords (name must NOT start with "omni")
  rigyd_ext/
    __init__.py
    extension.py               # omni.ext.IExt: on_startup/on_shutdown; menu + window wiring
    api_client.py              # httpx/omni-async client: create/poll/result; key storage
    panel.py                   # omni.ui panel: key field, 3 input flows, progress, "Load to stage"
    loader.py                  # download+unzip result, reference/payload {asset}.usd onto stage
    settings.py                # API key persistence via carb settings / secret store
  README.md
  PLAN.md  (this file)
```
- `extension.py` registers a menu item (*Window → Rigyd*, and *File → Import → Rigyd Asset…*) and a dockable `omni.ui` window. Reference templates: built-in `isaacsim.asset.importer.mjcf` / `.urdf` for menu+import wiring; NVIDIA "ready-to-use (Python) extension" template / VS Code Extension Template Generator for scaffolding.
- `api_client.py` runs network calls async (Kit's asyncio loop) so the UI never blocks; poll `GET /conversions/:id` every ~2s with backoff.
- `loader.py`: when `status=completed`, fetch USD (direct URL if presigned, else download+unzip ZIP to temp), then `omni.usd` reference/payload `{asset}.usd` onto the current stage at a sane default transform. USD is already SimReady, so physics survives — Play just works.

## Milestones
- **M0 — Scaffold:** `extension.toml`, empty `IExt`, "Hello Rigyd" window. Loads in Isaac Sim with no startup errors.
- **M1 — Auth + API client:** key field (persisted), `GET /conversions/pricing` smoke test surfaced in the panel. Confirms auth + connectivity.
- **M2 — Text → stage (vertical slice):** prompt input → `POST /conversions/generate` → poll w/ progress widget → load USD onto stage. **This is the proof-of-integration.**
- **M3 — File upload + images:** add `POST /conversions` (file picker, optional `target_triangle_count`) and 1–4 image flow.
- **M4 — Simulate + polish:** `POST /conversions/:id/simulate` on completed jobs; job history list; error/credit-exhausted handling; activity/progress UX.
- **M5 — Distribution:** finalize `extension.toml` (keywords, repo, non-`omni` name), tag repo `omniverse-kit-extension`, cut GitHub release → Community Registry listing (~24h crawler).

## Verification
1. Add this folder to Isaac Sim ext search path (*Window → Extensions → +local path*), enable it; console shows clean `on_startup`.
2. Enter a valid `rgyd_live_…` key + text prompt; job is created; panel shows live `status`/`progress`/`stage`.
3. On `completed`, SimReady USD references onto the stage, renders, and **simulates** (press Play — object has mass + collision).
4. Repeat for 3D-file-upload and image flows; run Simulate on a finished job.

## Open decisions
- Public Community Registry listing vs. internal/private (affects naming + release only).
- HTTP-target Isaac version (4.5 / 5.x) to pin against in `extension.toml`.
