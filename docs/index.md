# Tracktolib

**Tracktolib** is a Swiss-knife utility library for Python, providing helpers for PostgreSQL, S3, FastAPI, and more.

[![Python versions](https://img.shields.io/pypi/pyversions/tracktolib)](https://pypi.python.org/pypi/tracktolib)
[![Latest PyPI version](https://img.shields.io/pypi/v/tracktolib?logo=pypi)](https://pypi.python.org/pypi/tracktolib)

## Installation

```bash
uv add tracktolib
```

With specific extras:

```bash
uv add tracktolib[pg-sync,api]
```

## Available Extras

| Extra         | Description                              |
|---------------|------------------------------------------|
| `pg`          | Async PostgreSQL helpers (asyncpg)       |
| `pg-sync`     | Sync PostgreSQL helpers (psycopg v3)     |
| `s3`          | Async S3 helpers (aiobotocore)           |
| `s3-minio`    | S3 helpers (minio)                       |
| `s3-niquests` | S3 helpers (niquests + botocore)         |
| `api`         | FastAPI utilities                        |
| `logs`        | Logging configuration                    |
| `tests`       | Testing utilities (deepdiff)             |

## Quick Example

```python
from psycopg import connect
from tracktolib.pg_sync import insert_many, fetch_one, fetch_all

conn = connect('postgresql://user:pass@localhost/db')

data = [
    {'foo': 'bar', 'value': 1},
    {'foo': 'baz', 'value': 2}
]
insert_many(conn, 'public.test', data)

value = fetch_one(conn, 'SELECT foo from public.test order by value asc', required=True)
# {'foo': 'bar'}

assert fetch_all(conn, 'SELECT * from public.test order by value asc') == data
```
