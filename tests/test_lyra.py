import copy
import json
import os
import stat
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from lyra.app import create_app

KEY = "k" * 40
GW = {"x-nexus-gateway-key": KEY}
RES = {"x-nexus-resolver-key": KEY}
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJ0ZXN0In0.c2lnbmF0dXJl"
NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)

MOVIE = {
    "id": 603,
    "title": "The Matrix",
    "original_title": "The Matrix",
    "overview": "A hacker learns the truth.",
    "release_date": "1999-03-31",
    "runtime": 136,
    "genres": [{"id": 1, "name": "Science Fiction"}],
    "poster_path": "/matrix.jpg",
    "backdrop_path": "/matrix-bg.jpg",
    "status": "Released",
    "imdb_id": "tt0133093",
    "credits": {
        "cast": [{"name": "Keanu Reeves", "character": "Neo"}],
        "crew": [{"name": "Lana Wachowski", "job": "Director"}],
    },
    "external_ids": {"imdb_id": "tt0133093"},
    "release_dates": {
        "results": [
            {
                "iso_3166_1": "US",
                "release_dates": [{"type": 3, "release_date": "1999-03-31T00:00:00.000Z"}],
            }
        ]
    },
}
UPCOMING = {
    **MOVIE,
    "id": 900,
    "title": "Future Film",
    "imdb_id": "tt9000000",
    "external_ids": {"imdb_id": "tt9000000"},
    "release_date": "2026-12-18",
    "status": "Post Production",
    "release_dates": {
        "results": [
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 3, "release_date": "2026-12-18T00:00:00.000Z"},
                    {"type": 4, "release_date": "2027-02-02T00:00:00.000Z"},
                ],
            },
            {
                "iso_3166_1": "SK",
                "release_dates": [{"type": 3, "release_date": "2026-12-25T00:00:00.000Z"}],
            },
        ]
    },
}


def episodes(season, count, first_air, *, start=1):
    from datetime import date, timedelta

    base = date.fromisoformat(first_air)
    return [
        {
            "id": season * 1000 + n,
            "episode_number": n,
            "name": f"Chapter {n}",
            "air_date": (base + timedelta(days=7 * (n - start))).isoformat(),
            "runtime": 55,
        }
        for n in range(start, start + count)
    ]


def make_tv():
    return {
        "id": 1405,
        "name": "Dexter",
        "original_name": "Dexter",
        "overview": "A forensic analyst.",
        "first_air_date": "2026-07-01",
        "status": "Returning Series",
        "in_production": True,
        "genres": [{"name": "Crime"}],
        "networks": [{"name": "Showtime"}],
        "poster_path": "/dexter.jpg",
        "backdrop_path": "/dexter-bg.jpg",
        "episode_run_time": [55],
        "external_ids": {"imdb_id": "tt0773262", "tvdb_id": 79349},
        "credits": {"cast": [{"name": "Michael C. Hall", "character": "Dexter"}]},
        "seasons": [
            {"id": 10, "season_number": 0, "name": "Specials", "episode_count": 1},
            {
                "id": 11,
                "season_number": 1,
                "name": "Season 1",
                "air_date": "2026-07-01",
                "episode_count": 4,
            },
            {
                "id": 12,
                "season_number": 2,
                "name": "Season 2",
                "air_date": "2026-11-09",
                "episode_count": 3,
            },
        ],
        "seasons_data": {
            0: {
                "id": 10,
                "episodes": [
                    {"id": 1, "episode_number": 1, "name": "Special", "air_date": "2026-06-01"}
                ],
            },
            1: {"id": 11, "episodes": episodes(1, 4, "2026-07-01")},
            2: {"id": 12, "episodes": episodes(2, 3, "2026-11-09")},
        },
    }


class Provider:
    """Fake TMDB API and image service."""

    def __init__(self):
        self.movies = {603: copy.deepcopy(MOVIE), 900: copy.deepcopy(UPCOMING)}
        self.tv = make_tv()
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if request.url.host == "image.tmdb.org":
            return httpx.Response(
                200, content=b"\xff\xd8fakejpeg", headers={"content-type": "image/jpeg"}
            )
        auth = request.headers.get("authorization") == "Bearer " + TOKEN
        if not auth:
            return httpx.Response(401, json={"status_message": "Invalid API key"})
        path = request.url.path.removeprefix("/3")
        if path == "/configuration":
            return httpx.Response(200, json={"images": {}})
        if path == "/search/multi":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "media_type": "movie",
                            "id": 603,
                            "title": "The Matrix",
                            "release_date": "1999-03-31",
                            "poster_path": "/matrix.jpg",
                        },
                        {
                            "media_type": "tv",
                            "id": 1405,
                            "name": "Dexter",
                            "first_air_date": "2026-07-01",
                        },
                        {"media_type": "person", "id": 5, "name": "Someone"},
                    ]
                },
            )
        if path.startswith("/movie/"):
            tmdb_id = int(path.split("/")[2])
            return (
                httpx.Response(200, json=self.movies[tmdb_id])
                if tmdb_id in self.movies
                else httpx.Response(404, json={})
            )
        if path == "/tv/1405":
            data = {k: v for k, v in self.tv.items() if k != "seasons_data"}
            for part in request.url.params.get("append_to_response", "").split(","):
                if part.startswith("season/"):
                    number = int(part.split("/")[1])
                    if number in self.tv["seasons_data"]:
                        data[part] = self.tv["seasons_data"][number]
            return httpx.Response(200, json=data)
        return httpx.Response(404, json={})


class FakeNexus:
    def __init__(self):
        self.calls = []
        self.edges = {}

    def request(self, method, path, body=None, params=None):
        self.calls.append((method, path, body, params))
        if path == "/references":
            return {"references": self.edges.get(params["resource"], [])}
        if path == "/resources/resolve":
            return {
                "availability": "available",
                "label": "Watch together",
                "representation": {"start": "2026-11-09", "all_day": True},
            }
        return {}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RESOLVER_KEY", KEY)
    provider, nexus = Provider(), FakeNexus()
    app = create_app(
        tmp_path,
        nexus=nexus,
        tmdb_transport=httpx.MockTransport(provider),
        clock=lambda: NOW,
        workers=False,
    )
    with TestClient(app, headers=GW) as client:
        yield client, app, provider, nexus, tmp_path


@pytest.fixture
def ready(env):
    client = env[0]
    assert client.put("/api/credential", json={"value": TOKEN}).json() == {
        "configured": True,
        "kind": "bearer",
    }
    return env


def dexter(client):
    return client.post(
        "/api/library", json={"kind": "tv", "tmdb_id": 1405, "status": "planned"}
    ).json()


def test_credential_is_validated_write_only_and_private(env):
    client, _, provider, _, path = env
    assert (
        client.put("/api/credential", json={"value": "not a credential at all"}).status_code == 422
    )
    bad = client.put("/api/credential", json={"value": TOKEN.replace("c2ln", "eHh4")})
    assert bad.status_code == 401 and TOKEN not in bad.text
    assert client.get("/api/search?q=matrix").json()["remote_error"] is None
    assert (
        client.post("/api/search/external", json={"query": "matrix"}).json()["remote_error"]
        == "not_configured"
    )
    assert client.put("/api/credential", json={"value": TOKEN}).status_code == 200
    stored = path / "secrets" / "tmdb.json"
    assert stat.S_IMODE(os.stat(stored).st_mode) & 0o077 == 0 or os.name == "nt"
    state = client.get("/api/state").json()
    assert state["tmdb"] == {"configured": True, "kind": "bearer"}
    assert TOKEN not in json.dumps(state)
    assert "not endorsed or certified by TMDB" in state["attribution"]
    # Only search text, ids, language and region reach TMDB.
    client.post("/api/search/external", json={"query": "matrix"})
    sent = provider.requests[-1].url.params
    assert set(sent) <= {"query", "language", "page", "include_adult"}


def test_search_and_identity_mapping(ready):
    client = ready[0]
    found = client.post("/api/search/external", json={"query": "matrix"}).json()
    assert [r["kind"] for r in found["remote"]] == ["movie", "tv"]  # people are ignored
    assert found["remote"][0]["resource"] is None
    movie = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    assert movie["id"][14] == "7" and movie["reference"] == f"nexus:v1:lyra:movie:{movie['id']}"
    assert movie["external"] == {"tmdb": "603", "imdb": "tt0133093"}
    again = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    assert again["id"] == movie["id"]
    found = client.get("/api/search?q=matrix").json()
    assert found["remote"] == []
    external = client.post("/api/search/external", json={"query": "matrix"}).json()
    assert external["remote"][0]["resource"] == {"type": "movie", "id": movie["id"]}
    assert [c["id"] for c in found["local"]] == [movie["id"]]
    assert client.get("/api/preview/movie/603").json() == {
        "resource": {"type": "movie", "id": movie["id"]}
    }


def test_local_search_and_cached_artwork_never_contact_tmdb(ready):
    client, _, provider, _, _ = ready
    movie = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    provider.requests.clear()
    for query in ("m", "ma", "matrix", "no local match", "", "%", "_", "x" * 201):
        result = client.get("/api/search", params={"q": query}).json()
        assert result["remote"] == [] and result["remote_error"] is None
    assert client.get("/api/search", params={"q": "matrix"}).json()["local"][0]["id"] == movie["id"]
    images = client.post("/api/images", json={"keys": ["w342/matrix.jpg"], "cached_only": True})
    assert images.json() == {"images": {}}
    assert provider.requests == []

    assert client.post("/api/images", json={"keys": ["w342/matrix.jpg"]}).json()["images"]
    provider.requests.clear()
    assert client.post(
        "/api/images", json={"keys": ["w342/matrix.jpg"], "cached_only": True}
    ).json()["images"]
    assert provider.requests == []
    client.delete("/api/credential")
    assert client.post(
        "/api/images", json={"keys": ["w342/matrix.jpg"], "cached_only": True}
    ).json()["images"]
    assert client.get("/api/search", params={"q": "matrix"}).json()["local"]
    assert provider.requests == []


@pytest.mark.parametrize("query", ["", "a", "  ", "x" * 201])
def test_external_search_rejects_invalid_input_without_provider_request(ready, query):
    client, _, provider, _, _ = ready
    provider.requests.clear()
    assert client.post("/api/search/external", json={"query": query}).status_code == 422
    assert provider.requests == []


def test_external_search_failure_keeps_library_local(ready, monkeypatch):
    from lyra.tmdb import TMDB, TMDBError

    client, _, provider, _, _ = ready

    def fail(*args):
        raise TMDBError("TMDB could not be reached.")

    monkeypatch.setattr(TMDB, "search", fail)
    external = client.post("/api/search/external", json={"query": "synthetic query"})
    assert external.status_code == 200 and external.json()["remote_error"]
    provider.requests.clear()
    assert client.get("/api/search", params={"q": "synthetic query"}).json() == {
        "local": [],
        "remote": [],
        "remote_error": None,
    }
    assert provider.requests == []


def test_same_title_by_another_provider_id_is_not_duplicated(ready):
    client, _, provider = ready[0], ready[1], ready[2]
    first = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    provider.movies[604] = {**copy.deepcopy(MOVIE), "id": 604}  # same IMDb identity
    second = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 604, "status": "planned"}
    ).json()
    assert second["id"] == first["id"]
    assert client.get("/api/library?type=movie").json()["items"].__len__() == 1


def test_series_tracking_next_episode_and_status(ready):
    client = ready[0]
    series = dexter(client)
    assert [s["number"] for s in series["seasons"]] == [1, 2, 0]  # specials last
    assert series["progress"] == {"watched": 0, "aired": 4, "total": 7, "caught_up": False}
    assert (
        series["next"]["season_number"],
        series["next"]["episode_number"],
        series["next"]["state"],
    ) == (1, 1, "available")
    first = series["seasons"][0]["episodes"][0]["id"]
    after = client.post(f"/api/episodes/{first}/watch").json()
    assert after["library"]["status"] == "watching"
    assert after["next"]["episode_number"] == 2
    third = series["seasons"][0]["episodes"][2]["id"]
    through = client.post(f"/api/episodes/{third}/watch-through").json()
    assert through["progress"]["watched"] == 3 and through["next"]["episode_number"] == 4
    season1 = series["seasons"][0]["id"]
    caught = client.post(f"/api/seasons/{season1}/watch").json()
    assert caught["progress"]["caught_up"] is True
    assert caught["next"]["season_number"] == 2 and caught["next"]["state"] == "upcoming"
    assert caught["suggest_completed"] is False  # still returning
    client.delete(f"/api/episodes/{first}/watch")
    # Unwatching an early episode does not rewind "next": it follows the furthest watched.
    assert client.get(f"/api/series/{series['id']}").json()["next"]["season_number"] == 2
    home = client.get("/api/home").json()
    assert home["watching"][0]["id"] == series["id"]
    assert [u["label"] for u in home["upcoming"]][:3] == ["S2E1", "S2E2", "S2E3"]
    assert {e["label"] for e in home["recent"] if e["type"] == "episode"} >= {
        "S1E2",
        "S1E3",
        "S1E4",
    }


def test_refresh_preserves_personal_data_and_identity(ready):
    client, app, provider, _, _ = ready
    series = dexter(client)
    first = series["seasons"][0]["episodes"][0]
    client.post(f"/api/episodes/{first['id']}/watch")
    client.put(
        f"/api/library/series/{series['id']}",
        json={"rating": 9, "notes": "Rewatch S1", "status": "on_hold", "calendar": "always"},
    )
    # Upstream: title changes, an air date moves, the first episode disappears, a season is added.
    provider.tv["name"] = "Dexter: Resurrection"
    provider.tv["seasons_data"][2]["episodes"][0]["air_date"] = "2026-11-16"
    provider.tv["seasons_data"][1]["episodes"] = provider.tv["seasons_data"][1]["episodes"][1:]
    provider.tv["seasons"].append(
        {"id": 13, "season_number": 3, "name": "Season 3", "episode_count": 1}
    )
    provider.tv["seasons_data"][3] = {"id": 13, "episodes": episodes(3, 1, "2027-09-01")}
    with app.state.db.connect() as conn:
        conn.execute("DELETE FROM outbox")
    app.state.refresh("series", series["id"])
    after = client.get(f"/api/series/{series['id']}").json()
    assert after["id"] == series["id"] and after["title"] == "Dexter: Resurrection"
    assert after["library"]["rating"] == 9 and after["library"]["notes"] == "Rewatch S1"
    assert after["library"]["status"] == "on_hold" and after["library"]["calendar"] == "always"
    s2e1 = next(
        e for s in after["seasons"] for e in s["episodes"] if (s["number"], e["number"]) == (2, 1)
    )
    assert (
        s2e1["id"] == series["seasons"][1]["episodes"][0]["id"] and s2e1["air_date"] == "2026-11-16"
    )
    assert first["id"] not in [e["id"] for s in after["seasons"] for e in s["episodes"]]
    with app.state.db.connect() as conn:
        assert (
            conn.execute("SELECT missing FROM episodes WHERE id=?", (first["id"],)).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM history WHERE resource_id=?", (first["id"],)
            ).fetchone()[0]
            == 1
        )
        assert conn.execute("SELECT count(*) FROM outbox WHERE path='/events'").fetchone()[0] == 1
    assert [s["number"] for s in after["seasons"]] == [1, 2, 3, 0]


def query(client, start="2026-06-01", end="2027-12-31", cursor=None):
    return client.post(
        "/empyrean/v1/projections/dated-items",
        headers=RES,
        json={"requester": "chronos", "query": {"from": start, "to": end}, "cursor": cursor},
    )


def test_projection_follows_sharing_settings(ready):
    client = ready[0]
    assert (
        client.post("/empyrean/v1/projections/dated-items", json={"query": {}}).status_code == 403
    )
    series = dexter(client)
    movie = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 900, "status": "planned"}
    ).json()
    client.post("/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "watched"})
    items = query(client).json()["items"]
    # Default: episodes only for series being watched; Dexter is merely planned.
    assert [i["kind"] for i in items] == ["lyra.movie-release", "lyra.movie-release"]
    theatrical, digital = items
    assert (theatrical["start"], theatrical["all_day"], theatrical["certainty"]) == (
        "2026-12-18",
        True,
        "tentative",
    )
    assert theatrical["resource"] == movie["reference"] and theatrical["id"].endswith(":theatrical")
    assert digital["start"] == "2027-02-02"
    client.put("/api/settings", json={"region": "SK"})
    assert [i["start"] for i in query(client).json()["items"]] == ["2026-12-25"]
    client.put("/api/settings", json={"region": "DE"})
    fallback = query(client).json()["items"]
    assert fallback[0]["certainty"] == "estimated" and fallback[0]["start"] == "2026-12-18"

    client.put("/api/settings", json={"calendar_episodes": "tracked", "region": "US"})
    episodes_items = [i for i in query(client).json()["items"] if i["kind"] == "lyra.episode-air"]
    assert len(episodes_items) == 7  # specials excluded
    past = episodes_items[0]
    assert (
        past["start"] == "2026-07-01"
        and past["certainty"] == "confirmed"
        and past["summary"] == "Series premiere"
    )
    assert past["group"] == {"resource": series["reference"], "label": "Dexter"}
    assert "T" not in past["start"]  # date-only stays date-only
    client.put("/api/settings", json={"calendar_premieres_only": True})
    premieres = [i for i in query(client).json()["items"] if i["kind"] == "lyra.episode-air"]
    assert [p["summary"] for p in premieres] == ["Series premiere", "Season 2 premiere"]
    client.put(f"/api/library/series/{series['id']}", json={"calendar": "never"})
    assert not [i for i in query(client).json()["items"] if i["kind"] == "lyra.episode-air"]
    client.put(
        "/api/settings",
        json={
            "calendar_episodes": "selected",
            "calendar_premieres_only": False,
            "calendar_movies": "none",
        },
    )
    client.put(f"/api/library/series/{series['id']}", json={"calendar": "always"})
    selected = query(client, "2026-11-01", "2026-12-01").json()["items"]
    assert [i["title"] for i in selected] == [
        "Dexter · S2E1 · Chapter 1",
        "Dexter · S2E2 · Chapter 2",
        "Dexter · S2E3 · Chapter 3",
    ]
    assert query(client, "2026-11-01", "2026-10-01").status_code == 422


def test_projection_pages(ready, monkeypatch):
    client = ready[0]
    import lyra.app as module

    monkeypatch.setattr(module, "PAGE", 3)
    client.put("/api/settings", json={"calendar_episodes": "tracked"})
    dexter(client)
    first = query(client).json()
    assert len(first["items"]) == 3 and first["next_cursor"] == "3"
    rest = query(client, cursor="3").json()
    assert len(rest["items"]) == 3 and query(client, cursor="6").json()["next_cursor"] is None


def test_resolver_and_backlinks(ready):
    client, _, _, nexus, _ = ready
    series = dexter(client)
    episode = series["seasons"][1]["episodes"][0]

    def resolve(ref):
        return client.post(
            "/empyrean/v1/resources/resolve",
            headers=RES,
            json={"resource": ref, "requester": "chronos"},
        )

    assert resolve(series["reference"]).json()["label"] == "Dexter"
    assert (
        resolve(f"nexus:v1:lyra:episode:{episode['id']}").json()["label"]
        == "Dexter · S2E1 · Chapter 1"
    )
    assert resolve("nexus:v1:lyra:episode:0190f0e4-0000-7000-8000-000000000000").status_code == 404
    nexus.edges[f"nexus:v1:lyra:episode:{episode['id']}"] = [
        {
            "source": "nexus:v1:chronos:event:0190f0e4-0000-7000-8000-000000000001",
            "relation": "chronos.about",
        }
    ]
    planned = client.get(f"/api/series/{series['id']}/planned").json()
    assert planned["available"] and planned["events"][0]["label"] == "Watch together"


def test_movie_history_and_removal(ready):
    client = ready[0]
    movie = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    watched = client.post(
        f"/api/movies/{movie['id']}/watch", json={"watched_at": "2026-10-30T20:00:00+01:00"}
    ).json()
    assert (
        watched["library"]["status"] == "watched"
        and watched["history"][0]["watched_at"] == "2026-10-30T19:00:00Z"
    )
    client.post(f"/api/movies/{movie['id']}/watch")
    assert len(client.get(f"/api/movies/{movie['id']}").json()["history"]) == 2  # rewatches count
    entries = client.get("/api/history").json()["entries"]
    for e in entries:
        client.delete(f"/api/history/{e['id']}")
    assert client.get(f"/api/movies/{movie['id']}").json()["library"]["status"] == "planned"
    client.delete(f"/api/library/movie/{movie['id']}")
    assert client.get("/api/library?type=movie").json()["items"] == []
    readded = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    assert readded["id"] == movie["id"]  # the catalog identity survives removal


def test_images_are_data_uris_and_cached(ready):
    client, _, provider, _, _ = ready
    result = client.post(
        "/api/images", json={"keys": ["w342/matrix.jpg", "w342/../etc.jpg", "x/evil.jpg"]}
    ).json()["images"]
    assert list(result) == ["w342/matrix.jpg"] and result["w342/matrix.jpg"].startswith(
        "data:image/jpeg;base64,"
    )
    count = len(provider.requests)
    client.post("/api/images", json={"keys": ["w342/matrix.jpg"]})
    assert len(provider.requests) == count


def test_provider_outage_keeps_library_usable(ready):
    client, app, provider, _, _ = ready
    series = dexter(client)
    provider.tv = None  # every TMDB request now fails
    app.state.refresh = None
    assert client.get(f"/api/series/{series['id']}").status_code == 200
    assert client.get("/api/home").status_code == 200
    failing = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 12345, "status": "planned"}
    )
    assert failing.status_code == 404 and "TMDB" in failing.json()["detail"]


def test_backup_roundtrip_excludes_credential(ready):
    client, _, _, _, path = ready
    series = dexter(client)
    exported = client.post("/empyrean/v1/backup/export", headers=RES)
    assert exported.status_code == 200 and TOKEN.encode() not in exported.content
    headers = {
        k: v for k, v in exported.headers.items() if k.lower().startswith("x-empyrean-backup-")
    }
    client.delete(f"/api/library/series/{series['id']}")
    assert client.post(
        "/empyrean/v1/backup/validate", headers={**RES, **headers}, content=exported.content
    ).json() == {"valid": True}
    assert client.post(
        "/empyrean/v1/backup/restore", headers={**RES, **headers}, content=exported.content
    ).json() == {"restored": True}
    assert (path / "refresh-suspended").exists()
    assert client.get(f"/api/series/{series['id']}").json()["library"]["status"] == "planned"
    client.post("/empyrean/v1/backup/finalize", headers=RES)
    assert not (path / "refresh-suspended").exists()


def test_interface_uses_shared_design_files(env):
    page = env[0].get("/").text
    assert "Aureate Empyrean shared design tokens — version 2" in page
    assert "--accent: #c98be0" in page.lower()


def test_serves_its_application_icon(env):
    """The manifest `icon` Nexus loads through its gateway: an SVG tile, not the UI page."""
    response = env[0].get("/icon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.lstrip().startswith("<svg") and "<script" not in response.text


def test_backlinks_show_every_shared_link(ready):
    client, _, _, nexus, _ = ready
    movie = client.post(
        "/api/library", json={"kind": "movie", "tmdb_id": 603, "status": "planned"}
    ).json()
    rid = movie.get("id") or movie["movie"]["id"]
    target = f"nexus:v1:lyra:movie:{rid}"
    event = "nexus:v1:chronos:event:0190f0e4-0000-7000-8000-000000000001"
    other = "nexus:v1:mnemosyne:note:0190f0e4-0000-7000-8000-000000000002"
    nexus.edges[target] = [
        {"source": event, "relation": "chronos.about"},
        {"source": other, "relation": "mnemosyne.related"},
        {"source": target, "relation": "lyra.self"},
    ]
    got = client.get(f"/api/movie/{rid}/linked-from").json()
    assert got["availability"] == "available"
    assert [x["module"] for x in got["items"]] == ["chronos", "mnemosyne"]
    assert got["items"][0]["label"] == "Watch together"
