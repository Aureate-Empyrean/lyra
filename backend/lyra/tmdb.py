"""TMDB API v3 client: an explicitly invoked external metadata provider (ADR 0013).

Only search text, provider IDs, language and region are sent; never library or watch data.
The credential stays on the server and is never logged or returned."""

import json
import os
import re
import threading
import time
from pathlib import Path

import httpx

API = "https://api.themoviedb.org/3"
IMAGES = "https://image.tmdb.org/t/p"
IMAGE_SIZES = {"w92", "w154", "w185", "w300", "w342", "w500", "w780"}
IMAGE_PATH = re.compile(r"^/[A-Za-z0-9_-]{1,80}\.(jpg|jpeg|png)$")
ATTRIBUTION = "This product uses the TMDB API but is not endorsed or certified by TMDB."
MAX_IMAGE = 1024 * 1024


class TMDBError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class Credential:
    """Write-only storage for the TMDB credential in the data volume (mode 0600)."""

    def __init__(self, directory: Path):
        self.path = directory / "secrets" / "tmdb.json"

    def get(self):
        try:
            value = json.loads(self.path.read_text())
            return value if value.get("value") else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def kind_of(value: str) -> str:
        value = value.strip()
        if re.fullmatch(r"[0-9a-f]{32}", value):
            return "api_key"
        if (
            re.fullmatch(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", value)
            and len(value) < 2000
        ):
            return "bearer"
        raise TMDBError("This does not look like a TMDB API key or read access token.", 422)

    def set(self, value: str):
        value = value.strip()
        kind = self.kind_of(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(".part")
        temporary.write_text(json.dumps({"kind": kind, "value": value}))
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        return kind

    def clear(self):
        self.path.unlink(missing_ok=True)


class TMDB:
    def __init__(self, credential: Credential, transport=None):
        self.credential = credential
        self.transport = transport
        self.slots = threading.BoundedSemaphore(4)
        self.cache = {}
        self.cache_lock = threading.Lock()

    def configured(self) -> bool:
        return self.credential.get() is not None

    def _client(self):
        return httpx.Client(
            transport=self.transport,
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        )

    def get(self, path, params=None, *, credential=None, cache_seconds=0):
        secret = credential or self.credential.get()
        if not secret:
            raise TMDBError(
                "Add a TMDB credential in Lyra's settings to search and load details.", 409
            )
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        key = (path, tuple(sorted(params.items())))
        if cache_seconds:
            with self.cache_lock:
                hit = self.cache.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
        headers = {"Accept": "application/json"}
        if secret["kind"] == "bearer":
            headers["Authorization"] = "Bearer " + secret["value"]
        else:
            params["api_key"] = secret["value"]
        for attempt in range(3):
            with self.slots:
                try:
                    with self._client() as client:
                        response = client.get(API + path, params=params, headers=headers)
                except httpx.TimeoutException as exc:
                    raise TMDBError("TMDB did not respond in time.") from exc
                except httpx.HTTPError as exc:
                    raise TMDBError("TMDB could not be reached.") from exc
            if response.status_code == 429 and attempt < 2:
                wait = response.headers.get("retry-after", "1")
                time.sleep(min(5.0, float(wait) if wait.replace(".", "", 1).isdigit() else 1.0))
                continue
            break
        if response.status_code == 401:
            raise TMDBError("TMDB rejected the credential. Check it in Lyra's settings.", 401)
        if response.status_code == 404:
            raise TMDBError("TMDB has no such title.", 404)
        if response.status_code == 429:
            raise TMDBError("TMDB is limiting requests. Try again in a moment.", 429)
        if response.status_code != 200:
            raise TMDBError(f"TMDB answered with HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as exc:
            raise TMDBError("TMDB sent an unreadable response.") from exc
        if cache_seconds:
            with self.cache_lock:
                if len(self.cache) > 500:
                    self.cache.clear()
                self.cache[key] = (time.monotonic() + cache_seconds, data)
        return data

    def verify(self, value: str):
        """Check a credential before storing it; returns its kind."""
        kind = Credential.kind_of(value)
        self.get("/configuration", credential={"kind": kind, "value": value.strip()})
        return kind

    # Typed calls -------------------------------------------------------

    def search(self, query, language, page=1):
        return self.get(
            "/search/multi",
            {"query": query[:200], "language": language, "page": page, "include_adult": "false"},
            cache_seconds=600,
        )

    def movie(self, tmdb_id, language):
        return self.get(
            f"/movie/{int(tmdb_id)}",
            {"language": language, "append_to_response": "credits,release_dates,external_ids"},
        )

    def tv(self, tmdb_id, language, seasons=()):
        append = ["credits", "external_ids"] + [f"season/{n}" for n in seasons]
        return self.get(
            f"/tv/{int(tmdb_id)}",
            {"language": language, "append_to_response": ",".join(append[:20])},
        )

    def season(self, tmdb_id, number, language):
        return self.get(f"/tv/{int(tmdb_id)}/season/{int(number)}", {"language": language})

    def trending(self, language):
        return self.get("/trending/all/week", {"language": language}, cache_seconds=1800)

    def upcoming(self, language, region):
        return self.get(
            "/movie/upcoming", {"language": language, "region": region}, cache_seconds=1800
        )

    def on_the_air(self, language):
        return self.get("/tv/on_the_air", {"language": language}, cache_seconds=1800)

    def image(self, size, path):
        if size not in IMAGE_SIZES or not IMAGE_PATH.fullmatch(path or ""):
            raise TMDBError("Invalid image", 422)
        try:
            with self._client() as client, client.stream("GET", f"{IMAGES}/{size}{path}") as r:
                if r.status_code != 200:
                    raise TMDBError("Image unavailable", 404)
                media = r.headers.get("content-type", "")
                if media not in {"image/jpeg", "image/png"}:
                    raise TMDBError("Unexpected image type", 502)
                data = bytearray()
                for chunk in r.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE:
                        raise TMDBError("Image too large", 502)
                return media, bytes(data)
        except httpx.HTTPError as exc:
            raise TMDBError("Image unavailable") from exc
