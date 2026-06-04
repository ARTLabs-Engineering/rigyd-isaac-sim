# Changelog

## [1.0.0] - 2026-06-04
First public release.
- Three conversion flows — **Text**, **Images (1 or 4)**, and **3D file** →
  SimReady: submit, poll, download the `format=usd` result ZIP, and reference the
  physics-enabled USD onto the active stage.
- Persisted API key; account header with signed-in user + credit balance.
- Custom percentage progress bar (hidden when idle) and an inset status bar.
- Validated end-to-end on NVIDIA Isaac Sim (textures + SimReady physics intact).
