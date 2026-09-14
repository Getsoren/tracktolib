# Tracktolib

[![Python versions](https://img.shields.io/pypi/pyversions/tracktolib)](https://pypi.python.org/pypi/tracktolib)
[![Latest PyPI version](https://img.shields.io/pypi/v/tracktolib?logo=pypi)](https://pypi.python.org/pypi/tracktolib)
[![CI](https://github.com/Getsoren/tracktolib/actions/workflows/ci.yml/badge.svg)](https://github.com/Getsoren/tracktolib/actions/workflows/ci.yml)

Tracktor Swiss-knife Utility library.

## Installation

```bash
uv add tracktolib
```

With specific extras:

```bash
uv add tracktolib[pg,api]
```

## Modules

### logs

Utility functions to initialize logging formatting and streams.

```python
import logging
from tracktolib.logs import init_logging

logger = logging.getLogger()
formatter, stream_handler = init_logging(logger, 'json', version='0.0.1')
```

### pg

Async PostgreSQL helpers using [asyncpg](https://github.com/MagicStack/asyncpg).

```bash
uv add tracktolib[pg]
```

```python
import asyncpg
from tracktolib.pg import insert_one, insert_many, insert_returning, update_one, SQLExpr

conn = await asyncpg.connect('postgresql://user:pass@localhost/db')

# Insert a single row
await insert_one(conn, 'public.test', {'foo': 'bar', 'value': 1})

# Insert multiple rows
await insert_many(conn, 'public.test', [
    {'foo': 'bar', 'value': 1},
    {'foo': 'baz', 'value': 2},
])

# Insert and return generated values
new_id = await insert_returning(conn, 'public.test', {'foo': 'bar'}, returning='id')

# Upsert (insert or update on conflict)
from tracktolib.pg import Conflict
await insert_one(conn, 'public.test', {'id': 1, 'foo': 'updated'}, on_conflict=Conflict(keys=['id']))

# Update a single row
await update_one(conn, 'public.test', {'foo': 'new', 'id': 1}, keys=['id'])

# Use raw SQL expressions as values (e.g. NOW(), gen_random_uuid())
await insert_one(conn, 'public.test', {'foo': 'bar', 'created_at': SQLExpr('NOW()')})
# → INSERT INTO public.test AS t (created_at, foo) VALUES (NOW(), $1)

await update_one(conn, 'public.test', {'updated_at': SQLExpr('NOW()'), 'id': 1}, keys=['id'])
# → UPDATE public.test t SET updated_at = NOW() WHERE id = $1
```

### pg-sync

Sync PostgreSQL helpers using [psycopg](https://www.psycopg.org/psycopg3/) (v3).

```bash
uv add tracktolib[pg-sync]
```

```python
from psycopg import connect
from tracktolib.pg_sync import insert_many, fetch_one, fetch_count, fetch_all

conn = connect('postgresql://user:pass@localhost/db')

data = [
    {'foo': 'bar', 'value': 1},
    {'foo': 'baz', 'value': 2}
]
insert_many(conn, 'public.test', data)

query = 'SELECT foo from public.test order by value asc'
value = fetch_one(conn, query, required=True)  # {'foo': 'bar'}, raises if not found

assert fetch_count(conn, 'public.test') == 2

query = 'SELECT * from public.test order by value asc'
assert fetch_all(conn, query) == data
```

### s3

Async S3 helpers using [aiobotocore](https://github.com/aio-libs/aiobotocore).

```bash
uv add tracktolib[s3]
```

### s3-minio

S3 helpers using [minio](https://min.io/docs/minio/linux/developers/python/API.html).

```bash
uv add tracktolib[s3-minio]
```

### s3-niquests

Async S3 helpers using [niquests](https://github.com/jawah/niquests) and [botocore](https://github.com/boto/botocore) presigned URLs.

```bash
uv add tracktolib[s3-niquests]
```

```python
from tracktolib.s3.niquests import S3Session

async with S3Session(
    endpoint_url='http://localhost:9000',
    access_key='...',
    secret_key='...',
    region='us-east-1',
) as s3:
    # Object operations
    await s3.put_object('bucket', 'path/file.txt', b'content')
    content = await s3.get_object('bucket', 'path/file.txt')
    await s3.delete_object('bucket', 'path/file.txt')

    # Streaming upload (multipart for large files)
    async def data_stream():
        yield b'chunk1'
        yield b'chunk2'
    await s3.file_upload('bucket', 'large-file.bin', data_stream())

    # Bucket policy management
    policy = {'Version': '2012-10-17', 'Statement': [...]}
    await s3.put_bucket_policy('bucket', policy)
    await s3.get_bucket_policy('bucket')
    await s3.delete_bucket_policy('bucket')

    # Empty a bucket (delete all objects)
    deleted_count = await s3.empty_bucket('bucket')

    # Sync a local directory to S3 (like aws s3 sync)
    from pathlib import Path
    result = await s3.sync_directory('bucket', Path('./local'), 'remote/prefix')
    print(f"Uploaded: {result['uploaded']}, Deleted: {result['deleted']}, Skipped: {result['skipped']}")

    # With delete flag to remove remote files not present locally
    result = await s3.sync_directory('bucket', Path('./local'), 'remote/prefix', delete=True)
```

### api

FastAPI utilities using [fastapi](https://fastapi.tiangolo.com/) and [pydantic](https://docs.pydantic.dev/).

```bash
uv add tracktolib[api]
```

### gh

GitHub API helpers using [niquests](https://github.com/jawah/niquests).

```bash
uv add tracktolib[gh]
```

```python
from tracktolib.gh import GitHubClient

async with GitHubClient() as gh:  # Uses GITHUB_TOKEN env var
    # Issue comments
    comments = await gh.get_issue_comments("owner/repo", 123)
    await gh.create_issue_comment("owner/repo", 123, "Hello!")
    await gh.delete_comments_with_marker("owner/repo", 123, "<!-- bot -->")

    # Labels
    labels = await gh.get_issue_labels("owner/repo", 123)
    await gh.add_labels("owner/repo", 123, ["bug", "priority"])
    await gh.remove_label("owner/repo", 123, "wontfix")

    # Pull requests
    pr = await gh.get_pull_request("owner/repo", 42)
    diff = await gh.get_pull_request_diff("owner/repo", 42)
    await gh.create_pull_request_review(
        "owner/repo", 42,
        body="Found a few things",
        event="REQUEST_CHANGES",
        comments=[{"path": "app/main.py", "line": 12, "side": "RIGHT", "body": "This can be None here"}],
    )

    # Permissions
    permission = await gh.get_collaborator_permission("owner/repo", "octocat")  # admin, write, read or none

    # Deployments
    deploys = await gh.get_deployments("owner/repo", environment="production")
    await gh.mark_deployment_inactive("owner/repo", "preview-123")
```

### cf

Cloudflare DNS API helpers using [niquests](https://github.com/jawah/niquests).

```bash
uv add tracktolib[cf]
```

```python
from tracktolib.cf import CloudflareDNSClient

async with CloudflareDNSClient() as cf:  # Uses CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_ID env vars
    # Get a DNS record
    record = await cf.get_dns_record("app.example.com", "CNAME")

    # Create a DNS record
    record = await cf.create_dns_record(
        "app.example.com",
        "target.example.com",
        record_type="CNAME",
        ttl=60,
        proxied=True,
    )

    # Delete by ID or name
    await cf.delete_dns_record(record["id"])
    await cf.delete_dns_record_by_name("app.example.com", "CNAME")

    # Check existence
    exists = await cf.dns_record_exists("app.example.com")
```

### tests

Testing utilities using [deepdiff](https://github.com/seperman/deepdiff).

```bash
uv add tracktolib[tests]
```
