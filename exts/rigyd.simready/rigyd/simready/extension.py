"""Extension entry point: own the window + a Window-menu toggle."""

from __future__ import annotations

import carb
import omni.ext
import omni.ui as ui

from .panel import RigydWindow

_WINDOW_TITLE = "Rigyd"
_MENU_GROUP = "Window"


class RigydSimReadyExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        carb.log_info(f"[rigyd.simready] startup ({ext_id})")
        self._window: RigydWindow | None = RigydWindow(
            _WINDOW_TITLE, width=440, height=580
        )

        # Let the standard Window menu re-open the panel after it's closed.
        ui.Workspace.set_show_window_fn(_WINDOW_TITLE, self._show_window)
        self._menu = None
        try:
            from omni.kit.menu.utils import MenuItemDescription, add_menu_items

            self._menu = [
                MenuItemDescription(
                    name=_WINDOW_TITLE,
                    ticked=True,
                    ticked_fn=self._is_visible,
                    onclick_fn=self._toggle_window,
                )
            ]
            add_menu_items(self._menu, _MENU_GROUP)
        except Exception as exc:  # noqa: BLE001 — menu is a nicety, not required
            carb.log_warn(f"[rigyd.simready] could not register Window menu: {exc}")

    def on_shutdown(self):
        carb.log_info("[rigyd.simready] shutdown")
        if self._menu is not None:
            try:
                from omni.kit.menu.utils import remove_menu_items

                remove_menu_items(self._menu, _MENU_GROUP)
            except Exception:  # noqa: BLE001
                pass
            self._menu = None
        ui.Workspace.set_show_window_fn(_WINDOW_TITLE, None)
        if self._window is not None:
            self._window.destroy()
            self._window = None

    # -- window plumbing ---------------------------------------------------
    def _is_visible(self) -> bool:
        return bool(self._window and self._window.visible)

    def _show_window(self, _visible: bool = True):
        if self._window is None:
            self._window = RigydWindow(_WINDOW_TITLE, width=440, height=580)
        self._window.visible = True

    def _toggle_window(self, *_args):
        if self._window is not None:
            self._window.visible = not self._window.visible
