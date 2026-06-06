import uuid
import requests
from typing import Optional

_DEVICE_ID = str(uuid.uuid4())
_CLIENT = "DKS JellyLogin"
_VERSION = "1.0.0"


def _auth_header(token: Optional[str] = None) -> str:
    parts = (
        f'MediaBrowser Client="{_CLIENT}", '
        f'Device="Web", '
        f'DeviceId="{_DEVICE_ID}", '
        f'Version="{_VERSION}"'
    )
    if token:
        parts += f', Token="{token}"'
    return parts


class JellyfinError(Exception):
    pass


class JellyfinAuthError(JellyfinError):
    pass


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _get(self, path: str, **kwargs) -> requests.Response:
        return requests.get(
            f"{self.server_url}{path}",
            headers={
                "X-Emby-Authorization": _auth_header(self.api_key),
                "Content-Type": "application/json",
            },
            timeout=kwargs.pop("timeout", 8),
            **kwargs,
        )

    def _post(self, path: str, json: dict, extra_headers: Optional[dict] = None) -> requests.Response:
        headers = {
            "X-Emby-Authorization": _auth_header(),
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        return requests.post(
            f"{self.server_url}{path}",
            json=json,
            headers=headers,
            timeout=10,
        )

    def test_connection(self) -> dict:
        try:
            resp = self._get("/System/Info/Public", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise JellyfinError(f"Verbindung fehlgeschlagen: {exc}") from exc

    def authenticate(self, username: str, password: str) -> dict:
        try:
            resp = self._post(
                "/Users/AuthenticateByName",
                json={"Username": username, "Pw": password},
            )
            if resp.status_code == 401:
                raise JellyfinAuthError("Ungültige Anmeldedaten")
            resp.raise_for_status()
            return resp.json()
        except JellyfinAuthError:
            raise
        except requests.RequestException as exc:
            raise JellyfinError(f"Authentifizierung fehlgeschlagen: {exc}") from exc

    def get_users(self) -> list:
        try:
            resp = self._get("/Users")
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise JellyfinError(f"Benutzerliste konnte nicht abgerufen werden: {exc}") from exc
