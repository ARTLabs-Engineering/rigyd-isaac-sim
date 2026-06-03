"""Persisted extension settings (API key + base URL).

The API key is stored under carb's ``/persistent/`` namespace, which Kit writes
back to the user config on disk — so it survives across sessions without us
managing our own file.
"""

import carb.settings

_EXT_ID = "rigyd.simready"
_KEY_API_KEY = f"/persistent/exts/{_EXT_ID}/api_key"
_KEY_BASE_URL = f"/exts/{_EXT_ID}/base_url"

_DEFAULT_BASE_URL = "https://api.rigyd.com/api"


def _settings() -> "carb.settings.ISettings":
    return carb.settings.get_settings()


def get_api_key() -> str:
    return _settings().get(_KEY_API_KEY) or ""


def set_api_key(value: str) -> None:
    _settings().set_string(_KEY_API_KEY, (value or "").strip())


def get_base_url() -> str:
    return _settings().get(_KEY_BASE_URL) or _DEFAULT_BASE_URL


def set_base_url(value: str) -> None:
    _settings().set_string(_KEY_BASE_URL, (value or _DEFAULT_BASE_URL).strip())
