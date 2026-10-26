---
title: "PostgreSQL (Async)"
---

# PostgreSQL (Async)

Async PostgreSQL helpers using [asyncpg](https://github.com/MagicStack/asyncpg).

## Installation

```bash
uv add tracktolib[pg]
```

## Dependencies

- [asyncpg](https://github.com/MagicStack/asyncpg)
- [rich](https://github.com/Textualize/rich) (for formatting)

## Quick Start

```python
import asyncpg
from tracktolib.pg import insert_many, insert_one, insert_returning

async def main():
    conn = await asyncpg.connect('postgresql://user:pass@localhost/db')

    # Insert single row
    await insert_one(conn, 'users', {'name': 'John', 'email': 'john@example.com'})

    # Insert multiple rows
    users = [
        {'name': 'Alice', 'email': 'alice@example.com'},
        {'name': 'Bob', 'email': 'bob@example.com'},
    ]
    await insert_many(conn, 'users', users)

    # Insert and return the inserted ID
    user_id = await insert_returning(conn, 'users', {'name': 'Charlie'}, 'id')
```

## Insert Functions

### `insert_one`

Insert a single row into a table.

```python
await insert_one(
    conn,
    'users',
    {'name': 'John', 'email': 'john@example.com'},
    on_conflict='ON CONFLICT DO NOTHING'
)
```

### `insert_many`

Insert multiple rows into a table.

```python
users = [
    {'name': 'Alice', 'email': 'alice@example.com'},
    {'name': 'Bob', 'email': 'bob@example.com'},
]
await insert_many(conn, 'users', users)

# With returning
records = await insert_many(conn, 'users', users, returning='id')
```

### `insert_returning`

Insert and return values from the inserted row.

```python
# Return single value
user_id = await insert_returning(conn, 'users', {'name': 'John'}, 'id')

# Return multiple values
record = await insert_returning(conn, 'users', {'name': 'John'}, ['id', 'created_at'])
```

## Update Functions

### `update_one`

Update a single row.

```python
await update_one(
    conn,
    'users',
    {'id': 1, 'name': 'John Updated'},
    keys=['id']  # WHERE clause keys
)
```

### `update_many`

Update multiple rows.

```python
updates = [
    {'id': 1, 'status': 'active'},
    {'id': 2, 'status': 'inactive'},
]
await update_many(conn, 'users', updates, keys=['id'])
```

### `update_returning`

Update and return values.

```python
record = await update_returning(
    conn,
    'users',
    {'id': 1, 'name': 'Updated'},
    keys=['id'],
    returning=['name', 'updated_at']
)
```

## Query Builders

### `PGInsertQuery`

Build complex INSERT queries with conflict handling and returning clauses.

```python
from tracktolib.pg import PGInsertQuery, PGConflictQuery, PGReturningQuery

query = PGInsertQuery(
    table='users',
    items=[{'name': 'John', 'email': 'john@example.com'}],
    on_conflict=PGConflictQuery(keys=['email']),
    returning=PGReturningQuery.load(keys=['id'])
)

# Execute
await query.run(conn)

# Or fetch results
result = await query.fetchrow(conn)
```

### `PGUpdateQuery`

Build complex UPDATE queries.

```python
from tracktolib.pg import PGUpdateQuery

query = PGUpdateQuery(
    table='users',
    items=[{'id': 1, 'name': 'Updated', 'status': 'active'}],
    where_keys=['id'],
    returning=['name', 'updated_at']
)

result = await conn.fetchrow(query.query, *query.values)
```

## Conflict Handling

### Using `Conflict` helper

```python
from tracktolib.pg import insert_many, Conflict

await insert_many(
    conn,
    'users',
    users,
    on_conflict=Conflict(keys=['email'], ignore_keys=['created_at'])
)
```

### Using `PGConflictQuery`

```python
from tracktolib.pg import PGConflictQuery

conflict = PGConflictQuery(
    keys=['email'],           # Conflict detection keys
    ignore_keys=['id'],       # Keys to ignore in update
    where='t.status != $1',   # Additional WHERE clause
    merge_keys=['metadata'],  # JSONB merge (a || b)
    overwrite_keys=['deleted_at'],  # Set as inserted, None included (no COALESCE)
)
```

## Utility Functions

### `fetch_count`

Count rows from a query.

```python
from tracktolib.pg import fetch_count

count = await fetch_count(conn, 'SELECT * FROM users WHERE status = $1', 'active')
```

### `insert_pg`

Factory function to create `PGInsertQuery` instances.

```python
from tracktolib.pg import insert_pg

query = insert_pg(
    'users',
    [{'name': 'John'}],
    on_conflict='ON CONFLICT DO NOTHING',
    returning=['id'],
    fill=True  # Fill missing keys with None
)
```

## Utilities Module

Additional utilities from `tracktolib.pg.utils`:

### `iterate_pg`

Iterate over large result sets efficiently.

```python
from tracktolib.pg import iterate_pg

async for batch in iterate_pg(conn, 'SELECT * FROM large_table', batch_size=1000):
    for record in batch:
        process(record)
```

### `safe_pg` / `safe_pg_context`

Handle PostgreSQL errors gracefully.

```python
from tracktolib.pg import safe_pg, PGError

@safe_pg
async def get_user(conn, user_id: int):
    return await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)

result = await get_user(conn, 1)
if isinstance(result, PGError):
    print(f"Error: {result.message}")
```
