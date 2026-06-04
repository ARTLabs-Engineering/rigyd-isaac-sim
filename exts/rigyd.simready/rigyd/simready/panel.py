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


class RigydWindow(ui.Window):
    def __init__(self, title: str, **kwargs):
        super().__init__(title, **kwargs)
        self._busy = False
        self._status_model = ui.SimpleStringModel("Ready.")
        self._progress_model = ui.SimpleFloatModel(0.0)
        self._key_model = ui.SimpleStringModel(settings.get_api_key())
        self._prompt_model = ui.SimpleStringModel("")
        self._file_model = ui.SimpleStringModel("")
        self._tris_model = ui.SimpleStringModel("")
        self.frame.set_build_fn(self._build)

    # -- UI ----------------------------------------------------------------
    def _build(self):
        with ui.VStack(spacing=8, height=0):
            ui.Label("Rigyd  |  SimReady", height=22,
                     style={"font_size": 18, "color": 0xFFCCAA33})

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

            with ui.CollapsableFrame("3D file to SimReady (1 credit)", collapsed=True):
                with ui.VStack(spacing=4):
                    with ui.HStack(spacing=6, height=24):
                        ui.StringField(self._file_model,
                                       placeholder=".glb/.gltf/.fbx/.obj/.stl/.ply/.usd*")
                        ui.Button("Browse…", width=80, clicked_fn=self._on_browse)
                    with ui.HStack(spacing=6, height=24):
                        ui.Label("Target triangles (optional):", width=160)
                        ui.StringField(self._tris_model, placeholder="1000 – 1000000")
                    ui.Button("Convert & load",
                              clicked_fn=lambda: self._run(self._import_file()), height=28)

            ui.Separator(height=2)
            ui.ProgressBar(self._progress_model, height=18)
            ui.Label("", height=0)
            ui.StringField(self._status_model, read_only=True, height=22)

    # -- helpers -----------------------------------------------------------
    def _client(self) -> RigydClient:
        return RigydClient(settings.get_base_url(), settings.get_api_key())

    def _set_status(self, text: str):
        self._status_model.set_value(text)

    def _set_progress(self, frac: float):
        self._progress_model.set_value(max(0.0, min(1.0, frac)))

    def _on_save_key(self):
        settings.set_api_key(self._key_model.get_value_as_string())
        self._set_status("API key saved.")

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

    def _run(self, coro: Awaitable):
        if self._busy:
            self._set_status("Busy — wait for the current job to finish.")
            return
        omni.kit.async_engine.run_coroutine(self._guarded(coro))

    async def _guarded(self, coro: Awaitable):
        self._busy = True
        self._set_progress(0.0)
        try:
            await coro
        except RigydError as exc:
            self._set_status(f"Error: {exc}")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Unexpected error: {exc}")
        finally:
            self._busy = False

    async def _call(self, fn: Callable, *args):
        """Run a blocking client call on the executor thread."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(fn, *args))

    # -- flows -------------------------------------------------------------
    async def _test_connection(self):
        self._set_status("Testing…")
        client = self._client()
        pricing = await self._call(client.pricing)
        self._set_status(f"Connected. Pricing: {pricing}")

    async def _generate_prompt(self):
        prompt = self._prompt_model.get_value_as_string().strip()
        if not prompt:
            self._set_status("Enter a prompt first.")
            return
        client = self._client()
        self._set_status("Submitting prompt…")
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
        self._set_status(f"Uploading {os.path.basename(path)}…")
        job = await self._call(client.create_from_file, path, target)
        await self._track_and_load(client, job, label=os.path.basename(path))

    # -- poll + load -------------------------------------------------------
    async def _track_and_load(self, client: RigydClient, job: dict, label: str):
        job_id = job.get("id")
        if not job_id:
            self._set_status(f"Unexpected response: {job}")
            return
        self._set_status(f"Queued (job {job_id})…")

        final = await self._poll(client, job_id)
        status = final.get("status")
        if status != "completed":
            self._set_status(f"Job {status}: {final.get('error') or 'no result'}")
            return

        self._set_status("Downloading result…")
        zip_path = os.path.join(tempfile.gettempdir(), f"rigyd_{job_id}.zip")
        await self._call(client.download_result, job_id, zip_path, "usd")

        usd_path = await self._call(loader.unzip_result, zip_path, job_id)
        prim_path = loader.add_usd_to_stage(usd_path, label or "RigydAsset")
        self._set_progress(1.0)
        self._set_status(f"Loaded at {prim_path}")

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
