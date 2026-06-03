# Rigyd SimReady Importer

Convert any 3D model, text prompt, or image into a physics-enabled **SimReady USD**
asset with [Rigyd](https://rigyd.com) — without leaving Isaac Sim. The result is
referenced straight onto the active stage with mass, collision, and friction
already set, so it simulates as soon as you press **Play**.

## Setup

1. Get an API key from your Rigyd dashboard (`rgyd_live_…`).
2. Open **Window → Rigyd**, paste the key, and click **Save key**.
3. Click **Test connection** to confirm.

## Use

- **Text → SimReady** — type a prompt (e.g. *"a wooden dining chair"*) and click
  **Generate & load** (2 credits).
- **3D file → SimReady** — browse to a `.glb/.gltf/.fbx/.obj/.stl/.ply/.usd*`
  file (optionally set a target triangle count) and click **Convert & load**
  (1 credit).

The panel shows live status/progress while the job runs on Rigyd, then downloads
the USD package and adds it under `/World`.

## How it works

The extension talks to the Rigyd public API (`api.rigyd.com`), polls the job to
completion, downloads the self-contained `format=usd` result ZIP (USD + textures
with correct relative paths), unzips it locally, and references the `.usd` onto
the stage.
