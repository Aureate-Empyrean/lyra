"""Real SQLite transactions and raw API clients: no automatic token refresh."""

import sqlite3
import subprocess
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from lyra.app import create_app
from lyra.db import MIGRATIONS, Database
from lyra.library import now_iso, upsert_movie, upsert_series
from lyra.personal import revision
from lyra.tmdb import Credential

KEY = "synthetic-concurrency-key-" * 2
GW = {"x-nexus-gateway-key": KEY}
MOVIE = {"id": 101, "title": "Synthetic Orbit", "release_date": "2020-01-01"}


class NoNexus:
    def request(self, *args, **kwargs):
        return {"references": []}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_RESOLVER_KEY", KEY)

    def provider(request):
        return httpx.Response(200, json={**MOVIE, "title": "Synthetic updated metadata"})

    app = create_app(
        tmp_path, nexus=NoNexus(), workers=False, tmdb_transport=httpx.MockTransport(provider)
    )
    Credential(tmp_path).set(".".join(["synthetic"] * 3))
    with app.state.db.connect() as conn:
        mid = upsert_movie(conn, MOVIE)
        sid = upsert_series(
            conn,
            {
                "id": 303,
                "name": "Synthetic Series",
                "status": "Ended",
                "seasons": [{"season_number": 1, "episode_count": 2}],
            },
            {
                1: {
                    "episodes": [
                        {"id": 501, "episode_number": 1, "name": "One", "air_date": "2020-01-01"},
                        {"id": 502, "episode_number": 2, "name": "Two", "air_date": "2020-01-02"},
                    ]
                }
            },
            complete=True,
        )
        for kind, rid in [("movie", mid), ("series", sid)]:
            conn.execute(
                "INSERT INTO library(resource_type,resource_id,status,notes,added_at,updated_at) VALUES(?,?,'planned','base',?,?)",
                (kind, rid, now_iso(), now_iso()),
            )
        season = conn.execute("SELECT id FROM seasons WHERE series_id=?", (sid,)).fetchone()[0]
        episodes = [r[0] for r in conn.execute("SELECT id FROM episodes ORDER BY episode_number")]
    with TestClient(app, headers=GW) as first, TestClient(app, headers=GW) as second:
        yield (
            first,
            second,
            app,
            {"movie": mid, "series": sid, "season": season, "episodes": episodes},
        )


def read(client, kind, rid):
    return client.get(f"/api/{'movies' if kind == 'movie' else 'series'}/{rid}").json()


def mutate(client, method, path, token, body=None):
    kwargs = {"params": {"expected_revision": token}}
    if body is not None:
        kwargs["json"] = body
    return client.request(method, "/api" + path, **kwargs)


@pytest.mark.parametrize("kind", ["movie", "series"])
def test_two_clients_same_revision_cannot_overwrite(world, kind):
    a, b, _, ids = world
    first, second = read(a, kind, ids[kind]), read(b, kind, ids[kind])
    assert first["revision"] == second["revision"]
    winner = mutate(
        a,
        "PUT",
        f"/library/{kind}/{ids[kind]}",
        first["revision"],
        {"notes": "first client", "rating": 8},
    )
    assert winner.status_code == 200 and winner.json()["revision"] != first["revision"]
    loser = mutate(
        b,
        "PUT",
        f"/library/{kind}/{ids[kind]}",
        second["revision"],
        {"notes": "second client", "rating": 2},
    )
    assert loser.status_code == 409
    saved = read(a, kind, ids[kind])
    assert saved["library"]["notes"] == "first client" and saved["library"]["rating"] == 8
    assert saved["revision"] == winner.json()["revision"]


def test_atomic_simultaneous_writers_and_repeated_watch(world):
    a, b, _, ids = world
    token = read(a, "movie", ids["movie"])["revision"]
    barrier = threading.Barrier(2)

    def write(client):
        barrier.wait()
        return mutate(client, "POST", f"/movies/{ids['movie']}/watch", token)

    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(write, [a, b]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(read(a, "movie", ids["movie"])["history"]) == 1
    for _ in range(5):
        assert mutate(b, "POST", f"/movies/{ids['movie']}/watch", token).status_code == 409
    assert len(read(a, "movie", ids["movie"])["history"]) == 1


@pytest.mark.parametrize("operation", ["watch", "unwatch", "through", "season", "unseason"])
def test_episode_and_season_progress_share_the_series_revision(world, operation):
    a, b, _, ids = world
    old = read(a, "series", ids["series"])["revision"]
    assert mutate(a, "POST", f"/episodes/{ids['episodes'][0]}/watch", old).status_code == 201
    method, path = {
        "watch": ("POST", f"/episodes/{ids['episodes'][1]}/watch"),
        "unwatch": ("DELETE", f"/episodes/{ids['episodes'][0]}/watch"),
        "through": ("POST", f"/episodes/{ids['episodes'][1]}/watch-through"),
        "season": ("POST", f"/seasons/{ids['season']}/watch"),
        "unseason": ("DELETE", f"/seasons/{ids['season']}/watch"),
    }[operation]
    assert mutate(b, method, path, old).status_code == 409
    saved = read(a, "series", ids["series"])
    assert saved["progress"]["watched"] == 1 and saved["library"]["status"] == "watching"
    assert (
        mutate(b, "PUT", f"/library/series/{ids['series']}", old, {"status": "dropped"}).status_code
        == 409
    )


@pytest.mark.parametrize("kind", ["movie", "series"])
def test_removal_and_readd_never_reuse_old_revision(world, kind):
    a, b, _, ids = world
    old = read(a, kind, ids[kind])["revision"]
    path = f"/library/{kind}/{ids[kind]}"
    assert mutate(a, "DELETE", path, old).status_code == 200
    assert mutate(b, "PUT", path, old, {"notes": "stale resurrection"}).status_code == 409
    assert mutate(b, "DELETE", path, old).status_code == 409
    removed = read(a, kind, ids[kind])
    assert removed["library"] is None and removed["revision"] != old
    assert (
        mutate(b, "PUT", path, removed["revision"], {"notes": "still removed"}).status_code == 409
    )
    assert read(a, kind, ids[kind])["library"] is None
    if kind == "movie":
        readded = mutate(
            a,
            "POST",
            "/library",
            removed["revision"],
            {"kind": "movie", "tmdb_id": 101, "status": "planned"},
        )
        assert readded.status_code == 201
        assert readded.json()["revision"] not in {old, removed["revision"]}
        assert mutate(b, "PUT", path, old, {"notes": "old incarnation"}).status_code == 409


def test_history_delete_and_settings_require_current_tokens(world):
    a, b, _, ids = world
    watched = mutate(a, "POST", f"/movies/{ids['movie']}/watch", "0").json()
    hid = watched["history"][0]["id"]
    assert mutate(a, "DELETE", f"/history/{hid}", watched["revision"]).status_code == 200
    assert mutate(b, "DELETE", f"/history/{hid}", watched["revision"]).status_code == 409
    assert read(a, "movie", ids["movie"])["library"]["status"] == "planned"
    old = a.get("/api/state").json()["settings"]["revision"]
    assert mutate(a, "PUT", "/settings", old, {"region": "SK"}).status_code == 200
    assert mutate(b, "PUT", "/settings", old, {"region": "DE"}).status_code == 409
    assert a.get("/api/state").json()["settings"]["region"] == "SK"


def test_preconditions_authorization_and_failed_validation_change_nothing(world):
    a, _, _, ids = world
    path = f"/api/library/movie/{ids['movie']}"
    before = read(a, "movie", ids["movie"])
    assert a.put(path, json={"notes": "missing precondition"}).status_code == 428
    assert (
        a.put(
            path,
            params={"expected_revision": "0"},
            json={"notes": "unauthorized"},
            headers={"x-nexus-gateway-key": "wrong"},
        ).status_code
        == 403
    )
    assert (
        mutate(
            a, "POST", f"/movies/{ids['movie']}/watch", "0", {"watched_at": "not a date"}
        ).status_code
        == 422
    )
    assert read(a, "movie", ids["movie"]) == before


def test_metadata_refresh_is_not_a_personal_edit_and_read_snapshots_are_consistent(world):
    a, b, app, ids = world
    old = read(a, "movie", ids["movie"])
    app.state.refresh("movie", ids["movie"])
    latest = read(a, "movie", ids["movie"])
    assert latest["title"] == "Synthetic updated metadata" and latest["revision"] == old["revision"]
    with app.state.db.connect(snapshot=True) as reader:
        assert (
            reader.execute(
                "SELECT notes FROM library WHERE resource_id=?", (ids["movie"],)
            ).fetchone()[0]
            == "base"
        )
        assert (
            mutate(
                b, "PUT", f"/library/movie/{ids['movie']}", old["revision"], {"notes": "new"}
            ).status_code
            == 200
        )
        assert revision(reader, "movie", ids["movie"]) == old["revision"]
        assert (
            reader.execute(
                "SELECT notes FROM library WHERE resource_id=?", (ids["movie"],)
            ).fetchone()[0]
            == "base"
        )


def test_schema_migration_and_rollback_preserve_personal_data(tmp_path):
    path, backup, rollback = [
        tmp_path / name
        for name in ["development.sqlite3", "before-schema-2.bak", "rollback.sqlite3"]
    ]
    with sqlite3.connect(path) as conn:
        conn.executescript(MIGRATIONS[0] + "PRAGMA user_version=1;")
        rid = upsert_movie(conn, MOVIE)
        conn.execute(
            "INSERT INTO library VALUES('movie',?,'planned',9,'synthetic note','never',?,?)",
            (rid, now_iso(), now_iso()),
        )
        conn.commit()
        with sqlite3.connect(backup) as saved:
            conn.backup(saved)
    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        row = dict(conn.execute("SELECT * FROM library").fetchone())
        assert (
            row["notes"] == "synthetic note" and row["rating"] == 9 and row["calendar"] == "never"
        )
        assert revision(conn, "movie", rid) != "0"
    legacy = types.ModuleType("wp01_database")
    exec(
        subprocess.check_output(["git", "show", "075b72c:backend/lyra/db.py"]).decode(),
        legacy.__dict__,
    )
    with pytest.raises(RuntimeError, match="newer"):
        legacy.Database(path)
    with sqlite3.connect(backup) as saved, sqlite3.connect(rollback) as target:
        saved.backup(target)
    with legacy.Database(rollback).connect() as conn:
        assert dict(conn.execute("SELECT * FROM library").fetchone()) == row
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_restore_rotates_tokens_and_preserves_data(world):
    a, b, _, ids = world
    headers = {"x-nexus-resolver-key": KEY}
    old = read(a, "movie", ids["movie"])
    exported = a.post("/empyrean/v1/backup/export", headers=headers)
    headers.update(
        {k: v for k, v in exported.headers.items() if k.startswith("x-empyrean-backup-")}
    )
    assert (
        mutate(
            a, "PUT", f"/library/movie/{ids['movie']}", old["revision"], {"notes": "later"}
        ).status_code
        == 200
    )
    assert (
        a.post("/empyrean/v1/backup/restore", headers=headers, content=exported.content).status_code
        == 200
    )
    restored = read(a, "movie", ids["movie"])
    assert restored["library"] == old["library"] and restored["revision"] != old["revision"]
    assert (
        mutate(
            b,
            "PUT",
            f"/library/movie/{ids['movie']}",
            old["revision"],
            {"notes": "pre-restore draft"},
        ).status_code
        == 409
    )


def test_sql_failure_rolls_back_revision_and_personal_fields(world):
    a, _, app, ids = world
    before = read(a, "movie", ids["movie"])
    with app.state.db.connect() as conn:
        conn.executescript(
            "CREATE TRIGGER refuse_notes BEFORE UPDATE OF notes ON library BEGIN SELECT RAISE(ABORT,'synthetic disk failure'); END;"
        )
    with pytest.raises(sqlite3.IntegrityError):
        mutate(
            a,
            "PUT",
            f"/library/movie/{ids['movie']}",
            before["revision"],
            {"notes": "cannot persist"},
        )
    assert read(a, "movie", ids["movie"]) == before


def test_episode_history_delete_uses_parent_series_revision(world):
    a, b, _, ids = world
    watched = mutate(a, "POST", f"/episodes/{ids['episodes'][0]}/watch", "0").json()
    item = a.get("/api/history").json()["entries"][0]
    assert item["revision"] == watched["revision"]
    updated = mutate(
        a, "PUT", f"/library/series/{ids['series']}", watched["revision"], {"calendar": "never"}
    ).json()
    assert mutate(b, "DELETE", f"/history/{item['id']}", watched["revision"]).status_code == 409
    assert read(a, "series", ids["series"])["progress"]["watched"] == 1
    assert mutate(a, "DELETE", f"/history/{item['id']}", updated["revision"]).status_code == 200
    assert read(a, "series", ids["series"])["progress"]["watched"] == 0


def test_damaged_revision_schema_is_refused_before_restore(world, tmp_path):
    a, _, _, ids = world
    headers = {"x-nexus-resolver-key": KEY}
    before = read(a, "movie", ids["movie"])
    exported = a.post("/empyrean/v1/backup/export", headers=headers)
    headers.update(
        {k: v for k, v in exported.headers.items() if k.startswith("x-empyrean-backup-")}
    )
    damaged = tmp_path / "synthetic-damaged-backup.sqlite3"
    damaged.write_bytes(exported.content)
    with sqlite3.connect(damaged) as conn:
        conn.execute("DROP TABLE personal_revisions")
    assert (
        a.post(
            "/empyrean/v1/backup/restore", headers=headers, content=damaged.read_bytes()
        ).status_code
        == 422
    )
    assert read(a, "movie", ids["movie"]) == before


def test_schema_one_backup_restores_forward_without_losing_personal_data(world, tmp_path):
    a, _, _, ids = world
    before = read(a, "movie", ids["movie"])
    headers = {"x-nexus-resolver-key": KEY}
    exported = a.post("/empyrean/v1/backup/export", headers=headers)
    headers.update(
        {k: v for k, v in exported.headers.items() if k.startswith("x-empyrean-backup-")}
    )
    old = tmp_path / "synthetic-schema-one.sqlite3"
    old.write_bytes(exported.content)
    with sqlite3.connect(old) as conn:
        conn.execute("DROP TABLE personal_revisions")
        conn.execute("PRAGMA user_version=1")
    headers["x-empyrean-backup-module-version"] = "0.2.0"
    headers["x-empyrean-backup-restorable-by"] = ">=0.2.0,<1"
    assert (
        a.post(
            "/empyrean/v1/backup/validate", headers=headers, content=old.read_bytes()
        ).status_code
        == 200
    )
    assert (
        a.post("/empyrean/v1/backup/restore", headers=headers, content=old.read_bytes()).status_code
        == 200
    )
    restored = read(a, "movie", ids["movie"])
    assert restored["id"] == before["id"] and restored["library"] == before["library"]
    assert restored["revision"] != before["revision"]
