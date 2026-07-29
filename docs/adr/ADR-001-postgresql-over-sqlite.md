# ADR-001: PostgreSQL over SQLite

- **Date:** 2026-07-29
- **Status:** Accepted

## Context

PacketWise MVP used SQLite for zero-config local development. Moving to
production requires a database that supports concurrent connections, cloud
hosting, and proper connection pooling.

## Decision

Use Supabase PostgreSQL as the production database backend.

SQLite is retained as the local dev fallback via the `DATABASE_URL` environment
variable.

psycopg2 (synchronous) was chosen over asyncpg because the FastAPI application
is synchronous top to bottom — rewriting to async was out of scope.

## Consequences

**Positive**

- Production-grade database
- Supabase dashboard for data inspection
- Connection pooling via `pool_pre_ping`
- ~340ms additional latency vs SQLite (acceptable for batch processing)

**Negative**

- Requires `DATABASE_URL` in `.env`
- Requires the `psycopg2-binary` dependency
- `check_same_thread` must be conditional (SQLite-only parameter)

## Implementation

`src/core_banking/models.py` selects connect arguments by URL scheme:

```python
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
)
```

Passing `check_same_thread` to psycopg2 fails with `invalid connection option`,
which is why the argument is gated on the scheme rather than always supplied.
