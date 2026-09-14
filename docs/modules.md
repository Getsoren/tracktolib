---
title: "Modules Overview"
---

# Modules

Tracktolib is organized into modules, each providing utilities for specific use cases. Install only what you need using extras.

## Database

| Module | Extra | Description |
|--------|-------|-------------|
| [PostgreSQL (Async)](modules/pg.md) | `pg` | Async PostgreSQL helpers using asyncpg |
| [PostgreSQL (Sync)](modules/pg-sync.md) | `pg-sync` | Sync PostgreSQL helpers using psycopg v3 |

## Storage

| Module | Extra | Description |
|--------|-------|-------------|
| [S3 (Async)](modules/s3-niquests.md) | `s3-niquests` | Async S3 helpers using niquests + botocore |
| [S3 (MinIO)](modules/s3-minio.md) | `s3-minio` | S3 helpers using MinIO client |
| [S3 (aiobotocore)](modules/s3.md) | `s3` | Async S3 helpers using aiobotocore (deprecated) |

## Web

| Module | Extra | Description |
|--------|-------|-------------|
| [API (FastAPI)](modules/api.md) | `api` | FastAPI utilities and endpoint builders |
| [Cloudflare](modules/cf.md) | `cf` | Cloudflare DNS API helpers |
| [GitHub](modules/gh.md) | `gh` | GitHub API helpers |

## Utilities

| Module | Extra | Description |
|--------|-------|-------------|
| [Logs](modules/logs.md) | `logs` | Logging configuration (JSON/console) |
| [Tests](modules/tests.md) | `tests` | Testing utilities with deepdiff |

## Installation Examples

Install a single extra:

```bash
uv add tracktolib[pg]
```

Install multiple extras:

```bash
uv add tracktolib[pg,api,logs]
```

Install all extras:

```bash
uv add tracktolib[pg,pg-sync,s3,s3-minio,s3-niquests,api,cf,gh,logs,tests]
```
