# isaac-rigyd-ext

An **NVIDIA Isaac Sim / Omniverse Kit extension** that brings the
[Rigyd](https://rigyd.com) SimReady conversion pipeline into the simulator.
Convert any 3D model, text prompt, or image into a physics-enabled SimReady USD
asset and reference it straight onto your stage — no manual download/drag.

> Rigyd already emits **native SimReady USD** (Z-up, `metersPerUnit=1.0`, with
> mass / center-of-mass / inertia / friction / restitution), so this extension is
> a thin API client + stage loader, not a format converter.

## Install (local)

1. Clone this repo.
2. In Isaac Sim: **Window → Extensions → ☰ → Settings → + (Extension Search
   Paths)** and add the absolute path to this repo's `exts/` folder.
3. Find **rigyd.simready** in the extension list and enable it (toggle "Autoload"
   to keep it on).
4. Open **Window → Rigyd**, paste your `rgyd_live_…` API key, **Save key**, then
   **Test connection**.

## Use

| Flow | Input | Cost |
|------|-------|------|
| Text → SimReady | a prompt | 2 credits |
| 3D file → SimReady | `.glb/.gltf/.fbx/.obj/.stl/.ply/.usd*` (+ optional target triangle count) | 1 credit |
| Image → SimReady | 1–4 images *(M3)* | 3 credits |

The panel submits the job to `api.rigyd.com`, polls to completion, downloads the
self-contained `format=usd` result ZIP, unzips it, and references the `.usd`
under `/World`. Press **Play** to simulate.

## Layout

```
exts/rigyd.simready/
  config/extension.toml        # metadata + Kit dependencies
  rigyd/simready/
    extension.py               # omni.ext.IExt — window + Window-menu toggle
    panel.py                   # omni.ui window; async submit/poll/load
    api_client.py              # stdlib urllib client for the Rigyd API
    loader.py                  # unzip result + reference USD onto the stage
    settings.py                # persisted API key (carb /persistent)
  docs/README.md, docs/CHANGELOG.md
```

## Status

Early — see `PLAN.md` for the milestone roadmap (M0 scaffold → M5 Community
Registry). Text and 3D-file flows are implemented; image/simulate/history and
registry publishing are in progress.

## License

MIT — see [LICENSE](./LICENSE).
