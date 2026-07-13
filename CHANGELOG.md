## 0.75.0 (2026-07-13)

### Feat

- **pg**: add SQLExpr for inlining raw SQL in insert/update values (#51)

### Fix

- **s3**: default to s3v4 signature when no config is provided (#50)

## 0.74.0 (2026-02-26)

### Feat

- **s3,utils**: use niquests on_upload hook and optimize stream chunking (#49)

## 0.73.0 (2026-02-10)

### Feat

- **gh**: add update_issue_comment method to GitHubClient

## 0.72.0 (2026-02-10)

### Feat

- **cf**: add update_dns_record method to CloudflareDNSClient

## 0.71.1 (2026-02-06)

### Fix

- **gh**: use typing_extensions.TypedDict for extra_items compatibility

## 0.71.0 (2026-02-06)

### Feat

- **gh**: add list_pull_requests method to GitHubClient (#48)

## 0.70.0 (2026-02-05)

### Feat

- **s3-niquests**: add sync support with s3_sync_directory (#47)

## 0.69.0 (2026-02-04)

### Feat

- adding gh/cloudflare utils (#46)

## 0.68.0 (2026-01-26)

### Feat

- add notion utils (#42)

## 0.67.0 (2026-01-26)

### Feat

- **s3-niquests**: adding on_resp utils for download_file (#45)

## 0.66.3 (2026-01-22)

### Fix

- remove s3 deprecation warning

## 0.66.2 (2026-01-21)

### Fix

- s3 niquests headers (#44)

## 0.66.1 (2026-01-21)

## 0.66.0 (2026-01-21)

### Feat

- s3 niquests, doc, github actions (#43)

### Fix

- ci
- ci
- ci
- ci

## 0.65.1 (2025-12-29)

### Fix

- fetch notion database payload

## 0.65.0 (2025-12-23)

### Feat

- add tests for python 3.14 (#41)

## 0.64.0 (2025-12-23)

### Feat

- Add returning support to insert_many for asyncpg helpers
- add support for return many

## 0.63.0 (2025-12-22)

### Feat

- add notion helpers
- add notion helpers
- add notion helpers

### Fix

- base path
- api version + basic auth

## 0.62.1 (2025-11-27)

### Fix

- handling correctly one item when calling update_many

## 0.62.0 (2025-11-18)

## 0.61.2 (2025-11-18)

### Feat

- migrate to uv

### Fix

- pg update invalid values

## 0.61.1 (2025-11-18)

### Fix

- pg update invalid placeholders

## 0.61.0 (2025-11-17)

### Feat

- adding query callback to asyncpg utils functions
- adding query callback to asyncpg utils functions
- adding query callback to asyncpg utils functions

## 0.60.0 (2025-11-07)

### Feat

- adding support for update_many

## 0.59.0 (2025-10-22)

### Feat

- replacing dict with broader Mapping type for response

## 0.58.1 (2025-09-29)

### Fix

- cursor support for insert one
- cursor support for insert one

## 0.58.0 (2025-09-29)

### Feat

- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one

## 0.57.0 (2025-07-11)

### Fix

- typing for pg-sync
- typing for pg-sync

## 0.56.0 (2025-07-02)

### Feat

- adding cursor support to insert_many
- adding cursor support to insert_many
- adding cursor support to insert_many

## 0.55.0 (2025-05-23)

### Feat

- adding deprecated arg to endpoint
- adding deprecated arg to endpoint
- adding deprecated arg to endpoint

### Fix

- types

## 0.54.0 (2025-02-19)

### Feat

- adding returning to insert_one pg_sync

## 0.53.1 (2025-01-22)

### Fix

- fix listfiles s3
- fix listfiles s3

## 0.53.0 (2025-01-13)

### Feat

- bump deepdiff/python-json-logger versions
- bump deepdiff/python-json-logger versions

## 0.52.0 (2024-12-13)

### Feat

- update download utils and exc_cmd utils
- update download utils and exc_cmd utils

## 0.51.1 (2024-10-14)

### Fix

- update one merge keys
- update one merge keys
- update one merge keys

## 0.51.0 (2024-10-14)

### Feat

- adding merge keys to update one
- adding merge keys to update one
- adding merge keys to update one

## 0.50.0 (2024-10-14)

### Feat

- add merge keys on conflict
- adding merge keys
- adding merge keys

## 0.49.1 (2024-10-14)

### Fix

- pg sync commit
- adding mising commit
- adding missing commit

## 0.49.0 (2024-07-16)

### Feat

- bump python version

## 0.48.1 (2024-07-15)

### Fix

- check status
- check status
- check status

## 0.48.0 (2024-07-12)

### Feat

- **s3**: add delete files function
- **files**: add delete files function
- **files**: improve description
- **files**: add description
- **files**: fix ruff
- **files**: return changes
- **files**: add chaque response type
- **files**: add chaque response type
- **files**: change List to list
- **files**: fix pyright 1
- **files**: fix pyright
- **files**: format code
- **files**: add delete-files function

## 0.47.2 (2024-03-28)

### Fix

- pg-sync csv upsert columns
- csv upsert
- csv upsert

## 0.47.1 (2024-03-17)

### Fix

- openapi attributes for name, summary and description
- openapi attributes for name, summary and description
- naming

## 0.47.0 (2024-03-14)

## 0.46.2 (2024-02-29)

### Feat

- adding deep_reload

### Fix

- rollback ignore config
- rollback ignore config
- updating ignore path
- updating ignore path

## 0.46.1 (2024-02-29)

### Fix

- ignore path utils
- ignore path utils
- updating ignore path
- updating ignore path

## 0.46.0 (2024-02-28)

### Feat

- add ignore config utils
- add ignore config utils

## 0.45.0 (2024-02-27)

### Feat

- adding ignore endpoint  config

## 0.44.1 (2024-01-23)

### Feat

- adding ignore config utils
- add ignore endpoint config
- add ignore endpoint config

### Fix

- adding coerce number to str

## 0.44.0 (2023-12-22)

### Feat

- updating json format
- updating json format
- updating json format

## 0.43.2 (2023-12-22)

### Fix

- pydantic v2
- pydantic v2
- pydantic v2

## 0.43.1 (2023-11-20)

### Fix

- bump version
- adding download tests. This is a breaking change since we now import from tracktolib.download.

## 0.43.0 (2023-11-20)

### Feat

- adding download text file support

## 0.42.3 (2023-11-06)

### Fix

- bump version
- bump version

## 0.42.2 (2023-11-06)

## 0.42.1 (2023-10-17)

### Fix

- adding pg quote issue

## 0.42.0 (2023-10-17)

## 0.41.0 (2023-10-09)

### Feat

- adding quote_columns option to pg
- bumping packages versions

## 0.40.0 (2023-10-06)

### Feat

- bumping packages versions
- adding where to on_conflict

## 0.39.1 (2023-09-18)

### Fix

- CamelCaseModel for v2 pydantic

## 0.39.0 (2023-08-22)

### Feat

- adding openapi_extra to api

### Fix

- CamelCaseModel for v2 pydantic

## 0.38.1 (2023-08-11)

## 0.38.0 (2023-07-02)

### Fix

- bump dependencies

## 0.37.2 (2023-06-07)

### Feat

- adding safe_pg and safe_pg_context to asyncpg

## 0.37.1 (2023-06-07)

### Fix

- insert tmp query

## 0.37.0 (2023-06-07)

### Fix

- csv insert pg
- typing

## 0.36.0 (2023-06-07)

### Feat

- adding custom fields to csv upsert
- adding upsert csv update

## 0.35.0 (2023-06-05)

## 0.34.0 (2023-04-26)

### Feat

- adding delete_file utils

## 0.33.0 (2023-03-30)

### Feat

- adding aexec_cmd

## 0.32.0 (2023-03-28)

### Feat

- adding ignore_order to assert_equals

## 0.31.0 (2023-03-07)

### Feat

- adding env to exec_cmd
- adding restart_seq to clean_tables

## 0.30.0 (2023-03-02)

## 0.29.1 (2023-02-21)

### Feat

- add exclude columns argument to pg_sync csv upsert

## 0.29.0 (2023-02-16)

### Feat

- adding num_not_null

### Fix

- fix return * for insert_returning
- fix tests

## 0.28.3 (2023-02-10)

## 0.28.2 (2023-02-07)

### Fix

- insert_one pg_sync
- do not import httpx in api

## 0.28.1 (2023-02-07)

### Fix

- do not import httpx in api

## 0.28.0 (2023-02-06)

### Fix

- rm_keys and dict_to_camel types

## 0.27.0 (2023-02-06)

### Feat

- adding check_status function to api utils

## 0.26.0 (2023-02-06)

### Feat

- adding dict_to_camel and rm_keys utils

## 0.25.0 (2023-02-02)

### Feat

- updating model type for get
- adding snake/camel utilities

## 0.24.0 (2023-02-01)

### Feat

- adding acl to s3 upload_file
- improving list_files s3

## 0.23.1 (2023-01-27)

## 0.23.0 (2023-01-19)

### Fix

- issue with PGUpdateQuery that was not ordering correctly values

## 0.22.0 (2023-01-10)

### Feat

- adding deprecation warning to get_uuid

## 0.21.2 (2023-01-09)

### Feat

- adding import_module utility

## 0.21.1 (2023-01-08)

### Fix

- issue with fastapi openapi.json

## 0.21.0 (2023-01-06)

### Fix

- bumping minio version

## 0.20.2 (2023-01-06)

### Feat

- adding json_serial to JSONSerialResponse

## 0.20.1 (2023-01-05)

### Fix

- typing of api model
- fix types for update_returning

## 0.20.0 (2023-01-05)

## 0.19.0 (2022-12-28)

### Feat

- adding return_key to update_one to return updated keys

## 0.18.0 (2022-12-26)

### Feat

- adding model to endpoint methods.\nfeat: Adding update_one to pg functions

## 0.17.0 (2022-12-21)

### Feat

- adding support for path parameters to api utils

## 0.16.2 (2022-12-16)

### Feat

- adding Pool as possible engine for pg functions

## 0.16.1 (2022-12-14)

### Fix

- fix typing for pg insert_returning

## 0.16.0 (2022-12-14)

### Fix

- fix insert_many with dict values

## 0.15.0 (2022-12-06)

### Feat

- moving from psycopg2 to psycopg

## 0.14.1 (2022-12-01)

### Feat

- adding truncate to clean_tables (pg_sync) and utilities for pg

## 0.14.0 (2022-11-30)

### Fix

- fix pg query for returning and conflict

## 0.13.2 (2022-11-29)

### Feat

- adding asyncpg

## 0.13.1 (2022-11-28)

### Fix

- remove print

## 0.13.0 (2022-11-28)

### Fix

- return type for optional response

## 0.12.0 (2022-11-28)

### Feat

- adding dependencies to endpoint

## 0.11.2 (2022-11-28)

### Feat

- renaming ReturnType to Reponse

## 0.11.1 (2022-11-28)

### Fix

- fix default for get_chunks and fetch_one

## 0.11.0 (2022-11-22)

### Fix

- fix types for api

## 0.10.1 (2022-11-22)

### Feat

- adding get_nb_lines

## 0.10.0 (2022-11-21)

### Fix

- setting max python version

## 0.9.1 (2022-11-18)

### Feat

- adding support for Decimal and ipadresses for json_serial

### Fix

- extras dependecies installation

## 0.9.0 (2022-11-18)

## 0.8.1 (2022-11-16)

### Feat

- adding api utils

### Fix

- better typing for get_chunks

## 0.68.0 (2026-01-26)

### Feat

- **notion**: add comprehensive documentation for notion module (#46)

## 0.67.0 (2026-01-26)

### Feat

- **s3-niquests**: adding on_resp utils for download_file (#45)

## 0.66.3 (2026-01-22)

### Fix

- remove s3 deprecation warning

## 0.66.2 (2026-01-21)

### Fix

- s3 niquests headers (#44)

## 0.66.1 (2026-01-21)

## 0.66.0 (2026-01-21)

### Feat

- s3 niquests, doc, github actions (#43)

### Fix

- ci
- ci
- ci
- ci

## 0.65.1 (2025-12-29)

### Fix

- fetch notion database payload

## 0.65.0 (2025-12-23)

### Feat

- add tests for python 3.14 (#41)

## 0.64.0 (2025-12-23)

### Feat

- Add returning support to insert_many for asyncpg helpers
- add support for return many

## 0.63.0 (2025-12-22)

### Feat

- add notion helpers
- add notion helpers
- add notion helpers

### Fix

- base path
- api version + basic auth

## 0.62.1 (2025-11-27)

### Fix

- handling correctly one item when calling update_many

## 0.62.0 (2025-11-18)

## 0.61.2 (2025-11-18)

### Feat

- migrate to uv

### Fix

- pg update invalid values

## 0.61.1 (2025-11-18)

### Fix

- pg update invalid placeholders

## 0.61.0 (2025-11-17)

### Feat

- adding query callback to asyncpg utils functions
- adding query callback to asyncpg utils functions
- adding query callback to asyncpg utils functions

## 0.60.0 (2025-11-07)

### Feat

- adding support for update_many

## 0.59.0 (2025-10-22)

### Feat

- replacing dict with broader Mapping type for response

## 0.58.1 (2025-09-29)

### Fix

- cursor support for insert one
- cursor support for insert one

## 0.58.0 (2025-09-29)

### Feat

- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one
- cursor support for insert one

## 0.57.0 (2025-07-11)

### Fix

- typing for pg-sync
- typing for pg-sync

## 0.56.0 (2025-07-02)

### Feat

- adding cursor support to insert_many
- adding cursor support to insert_many
- adding cursor support to insert_many

## 0.55.0 (2025-05-23)

### Feat

- adding deprecated arg to endpoint
- adding deprecated arg to endpoint
- adding deprecated arg to endpoint

### Fix

- types

## 0.54.0 (2025-02-19)

### Feat

- adding returning to insert_one pg_sync

## 0.53.1 (2025-01-22)

### Fix

- fix listfiles s3
- fix listfiles s3

## 0.53.0 (2025-01-13)

### Feat

- bump deepdiff/python-json-logger versions
- bump deepdiff/python-json-logger versions

## 0.52.0 (2024-12-13)

### Feat

- update download utils and exc_cmd utils
- update download utils and exc_cmd utils

## 0.51.1 (2024-10-14)

### Fix

- update one merge keys
- update one merge keys
- update one merge keys

## 0.51.0 (2024-10-14)

### Feat

- adding merge keys to update one
- adding merge keys to update one
- adding merge keys to update one

## 0.50.0 (2024-10-14)

### Feat

- add merge keys on conflict
- adding merge keys
- adding merge keys

## 0.49.1 (2024-10-14)

### Fix

- pg sync commit
- adding missing commit
- adding missing commit

## 0.49.0 (2024-07-16)

### Feat

- bump python version

## 0.48.1 (2024-07-15)

### Fix

- check status
- check status
- check status

## 0.48.0 (2024-07-12)

### Feat

- **s3**: add delete files function
- **files**: add delete files function
- **files**: improve description
- **files**: add description
- **files**: fix ruff
- **files**: return changes
- **files**: add chaque response type
- **files**: add chaque response type
- **files**: change List to list
- **files**: fix pyright 1
- **files**: fix pyright
- **files**: format code
- **files**: add delete-files function

## 0.47.2 (2024-03-28)

### Fix

- pg-sync csv upsert columns
- csv upsert
- csv upsert

## 0.47.1 (2024-03-17)

### Fix

- openapi attributes for name, summary and description
- openapi attributes for name, summary and description
- naming

## 0.47.0 (2024-03-14)

## 0.46.2 (2024-02-29)

### Feat

- adding deep_reload

### Fix

- rollback ignore config
- rollback ignore config
- updating ignore path
- updating ignore path

## 0.46.1 (2024-02-29)

### Fix

- ignore path utils
- ignore path utils
- updating ignore path
- updating ignore path

## 0.46.0 (2024-02-28)

### Feat

- add ignore config utils
- add ignore config utils

## 0.45.0 (2024-02-27)

### Feat

- adding ignore endpoint config

## 0.44.1 (2024-01-23)

### Feat

- adding ignore config utils
- add ignore endpoint config
- add ignore endpoint config

### Fix

- adding coerce number to str

## 0.44.0 (2023-12-22)

### Feat

- updating json format
- updating json format
- updating json format

## 0.43.2 (2023-12-22)

### Fix

- pydantic v2
- pydantic v2
- pydantic v2

## 0.43.1 (2023-11-20)

### Fix

- bump version
- adding download tests. This is a breaking change since we now import from tracktolib.download.

## 0.43.0 (2023-11-20)

### Feat

- adding download text file support

## 0.42.3 (2023-11-06)

### Fix

- bump version
- bump version

## 0.42.2 (2023-11-06)

## 0.42.1 (2023-10-17)

### Fix

- adding pg quote issue

## 0.42.0 (2023-10-17)

## 0.41.0 (2023-10-09)

### Feat

- adding quote_columns option to pg
- bumping packages versions

## 0.40.0 (2023-10-06)

### Feat

- bumping packages versions
- adding where to on_conflict

## 0.39.1 (2023-09-18)

### Fix

- CamelCaseModel for v2 pydantic

## 0.39.0 (2023-08-22)

### Feat

- adding openapi_extra to api

### Fix

- CamelCaseModel for v2 pydantic

## 0.38.1 (2023-08-11)

## 0.38.0 (2023-07-02)

### Fix

- bump dependencies

## 0.37.2 (2023-06-07)

### Feat

- adding safe_pg and safe_pg_context to asyncpg

## 0.37.1 (2023-06-07)

### Fix

- insert tmp query

## 0.37.0 (2023-06-07)

### Fix

- csv insert pg
- typing

## 0.36.0 (2023-06-07)

### Feat

- adding custom fields to csv upsert
- adding upsert csv update

## 0.35.0 (2023-06-05)

## 0.34.0 (2023-04-26)

### Feat

- adding delete_file utils

## 0.33.0 (2023-03-30)

### Feat

- adding aexec_cmd

## 0.32.0 (2023-03-28)

### Feat

- adding ignore_order to assert_equals

## 0.31.0 (2023-03-07)

### Feat

- adding env to exec_cmd
- adding restart_seq to clean_tables

## 0.30.0 (2023-03-02)

## 0.29.1 (2023-02-21)

### Feat

- add exclude columns argument to pg_sync csv upsert

## 0.29.0 (2023-02-16)

### Feat

- adding num_not_null

### Fix

- fix return * for insert_returning
- fix tests

## 0.28.3 (2023-02-10)

## 0.28.2 (2023-02-07)

### Fix

- insert_one pg_sync
- do not import httpx in api

## 0.28.1 (2023-02-07)

### Fix

- do not import httpx in api

## 0.28.0 (2023-02-06)

### Fix

- rm_keys and dict_to_camel types

## 0.27.0 (2023-02-06)

### Feat

- adding check_status function to api utils

## 0.26.0 (2023-02-06)

### Feat

- adding dict_to_camel and rm_keys utils

## 0.25.0 (2023-02-02)

### Feat

- updating model type for get
- adding snake/camel utilities

## 0.24.0 (2023-02-01)

### Feat

- adding acl to s3 upload_file
- improving list_files s3

## 0.23.1 (2023-01-27)

## 0.23.0 (2023-01-19)

### Fix

- issue with PGUpdateQuery that was not ordering correctly values

## 0.22.0 (2023-01-10)

### Feat

- adding deprecation warning to get_uuid

## 0.21.2 (2023-01-09)

### Feat

- adding import_module utility

## 0.21.1 (2023-01-08)

### Fix

- issue with fastapi openapi.json

## 0.21.0 (2023-01-06)

### Fix

- bumping minio version

## 0.20.2 (2023-01-06)

### Feat

- adding json_serial to JSONSerialResponse

## 0.20.1 (2023-01-05)

### Fix

- typing of api model
- fix types for update_returning

## 0.20.0 (2023-01-05)

## 0.19.0 (2022-12-28)

### Feat

- adding return_key to update_one to return updated keys

## 0.18.0 (2022-12-26)

### Feat

- adding model to endpoint methods.\nfeat: Adding update_one to pg functions

## 0.17.0 (2022-12-21)

### Feat

- adding support for path parameters to api utils

## 0.16.2 (2022-12-16)

### Feat

- adding Pool as possible engine for pg functions

## 0.16.1 (2022-12-14)

### Fix

- fix typing for pg insert_returning

## 0.16.0 (2022-12-14)

### Fix

- fix insert_many with dict values

## 0.15.0 (2022-12-06)

### Feat

- moving from psycopg2 to psycopg

## 0.14.1 (2022-12-01)

### Feat

- adding truncate to clean_tables (pg_sync) and utilities for pg

## 0.14.0 (2022-11-30)

### Fix

- fix pg query for returning and conflict

## 0.13.2 (2022-11-29)

### Feat

- adding asyncpg

## 0.13.1 (2022-11-28)

### Fix

- remove print

## 0.13.0 (2022-11-28)

### Fix

- return type for optional response

## 0.12.0 (2022-11-28)

### Feat

- adding dependencies to endpoint

## 0.11.2 (2022-11-28)

### Feat

- renaming ReturnType to Reponse

## 0.11.1 (2022-11-28)

### Fix

- fix default for get_chunks and fetch_one

## 0.11.0 (2022-11-22)

### Fix

- fix types for api

## 0.10.1 (2022-11-22)

### Feat

- adding get_nb_lines

## 0.10.0 (2022-11-21)

### Fix

- setting max python version

## 0.9.1 (2022-11-18)

### Feat

- adding support for Decimal and ipadresses for json_serial

### Fix

- extras dependecies installation

## 0.9.0 (2022-11-18)

## 0.8.1 (2022-11-16)

### Feat

- adding api utils

## 0.8.0 (2022-11-16)

### Fix

- better typing for get_chunks

## 0.7.2 (2022-11-15)

### Feat

- adding aiobotocore utils

## 0.7.1 (2022-11-14)

### Fix

- http import inside importError
- version bump
- version bump
- version bump

## 0.7.0 (2022-11-14)

## 0.6.2 (2022-11-14)

### Feat

- adding http utils

## 0.6.1 (2022-11-14)

### Fix

- renaming is_valid_logging to is_valid_log_format

## 0.6.0 (2022-11-14)

### Feat

- adding json_serial

### Fix

- fix init_logging log format
- fix return of init_logging

## 0.5.0 (2022-11-14)

## 0.4.2 (2022-11-10)

### Feat

- adding 'required' optional arg to pg fetch_one

## 0.4.1 (2022-11-10)

### Fix

- assert_equals types

## 0.4.0 (2022-11-10)

### Fix

- updating exec_cmd

## 0.3.0 (2022-11-10)

### Feat

- adding test utilities

## 0.2.2 (2022-11-10)

### Feat

- adding new pg utility functions

### Fix

- pypi commit
- pypi commit

## 0.2.0 (2022-11-10)

### Feat

- first commit
