# Development Workflow

## How To Use The Memory Files

- Read `docs/architecture.md` first when planning code changes.
- Read `docs/features.md` before changing behavior so you can verify whether a workflow already exists.
- Read `docs/working-memory.md` at the start and end of each development session.

## Update Expectations

- Update `docs/architecture.md` when files move, responsibilities change, or a new subsystem is introduced.
- Update `docs/features.md` when user-visible behavior changes, new persistence files are added, or compatibility guarantees change.
- Update `docs/working-memory.md` every time a meaningful branch of work lands.

## Recommended Session Routine

1. Review `docs/working-memory.md`.
2. Confirm the target area in `docs/architecture.md`.
3. Check `docs/features.md` for the affected workflows and invariants.
4. Make the code change.
5. Run the narrowest useful tests first, then broader regression coverage.
6. Record the result in `docs/working-memory.md`.

## Rule For Future Refactors

- Prefer moving behavior behind stable interfaces instead of renaming public entrypoints.
- Keep compatibility shims in place until tests and downstream usage no longer depend on them.
- Do not introduce a new monolithic file to replace the old one.
