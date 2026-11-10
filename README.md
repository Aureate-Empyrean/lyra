# Lyra

The consumed-media library of Aureate Empyrean. Long-term: multimedia library and playback —
music first; movies, TV, books, audiobooks later. **0.1.0 implements films and series
tracking**; music, books, audiobooks, playback, *arr integrations and streaming providers are
not implemented. Canonical architecture: `../architecture/modules/lyra.md` (ADR 0010, 0011,
0012, 0013). Licensed AGPL-3.0-or-later.

## Included (0.1.0)

- **Up next**: series you are watching with the next episode and one-click "Watched";
  upcoming episodes and watchlist releases for 60 days; recently watched.
- **Series**: plan, watching, on hold, completed, dropped; seasons and episodes from TMDB;
  mark an episode, "watched up to here" or a whole season; next episode follows the furthest
  watched one; rewatches; completion is suggested, never forced.
- **Movies**: watchlist and watched with viewing history (rewatches kept).
- Personal rating (1–10), notes, per-title calendar sharing, "Planned in Chronos" backlinks.
- **Search your library** stays local, including empty results and rapid typing.
- **Discover**: explicitly choose **Search TMDB** for the current words, or **Browse TMDB
  recommendations** for trending, upcoming cinema releases (your region) and series on the air.
  Preview pages require **Load details from TMDB**. Previews are not stored until you add them.
- History grouped by day, with per-entry removal.
- Release dates: date-only; theatrical, digital and disc dates for your release region,
  falling back to TMDB's primary date marked *estimated*; future dates are *may change*.

## Identity and data ownership

Movie, Series, Season and Episode are Lyra resources with UUIDv7 identities
(`nexus:v1:lyra:<type>:<uuid>`). TMDB, IMDb and TVDB IDs are external mappings; a title found
again by any path (TMDB ID, then IMDb ID) maps to the same resource. Provider metadata and your
data are stored in separate tables; refreshing metadata never changes status, rating, notes,
history or calendar choices. Episodes removed upstream are marked missing, never deleted with
their history. Removing a title from the library deletes your data for it but keeps its
identity, so re-adding it is the same resource.

## Concurrent personal edits (0.3.0 candidate)

Movies and series now have an opaque personal-data revision, independent of provider
metadata. Notes, ratings, status/watchlist, calendar preferences, watch/unwatch, season
progress and history removal all compare that revision atomically before writing. Library-wide
settings have their own revision. An outdated write receives HTTP 409; an existing-record
mutation without a revision receives HTTP 428. The request parameter is `expected_revision`;
use the token from the record or settings snapshot the user actually edited, not a fresh
unreviewed read immediately before saving. Initial creation of a never-tracked provider title
can use `0`; a removed/re-added title retains its revision history and needs its current token.

On conflict Lyra keeps the pending change and shows **Review latest**. Only after reviewing
the saved values can the user choose **Apply my change after review**, which compares the
reviewed revision again. It never forces a write or merges conflicts automatically. Removed
records cannot be silently recreated by a stale edit. Notes and pending conflicts survive P1
Back/Forward and refresh in the existing owner/tab-scoped draft checkpoint, with their original
base revisions. The shared navigation SDK and routes are unchanged. Standalone/legacy-host
navigation retains in-memory drafts; durable refresh recovery requires a supporting P1 host.

Schema 1 → 2 adds `personal_revisions` and seeds existing title/settings tokens without changing
personal records or identities. Before an upgrade, retain and validate the pre-update database
backup; this task migrated only backed-up disposable fixtures. Schema-2 backups require the
0.3.0 candidate or later, and restore invalidates outstanding tokens. Roll back with the previous
image **and its pre-migration backup**, never the old image against the schema-2 database.
See `docs/WP02B_CONCURRENT_EDITS_VALIDATION.md` for scope, tests and integration limits.

## TMDB setup

1. Create a TMDB account and request an API key at <https://www.themoviedb.org/settings/api>.
2. Copy the **API Read Access Token** (recommended) or the v3 API key.
3. In Lyra: Settings → Metadata provider → paste → **Verify and save**.

Lyra checks the credential with TMDB, then stores it in the module's data volume
(`/data/secrets/tmdb.json`, mode 0600). It is never returned to the browser, logged, sent to
Nexus or included in backups (re-enter it after a restore). No rebuild or environment variable
is needed. Requests to TMDB carry only search text, TMDB IDs, language and region; posters and
stills are fetched by the server and cached in `/data/images`. Lyra keeps working from local
data when TMDB is unavailable. Requests are limited to 4 concurrent calls, retried on 429 with
`Retry-After`, 10 s timeout. Library titles refresh in the background (watching 12 h, planned
24 h, ended 14 days; upcoming movies daily) and on demand.

Opening/restoring Discover or a preview, refreshing, and Back/Forward never authorize a new
provider lookup. External results are transient; changing the query or leaving the screen
requires another explicit action. Ordinary rendering reads cached artwork only, with a
placeholder for missing images; explicit discovery may fetch and cache provider artwork.
An already forwarded provider request cannot be cancelled by the existing Nexus bridge, but
obsolete results are ignored and no further artwork batches are sent. Existing authorized
background metadata refresh, credential verification and explicit add/refresh actions are unchanged.

`GET /api/search?q=…` keeps its local/remote response envelope, always returning an empty
remote list. Explicit search uses `POST /api/search/external` with a bounded `query` JSON body;
the provider query is not added to browser navigation URLs. `POST /api/images` supports
`cached_only: true` to forbid a provider fetch on a cache miss.

This product uses the TMDB API but is not endorsed or certified by TMDB. (The attribution is
shown in Discover, search, title pages and Settings; TMDB's logo is not bundled.)

## Sharing with Chronos

Lyra provides the `dated-items` projection (architecture `concepts/projections.md`). Settings
choose what is shared: episodes of series you are watching (default), of every non-dropped
series, of selected series only, or none; optionally season premieres only; watchlist movie
releases (default) or none; per title "always" or "never". Lyra publishes the hint
`lyra.dated-items.changed` when shared dates or choices change; Chronos also reconciles every
15 minutes, so a lost hint is harmless.

## Design

Lyra uses token set 2.1 and foundation 1.1 (architecture ADR 0012, ADR 0014) with its own cinematic composition: a projector-light atmosphere in orchid and indigo, a floating glass rail and search bar, a spotlight hero for the series you are watching, full-bleed title heroes lit by the artwork, designed artwork fallbacks (title-derived hue and the title set on the poster) until TMDB images load, a date-badge release timeline and glass panels. Before/after screenshots (Playwright, 1440 px and 390 px, inside the Nexus sandbox): `docs/screenshots/`.

Its application icon (0.1.1) is the header's lyre mark on its lavender-to-indigo tile, served at `/icon.svg` for Nexus (manifest `icon`).

## Navigation (0.2.0 on aetest)

Lyra's views and titles are browser history entries through the Nexus navigation contract (`frontend/navigation.js`,
references `/`, `/series`, `/movies`, `/discover`, `/history`, `/series/<id>`, `/movie/<id>`, `/preview/<kind>/<tmdb>`).
Search text and filters are private per-entry state. The arrow on a title goes up to its list; browser Back is the
traversal. Notes are saved on the way out, or kept as a draft if that fails. See
`../empyrean-nexus/docs/navigation-history.md`.

## Run through Nexus

0.1.3 (production since 2026-11-09) opens a title from a deep link. 0.1.2 adds a [Linked from other modules](../architecture/concepts/backlinks.md) panel on titles ([record](../VALIDATION_PHASE4_AETEST_2026-11-09.md)).

Requires Nexus 0.1.8 or later within 0.1.x (0.1.1 declares an application icon). Port 16333.

```sh
docker compose build
python scripts/manifest.py
```

Review and install `manifest.local.json`, enable, open `/app/modules/lyra`. Requested
permissions: full-window application, private data volume, outbound network (TMDB API and
image hosts only, by code), event publication (`lyra.dated-items.changed`), reference reads
and resolution of Chronos events (backlinks), projection provider `dated-items`, backup v1.
Resolution discloses catalog titles and dates to modules the owner granted a resolve scope.

## Development and tests

```sh
python -m venv .venv && .venv/bin/pip install -r requirements-dev.lock
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend tests scripts && .venv/bin/ruff format --check backend tests scripts
node --check frontend/app.js
```

TMDB is replaced by an `httpx` mock in tests: credential validation and privacy, search and
identity mapping, duplicate detection by IMDb ID, episode tracking and next episode, refresh
that preserves personal data and identities, projection rules (policies, premieres, regions,
fallback, certainty, paging), resolver and backlinks, history, image data URIs and caching,
provider outage, backup without the credential, shared design files. A live TMDB request has
not been verified in this repository's test runs (no credential was available).

The isolated real-browser privacy suite uses the actual Lyra backend, unchanged P1 SDK/adapter,
and a synthetic TMDB HTTP server over loopback sockets. It creates temporary data, random ports,
and synthetic credentials; it cannot contact aetest, Exodus or the live provider. With Playwright
and Chromium installed, run `node --test tests/e2e/privacy_search.cjs`. It reuses the workspace's
Playwright by default; set `PLAYWRIGHT_PATH` for another installation and `PYTHON` for a non-Windows
virtual-environment executable. It verifies provider HTTP counts, actual browser requests, explicit
search/recommendations/preview/add, errors, stale responses, private state restoration and filters.

## Localization

All interface strings use the message catalog (`frontend/locales/en.json`); `Intl` formats
dates, regions and relative times. Add catalogs (e.g. `sk.json`) to `frontend/locales` or to
`/data/locales/<language-tag>.json`. TMDB metadata language is a separate setting.
