# WP01 privacy-first Lyra search

Date: 2026-11-10 (Europe/Bratislava). WP01 finalized for its isolated branch; no merge, push or deployment.

## Behavior

- Ordinary search remains scoped to the existing personal library, using the same query matching, result limits and cards. Typing, Enter, debounce and empty results never invoke provider search. The compatible `/api/search` response now always has `remote: []` and `remote_error: null`.
- **Search TMDB** is an explicit external action for the current words. It sends a bounded JSON POST to `/api/search/external`; existing server-side credentials, TMDB client, identity mapping and error handling are reused. No private query was added to navigation URLs or application logs.
- Discover opens as a passive page. **Browse TMDB recommendations** explicitly loads the existing trending/upcoming/on-air results. Preview routes likewise require **Load details from TMDB**, including direct URLs, reload and history restoration. Preview/add-to-library functionality remains available.
- External results/intent are transient, outside the P1 view-state contract. Changed queries invalidate results immediately. New renders, query changes and leaving the page suppress obsolete responses and subsequent artwork batches; duplicate clicks while loading are disabled.
- Passive artwork hydration is cache-only. Missing images keep the existing designed placeholder; explicit external actions may fetch/cache artwork. Cached artwork remains readable after removing the provider credential, and local search still works.
- Local filters, sorting, routes, draft handling, P1 navigation adapter and vendored SDK are unchanged. Existing separately authorized credential verification, explicit metadata/add actions and scheduled background metadata refresh are unchanged.

## Files changed

| File | Purpose |
|---|---|
| `backend/lyra/app.py` | Local-only search, bounded explicit external endpoint, cached-only artwork option. |
| `frontend/app.js` | Clear local/external actions, passive recommendations/preview mounts, stale-response guards and cached-only passive images. |
| `frontend/style.css` | Space between explicit action and external results. |
| `frontend/locales/en.json` | New action labels and accurate credential-removal explanation. |
| `tests/test_lyra.py` | Explicit search expectations, zero-provider local/cache tests, input validation and provider-failure isolation. |
| `tests/e2e/search_harness.py` | Disposable synthetic backend, P1 host and real loopback HTTP provider; no live Nexus connection. |
| `tests/e2e/privacy_search.cjs` | Seven real-browser network/navigation/error/race/layout scenarios. |
| `README.md` | Search/privacy/API behavior, test setup and cancellation boundary. |
| `docs/WP01_PRIVACY_SEARCH_VALIDATION.md` | This handoff record. |

## Tests executed

Using the isolated worktree's Python environment with `requirements-dev.lock` installed:

| Check | Result |
|---|---|
| `.venv/Scripts/python -m pytest -q` | **21 passed**. One existing Starlette/httpx deprecation warning. |
| `node --test tests/e2e/privacy_search.cjs` | **7 passed**, Chromium. |
| Nexus `node --test tests/frontend.test.mjs tests/navigation.test.mjs` | **31 passed**, including the existing P1 protocol, history, private view state, draft checkpoint, legacy fallback and SDK-vendoring regressions. |
| Nexus `pytest -q -p no:cacheprovider tests/test_navigation_history.py` | **1 passed**, existing P1 backend negotiation/default/authentication regression. |
| `.venv/Scripts/ruff check backend tests scripts` | Passed. |
| `node --check frontend/app.js` and `node --check tests/e2e/privacy_search.cjs` | Passed. |
| Ruff format checks for changed Python test files | Passed. |
| `git diff --check` | Passed. |
| Whole-repository `ruff format --check backend tests scripts` | Retains two pre-existing unformatted statements in the unrelated backlink handler in `backend/lyra/app.py`. The base commit fails the formatter too; these statements were deliberately left unchanged. |

Finalization reran the full Lyra backend suite, all seven isolated Chromium scenarios and the shared Nexus UI/P1 tests. Firefox and WebKit availability was checked through the installed Playwright executable paths and browser-cache inventory: neither engine is installed, so neither was run. No browser installation or host security setting was changed.

Formatting provenance was verified programmatically against base commit `8f03579`: formatting the base and WP01 versions produces exactly the same two replacement blocks. Both are inside the unrelated `linked_from` backlink handler: the existing `nexus.request` call and the existing `entry` dictionary literal. Their source content is unchanged by WP01; no formatter fixes were mixed into this commit. The P1 adapter and vendored SDK likewise match the base Git content, normalizing checkout line endings.

The backend suite verifies no provider call for configured local searches, empty/nonmatching queries and cache misses; explicit query handling and stable resource mapping; cached images after credential removal; invalid external input and failed provider search. Existing metadata/history/projection/backup tests also pass.

The browser suite uses the actual rendered Lyra frontend, actual backend endpoints, unchanged P1 host SDK/client adapter, browser messages and real browser history. Provider requests use real HTTP sockets to a separate synthetic loopback server, with independent counters for search/images/details/recommendations. Browser-origin requests are also observed; the explicit search is a POST. The harness uses random loopback ports and a temporary synthetic library, never shared data. It prevents inherited Nexus URL/token use and forces provider traffic to its local server. Uvicorn access logging is disabled.

Verified browser scenarios:

1. Initial mount, rapid typing, matching/empty local results and cached-only artwork: **zero provider HTTP requests**, including uncached artwork.
2. Explicit search: one provider search request on a cold query; results, explicit preview and add-to-library work.
3. Search refresh and actual Back/Forward preserve private local query state without provider requests or replaying external intent.
4. Direct Discover/preview URLs, clearing/short queries and refresh stay passive; explicit recommendations make the existing three provider requests.
5. Slow external response after query change is ignored; provider failure does not break local results and explicit retry works.
6. Existing movie filter, keyboard Enter search and 390/1440 px layouts work; no browser page errors.
7. Leaving during an in-flight external request does not inject stale results or start subsequent artwork requests.

Synthetic screenshots, generated and visually inspected, are ignored local artifacts:
`artifacts/wp01-search-phone.png` and `artifacts/wp01-search-desktop.png`. The solid fixture image represents fake artwork, not a real photograph.

## Branch, commit and safety

- Worktree: `G:/AureateEmpyrean/lyra-wp01-privacy-first-search`.
- Branch: `codex/wp01-privacy-first-search`.
- Base commit: `8f03579b3188c11aca6bce9bebb36a79a3379e00` (release provenance after P1). The implementation and final validation record are committed together on `codex/wp01-privacy-first-search`; identify the final commit with `git log -1` on that branch. No existing release branch or tag is moved.
- Original Lyra checkout remains clean on `release/p1-navigation`. Its branch, existing release tags and P1 navigation files were not changed. The task adds its own isolated branch/worktree only.
- No Meridian, Atlas, Argus or Nexus files were modified. No real credentials or personal records were used, and no production/aetest database, container or service was accessed or deployed.

## Limits

No live TMDB account/API was exercised: upstream responses are synthetic, carried over actual loopback HTTP. Browser verification is Chromium only; Firefox/WebKit were not installed. This is a real-browser/application-network test, not evidence of live-provider availability or a full production Nexus deployment.

The existing cross-module `aetest` universal-navigation journey was not run: it uses shared records/services and would exercise the deployed P1 release rather than this isolated WP01 candidate. P1 regression evidence here is the existing shared protocol/UI suite plus actual local history/restore behavior through the unchanged P1 SDK/adapter in the seven Chromium scenarios.

The existing request bridge cannot cancel a provider request already forwarded by the server. Such a request can finish, but obsolete results are ignored and no further artwork batch is started. No P1 bridge modification was introduced to change this contract. Existing background metadata refresh is independent of personal-library search and remains enabled according to the prior settings.

No schema, migration, version, capability or navigation-protocol change is needed. Older callers of ordinary search now receive only local results; explicit external callers must use the new POST endpoint. Rolling back should retain a local-only safe fallback rather than restore implicit query disclosure.
