"""Lyra-owned screen-media records: identity mapping, provider refresh, watch state and dates.

Provider metadata is written only by `upsert_movie` / `upsert_series`; user data (library,
history) is written only by user actions. A refresh therefore cannot change what a user did."""

import json
import os
import time
import uuid
from datetime import date

MOVIE_STATUSES = {"planned", "watched"}
SERIES_STATUSES = {"planned", "watching", "completed", "on_hold", "dropped"}
RELEASE_TYPES = {1: "premiere", 2: "limited", 3: "theatrical", 4: "digital", 5: "physical", 6: "tv"}
ENDED = {"Ended", "Canceled"}


def uuid7() -> str:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | ((rand >> 62) & 0xFFF) << 64
    value |= 0b10 << 62 | rand & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def now_iso():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reference(kind, rid):
    return f"nexus:v1:lyra:{kind}:{rid}"


def day(value):
    """Provider dates are date-only facts; keep exactly the date or nothing."""
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def mapped(conn, provider, kind, external_id):
    row = conn.execute(
        "SELECT resource_id FROM external_ids WHERE provider=? AND kind=? AND external_id=?",
        (provider, kind, str(external_id)),
    ).fetchone()
    return row["resource_id"] if row else None


def map_external(conn, provider, kind, external_id, resource_type, resource_id):
    if external_id in (None, ""):
        return
    conn.execute(
        "INSERT INTO external_ids(provider,kind,external_id,resource_type,resource_id) VALUES(?,?,?,?,?) "
        "ON CONFLICT(provider,kind,external_id) DO NOTHING",
        (provider, kind, str(external_id), resource_type, resource_id),
    )


def credits(data):
    cast = [
        {
            "name": c.get("name", "")[:100],
            "character": (c.get("character") or "")[:100],
            "profile": c.get("profile_path"),
        }
        for c in (data.get("credits") or {}).get("cast", [])[:12]
    ]
    crew = [
        {"name": c.get("name", "")[:100], "job": (c.get("job") or "")[:60]}
        for c in (data.get("credits") or {}).get("crew", [])
        if c.get("job")
        in {
            "Director",
            "Screenplay",
            "Writer",
            "Original Music Composer",
            "Creator",
            "Executive Producer",
        }
    ][:8]
    creators = [
        {"name": c.get("name", "")[:100], "job": "Creator"} for c in data.get("created_by", [])[:4]
    ]
    return json.dumps({"cast": cast, "crew": creators + crew})


def resolve_identity(conn, kind, data):
    """The existing Lyra resource for a provider title, by TMDB ID then IMDb ID."""
    resource_type = "movie" if kind == "movie" else "series"
    existing = mapped(conn, "tmdb", kind, data["id"])
    if existing:
        return existing
    imdb = (data.get("external_ids") or {}).get("imdb_id") or data.get("imdb_id")
    if imdb:
        existing = mapped(conn, "imdb", resource_type, imdb)
        if existing:
            map_external(conn, "tmdb", kind, data["id"], resource_type, existing)
            return existing
    return None


def upsert_movie(conn, data):
    stamp = now_iso()
    movie_id = resolve_identity(conn, "movie", data)
    values = {
        "title": (data.get("title") or data.get("original_title") or "Untitled")[:300],
        "original_title": (data.get("original_title") or "")[:300],
        "overview": (data.get("overview") or "")[:5000],
        "tagline": (data.get("tagline") or "")[:300],
        "release_date": day(data.get("release_date")),
        "runtime": data.get("runtime") or None,
        "genres": json.dumps([g.get("name", "") for g in data.get("genres", [])][:8]),
        "poster_path": data.get("poster_path"),
        "backdrop_path": data.get("backdrop_path"),
        "provider_status": (data.get("status") or "")[:40],
        "original_language": (data.get("original_language") or "")[:10],
        "credits": credits(data),
        "release_dates": json.dumps(
            [
                {
                    "region": r.get("iso_3166_1"),
                    "type": d.get("type"),
                    "date": day(d.get("release_date")),
                    "note": (d.get("note") or "")[:80],
                }
                for r in (data.get("release_dates") or {}).get("results", [])
                for d in r.get("release_dates", [])
                if day(d.get("release_date"))
            ]
        ),
        "refreshed_at": stamp,
        "refresh_requested": 0,
    }
    if movie_id:
        conn.execute(
            f"UPDATE movies SET {','.join(k + '=?' for k in values)} WHERE id=?",
            (*values.values(), movie_id),
        )
    else:
        movie_id = uuid7()
        conn.execute(
            f"INSERT INTO movies(id,{','.join(values)},created_at) VALUES(?,{','.join('?' * len(values))},?)",
            (movie_id, *values.values(), stamp),
        )
    map_external(conn, "tmdb", "movie", data["id"], "movie", movie_id)
    ids = data.get("external_ids") or {}
    map_external(
        conn, "imdb", "movie", ids.get("imdb_id") or data.get("imdb_id"), "movie", movie_id
    )
    return movie_id


def upsert_series(conn, data, seasons_data=None, complete=False):
    """Write provider metadata for a series and the seasons/episodes supplied.

    `seasons_data` maps season number to a TMDB season object. With `complete`, every
    regular season was supplied, so episodes absent upstream are marked missing (never
    deleted: they may carry watch history)."""
    stamp = now_iso()
    series_id = resolve_identity(conn, "tv", data)
    runtimes = data.get("episode_run_time") or []
    values = {
        "title": (data.get("name") or data.get("original_name") or "Untitled")[:300],
        "original_title": (data.get("original_name") or "")[:300],
        "overview": (data.get("overview") or "")[:5000],
        "tagline": (data.get("tagline") or "")[:300],
        "first_air_date": day(data.get("first_air_date")),
        "last_air_date": day(data.get("last_air_date")),
        "provider_status": (data.get("status") or "")[:40],
        "in_production": int(bool(data.get("in_production"))),
        "genres": json.dumps([g.get("name", "") for g in data.get("genres", [])][:8]),
        "networks": json.dumps([n.get("name", "") for n in data.get("networks", [])][:4]),
        "poster_path": data.get("poster_path"),
        "backdrop_path": data.get("backdrop_path"),
        "credits": credits(data),
        "episode_runtime": runtimes[0] if runtimes else None,
        "refreshed_at": stamp,
        "refresh_requested": 0,
    }
    if series_id:
        conn.execute(
            f"UPDATE series SET {','.join(k + '=?' for k in values)} WHERE id=?",
            (*values.values(), series_id),
        )
    else:
        series_id = uuid7()
        conn.execute(
            f"INSERT INTO series(id,{','.join(values)},created_at) VALUES(?,{','.join('?' * len(values))},?)",
            (series_id, *values.values(), stamp),
        )
    map_external(conn, "tmdb", "tv", data["id"], "series", series_id)
    ids = data.get("external_ids") or {}
    map_external(conn, "imdb", "series", ids.get("imdb_id"), "series", series_id)
    map_external(conn, "tvdb", "series", ids.get("tvdb_id"), "series", series_id)
    listed = {
        s.get("season_number"): s
        for s in data.get("seasons", [])
        if isinstance(s.get("season_number"), int)
    }
    for number, summary in listed.items():
        season_id = _upsert_season(
            conn, series_id, number, {**summary, **((seasons_data or {}).get(number) or {})}, stamp
        )
        detail = (seasons_data or {}).get(number)
        if detail is not None:
            seen = set()
            for episode in detail.get("episodes", []):
                if isinstance(episode.get("episode_number"), int):
                    seen.add(_upsert_episode(conn, series_id, season_id, number, episode, stamp))
            conn.execute(
                f"UPDATE episodes SET missing=1 WHERE season_id=? AND id NOT IN ({','.join('?' * len(seen))})",
                (season_id, *seen),
            )
    if complete:
        conn.execute(
            f"UPDATE seasons SET missing=1 WHERE series_id=? AND season_number NOT IN ({','.join('?' * len(listed))})",
            (series_id, *listed),
        )
        conn.execute(
            "UPDATE episodes SET missing=1 WHERE season_id IN (SELECT id FROM seasons WHERE series_id=? AND missing=1)",
            (series_id,),
        )
    return series_id


def _upsert_season(conn, series_id, number, data, stamp):
    values = (
        (data.get("name") or "")[:200],
        (data.get("overview") or "")[:3000],
        day(data.get("air_date")),
        data.get("poster_path"),
        data.get("episode_count") or len(data.get("episodes", [])) or None,
    )
    row = conn.execute(
        "SELECT id FROM seasons WHERE series_id=? AND season_number=?", (series_id, number)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE seasons SET name=?,overview=?,air_date=?,poster_path=?,episode_count=?,missing=0 WHERE id=?",
            (*values, row["id"]),
        )
        season_id = row["id"]
    else:
        season_id = uuid7()
        conn.execute(
            "INSERT INTO seasons(id,series_id,season_number,name,overview,air_date,poster_path,episode_count,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (season_id, series_id, number, *values, stamp),
        )
    if data.get("id"):
        map_external(conn, "tmdb", "season", data["id"], "season", season_id)
    return season_id


def _upsert_episode(conn, series_id, season_id, season_number, data, stamp):
    number = data["episode_number"]
    existing = mapped(conn, "tmdb", "episode", data.get("id")) if data.get("id") else None
    if not existing:
        row = conn.execute(
            "SELECT id FROM episodes WHERE series_id=? AND season_number=? AND episode_number=?",
            (series_id, season_number, number),
        ).fetchone()
        existing = row["id"] if row else None
    values = (
        season_id,
        season_number,
        number,
        (data.get("name") or "")[:300],
        (data.get("overview") or "")[:3000],
        day(data.get("air_date")),
        data.get("runtime") or None,
        data.get("still_path"),
    )
    if existing:
        # A renumbered episode may collide with a stale row at its new number.
        clash = conn.execute(
            "SELECT id FROM episodes WHERE series_id=? AND season_number=? AND episode_number=? AND id!=?",
            (series_id, season_number, number, existing),
        ).fetchone()
        if clash:
            conn.execute(
                "UPDATE episodes SET episode_number=-episode_number-1000000,missing=1 WHERE id=?",
                (clash["id"],),
            )
        conn.execute(
            "UPDATE episodes SET season_id=?,season_number=?,episode_number=?,name=?,overview=?,air_date=?,"
            "runtime=?,still_path=?,missing=0 WHERE id=?",
            (*values, existing),
        )
        episode_id = existing
    else:
        episode_id = uuid7()
        conn.execute(
            "INSERT INTO episodes(id,series_id,season_id,season_number,episode_number,name,overview,air_date,"
            "runtime,still_path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (episode_id, series_id, *values, stamp),
        )
    map_external(conn, "tmdb", "episode", data.get("id"), "episode", episode_id)
    return episode_id


def dates_signature(conn, series_id=None, movie_id=None):
    """Fingerprint of projectable dates, to announce only real changes."""
    if series_id:
        rows = conn.execute(
            "SELECT id,air_date,missing FROM episodes WHERE series_id=? ORDER BY id", (series_id,)
        ).fetchall()
        return json.dumps([tuple(r) for r in rows])
    row = conn.execute(
        "SELECT release_date,release_dates FROM movies WHERE id=?", (movie_id,)
    ).fetchone()
    return json.dumps(tuple(row)) if row else ""


# ── Watch state ─────────────────────────────────────────────────────────────


def watched_episodes(conn, series_id):
    return {
        r["resource_id"]
        for r in conn.execute(
            "SELECT DISTINCT h.resource_id FROM history h JOIN episodes e ON e.id=h.resource_id "
            "WHERE h.resource_type='episode' AND e.series_id=?",
            (series_id,),
        )
    }


def regular_episodes(conn, series_id):
    return conn.execute(
        "SELECT * FROM episodes WHERE series_id=? AND season_number>0 AND missing=0 "
        "ORDER BY season_number, episode_number",
        (series_id,),
    ).fetchall()


def next_episode(conn, series_id, today):
    """First unwatched regular episode after the furthest watched one."""
    episodes = regular_episodes(conn, series_id)
    seen = watched_episodes(conn, series_id)
    furthest = max((i for i, e in enumerate(episodes) if e["id"] in seen), default=-1)
    for episode in episodes[furthest + 1 :]:
        if episode["id"] not in seen:
            state = (
                "unannounced"
                if not episode["air_date"]
                else "available"
                if episode["air_date"] <= today
                else "upcoming"
            )
            return {**dict(episode), "state": state}
    return None


def progress(conn, series_id, today):
    episodes = regular_episodes(conn, series_id)
    aired = [e for e in episodes if e["air_date"] and e["air_date"] <= today]
    seen = watched_episodes(conn, series_id)
    return {
        "watched": sum(1 for e in episodes if e["id"] in seen),
        "aired": len(aired),
        "total": len(episodes),
        "caught_up": bool(aired) and all(e["id"] in seen for e in aired),
    }


# ── Release dates and the dated-items projection ────────────────────────────


def movie_releases(row, region):
    """(kind, date, certainty, label) for a movie in the user's region (date-only)."""
    found = {}
    for entry in json.loads(row["release_dates"] or "[]"):
        if entry["region"] == region and entry["date"]:
            kind = RELEASE_TYPES.get(entry["type"])
            if kind and (kind not in found or entry["date"] < found[kind]):
                found[kind] = entry["date"]
    releases = []
    theatrical = found.get("theatrical") or found.get("limited") or found.get("premiere")
    if theatrical:
        releases.append(("theatrical", theatrical, False))
    if found.get("digital"):
        releases.append(("digital", found["digital"], False))
    if not releases and found.get("physical"):
        releases.append(("physical", found["physical"], False))
    if not releases and row["release_date"]:
        releases.append(("release", row["release_date"], True))
    return releases


def certainty(value, today, estimated=False):
    if estimated:
        return "estimated"
    return "confirmed" if value <= today else "tentative"


def shared_series(conn, policy):
    rows = conn.execute(
        "SELECT s.*, l.status, l.calendar FROM series s JOIN library l "
        "ON l.resource_type='series' AND l.resource_id=s.id"
    ).fetchall()
    chosen = []
    for row in rows:
        if policy == "none" or row["calendar"] == "never":
            continue
        if row["calendar"] == "always":
            chosen.append(row)
        elif policy == "watching" and row["status"] == "watching":
            chosen.append(row)
        elif policy == "tracked" and row["status"] != "dropped":
            chosen.append(row)
    return chosen


def dated_items(conn, settings, start, end, today):
    """Items for the dated-items v1 projection, as selected by the user's sharing settings."""
    items = []
    premieres = settings["calendar_premieres_only"]
    for series in shared_series(conn, settings["calendar_episodes"]):
        for e in conn.execute(
            "SELECT * FROM episodes WHERE series_id=? AND season_number>0 AND missing=0 "
            "AND air_date>=? AND air_date<?",
            (series["id"], start, end),
        ):
            if premieres and e["episode_number"] != 1:
                continue
            label = f"S{e['season_number']}E{e['episode_number']}"
            summary = (
                (
                    "Series premiere"
                    if e["season_number"] == 1
                    else f"Season {e['season_number']} premiere"
                )
                if e["episode_number"] == 1
                else (e["name"] or "")
            )
            items.append(
                {
                    "id": f"episode:{e['id']}",
                    "resource": reference("episode", e["id"]),
                    "kind": "lyra.episode-air",
                    "title": f"{series['title']} · {label}"
                    + (
                        f" · {e['name']}"
                        if e["name"] and not e["name"].startswith("Episode ")
                        else ""
                    ),
                    "start": e["air_date"],
                    "all_day": True,
                    "certainty": certainty(e["air_date"], today),
                    "status": "scheduled",
                    "summary": summary[:300],
                    "group": {
                        "resource": reference("series", series["id"]),
                        "label": series["title"],
                    },
                }
            )
    if settings["calendar_movies"] == "watchlist":
        for movie in conn.execute(
            "SELECT m.*, l.calendar FROM movies m JOIN library l ON l.resource_type='movie' "
            "AND l.resource_id=m.id WHERE (l.status='planned' OR l.calendar='always') AND l.calendar!='never'"
        ):
            for kind, value, estimated in movie_releases(movie, settings["region"]):
                if start <= value < end:
                    items.append(
                        {
                            "id": f"movie:{movie['id']}:{kind}",
                            "resource": reference("movie", movie["id"]),
                            "kind": "lyra.movie-release",
                            "title": movie["title"],
                            "start": value,
                            "all_day": True,
                            "certainty": certainty(value, today, estimated),
                            "status": "scheduled",
                            "summary": {
                                "theatrical": f"In cinemas ({settings['region']})",
                                "digital": f"Digital release ({settings['region']})",
                                "physical": f"Disc release ({settings['region']})",
                                "release": "Release date (region unknown)",
                            }[kind],
                        }
                    )
    items.sort(key=lambda i: (i["start"], i["id"]))
    return items
