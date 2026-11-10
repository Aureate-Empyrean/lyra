"""Sequential legacy regressions explicitly model a freshly-read API client.

Concurrency tests use raw TestClient instances instead; this helper must never be
used to test stale writes, missing preconditions or races.
"""

import re
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from lyra.personal import revision


class CurrentRevisionClient(TestClient):
    def request(self, method, url, **kwargs):
        path = urlsplit(str(url)).path
        kind = rid = None
        if method.upper() != "GET" and path.startswith("/api/"):
            path = path[4:]
            with self.app.state.db.connect() as conn:
                if path == "/settings":
                    kind, rid = "settings", "global"
                elif path == "/library":
                    body = kwargs.get("json") or {}
                    kind = "movie" if body.get("kind") == "movie" else "series"
                    row = conn.execute(
                        "SELECT resource_id FROM external_ids WHERE provider='tmdb' "
                        "AND kind=? AND external_id=?",
                        (body.get("kind"), str(body.get("tmdb_id"))),
                    ).fetchone()
                    rid = row[0] if row else "new"
                elif match := re.match(r"/(?:library/)?(movie|series|movies)/([^/]+)", path):
                    kind = "movie" if match[1] == "movies" else match[1]
                    rid = match[2]
                elif match := re.match(r"/(episodes|seasons|history)/([^/]+)", path):
                    table, item = match.groups()
                    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (item,)).fetchone()
                    if row and table == "history":
                        kind, rid = row["resource_type"], row["resource_id"]
                        if kind == "episode":
                            rid = conn.execute(
                                "SELECT series_id FROM episodes WHERE id=?", (rid,)
                            ).fetchone()[0]
                            kind = "series"
                    elif row:
                        kind, rid = "series", row["series_id"]
                if kind and rid:
                    kwargs["params"] = {
                        "expected_revision": revision(conn, kind, rid),
                        **(kwargs.get("params") or {}),
                    }
        return super().request(method, url, **kwargs)
