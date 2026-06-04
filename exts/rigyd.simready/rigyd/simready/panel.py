"""The Rigyd dockable window: key entry, the three input flows, and progress.

All network work runs through ``_run`` → an asyncio coroutine that off-loads the
blocking ``RigydClient`` calls to a thread executor, so the UI never freezes.
"""

import asyncio
import functools
import os
import tempfile
from typing import Awaitable, Callable, Optional

import omni.ui as ui
import omni.kit.async_engine

from . import settings, loader
from .api_client import RigydClient, RigydError

_POLL_INTERVAL_S = 2.0
_POLL_TIMEOUT_S = 20 * 60  # 20 minutes
_TERMINAL = ("completed", "failed")
MAX_IMAGES = 4


class RigydWindow(ui.Window):
    def __init__(self, title: str, **kwargs):
        super().__init__(title, **kwargs)
        self._busy = False
        self._key_model = ui.SimpleStringModel(settings.get_api_key())
        self._prompt_model = ui.SimpleStringModel("")
        self._file_model = ui.SimpleStringModel("")
        self._tris_model = ui.SimpleStringModel("")
        self._image_paths: list = []
        # Widgets assigned in _build(); referenced from async callbacks.
        self._account_label = None
        self._status_label = None
        self._progress_frame = None
        self._bar_fill = None
        self._bar_rest = None
        self._pct_label = None
        self._thumbs = None
        self._img_count_label = None
        self.frame.set_build_fn(self._build)

    # -- UI ----------------------------------------------------------------
    def _build(self):
        with ui.VStack(spacing=8, height=0):
            with ui.HStack(height=22):
                ui.Label("Rigyd  |  SimReady", width=0,
                         style={"font_size": 18, "color": 0xFFCCAA33})
                ui.Spacer()
                self._account_label = ui.Label(
                    "", alignment=ui.Alignment.RIGHT_CENTER, width=0,
                    style={"color": 0xFF9AA0A6})

            with ui.CollapsableFrame("API Key", collapsed=False):
                with ui.VStack(spacing=4):
                    ui.StringField(self._key_model, password_mode=True, height=24)
                    with ui.HStack(spacing=6, height=26):
                        ui.Button("Save key", clicked_fn=self._on_save_key)
                        ui.Button("Test connection",
                                  clicked_fn=lambda: self._run(self._test_connection()))

            with ui.CollapsableFrame("Text to SimReady (2 credits)", collapsed=False):
                with ui.VStack(spacing=4):
                    ui.StringField(self._prompt_model, height=24,
                                   placeholder="e.g. a wooden dining chair")
                    ui.Button("Generate & load",
                              clicked_fn=lambda: self._run(self._generate_prompt()), height=28)

            with ui.CollapsableFrame("Images to SimReady (3 credits)", collapsed=True):
                with ui.VStack(spacing=4):
                    ui.Label("1 image (single view) or 4 images (front, right, "
                             "back, left).", word_wrap=True,
                             style={"color": 0xFF9AA0A6})
                    self._thumbs = ui.HStack(spacing=4, height=60)
                    with ui.HStack(spacing=6, height=24):
                        ui.Button("Add image...", clicked_fn=self._on_add_image)
                        ui.Button("Clear", width=70, clicked_fn=self._on_clear_images)
                        self._img_count_label = ui.Label("0/4", width=40,
                                                         alignment=ui.Alignment.CENTER)
                    ui.Button("Generate & load",
                              clicked_fn=lambda: self._run(self._generate_images()), height=28)

            with ui.CollapsableFrame("3D file to SimReady (1 credit)", collapsed=True):
                with ui.VStack(spacing=4):
                    with ui.HStack(spacing=6, height=24):
                        ui.StringField(self._file_model,
                                       placeholder=".glb/.gltf/.fbx/.obj/.stl/.ply/.usd*")
                        ui.Button("Browse...", width=80, clicked_fn=self._on_browse)
                    with ui.HStack(spacing=6, height=24):
                        ui.Label("Target triangles (optional):", width=160)
                        ui.StringField(self._tris_model, placeholder="1000 - 1000000")
                    ui.Button("Convert & load",
                              clicked_fn=lambda: self._run(self._import_file()), height=28)

            ui.Separator(height=2)
            self._build_progress()
            self._build_status_bar()

        # Show who's signed in / credit balance if a key is already saved.
        if settings.get_api_key():
            self._run(self._refresh_account())

    def _build_progress(self):
        # A custom bar so we control the label ("42%") and can hide it when idle
        # — omni.ui.ProgressBar renders the raw float ("0.0000").
        self._progress_frame = ui.ZStack(height=18, visible=False)
        with self._progress_frame:
            ui.Rectangle(style={"background_color": 0xFF2A2A2A, "border_radius": 3})
            with ui.HStack():
                self._bar_fill = ui.Rectangle(
                    width=ui.Fraction(0.0001),
                    style={"background_color": 0xFFCCAA33, "border_radius": 3})
                self._bar_rest = ui.Spacer(width=ui.Fraction(1))
            self._pct_label = ui.Label("0%", alignment=ui.Alignment.CENTER,
                                       style={"color": 0xFFFFFFFF})

    def _build_status_bar(self):
        # A non-editable, inset bar — reads as status, not a text input.
        with ui.ZStack(height=24):
            ui.Rectangle(style={"background_color": 0xFF1E1E1E,
                                "border_radius": 3, "border_width": 0})
            with ui.HStack():
                ui.Spacer(width=8)
                self._status_label = ui.Label(
                    "Ready.", alignment=ui.Alignment.LEFT_CENTER,
                    style={"color": 0xFFBBBBBB})
                ui.Spacer(width=8)

    # -- helpers -----------------------------------------------------------
    def _client(self) -> RigydClient:
        return RigydClient(settings.get_base_url(), settings.get_api_key())

    def _set_status(self, text: str):
        if self._status_label is not None:
            self._status_label.text = text

    def _set_progress(self, frac: float):
        frac = max(0.0, min(1.0, frac))
        if self._progress_frame is None:
            return
        self._progress_frame.visible = True
        self._bar_fill.width = ui.Fraction(max(frac, 0.0001))
        self._bar_rest.width = ui.Fraction(max(1.0 - frac, 0.0001))
        self._pct_label.text = f"{int(round(frac * 100))}%"

    def _hide_progress(self):
        if self._progress_frame is not None:
            self._progress_frame.visible = False

    def _set_account(self, text: str):
        if self._account_label is not None:
            self._account_label.text = text

    async def _refresh_account(self):
        """Update the header with signed-in user + credit balance (best-effort)."""
        try:
            data = await self._call(self._client().me)
        except RigydError:
            # /me may still be JWT-only until the API change ships — fail quiet.
            self._set_account("")
            return
        user = data.get("user") or {}
        sub = data.get("subscription") or {}
        name = user.get("email") or user.get("username") or ""
        credits = sub.get("credits_remaining")
        if name and credits is not None:
            self._set_account(f"{name}   |   {credits} credits")
        else:
            self._set_account(name)

    def _on_save_key(self):
        settings.set_api_key(self._key_model.get_value_as_string())
        self._set_status("API key saved.")
        self._run(self._refresh_account())

    def _on_browse(self):
        try:
            from omni.kit.window.filepicker import FilePickerDialog

            def _picked(filename: str, dirname: str):
                if filename:
                    self._file_model.set_value(os.path.join(dirname or "", filename))
                dialog.hide()

            dialog = FilePickerDialog(
                "Select a 3D model",
                apply_button_label="Select",
                click_apply_handler=_picked,
            )
            dialog.show()
        except Exception as exc:  # noqa: BLE001 — fall back to manual path entry
            self._set_status(f"File picker unavailable ({exc}); type the path manually.")

    # -- images ------------------------------------------------------------
    _IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

    def _on_add_image(self):
        if len(self._image_paths) >= MAX_IMAGES:
            self._set_status(f"Max {MAX_IMAGES} images.")
            return
        try:
            from omni.kit.window.filepicker import FilePickerDialog

            def _picked(filename: str, dirname: str):
                path = os.path.join(dirname or "", filename or "")
                if filename and os.path.splitext(path)[1].lower() in self._IMG_EXTS:
                    if path not in self._image_paths and len(self._image_paths) < MAX_IMAGES:
                        self._image_paths.append(path)
                        self._rebuild_thumbs()
                        self._set_status(f"{len(self._image_paths)} image(s) selected.")
                elif filename:
                    self._set_status(f"Unsupported image: {os.path.basename(path)}")
                dialog.hide()

            dialog = FilePickerDialog(
                "Select an image", apply_button_label="Add", click_apply_handler=_picked,
            )
            dialog.show()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"File picker unavailable ({exc}).")

    def _on_clear_images(self):
        self._image_paths.clear()
        self._rebuild_thumbs()
        self._set_status("Cleared images.")

    def _rebuild_thumbs(self):
        if self._thumbs is None:
            return
        self._thumbs.clear()
        with self._thumbs:
            for path in self._image_paths:
                ui.Image(path, width=56, height=56,
                         fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
            ui.Spacer()
        if self._img_count_label is not None:
            self._img_count_label.text = f"{len(self._image_paths)}/{MAX_IMAGES}"

    def _run(self, coro: Awaitable):
        if self._busy:
            self._set_status("Busy - wait for the current job to finish.")
            return
        omni.kit.async_engine.run_coroutine(self._guarded(coro))

    async def _guarded(self, coro: Awaitable):
        self._busy = True
        try:
            await coro
        except RigydError as exc:
            self._set_status(f"Error: {exc}")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Unexpected error: {exc}")
        finally:
            self._busy = False
            self._hide_progress()

    async def _call(self, fn: Callable, *args):
        """Run a blocking client call on the executor thread."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(fn, *args))

    # -- flows -------------------------------------------------------------
    async def _test_connection(self):
        self._set_status("Testing...")
        await self._call(self._client().pricing)  # raises if the key is bad
        await self._refresh_account()
        self._set_status("Connected.")

    async def _generate_prompt(self):
        prompt = self._prompt_model.get_value_as_string().strip()
        if not prompt:
            self._set_status("Enter a prompt first.")
            return
        client = self._client()
        self._set_status("Submitting prompt...")
        job = await self._call(client.generate_from_prompt, prompt)
        await self._track_and_load(client, job, label=prompt[:40])

    async def _import_file(self):
        path = self._file_model.get_value_as_string().strip()
        if not path or not os.path.isfile(path):
            self._set_status("Pick a valid 3D file first.")
            return
        tris = self._tris_model.get_value_as_string().strip()
        target = int(tris) if tris.isdigit() else None
        client = self._client()
        self._set_status(f"Uploading {os.path.basename(path)}...")
        job = await self._call(client.create_from_file, path, target)
        await self._track_and_load(client, job, label=os.path.basename(path))

    async def _generate_images(self):
        n = len(self._image_paths)
        if n == 0:
            self._set_status("Add at least one image first.")
            return
        if n not in (1, MAX_IMAGES):
            self._set_status(
                f"Provide exactly 1 image, or {MAX_IMAGES} (front, right, back, left)."
            )
            return
        client = self._client()
        self._set_status(f"Uploading {n} image(s)...")
        job = await self._call(client.generate_from_images, list(self._image_paths))
        label = os.path.splitext(os.path.basename(self._image_paths[0]))[0]
        await self._track_and_load(client, job, label=label)

    # -- poll + load -------------------------------------------------------
    async def _track_and_load(self, client: RigydClient, job: dict, label: str):
        job_id = job.get("id")
        if not job_id:
            self._set_status(f"Unexpected response: {job}")
            return
        self._set_status(f"Queued (job {job_id})...")

        final = await self._poll(client, job_id)
        status = final.get("status")
        if status != "completed":
            self._set_status(f"Job {status}: {final.get('error') or 'no result'}")
            return

        self._set_status("Downloading result...")
        zip_path = os.path.join(tempfile.gettempdir(), f"rigyd_{job_id}.zip")
        await self._call(client.download_result, job_id, zip_path, "usd")

        usd_path = await self._call(loader.unzip_result, zip_path, job_id)
        prim_path = loader.add_usd_to_stage(usd_path, label or "RigydAsset")
        self._set_progress(1.0)
        self._set_status(f"Loaded at {prim_path}")
        await self._refresh_account()  # a credit was spent — refresh the balance

    async def _poll(self, client: RigydClient, job_id: str) -> dict:
        elapsed = 0.0
        last = {}
        while elapsed < _POLL_TIMEOUT_S:
            last = await self._call(client.get_job, job_id)
            status = last.get("status", "")
            progress = last.get("progress") or 0
            stage = last.get("stage") or status
            # Reserve the last 10% for download/load.
            self._set_progress(0.9 * (float(progress) / 100.0))
            self._set_status(f"{status} - {stage} - {progress}%")
            if status in _TERMINAL:
                return last
            await asyncio.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S
        last["status"] = last.get("status") or "timeout"
        return last
