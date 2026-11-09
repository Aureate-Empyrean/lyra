import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from lyra import VERSION
from lyra.db import MIGRATIONS, Database
from lyra.library import (
    ENDED,
    MOVIE_STATUSES,
    SERIES_STATUSES,
    certainty,
    dated_items,
    dates_signature,
    mapped,
    movie_releases,
    next_episode,
    now_iso,
    progress,
    reference,
    regular_episodes,
    upsert_movie,
    upsert_series,
    uuid7,
    watched_episodes,
)
from lyra.tmdb import ATTRIBUTION, TMDB, Credential, TMDBError

ROOT = Path(__file__).resolve().parents[2]
REF = re.compile(
    r"^nexus:v1:([a-z][a-z0-9-]{0,47}):([a-z][a-z0-9-]{0,47}):([a-zA-Z0-9][a-zA-Z0-9._~-]{0,127})$"
)
BACKUP_FORMAT = "lyra-sqlite"
BACKUP_FORMAT_VERSION = 1
BACKUP_HEADER = "X-Empyrean-Backup-"
MAX_ARTIFACT = 256 * 1024 * 1024
DEFAULT_SETTINGS = {
    "region": "US",
    "language": "en-US",
    "defaults_set": False,
    "calendar_episodes": "watching",
    "calendar_premieres_only": False,
    "calendar_movies": "watchlist",
}
FIRST_SEASONS = 18  # append_to_response allows 20 items; credits and external_ids take two
PAGE = 500
STALE = {"watching": 12 * 3600, "planned": 24 * 3600, "on_hold": 3 * 86400}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsBody(Strict):
    region: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    calendar_episodes: str | None = Field(
        default=None, pattern=r"^(watching|tracked|selected|none)$"
    )
    calendar_premieres_only: bool | None = None
    calendar_movies: str | None = Field(default=None, pattern=r"^(watchlist|none)$")


class CredentialBody(Strict):
    value: str = Field(min_length=20, max_length=2000)


class AddBody(Strict):
    kind: str = Field(pattern=r"^(movie|tv)$")
    tmdb_id: int = Field(ge=1)
    status: str = "planned"


class EntryPatch(Strict):
    status: str | None = None
    rating: int | None = Field(default=None, ge=0, le=10)
    notes: str | None = Field(default=None, max_length=10000)
    calendar: str | None = Field(default=None, pattern=r"^(default|always|never)$")


class WatchBody(Strict):
    watched_at: str | None = Field(default=None, max_length=40)


class ImagesBody(Strict):
    keys: list[str] = Field(max_length=24)


def styles():
    font = base64.b64encode((ROOT / "frontend/fonts/Roboto.woff2").read_bytes()).decode()
    face = (
        '@font-face{font-family:"Roboto";src:url(data:font/woff2;base64,'
        + font
        + ') format("woff2");font-weight:100 900;font-stretch:75% 100%;font-display:swap}'
    )
    return "\n".join(
        [
            (ROOT / "frontend/aureate-tokens.css").read_text(encoding="utf-8"),
            (ROOT / "frontend/aureate-foundation.css").read_text(encoding="utf-8"),
            face,
            (ROOT / "frontend/style.css").read_text(encoding="utf-8"),
        ]
    )


class Nexus:
    def __init__(self, transport=None):
        self.transport = transport

    def request(self, method, path, body=None, params=None):
        with httpx.Client(transport=self.transport, timeout=8, trust_env=False) as client:
            response = client.request(
                method,
                os.environ["NEXUS_URL"] + "/api/v1/module" + path,
                headers={"Authorization": "Bearer " + os.environ["NEXUS_TOKEN"]},
                json=body,
                params=params,
            )
            response.raise_for_status()
            return response.json()


def create_app(data_dir=None, nexus=None, tmdb_transport=None, clock=None, workers=True):
    clock = clock or (lambda: datetime.now(timezone.utc))
    data = Path(data_dir or os.getenv("LYRA_DATA", "/data"))
    db = Database(data / "lyra.sqlite3")
    images = data / "images"
    images.mkdir(parents=True, exist_ok=True)
    credential = Credential(data)
    tmdb = TMDB(credential, tmdb_transport)
    nexus = nexus or Nexus()
    stop = threading.Event()
    style = styles()
    pool = ThreadPoolExecutor(6)

    def today():
        return clock().date().isoformat()

    def settings():
        with db.connect() as conn:
            stored = {
                r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM settings")
            }
        return {**DEFAULT_SETTINGS, **stored}

    def announce(conn):
        """Hint for Chronos; consumers reconcile through the projection either way."""
        if not conn.execute("SELECT 1 FROM outbox WHERE path='/events'").fetchone():
            conn.execute(
                "INSERT INTO outbox(method,path,body) VALUES('POST','/events',?)",
                (json.dumps({"type": "lyra.dated-items.changed", "payload": {}}),),
            )

    # ── Provider refresh ─────────────────────────────────────────────

    def fetch_series(tmdb_id, first_only=False):
        language = settings()["language"]
        details = tmdb.tv(tmdb_id, language, range(1, FIRST_SEASONS + 1))
        numbers = sorted(
            s["season_number"]
            for s in details.get("seasons", [])
            if isinstance(s.get("season_number"), int)
        )
        seasons = {n: details[f"season/{n}"] for n in numbers if f"season/{n}" in details}
        missing = [n for n in numbers if n not in seasons]
        if first_only:
            return details, seasons, not missing
        for start in range(0, len(missing), 20):
            chunk = missing[start : start + 20]
            extra = tmdb.get(
                f"/tv/{int(tmdb_id)}",
                {
                    "language": language,
                    "append_to_response": ",".join(f"season/{n}" for n in chunk),
                },
            )
            seasons.update({n: extra[f"season/{n}"] for n in chunk if f"season/{n}" in extra})
        return details, seasons, len(seasons) == len(numbers)

    def refresh(resource_type, resource_id):
        with db.connect() as conn:
            tmdb_id = conn.execute(
                "SELECT external_id FROM external_ids WHERE provider='tmdb' AND resource_type=? AND resource_id=?",
                (resource_type, resource_id),
            ).fetchone()
        if not tmdb_id:
            return
        if resource_type == "movie":
            details = tmdb.movie(tmdb_id[0], settings()["language"])
            with db.connect() as conn:
                before = dates_signature(conn, movie_id=resource_id)
                upsert_movie(conn, details)
                if dates_signature(conn, movie_id=resource_id) != before:
                    announce(conn)
            return
        details, seasons, complete = fetch_series(tmdb_id[0])
        with db.connect() as conn:
            before = dates_signature(conn, series_id=resource_id)
            upsert_series(conn, details, seasons, complete)
            if dates_signature(conn, series_id=resource_id) != before:
                announce(conn)

    def due_refreshes():
        with db.connect() as conn:
            rows = [
                ("series", r["id"])
                for r in conn.execute("SELECT id FROM series WHERE refresh_requested=1")
            ] + [
                ("movie", r["id"])
                for r in conn.execute("SELECT id FROM movies WHERE refresh_requested=1")
            ]
            if rows:
                return rows
            stamp = clock()
            for row in conn.execute(
                "SELECT s.id,s.refreshed_at,s.provider_status,l.status FROM series s JOIN library l "
                "ON l.resource_type='series' AND l.resource_id=s.id"
            ):
                limit = STALE.get(row["status"], 7 * 86400)
                if row["provider_status"] in ENDED and row["status"] != "watching":
                    limit = 14 * 86400
                if (
                    not row["refreshed_at"]
                    or (stamp - _parse(row["refreshed_at"])).total_seconds() > limit
                ):
                    return [("series", row["id"])]
            for row in conn.execute(
                "SELECT m.id,m.refreshed_at,m.release_date FROM movies m JOIN library l "
                "ON l.resource_type='movie' AND l.resource_id=m.id"
            ):
                upcoming = not row["release_date"] or row["release_date"] >= today()
                limit = 86400 if upcoming else 30 * 86400
                if (
                    not row["refreshed_at"]
                    or (stamp - _parse(row["refreshed_at"])).total_seconds() > limit
                ):
                    return [("movie", row["id"])]
        return []

    def flush():
        with db.connect() as conn:
            entries = conn.execute(
                "SELECT * FROM outbox WHERE next_attempt<=? ORDER BY id LIMIT 20", (time.time(),)
            ).fetchall()
        for entry in entries:
            try:
                nexus.request(
                    entry["method"],
                    entry["path"],
                    json.loads(entry["body"]) if entry["body"] else None,
                )
            except (httpx.HTTPError, KeyError, OSError):
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE outbox SET attempts=attempts+1,next_attempt=? WHERE id=?",
                        (time.time() + min(300, 2 ** min(entry["attempts"] + 1, 8)), entry["id"]),
                    )
                continue
            with db.connect() as conn:
                conn.execute("DELETE FROM outbox WHERE id=?", (entry["id"],))

    def tick():
        if tmdb.configured() and not (data / "refresh-suspended").exists():
            for resource_type, resource_id in due_refreshes()[:3]:
                try:
                    refresh(resource_type, resource_id)
                except TMDBError as exc:
                    with db.connect() as conn:
                        # Keep the data; try again later rather than hammering the provider.
                        table = "series" if resource_type == "series" else "movies"
                        conn.execute(
                            f"UPDATE {table} SET refresh_requested=0,refreshed_at=? WHERE id=?",
                            (now_iso(), resource_id),
                        )
                    print(f"Metadata refresh failed: {exc.status}", flush=True)
        if "NEXUS_TOKEN" in os.environ:
            flush()

    def loop():
        while not stop.wait(3):
            try:
                tick()
            except Exception as exc:
                print(f"Background work failed: {type(exc).__name__}", flush=True)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=loop, daemon=True) if workers else None
        if thread:
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=5)
        pool.shutdown(wait=False)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.state.tick = tick
    app.state.refresh = refresh
    app.state.flush = flush

    @app.middleware("http")
    async def trusted_gateway(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            key = os.getenv("NEXUS_RESOLVER_KEY", "")
            if not key or not secrets.compare_digest(
                request.headers.get("x-nexus-gateway-key", ""), key
            ):
                return JSONResponse({"detail": "Nexus gateway required"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(TMDBError)
    async def provider_error(request, exc: TMDBError):
        return JSONResponse(
            {"detail": str(exc), "provider": "tmdb"},
            status_code=exc.status if exc.status in {401, 404, 409, 422, 429} else 502,
        )

    # ── Serialization ────────────────────────────────────────────────

    def image_key(size, path):
        return f"{size}{path}" if path else None

    def entry(conn, resource_type, resource_id):
        row = conn.execute(
            "SELECT * FROM library WHERE resource_type=? AND resource_id=?",
            (resource_type, resource_id),
        ).fetchone()
        return dict(row) if row else None

    def external(conn, resource_type, resource_id):
        return {
            f"{r['provider']}": r["external_id"]
            for r in conn.execute(
                "SELECT provider,external_id FROM external_ids WHERE resource_type=? AND resource_id=?",
                (resource_type, resource_id),
            )
        }

    def history_for(conn, resource_type, ids):
        if not ids:
            return {}
        result = {}
        for r in conn.execute(
            f"SELECT * FROM history WHERE resource_type=? AND resource_id IN ({','.join('?' * len(ids))}) ORDER BY watched_at DESC",
            (resource_type, *ids),
        ):
            result.setdefault(r["resource_id"], []).append(
                {"id": r["id"], "watched_at": r["watched_at"]}
            )
        return result

    def card(conn, resource_type, row):
        value = {
            "type": resource_type,
            "id": row["id"],
            "title": row["title"],
            "year": (
                row["release_date"] if resource_type == "movie" else row["first_air_date"] or ""
            )[:4]
            or None,
            "poster": image_key("w342", row["poster_path"]),
            "library": entry(conn, resource_type, row["id"]),
        }
        if resource_type == "series":
            value["progress"] = progress(conn, row["id"], today())
            value["provider_status"] = row["provider_status"]
        return value

    def movie_json(conn, movie_id):
        row = conn.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Movie not found")
        region = settings()["region"]
        history = history_for(conn, "movie", [movie_id]).get(movie_id, [])
        return {
            "type": "movie",
            "id": movie_id,
            "reference": reference("movie", movie_id),
            "title": row["title"],
            "original_title": row["original_title"],
            "year": (row["release_date"] or "")[:4] or None,
            "overview": row["overview"],
            "tagline": row["tagline"],
            "runtime": row["runtime"],
            "genres": json.loads(row["genres"]),
            "poster": image_key("w342", row["poster_path"]),
            "backdrop": image_key("w780", row["backdrop_path"]),
            "provider_status": row["provider_status"],
            "credits": json.loads(row["credits"]),
            "release_date": row["release_date"],
            "releases": [
                {"kind": k, "date": d, "certainty": certainty(d, today(), est)}
                for k, d, est in movie_releases(row, region)
            ],
            "region": region,
            "external": external(conn, "movie", movie_id),
            "library": entry(conn, "movie", movie_id),
            "history": history,
            "refreshed_at": row["refreshed_at"],
            "refreshing": bool(row["refresh_requested"]),
        }

    def series_json(conn, series_id):
        row = conn.execute("SELECT * FROM series WHERE id=?", (series_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Series not found")
        now = today()
        seen = watched_episodes(conn, series_id)
        episodes = conn.execute(
            "SELECT * FROM episodes WHERE series_id=? AND missing=0 ORDER BY season_number,episode_number",
            (series_id,),
        ).fetchall()
        history = history_for(conn, "episode", [e["id"] for e in episodes if e["id"] in seen])
        by_season = {}
        for e in episodes:
            by_season.setdefault(e["season_id"], []).append(
                {
                    "id": e["id"],
                    "number": e["episode_number"],
                    "season": e["season_number"],
                    "name": e["name"],
                    "overview": e["overview"][:400],
                    "air_date": e["air_date"],
                    "runtime": e["runtime"],
                    "watched": e["id"] in seen,
                    "watched_at": (history.get(e["id"]) or [{}])[0].get("watched_at"),
                    "state": "unannounced"
                    if not e["air_date"]
                    else "aired"
                    if e["air_date"] <= now
                    else "upcoming",
                }
            )
        seasons = []
        for s in conn.execute(
            "SELECT * FROM seasons WHERE series_id=? AND missing=0 ORDER BY season_number=0, season_number",
            (series_id,),
        ):
            eps = by_season.get(s["id"], [])
            seasons.append(
                {
                    "id": s["id"],
                    "number": s["season_number"],
                    "name": s["name"],
                    "air_date": s["air_date"]
                    or min((e["air_date"] for e in eps if e["air_date"]), default=None),
                    "poster": image_key("w185", s["poster_path"]),
                    "episode_count": s["episode_count"],
                    "watched": sum(1 for e in eps if e["watched"]),
                    "aired": sum(1 for e in eps if e["state"] == "aired"),
                    "episodes": eps,
                }
            )
        upcoming = [
            e for e in regular_episodes(conn, series_id) if e["air_date"] and e["air_date"] > now
        ]
        return {
            "type": "series",
            "id": series_id,
            "reference": reference("series", series_id),
            "title": row["title"],
            "original_title": row["original_title"],
            "year": (row["first_air_date"] or "")[:4] or None,
            "overview": row["overview"],
            "tagline": row["tagline"],
            "genres": json.loads(row["genres"]),
            "networks": json.loads(row["networks"]),
            "poster": image_key("w342", row["poster_path"]),
            "backdrop": image_key("w780", row["backdrop_path"]),
            "provider_status": row["provider_status"],
            "in_production": bool(row["in_production"]),
            "first_air_date": row["first_air_date"],
            "last_air_date": row["last_air_date"],
            "episode_runtime": row["episode_runtime"],
            "credits": json.loads(row["credits"]),
            "external": external(conn, "series", series_id),
            "library": entry(conn, "series", series_id),
            "progress": progress(conn, series_id, now),
            "next": next_episode(conn, series_id, now),
            "next_air": dict(upcoming[0]) if upcoming else None,
            "seasons": seasons,
            "refreshed_at": row["refreshed_at"],
            "refreshing": bool(row["refresh_requested"]),
        }

    def remote_card(item, conn):
        kind = item.get("media_type") or (
            "tv" if item.get("first_air_date") is not None and "title" not in item else "movie"
        )
        if kind not in {"movie", "tv"}:
            return None
        resource_type = "movie" if kind == "movie" else "series"
        resource_id = mapped(conn, "tmdb", kind, item["id"])
        return {
            "kind": kind,
            "tmdb_id": item["id"],
            "title": item.get("title") or item.get("name") or "Untitled",
            "year": (item.get("release_date") or item.get("first_air_date") or "")[:4] or None,
            "overview": (item.get("overview") or "")[:400],
            "poster": image_key("w342", item.get("poster_path")),
            "resource": {"type": resource_type, "id": resource_id} if resource_id else None,
            "library": entry(conn, resource_type, resource_id) if resource_id else None,
        }

    # ── Application API ──────────────────────────────────────────────

    @app.get("/health")
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "version": VERSION}

    @app.get("/api/state")
    def state():
        secret = credential.get()
        with db.connect() as conn:
            counts = {
                "movies": conn.execute(
                    "SELECT count(*) FROM library WHERE resource_type='movie'"
                ).fetchone()[0],
                "series": conn.execute(
                    "SELECT count(*) FROM library WHERE resource_type='series'"
                ).fetchone()[0],
            }
        return {
            "version": VERSION,
            "settings": settings(),
            "tmdb": {"configured": bool(secret), "kind": secret["kind"] if secret else None},
            "attribution": ATTRIBUTION,
            "library": counts,
        }

    @app.put("/api/settings")
    def put_settings(body: SettingsBody):
        changes = body.model_dump(exclude_none=True)
        if {"region", "language"} & set(changes):
            changes["defaults_set"] = True
        with db.connect() as conn:
            for key, value in changes.items():
                conn.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)),
                )
            if {"region", "calendar_episodes", "calendar_premieres_only", "calendar_movies"} & set(
                changes
            ):
                announce(conn)
        return settings()

    @app.put("/api/credential")
    def put_credential(body: CredentialBody):
        kind = tmdb.verify(body.value)  # raises 401 if TMDB rejects it
        credential.set(body.value)
        return {"configured": True, "kind": kind}

    @app.delete("/api/credential")
    def delete_credential():
        credential.clear()
        return {"configured": False}

    @app.get("/api/home")
    def home():
        now = today()
        horizon = (date.fromisoformat(now) + timedelta(days=60)).isoformat()
        with db.connect() as conn:
            watching = []
            for row in conn.execute(
                "SELECT s.* FROM series s JOIN library l ON l.resource_type='series' AND l.resource_id=s.id "
                "WHERE l.status='watching' ORDER BY l.updated_at DESC"
            ).fetchall():
                watching.append(
                    {
                        **card(conn, "series", row),
                        "next": next_episode(conn, row["id"], now),
                        "backdrop": image_key("w780", row["backdrop_path"]),
                    }
                )
            watching.sort(
                key=lambda c: (
                    not (c["next"] and c["next"]["state"] == "available"),
                    c["next"]["air_date"] if c["next"] and c["next"]["air_date"] else "9999",
                )
            )
            upcoming = []
            for row in conn.execute(
                "SELECT e.*, s.title AS series_title, s.poster_path FROM episodes e JOIN series s ON s.id=e.series_id "
                "JOIN library l ON l.resource_type='series' AND l.resource_id=s.id WHERE l.status!='dropped' "
                "AND e.season_number>0 AND e.missing=0 AND e.air_date>? AND e.air_date<=? ORDER BY e.air_date LIMIT 40",
                (now, horizon),
            ):
                upcoming.append(
                    {
                        "type": "episode",
                        "id": row["id"],
                        "series_id": row["series_id"],
                        "title": row["series_title"],
                        "label": f"S{row['season_number']}E{row['episode_number']}",
                        "name": row["name"],
                        "date": row["air_date"],
                        "certainty": "tentative",
                        "poster": image_key("w185", row["poster_path"]),
                    }
                )
            region = settings()["region"]
            for row in conn.execute(
                "SELECT m.* FROM movies m JOIN library l ON l.resource_type='movie' AND l.resource_id=m.id WHERE l.status='planned'"
            ):
                for kind, value, est in movie_releases(row, region):
                    if now < value <= horizon:
                        upcoming.append(
                            {
                                "type": "movie",
                                "id": row["id"],
                                "title": row["title"],
                                "label": kind,
                                "date": value,
                                "certainty": certainty(value, now, est),
                                "poster": image_key("w185", row["poster_path"]),
                            }
                        )
            upcoming.sort(key=lambda u: u["date"])
            recent = []
            for h in conn.execute("SELECT * FROM history ORDER BY watched_at DESC LIMIT 12"):
                recent.append(history_entry(conn, h))
            return {
                "watching": watching,
                "upcoming": upcoming[:30],
                "recent": [r for r in recent if r],
            }

    def history_entry(conn, h):
        if h["resource_type"] == "movie":
            m = conn.execute(
                "SELECT id,title,poster_path FROM movies WHERE id=?", (h["resource_id"],)
            ).fetchone()
            return m and {
                "id": h["id"],
                "watched_at": h["watched_at"],
                "type": "movie",
                "resource_id": m["id"],
                "title": m["title"],
                "poster": image_key("w185", m["poster_path"]),
            }
        e = conn.execute(
            "SELECT e.*, s.title AS series_title, s.poster_path FROM episodes e JOIN series s ON s.id=e.series_id WHERE e.id=?",
            (h["resource_id"],),
        ).fetchone()
        return e and {
            "id": h["id"],
            "watched_at": h["watched_at"],
            "type": "episode",
            "resource_id": e["series_id"],
            "episode_id": e["id"],
            "title": e["series_title"],
            "label": f"S{e['season_number']}E{e['episode_number']}",
            "name": e["name"],
            "poster": image_key("w185", e["poster_path"]),
        }

    @app.get("/api/library")
    def library(type: str = "series"):
        if type not in {"series", "movie"}:
            raise HTTPException(422, "Unknown library")
        table = "series" if type == "series" else "movies"
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT t.* FROM {table} t JOIN library l ON l.resource_type=? AND l.resource_id=t.id ORDER BY l.updated_at DESC",
                (type,),
            ).fetchall()
            return {"items": [card(conn, type, r) for r in rows]}

    @app.get("/api/history")
    def history(limit: int = 50, before: str = "9999"):
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM history WHERE watched_at<? ORDER BY watched_at DESC LIMIT ?",
                (before, max(1, min(limit, 200))),
            ).fetchall()
            return {"entries": [e for e in (history_entry(conn, h) for h in rows) if e]}

    @app.delete("/api/history/{hid}")
    def delete_history(hid: str):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM history WHERE id=?", (hid,)).fetchone()
            if not row:
                raise HTTPException(404, "History entry not found")
            conn.execute("DELETE FROM history WHERE id=?", (hid,))
            if (
                row["resource_type"] == "movie"
                and not conn.execute(
                    "SELECT 1 FROM history WHERE resource_type='movie' AND resource_id=?",
                    (row["resource_id"],),
                ).fetchone()
            ):
                conn.execute(
                    "UPDATE library SET status='planned',updated_at=? WHERE resource_type='movie' AND resource_id=?",
                    (now_iso(), row["resource_id"]),
                )
        return {"deleted": True}

    @app.get("/api/search")
    def search(q: str):
        query = q.strip()[:200]
        if len(query) < 2:
            return {"local": [], "remote": [], "remote_error": None}
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with db.connect() as conn:
            local = [
                card(conn, t, r)
                for t, table in (("series", "series"), ("movie", "movies"))
                for r in conn.execute(
                    f"SELECT t.* FROM {table} t JOIN library l ON l.resource_type=? AND l.resource_id=t.id "
                    "WHERE t.title LIKE ? ESCAPE '\\' OR t.original_title LIKE ? ESCAPE '\\' LIMIT 20",
                    (t, pattern, pattern),
                )
            ]
        remote, error = [], None
        if tmdb.configured():
            try:
                results = tmdb.search(query, settings()["language"]).get("results", [])
                with db.connect() as conn:
                    remote = [c for c in (remote_card(r, conn) for r in results) if c]
            except TMDBError as exc:
                error = str(exc)
        else:
            error = "not_configured"
        return {"local": local, "remote": remote, "remote_error": error}

    @app.get("/api/discover")
    def discover():
        if not tmdb.configured():
            return {"configured": False, "sections": []}
        s = settings()
        sections = []
        for key, call in (
            ("trending", lambda: tmdb.trending(s["language"])),
            ("upcoming", lambda: tmdb.upcoming(s["language"], s["region"])),
            ("on_the_air", lambda: tmdb.on_the_air(s["language"])),
        ):
            try:
                results = call().get("results", [])[:18]
            except TMDBError as exc:
                sections.append({"key": key, "items": [], "error": str(exc)})
                continue
            with db.connect() as conn:
                items = []
                for r in results:
                    if key == "upcoming":
                        r = {**r, "media_type": "movie"}
                    if key == "on_the_air":
                        r = {**r, "media_type": "tv"}
                    card_value = remote_card(r, conn)
                    if card_value:
                        items.append(card_value)
            sections.append({"key": key, "items": items})
        return {"configured": True, "sections": sections}

    @app.get("/api/preview/{kind}/{tmdb_id}")
    def preview(kind: str, tmdb_id: int):
        """A title's details before it is in the library; nothing is stored."""
        if kind not in {"movie", "tv"}:
            raise HTTPException(404, "Unknown kind")
        with db.connect() as conn:
            resource_id = mapped(conn, "tmdb", kind, tmdb_id)
        if resource_id:
            return {
                "resource": {"type": "movie" if kind == "movie" else "series", "id": resource_id}
            }
        language = settings()["language"]
        data = tmdb.movie(tmdb_id, language) if kind == "movie" else tmdb.tv(tmdb_id, language)
        cast = [c.get("name") for c in (data.get("credits") or {}).get("cast", [])[:8]]
        return {
            "preview": {
                "kind": kind,
                "tmdb_id": tmdb_id,
                "title": data.get("title") or data.get("name"),
                "year": (data.get("release_date") or data.get("first_air_date") or "")[:4] or None,
                "overview": data.get("overview") or "",
                "tagline": data.get("tagline") or "",
                "genres": [g.get("name") for g in data.get("genres", [])],
                "runtime": data.get("runtime") or ((data.get("episode_run_time") or [None])[0]),
                "poster": image_key("w342", data.get("poster_path")),
                "backdrop": image_key("w780", data.get("backdrop_path")),
                "provider_status": data.get("status"),
                "seasons": len([s for s in data.get("seasons", []) if s.get("season_number")])
                if kind == "tv"
                else None,
                "cast": cast,
            }
        }

    def touch(conn, resource_type, resource_id, status=None, **fields):
        stamp = now_iso()
        existing = entry(conn, resource_type, resource_id)
        if existing:
            updates = {"updated_at": stamp, **({"status": status} if status else {}), **fields}
            conn.execute(
                f"UPDATE library SET {','.join(k + '=?' for k in updates)} WHERE resource_type=? AND resource_id=?",
                (*updates.values(), resource_type, resource_id),
            )
        else:
            conn.execute(
                "INSERT INTO library(resource_type,resource_id,status,added_at,updated_at) VALUES(?,?,?,?,?)",
                (resource_type, resource_id, status or "planned", stamp, stamp),
            )
            if fields:
                touch(conn, resource_type, resource_id, **fields)
        announce(conn)

    @app.post("/api/library", status_code=201)
    def add(body: AddBody):
        allowed = MOVIE_STATUSES if body.kind == "movie" else SERIES_STATUSES
        if body.status not in allowed:
            raise HTTPException(422, "Unknown status")
        language = settings()["language"]
        if body.kind == "movie":
            details = tmdb.movie(body.tmdb_id, language)
            with db.connect() as conn:
                movie_id = upsert_movie(conn, details)
                touch(conn, "movie", movie_id, body.status)
                if (
                    body.status == "watched"
                    and not conn.execute(
                        "SELECT 1 FROM history WHERE resource_type='movie' AND resource_id=?",
                        (movie_id,),
                    ).fetchone()
                ):
                    conn.execute(
                        "INSERT INTO history(id,resource_type,resource_id,watched_at,created_at) VALUES(?,?,?,?,?)",
                        (uuid7(), "movie", movie_id, now_iso(), now_iso()),
                    )
                return movie_json(conn, movie_id)
        details, seasons, complete = fetch_series(body.tmdb_id, first_only=True)
        with db.connect() as conn:
            series_id = upsert_series(conn, details, seasons, complete)
            if not complete:
                conn.execute("UPDATE series SET refresh_requested=1 WHERE id=?", (series_id,))
            touch(conn, "series", series_id, body.status)
            return series_json(conn, series_id)

    @app.get("/api/movies/{mid}")
    def read_movie(mid: str):
        with db.connect() as conn:
            return movie_json(conn, mid)

    @app.get("/api/series/{sid}")
    def read_series(sid: str):
        with db.connect() as conn:
            return series_json(conn, sid)

    def kind_table(resource_type):
        if resource_type not in {"movie", "series"}:
            raise HTTPException(404, "Unknown type")
        return "movies" if resource_type == "movie" else "series"

    @app.put("/api/library/{resource_type}/{rid}")
    def update_entry(resource_type: str, rid: str, body: EntryPatch):
        table = kind_table(resource_type)
        allowed = MOVIE_STATUSES if resource_type == "movie" else SERIES_STATUSES
        if body.status and body.status not in allowed:
            raise HTTPException(422, "Unknown status")
        with db.connect() as conn:
            if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (rid,)).fetchone():
                raise HTTPException(404, "Not found")
            fields = body.model_dump(exclude_none=True, exclude={"status"})
            if fields.get("rating") == 0:
                fields["rating"] = None
            touch(conn, resource_type, rid, body.status, **fields)
            return movie_json(conn, rid) if resource_type == "movie" else series_json(conn, rid)

    @app.delete("/api/library/{resource_type}/{rid}")
    def remove_entry(resource_type: str, rid: str, history: str = "keep"):
        kind_table(resource_type)
        with db.connect() as conn:
            conn.execute(
                "DELETE FROM library WHERE resource_type=? AND resource_id=?", (resource_type, rid)
            )
            if history == "delete":
                if resource_type == "movie":
                    conn.execute(
                        "DELETE FROM history WHERE resource_type='movie' AND resource_id=?", (rid,)
                    )
                else:
                    conn.execute(
                        "DELETE FROM history WHERE resource_type='episode' AND resource_id IN (SELECT id FROM episodes WHERE series_id=?)",
                        (rid,),
                    )
            announce(conn)
        return {"removed": True}

    def stamp_value(body):
        if body and body.watched_at:
            try:
                return (
                    datetime.fromisoformat(body.watched_at.replace("Z", "+00:00"))
                    .astimezone(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            except ValueError as exc:
                raise HTTPException(422, "Invalid watch time") from exc
        return now_iso()

    @app.post("/api/movies/{mid}/watch", status_code=201)
    def watch_movie(mid: str, body: WatchBody | None = None):
        with db.connect() as conn:
            if not conn.execute("SELECT 1 FROM movies WHERE id=?", (mid,)).fetchone():
                raise HTTPException(404, "Movie not found")
            conn.execute(
                "INSERT INTO history(id,resource_type,resource_id,watched_at,created_at) VALUES(?,?,?,?,?)",
                (uuid7(), "movie", mid, stamp_value(body), now_iso()),
            )
            touch(conn, "movie", mid, "watched")
            return movie_json(conn, mid)

    def series_after_watch(conn, series_id):
        existing = entry(conn, "series", series_id)
        if not existing or existing["status"] == "planned":
            touch(conn, "series", series_id, "watching")
        row = conn.execute("SELECT provider_status FROM series WHERE id=?", (series_id,)).fetchone()
        p = progress(conn, series_id, today())
        result = series_json(conn, series_id)
        result["suggest_completed"] = (
            p["caught_up"]
            and p["watched"] >= p["total"]
            and row["provider_status"] in ENDED
            and result["library"]["status"] != "completed"
        )
        return result

    def mark(conn, episode_ids, at):
        seen = set()
        for eid in episode_ids:
            if eid in seen:
                continue
            seen.add(eid)
            if not conn.execute(
                "SELECT 1 FROM history WHERE resource_type='episode' AND resource_id=?", (eid,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO history(id,resource_type,resource_id,watched_at,created_at) VALUES(?,?,?,?,?)",
                    (uuid7(), "episode", eid, at, now_iso()),
                )

    def episode(conn, eid):
        row = conn.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()
        if not row:
            raise HTTPException(404, "Episode not found")
        return row

    @app.post("/api/episodes/{eid}/watch", status_code=201)
    def watch_episode(eid: str, body: WatchBody | None = None):
        with db.connect() as conn:
            e = episode(conn, eid)
            conn.execute(
                "INSERT INTO history(id,resource_type,resource_id,watched_at,created_at) VALUES(?,?,?,?,?)",
                (uuid7(), "episode", eid, stamp_value(body), now_iso()),
            )
            return series_after_watch(conn, e["series_id"])

    @app.delete("/api/episodes/{eid}/watch")
    def unwatch_episode(eid: str):
        with db.connect() as conn:
            e = episode(conn, eid)
            conn.execute(
                "DELETE FROM history WHERE resource_type='episode' AND resource_id=?", (eid,)
            )
            return series_json(conn, e["series_id"])

    @app.post("/api/episodes/{eid}/watch-through", status_code=201)
    def watch_through(eid: str):
        """Mark every aired regular episode up to and including this one."""
        with db.connect() as conn:
            target = episode(conn, eid)
            ids = [
                e["id"]
                for e in regular_episodes(conn, target["series_id"])
                if (e["season_number"], e["episode_number"])
                <= (target["season_number"], target["episode_number"])
                and (e["id"] == eid or (e["air_date"] and e["air_date"] <= today()))
            ]
            mark(conn, ids, now_iso())
            return series_after_watch(conn, target["series_id"])

    @app.post("/api/seasons/{season_id}/watch", status_code=201)
    def watch_season(season_id: str):
        with db.connect() as conn:
            s = conn.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
            if not s:
                raise HTTPException(404, "Season not found")
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM episodes WHERE season_id=? AND missing=0 AND air_date<=? ORDER BY episode_number",
                    (season_id, today()),
                )
            ]
            mark(conn, ids, now_iso())
            return series_after_watch(conn, s["series_id"])

    @app.delete("/api/seasons/{season_id}/watch")
    def unwatch_season(season_id: str):
        with db.connect() as conn:
            s = conn.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
            if not s:
                raise HTTPException(404, "Season not found")
            conn.execute(
                "DELETE FROM history WHERE resource_type='episode' AND resource_id IN (SELECT id FROM episodes WHERE season_id=?)",
                (season_id,),
            )
            return series_json(conn, s["series_id"])

    @app.post("/api/{resource_type}/{rid}/refresh", status_code=202)
    def request_refresh(resource_type: str, rid: str):
        table = kind_table(resource_type)
        if not tmdb.configured():
            raise HTTPException(409, "Add a TMDB credential in Lyra's settings first.")
        with db.connect() as conn:
            if not conn.execute(
                f"UPDATE {table} SET refresh_requested=1 WHERE id=? RETURNING id", (rid,)
            ).fetchone():
                raise HTTPException(404, "Not found")
        return {"refreshing": True}

    def title_targets(resource_type, rid):
        """A title, and for a series its next episodes: what links about it may point to."""
        targets = [reference(resource_type, rid)]
        if resource_type == "series":
            with db.connect() as conn:
                targets += [
                    reference("episode", r["id"])
                    for r in conn.execute(
                        "SELECT id FROM episodes WHERE series_id=? AND air_date>=? ORDER BY air_date LIMIT 6",
                        (rid, (clock().date() - timedelta(days=14)).isoformat()),
                    )
                ]
        return targets

    @app.get("/api/{resource_type}/{rid}/linked-from")
    def linked_from(resource_type: str, rid: str):
        """Backlinks standard (concepts/backlinks.md): every item in another module that links to
        this title, or to one of a series' current episodes, and shares it with Lyra, labelled
        by its owner. Never raises."""
        kind_table(resource_type)
        edges, seen = [], set()
        try:
            for target in title_targets(resource_type, rid):
                page = nexus.request("GET", "/references", params={"resource": target, "direction": "incoming"})
                edges += page.get("references") or []
        except (httpx.HTTPError, KeyError, ValueError):
            return {"availability": "nexus_unreachable", "items": []}
        items = []
        for edge in edges:
            parts = edge.get("source", "").split(":")
            if len(parts) != 5 or parts[2] == "lyra" or edge["source"] in seen:
                continue
            seen.add(edge["source"])
            entry = {"source": edge["source"], "module": parts[2], "type": parts[3], "label": "", "availability": "unknown"}
            try:
                out = nexus.request("POST", "/resources/resolve", {"resource": edge["source"]})
                entry["availability"] = out.get("availability") or "unknown"
                if entry["availability"] == "available":
                    entry["label"] = str(out.get("label") or "")[:200]
                    entry["open_path"] = (out.get("open") or {}).get("module_path")
            except Exception:
                entry["availability"] = "temporarily_unavailable"
            items.append(entry)
        return {"availability": "available", "items": items}

    @app.get("/api/{resource_type}/{rid}/planned")
    def planned(resource_type: str, rid: str):
        """Chronos events about this title (or its next episodes), shared with Lyra."""
        kind_table(resource_type)
        events, available = [], True
        try:
            for target in title_targets(resource_type, rid):
                page = nexus.request(
                    "GET", "/references", params={"resource": target, "direction": "incoming"}
                )
                for edge in page.get("references", []):
                    if edge.get("relation") != "chronos.about":
                        continue
                    resolved = nexus.request(
                        "POST", "/resources/resolve", {"resource": edge["source"]}
                    )
                    events.append(
                        {
                            "target": target,
                            "availability": resolved.get("availability"),
                            "label": resolved.get("label"),
                            "start": (resolved.get("representation") or {}).get("start"),
                            "all_day": (resolved.get("representation") or {}).get("all_day"),
                        }
                    )
        except (httpx.HTTPError, KeyError, ValueError):
            available = False
        return {"available": available, "events": events}

    @app.post("/api/images")
    def images_batch(body: ImagesBody):
        """Posters and stills as data URIs: the sandboxed interface cannot load remote images."""
        if not tmdb.configured():
            return {"images": {}}

        def load(key):
            match = re.fullmatch(r"(w\d{2,3})(/[A-Za-z0-9_-]{1,80}\.(?:jpg|jpeg|png))", key)
            if not match:
                return key, None
            path = images / hashlib.sha256(key.encode()).hexdigest()
            try:
                if path.exists():
                    raw = path.read_bytes()
                    media = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
                else:
                    media, raw = tmdb.image(match[1], match[2])
                    path.write_bytes(raw)
            except (TMDBError, OSError):
                return key, None
            return key, f"data:{media};base64," + base64.b64encode(raw).decode()

        result, size = {}, 0
        for key, value in pool.map(load, list(dict.fromkeys(body.keys))):
            if value and size + len(value) < 1_600_000:
                result[key] = value
                size += len(value)
        return {"images": result}

    # ── Module protocol ──────────────────────────────────────────────

    def require_resolver(request):
        key = os.getenv("NEXUS_RESOLVER_KEY", "")
        if not key or not secrets.compare_digest(
            request.headers.get("x-nexus-resolver-key", ""), key
        ):
            raise HTTPException(403, "Resolver authentication required")

    @app.post("/empyrean/v1/resources/resolve")
    def protocol_resolve(body: dict, request: Request):
        """Catalog metadata is disclosed to modules the owner granted a resolve scope."""
        require_resolver(request)
        match = REF.fullmatch(str(body.get("resource", "")))
        if not match or match[1] != "lyra":
            raise HTTPException(404, "Not found")
        kind, rid = match[2], match[3]
        with db.connect() as conn:
            if kind == "movie":
                row = conn.execute("SELECT * FROM movies WHERE id=?", (rid,)).fetchone()
                if row:
                    year = (row["release_date"] or "")[:4]
                    return {
                        "resource": body["resource"],
                        "label": (row["title"] + (f" ({year})" if year else ""))[:200],
                        "open_path": f"/movie/{rid}",
                        "representation": {"kind": "movie", "date": row["release_date"]},
                    }
            elif kind == "series":
                row = conn.execute("SELECT * FROM series WHERE id=?", (rid,)).fetchone()
                if row:
                    return {
                        "resource": body["resource"],
                        "label": row["title"][:200],
                        "open_path": f"/series/{rid}",
                        "representation": {"kind": "series", "date": row["first_air_date"]},
                    }
            elif kind == "season":
                row = conn.execute(
                    "SELECT x.*, s.title FROM seasons x JOIN series s ON s.id=x.series_id WHERE x.id=?",
                    (rid,),
                ).fetchone()
                if row:
                    return {
                        "resource": body["resource"],
                        "label": f"{row['title']} · Season {row['season_number']}"[:200],
                        "open_path": f"/series/{row['series_id']}",
                        "representation": {"kind": "season", "date": row["air_date"]},
                    }
            elif kind == "episode":
                row = conn.execute(
                    "SELECT e.*, s.title FROM episodes e JOIN series s ON s.id=e.series_id WHERE e.id=?",
                    (rid,),
                ).fetchone()
                if row:
                    label = f"{row['title']} · S{row['season_number']}E{row['episode_number']}" + (
                        f" · {row['name']}" if row["name"] else ""
                    )
                    return {
                        "resource": body["resource"],
                        "label": label[:200],
                        "open_path": f"/series/{row['series_id']}",
                        "representation": {"kind": "episode", "date": row["air_date"]},
                    }
        raise HTTPException(404, "Not found")

    @app.post("/empyrean/v1/projections/dated-items")
    def projection(body: dict, request: Request):
        require_resolver(request)
        query = body.get("query") or {}
        try:
            start = date.fromisoformat(str(query.get("from")))
            end = date.fromisoformat(str(query.get("to")))
        except ValueError as exc:
            raise HTTPException(422, "from and to must be ISO dates") from exc
        if end <= start or (end - start).days > 800:
            raise HTTPException(422, "The range must be 1 to 800 days")
        offset = int(body.get("cursor") or 0) if str(body.get("cursor") or "0").isdigit() else 0
        with db.connect() as conn:
            items = dated_items(conn, settings(), start.isoformat(), end.isoformat(), today())
        page = items[offset : offset + PAGE]
        return {
            "items": page,
            "next_cursor": str(offset + PAGE) if offset + PAGE < len(items) else None,
        }

    async def receive_artifact(request):
        path = data / f"restore-{uuid7()}.part"
        size = 0
        try:
            with open(path, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_ARTIFACT:
                        raise HTTPException(413, "Backup artifact exceeds 256 MiB")
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def check_artifact(request, path):
        headers = {
            k[len(BACKUP_HEADER) :].lower(): v
            for k, v in request.headers.items()
            if k.lower().startswith(BACKUP_HEADER.lower())
        }
        if headers.get("module") != "lyra" or headers.get("format") != BACKUP_FORMAT:
            raise ValueError("Not a Lyra backup")
        if headers.get("format-version") != str(BACKUP_FORMAT_VERSION):
            raise ValueError("Unsupported backup format version")
        try:
            snapshot = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise ValueError("Backup is not a readable database") from exc
        try:
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database is damaged")
            schema = snapshot.execute("PRAGMA user_version").fetchone()[0]
            if not 1 <= schema <= len(MIGRATIONS):
                raise ValueError("Backup schema is not supported by this version")
            tables = {
                r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"movies", "series", "episodes", "library", "history"} <= tables:
                raise ValueError("Backup is missing Lyra data")
        except sqlite3.Error as exc:
            raise ValueError("Backup is not a readable database") from exc
        finally:
            snapshot.close()

    @app.post("/empyrean/v1/backup/export")
    def backup_export(request: Request):
        """The database only: the TMDB credential and the image cache are not exported."""
        require_resolver(request)
        path = data / f"export-{uuid7()}.part"
        try:
            target = sqlite3.connect(path)
            with db.connect() as conn:
                conn.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
            target.close()
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return FileResponse(
            path,
            media_type="application/octet-stream",
            background=BackgroundTask(path.unlink, missing_ok=True),
            headers={
                BACKUP_HEADER + "Module": "lyra",
                BACKUP_HEADER + "Module-Version": VERSION,
                BACKUP_HEADER + "Format": BACKUP_FORMAT,
                BACKUP_HEADER + "Format-Version": str(BACKUP_FORMAT_VERSION),
                BACKUP_HEADER + "Created-At": clock().isoformat(),
                BACKUP_HEADER + "Restorable-By": f">={VERSION},<1",
            },
        )

    @app.post("/empyrean/v1/backup/validate")
    async def backup_validate(request: Request):
        require_resolver(request)
        path = await receive_artifact(request)
        try:
            await run_in_threadpool(check_artifact, request, path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            path.unlink(missing_ok=True)
        return {"valid": True}

    def replace_data(path):
        (data / "refresh-suspended").write_text(clock().isoformat())
        snapshot = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            with db.connect() as conn:
                snapshot.backup(conn)
        finally:
            snapshot.close()
        db.migrate()
        with db.connect() as conn:
            conn.execute("DELETE FROM outbox")
            announce(conn)

    @app.post("/empyrean/v1/backup/restore")
    async def backup_restore(request: Request):
        require_resolver(request)
        path = await receive_artifact(request)
        try:
            try:
                await run_in_threadpool(check_artifact, request, path)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            await run_in_threadpool(replace_data, path)
        finally:
            path.unlink(missing_ok=True)
        return {"restored": True}

    @app.post("/empyrean/v1/backup/finalize")
    def backup_finalize(request: Request):
        require_resolver(request)
        (data / "refresh-suspended").unlink(missing_ok=True)
        return {"finalized": True}

    # ── Interface ────────────────────────────────────────────────────

    def catalogs():
        result = {}
        for directory in (ROOT / "frontend/locales", data / "locales"):
            if not directory.exists():
                continue
            for file in directory.glob("*.json"):
                if not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?", file.stem):
                    continue
                try:
                    messages = json.loads(file.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                if isinstance(messages, dict) and all(
                    isinstance(v, str) for v in messages.values()
                ):
                    result[file.stem] = {**result.get(file.stem, {}), **messages}
        return result

    @app.get("/icon.svg", include_in_schema=False)
    def app_icon():
        """The application icon Nexus shows in its switcher and module list (manifest `icon`)."""
        return FileResponse(ROOT / "frontend/icon.svg", media_type="image/svg+xml")

    @app.get("/{path:path}", response_class=HTMLResponse)
    def ui(path: str):
        script = (
            (ROOT / "frontend/app.js")
            .read_text(encoding="utf-8")
            .replace("/*CATALOGS*/ {}", json.dumps(catalogs()).replace("<", "\\u003c"))
        )
        # Nexus navigation contract: the shared SDK, then Lyra's adapter.
        script = "\n".join(
            [
                script,
                (ROOT / "frontend/vendor/nexus-navigation.js").read_text(encoding="utf-8"),
                (ROOT / "frontend/navigation.js").read_text(encoding="utf-8"),
            ]
        )
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        return html.replace("/*STYLE*/", style).replace("/*SCRIPT*/", script)

    return app


def _parse(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
