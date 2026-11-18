# CLAUDE.md

@AGENTS.md

All project guidance lives in `AGENTS.md` (imported above) so every coding agent shares one source of truth.
Put new repo-wide rules there, not here.

## Claude-specific notes

- Before changing architecture, search, or the database, read the relevant section of `plan.md` and
  `backend/data/database.md` rather than inferring from the V0 code.
- When an open decision (models, embeddings, tracing) blocks the task, ask the user instead of picking one.
- For the database, prefer read-only checks; ask before any write to the shared Neon instance.
