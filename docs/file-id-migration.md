# Stable `file_id` Migration Plan

## Goal

Move document identity away from filename/path-derived keys and onto a stable `file_id` so rename becomes a metadata update instead of an identity change.

## Current Problem

The current application treats the filename as the effective identity in several places:

- Source history rows store `file_name`.
- Directory notes store `file_name`.
- Active checkout records store `source_file` and `locked_source_file`.
- Revision storage keys are derived from `project_dir + source_file + locked_source_file`.

That design makes rename expensive and fragile because every rename has to rewrite multiple path-based records.

## Target Model

Each tracked source document should have a stable `file_id` that survives:

- rename
- move within a tracked source root
- checkout/checkin cycles
- revision creation
- note creation

Filename and path then become mutable attributes of the document, not its identity.

## Proposed Persistence Shape

### Source document registry

Add a per-source-root registry file, for example:

- `<source>/.doc_control_index.json`

Suggested structure:

```json
{
  "schema_version": 1,
  "app_version": "0.1.x",
  "files": {
    "f_ab12cd34": {
      "file_id": "f_ab12cd34",
      "source_root": "C:/Source",
      "current_relative_path": "Subfolder/A-003.dwg",
      "created_at": "2026-04-01T12:00:00-04:00",
      "created_by_initials": "JWH",
      "status": "active"
    }
  }
}
```

The registry is the authority for mapping `file_id` to the current path.

### History

Change history entries from filename-led to `file_id`-led:

```json
{
  "timestamp": "...",
  "action": "RENAME",
  "file_id": "f_ab12cd34",
  "file_name": "A-005.dwg",
  "previous_file_name": "A-003.dwg",
  "revision_id": "",
  "user_initials": "JWH",
  "user_full_name": "Jared Hodgkins"
}
```

`file_name` can remain as a denormalized snapshot for display/export compatibility, but identity should be `file_id`.

### Directory Notes

Change note entries to store `file_id` first and keep `file_name` as optional display/cache data:

```json
{
  "id": "note-1",
  "file_id": "f_ab12cd34",
  "file_name": "A-005.dwg",
  "subject": "Review",
  "body": "..."
}
```

### Checkout Records

Extend `CheckoutRecord` to include `file_id`.

`source_file` and `locked_source_file` still matter operationally, but no longer define identity.

### Revision Registry

Store revisions by `file_id`, not by a key derived from path strings.

Suggested change:

- current: hash of `project_dir|source_file|locked_source_file`
- target: `files[file_id]`

This removes the need to migrate revision keys during rename.

## Migration Strategy

### Phase 1: Additive schema

Introduce `file_id` everywhere while preserving existing fields:

- document index registry
- history entries
- directory notes
- checkout records
- revision registry

All readers should continue accepting pre-`file_id` data.

### Phase 2: Backfill existing data

For each tracked source root:

1. Enumerate current files.
2. Read history and notes.
3. Assign a new `file_id` to each live source document.
4. Backfill matching history rows and notes with that `file_id`.
5. Backfill active checkout records.
6. Backfill revision registry entries for checked-out records.

This phase should be idempotent and safe to rerun.

### Phase 3: Runtime adoption

Switch runtime lookups to prefer `file_id`:

- file notes lookup
- history lookup
- controlled file detection
- selected-file operations
- revision lookup
- rename and move operations

### Phase 4: Rename/move expansion

Once identity is `file_id`-based, support:

- rename checked-out files
- move files between folders inside the same tracked source root
- batch rename operations
- explorer-style copy/paste with metadata-aware collision checks

## Matching and Backfill Rules

Because legacy data is filename-based, migration needs conservative matching:

- Prefer exact current-path match for active files.
- Use active checkout records to bind renamed locked files back to the original document.
- Only bind orphan history rows to live files when the latest known path/name is unambiguous.
- Leave ambiguous records unbound and report them for manual review instead of guessing.

## Required Code Changes

### `app.py`

- Add `file_id` to `CheckoutRecord`.

### `document_control/mixins/records.py`

- Add source-index load/save helpers.
- Update history normalization and append helpers to read/write `file_id`.
- Update notes helpers to use `file_id`.
- Update checkout/checkin/revision flows to preserve `file_id`.
- Replace `_record_version_key()` path hashing with a `file_id` key.

### `document_control/mixins/sources.py`

- Populate file list items with `file_id`.
- Resolve current paths through the source index when needed.

### Tests

Add compatibility tests for:

- reading legacy history without `file_id`
- backfilling `file_id` into mixed old/new data
- rename preserving notes/history/revisions across active and inactive files
- revision lookup after rename

## Risks

- Ambiguous legacy histories where multiple files reused the same name over time.
- Existing revision entries keyed by path-derived hashes need careful one-time migration.
- Partial migration could create split identity if some stores use `file_id` and others still rely on filename.

## Branch Recommendation

Implement this on a dedicated migration branch after `0.1.5` stabilizes:

- add schemas first
- land backfill tooling second
- switch runtime reads/writes third
- enable checked-out rename and future move/copy workflows last
