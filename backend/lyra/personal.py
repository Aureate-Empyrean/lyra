"""Atomic optimistic concurrency for a title's entire personal state.

Opaque tokens avoid timestamp collisions and remove/re-add ABA. The first write
obtains SQLite's ordinary transaction write reservation before comparing tokens;
all following personal changes commit or roll back with this comparison.
"""

import secrets

from fastapi import HTTPException


def revision(conn, kind, rid):
    row = conn.execute(
        "SELECT revision FROM personal_revisions WHERE resource_type=? AND resource_id=?",
        (kind, rid),
    ).fetchone()
    return row[0] if row else "0"


def claim(conn, kind, rid, expected):
    if expected is None:
        raise HTTPException(428, "Reload this record before saving; a revision is required.")
    conn.execute("INSERT OR IGNORE INTO personal_revisions VALUES(?,?,'0')", (kind, rid))
    token = secrets.token_hex(16)
    changed = conn.execute(
        "UPDATE personal_revisions SET revision=? "
        "WHERE resource_type=? AND resource_id=? AND revision=? RETURNING revision",
        (token, kind, rid, expected),
    ).fetchone()
    if not changed:
        raise HTTPException(
            409,
            "[LYRA_CONFLICT] This record changed elsewhere. Your edit was not saved. "
            "Review the latest record before retrying.",
        )
    return token
