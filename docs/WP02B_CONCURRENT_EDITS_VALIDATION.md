# Lyra personal-data concurrency — WP02b

Date: 2026-11-10 (Europe/Bratislava). Candidate 0.3.0, schema 2. Local implementation and validation only; no merge, push, image build, aetest change or deployment.

## Mechanism and scope

Each movie or series has one opaque random revision token for its complete mutable personal aggregate: library presence, watchlist/status, notes, rating, per-title calendar policy, viewing history and episode/season progress. Library-wide settings have a separate token. Provider metadata refresh does not consume a personal token.

The owning API accepts `expected_revision` as a query parameter. It atomically compares-and-replaces the aggregate token in `personal_revisions`, in the same real SQLite transaction as all associated changes. A mismatch returns **409**, rolling back every change, including the provisional token. Missing preconditions on existing update/watch/progress/settings/delete operations return **428**; already-removed history/library cases report conflict. SQLite's normal short write transaction serializes the comparison; no application-wide mutex, timestamp ordering or long provider-network lock is introduced. Explicit snapshot read transactions keep personal data and its returned token consistent.

For a never-mutated title the initial token is `0`. Adding a new provider title may assume that initial token. Once written, removal and re-addition retain/advance its ledger token, so an old edit cannot become valid again. Repeated requests with an already-consumed token cannot duplicate viewing history or overwrite later values. A user can deliberately rewatch with a new current token; a stale automatic retry cannot do so.

| Entity / operation | Protected endpoints |
|---|---|
| Create/re-add, notes, rating, status/watchlist, calendar policy, removal | `POST /api/library`; `PUT` and `DELETE /api/library/{movie|series}/{id}` |
| Movie viewing history/status | `POST /api/movies/{id}/watch` |
| Episode progress, rewatches and watch-through | `POST`/`DELETE /api/episodes/{id}/watch`; `POST /api/episodes/{id}/watch-through` |
| Season progress | `POST`/`DELETE /api/seasons/{id}/watch` |
| Individual history removal, including parent movie/series effects | `DELETE /api/history/{id}` |
| Region, language and global calendar-sharing policy | `PUT /api/settings` |

Movie/series detail responses, local library cards and history entries expose the aggregate revision. Settings snapshots include their separate revision. Tokens are not placed in browser navigation URLs or logs. Existing gateway/resolver authorization is unchanged. Personal credentials/provider configuration are outside this aggregate; no Janus, Nexus, Chronos, Meridian, Atlas or Argus implementation is touched.

## Conflict experience and draft integrity

The interface sends the revision associated with the rendered record, never an unreviewed fresh token obtained just before saving. Notes retain their own base token while edited. On conflict:

1. The pending change is retained; a labelled **Changed elsewhere** panel explains that it was not saved.
2. **Review latest** loads the saved values alongside the pending change without writing anything or replacing the draft.
3. **Apply my change after review** uses the reviewed token. An intervening write produces another conflict and requires another review.
4. Removed records cannot be resurrected by a stale personal patch. The draft remains recoverable; re-adding the title is an explicit separate action.
5. Discarding a pending notes change explicitly reloads the saved note. If the draft changes during that read, the newer draft stays kept.

Notes entered during an in-flight save or reviewed retry are not cleared by the older response. Note saves in one tab serialize against their own confirmed successful writes; this is not automatic merging with another client's edit. Generic conflicts are not automatically retried.

The Lyra P1 adapter checkpoints notes, original base revisions and pending actions in the existing version-1 opaque owner/tab-scoped checkpoint. It restores those values through Back/Forward and browser reload without upgrading their bases. Restored actions must be reviewed again. Shared P1 SDK bytes and route contracts remain unchanged. The adapter's narrow draft-handling changes are necessary to carry preconditions; no cross-module navigation implementation changes were made. Conflict controls also work inside the existing Settings modal. Desktop and 390 px conflict layouts were rendered and inspected with synthetic values.

## Migration, backup and rollback

- The additive schema 1 → 2 migration creates `personal_revisions` and seeds tokens for existing movies, series and settings. It changes no existing personal record, UUID, relationship or history row.
- Only disposable databases were migrated in this run. The migration test creates and validates a consistent SQLite backup **before** migration, checks schema/data integrity after migration, then restores the backup and opens it with the actual database implementation from WP01 commit `075b72c`.
- The old implementation refuses schema 2. Rollback therefore requires the old image **and a verified pre-migration backup**. In-place schema downgrades are not supported; post-upgrade edits must not be discarded by treating rollback as an ordinary update.
- Version labels and local build descriptors advance together to candidate **0.3.0**. No image was built or registered. Existing release branches and tags remain unchanged.
- Existing schema-1 backups still validate and migrate forward. New schema-2 artifacts require the new implementation; malformed/missing revision schemas are rejected before replacing live data.
- Restore preserves resource identities and personal values, but rotates/seeds tokens so pre-restore browser edits cannot silently apply to the restored database. The existing suspend/finalize and credential-exclusion behavior remains intact.
- Before any separately authorized integration, retain the verified pre-update module/database backup and rehearse the candidate against a disposable copy. No development or production database from the workspace was read, copied or modified here.

## Validation results

| Suite | Result |
|---|---|
| Full Lyra pytest suite | **40 passed**: 21 existing WP01/domain regressions and 19 new real-database concurrency/migration cases. |
| Chromium two-tab concurrency suite | **9 passed**, real application backend, actual P1 SDK/adapter and disposable SQLite database. |
| Existing WP01 Chromium privacy suite | **7 passed**, including zero-provider local search, explicit discovery, stale requests, refresh and Back/Forward. |
| Existing shared Nexus UI/P1 protocol suite | **31 passed**, read-only against its source and synthetic protocol/DOM data. No Nexus source changes. |
| Ruff lint; JS syntax; changed Python formatting; diff whitespace | Passed. Whole-app formatting retains the same two pre-existing unrelated backlink formatting blocks as WP01. |

Backend tests use two **raw** TestClient instances and real SQLite commits. They cover equal read tokens; first-writer success; stale rejection with first-writer fields intact; simultaneous writers; repeated watch requests; episode/season/watch-through and watchlist conflicts; movie and series-history deletion; removal/re-addition; settings conflicts; missing preconditions/authorization; validation and SQL-failure rollback; metadata independence; consistent read snapshots; migration/rollback; restore token invalidation and malformed backup rejection. Existing sequential regression tests explicitly send a freshly-read token through a test-only helper; concurrency tests never use that helper.

Browser tests cover losing notes; review/retry with an intervening third write; draft/token survival through Back/Forward and refresh; pending rating recovery; episode progress; typing during delayed saves and reviewed retries; settings-modal recovery; an already-open episode menu retaining its original token across background refresh; and concurrent removal. Provider responses are synthetic over actual loopback HTTP; all provider traffic and Nexus dependencies are isolated from live services. No real secrets, photographs or personal records are used.

Test commands (the existing locked WP01 test environment was reused without modifying tracked dependencies):

```powershell
../lyra-wp01-privacy-first-search/.venv/Scripts/python -m pytest -q
../lyra-wp01-privacy-first-search/.venv/Scripts/ruff check backend tests scripts
$env:PYTHON='G:/AureateEmpyrean/lyra-wp01-privacy-first-search/.venv/Scripts/python.exe'
node --test tests/e2e/concurrent_edits.cjs tests/e2e/privacy_search.cjs
```

Shared P1 tests: from the unchanged Nexus checkout, `node --test tests/frontend.test.mjs tests/navigation.test.mjs`. No live aetest/Exodus test was run. Firefox and WebKit are not installed; browser coverage is Chromium, not physical Safari/Firefox/mobile certification. One pre-existing Starlette/httpx deprecation warning remains.

## Branch and integration readiness

- Worktree: `G:/AureateEmpyrean/lyra-wp02b-concurrent-edits`.
- Branch: `codex/wp02b-lyra-concurrent-edits`.
- Parent: completed WP01 `075b72c5bac447d16f9a659f89c5616063c497f2`; WP01 privacy behavior and its full changes are preserved.
- The implementation and this record form the branch's candidate commit; `git log -1` identifies it. No existing branch/tag is rewritten.
- Ready for code review and an isolated integration rehearsal. Not deployed or approved for production. Existing clients must reload to use the revision-aware API; failures from old write contracts are deliberate and fail closed.
- Independent of Claude's Chronos work. No other module source/schema/tests/docs or shared service was modified.

Known limits: aggregate-level conflicts are intentionally conservative; disjoint edits in two tabs can conflict and require review. No field auto-merge, multi-device synchronization or universal Undo is introduced. Refresh recovery needs a supporting P1 host and successful checkpoint storage; a legacy/standalone host retains only in-memory drafts. Quota/host checkpoint failure is reported, not presented as durable recovery. Restore/rollback cannot preserve writes that the owner intentionally discards by restoring an older backup. Physical erasure and a full-installation recovery rehearsal are outside this package.
