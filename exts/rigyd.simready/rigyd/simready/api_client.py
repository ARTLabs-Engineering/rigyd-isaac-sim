"""Blocking HTTP client for the Rigyd public conversion API.

Dependency-free (stdlib ``urllib`` + a hand-rolled multipart encoder) so the
extension works in any Kit app without bundling ``requests``/``aiohttp``. Every
method blocks, so callers must run them off the UI thread — see ``panel.py``,
which dispatches through ``asyncio``'s default executor.

API surface (verified against api.rigyd.com/src/api/conversion-job):
  POST /conversions                 multipart `file`            -> 202 {data}
  POST /conversions/generate        json {prompt} | multipart images -> 202 {data}
  GET  /conversions/:id             -> {data: {status, progress, stage, output, ...}}
  GET  /conversions/:id/result?format=usd  -> application/zip (Bearer-gated)
  POST /conversions/:id/simulate    -> 202 {data}
  GET  /conversions/pricing         -> {data}
"""

import json
import mimetypes
import os
import uuid
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

_TERMINAL_OK = "completed"
_TERMINAL_FAIL = "failed"


class RigydError(Exception):
    """API/transport error with an optional HTTP status code."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _mime_for(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def _encode_multipart(
    fields: Dict[str, str],
    files: List[tuple],  # (field_name, filename, bytes, content_type)
) -> tuple:
    """Return (body_bytes, content_type_header) for multipart/form-data."""
    boundary = f"----rigyd{uuid.uuid4().hex}"
    crlf = b"\r\n"
    out = bytearray()

    for name, value in fields.items():
        out += b"--" + boundary.encode() + crlf
        out += f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf
        out += str(value).encode() + crlf

    for field_name, filename, data, content_type in files:
        out += b"--" + boundary.encode() + crlf
        out += (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode()
            + crlf
        )
        out += f"Content-Type: {content_type}".encode() + crlf + crlf
        out += data + crlf

    out += b"--" + boundary.encode() + b"--" + crlf
    return bytes(out), f"multipart/form-data; boundary={boundary}"


class RigydClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # -- low-level ---------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[bytes] = None,
        content_type: Optional[str] = None,
        accept_json: bool = True,
    ) -> Any:
        if not self.api_key:
            raise RigydError("No API key configured. Add your rgyd_live_… key first.")

        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if content_type:
            headers["Content-Type"] = content_type
        if accept_json:
            headers["Accept"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if accept_json:
                    return json.loads(raw.decode("utf-8")) if raw else {}
                return raw
        except urllib.error.HTTPError as err:
            detail = self._extract_error(err)
            raise RigydError(detail, status=err.code) from err
        except urllib.error.URLError as err:
            raise RigydError(f"Cannot reach Rigyd API: {err.reason}") from err

    @staticmethod
    def _extract_error(err: "urllib.error.HTTPError") -> str:
        try:
            payload = json.loads(err.read().decode("utf-8"))
            return (
                payload.get("error")
                or (payload.get("data") or {}).get("error")
                or (payload.get("error") or {}).get("message")
                or f"HTTP {err.code}"
            ) if isinstance(payload, dict) else f"HTTP {err.code}"
        except Exception:
            return f"HTTP {err.code} {err.reason}"

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Any:
        return self._request(
            "POST", path, body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )

    # -- endpoints ---------------------------------------------------------
    def pricing(self) -> Dict[str, Any]:
        return self._request("GET", "/conversions/pricing").get("data", {})

    def create_from_file(
        self, file_path: str, target_triangle_count: Optional[int] = None
    ) -> Dict[str, Any]:
        with open(file_path, "rb") as fh:
            data = fh.read()
        fields: Dict[str, str] = {}
        if target_triangle_count is not None:
            fields["optimize"] = "true"
            fields["target_triangle_count"] = str(int(target_triangle_count))
        files = [("file", os.path.basename(file_path), data, _mime_for(file_path))]
        body, ctype = _encode_multipart(fields, files)
        return self._request("POST", "/conversions", body=body, content_type=ctype).get("data", {})

    def generate_from_prompt(self, prompt: str) -> Dict[str, Any]:
        return self._post_json("/conversions/generate", {"prompt": prompt}).get("data", {})

    def generate_from_images(self, image_paths: List[str]) -> Dict[str, Any]:
        files = []
        for p in image_paths:
            with open(p, "rb") as fh:
                files.append(("images", os.path.basename(p), fh.read(), _mime_for(p)))
        body, ctype = _encode_multipart({}, files)
        return self._request("POST", "/conversions/generate", body=body, content_type=ctype).get("data", {})

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/conversions/{job_id}").get("data", {})

    def simulate(self, job_id: str, scene: Optional[str] = None) -> Dict[str, Any]:
        payload = {"scene": scene} if scene else {}
        return self._post_json(f"/conversions/{job_id}/simulate", payload).get("data", {})

    def download_result(self, job_id: str, dest_zip_path: str, fmt: str = "usd") -> str:
        """Download the result ZIP (Bearer-gated) to ``dest_zip_path``."""
        raw = self._request(
            "GET", f"/conversions/{job_id}/result?format={fmt}", accept_json=False
        )
        with open(dest_zip_path, "wb") as fh:
            fh.write(raw)
        return dest_zip_path
