# Testing

Three levels, cheapest first. Levels 1–2 don't need Isaac Sim.

## 1. API smoke test (any machine, no Isaac)

Validates auth + the full job lifecycle + download + unzip. Spends credits
(prompt = 2, file = 1) against production `api.rigyd.com`.

```bash
export RIGYD_API_KEY=rgyd_live_xxx      # or put it in .env (gitignored)
python3 scripts/smoke_test.py --prompt "a wooden dining chair"
# python3 scripts/smoke_test.py --file model.glb --tris 50000
```
Pass = `OK — USD ready at: …/<name>.usd`, with a sibling `textures/` folder.

## 2. Headless Isaac Sim test (cloud box, no GUI streaming)

Covers the one thing level 1 can't: `loader.add_usd_to_stage`. Run with Isaac
Sim's **bundled** Python (`python.sh`), not system Python.

```bash
# from the Isaac Sim install dir:
./python.sh /abs/path/scripts/isaac_test.py --usd /tmp/.../wooden_chair.usd
# or end-to-end (needs RIGYD_API_KEY exported in the shell):
./python.sh /abs/path/scripts/isaac_test.py --prompt "a wooden dining chair" --save /tmp/out.usd
```
Pass = `PASS — prim /World/TestAsset, N direct children, M mesh(es) in stage`.

## 3. Full GUI test (interactive)

Needs the Isaac Sim GUI — locally, or on a cloud instance via the **Omniverse
Streaming Client** / WebRTC.

1. **Window → Extensions** → ☰ → **Settings** → add the absolute path to this
   repo's `exts/` folder under **Extension Search Paths**.
2. Enable **rigyd.simready** (toggle **Autoload** to persist across restarts).
3. **Window → Rigyd** → paste your `rgyd_live_…` key → **Save key** →
   **Test connection** (shows pricing).
4. Type a prompt → **Generate & load**; or open the **3D file** section, browse
   to a model → **Convert & load**.
5. When it loads under `/World`, press **Play** — the asset should fall and
   collide (physics is baked into the SimReady USD).

Watch the **Console** window for `[rigyd.simready]` logs.

## Cloud Isaac Sim notes

- Easiest is the official **`nvcr.io/nvidia/isaac-sim`** container on a GPU box
  (L4/A10/A100…), or a marketplace "Isaac Sim" VM image.
- For headless validation (level 2) you only need the container + a GPU — no
  display. Use `./python.sh`.
- For the interactive GUI (level 3), run the container with streaming enabled and
  connect with the Omniverse Streaming Client.
- The extension makes only outbound HTTPS calls to `api.rigyd.com`; no inbound
  ports needed.
