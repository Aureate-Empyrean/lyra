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
- **Discover**: TMDB search (clearly separated from your library results), trending, upcoming
  cinema releases (your region), series on the air. Previews are not stored until you act.
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

## Run through Nexus

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

## Localization

All interface strings use the message catalog (`frontend/locales/en.json`); `Intl` formats
dates, regions and relative times. Add catalogs (e.g. `sk.json`) to `frontend/locales` or to
`/data/locales/<language-tag>.json`. TMDB metadata language is a separate setting.
