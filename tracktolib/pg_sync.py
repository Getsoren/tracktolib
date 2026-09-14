from operator import itemgetter
from pathlib import Path
from typing import Any, Iterable, Literal, LiteralString, Mapping, Optional, Sequence, cast, overload

try:
    from psycopg import Connection, Cursor
    from psycopg.abc import Query, QueryNoTemplate
    from psycopg.errors import InvalidCatalogName
    from psycopg.rows import DictRow, TupleRow, dict_row
    from psycopg.types.json import Json
except ImportError:
    raise ImportError('Please install psycopg or tracktolib with "pg-sync" to use this module')

from .pg_utils import get_tmp_table_query

__all__ = (
    "clean_tables",
    "drop_db",
    "fetch_all",
    "fetch_count",
    "fetch_one",
    "get_insert_data",
    "get_tables",
    "insert_csv",
    "insert_many",
    "insert_one",
    "set_seq_max",
)


def fetch_all(engine: Connection, query: LiteralString, *data) -> list[dict]:
    with engine.cursor(row_factory=dict_row) as cur:
        resp = (cur.execute(query) if not data else cur.execute(query, data)).fetchall()
    engine.commit()
    return resp


def fetch_count(engine: Connection, table: str, *args, where: str | None = None) -> int | None:
    query = f"SELECT count(*) from {table}"
    if where:
        query = f"{query} WHERE {where}"
    with engine.cursor() as cur:
        count = cur.execute(cast(LiteralString, query), params=args).fetchone()
    engine.commit()
    return count[0] if count else None


@overload
def fetch_one(engine: Connection, query: LiteralString, *args, required: Literal[False]) -> dict | None: ...


@overload
def fetch_one(engine: Connection, query: LiteralString, *args, required: Literal[True]) -> dict: ...


@overload
def fetch_one(engine: Connection, query: LiteralString, *args) -> dict | None: ...


def fetch_one(engine: Connection, query: LiteralString, *args, required: bool = False) -> dict | None:
    with engine.cursor(row_factory=dict_row) as cur:
        _data = cur.execute(cast(QueryNoTemplate, query), args).fetchone()
    engine.commit()
    if required and not _data:
        raise ValueError("No value found for query")
    return _data


def _parse_value(v: Any) -> Any:
    if isinstance(v, dict):
        return Json(v)
    return v


def get_insert_data(
    table: LiteralString, data: Sequence[Mapping[str, Any]]
) -> tuple[LiteralString, list[tuple[Any, ...]]]:
    keys = data[0].keys()
    _values = ",".join("%s" for _ in range(0, len(keys)))
    query = cast(LiteralString, f"INSERT INTO {table} as t ({','.join(keys)}) VALUES ({_values})")
    # itemgetter returns a scalar for a single key, so wrap that case
    get = itemgetter(*keys) if len(keys) > 1 else (lambda row, key=next(iter(keys)): (row[key],))
    # Same-length rows with every key present have exactly the same columns
    try:
        rows = [tuple(map(_parse_value, get(row))) for row in data if len(row) == len(keys)]
    except KeyError as e:
        raise ValueError("Inconsistent columns across insert rows") from e
    if len(rows) != len(data):
        raise ValueError("Inconsistent columns across insert rows")
    return query, rows


def insert_many(engine: Connection | Cursor, table: LiteralString, data: Sequence[Mapping[str, Any]]):
    query, _data = get_insert_data(table, data)
    if isinstance(engine, Connection):
        with engine.cursor() as cur:
            _ = cur.executemany(query, _data)
        engine.commit()
    else:
        # If we are using a cursor, we can use executemany directly
        _ = engine.executemany(query, _data)


@overload
def insert_one(
    engine: Connection | Cursor, table: LiteralString, data: Mapping[str, Any], returning: None = None
) -> None: ...


@overload
def insert_one(
    engine: Connection, table: LiteralString, data: Mapping[str, Any], returning: list[LiteralString]
) -> dict: ...


@overload
def insert_one(
    engine: Cursor, table: LiteralString, data: Mapping[str, Any], returning: list[LiteralString]
) -> DictRow | TupleRow | None: ...


def insert_one(
    engine: Connection | Cursor,
    table: LiteralString,
    data: Mapping[str, Any],
    returning: list[LiteralString] | None = None,
) -> dict | DictRow | TupleRow | None:
    query, _data = get_insert_data(table, [data])
    _is_returning = False
    if returning:
        query = f"{query} RETURNING {','.join(returning)}"
        _is_returning = True

    if isinstance(engine, Connection):
        with engine.cursor(row_factory=dict_row) as cur:
            _ = cur.execute(query, _data[0])
            resp = cur.fetchone() if _is_returning else None
        engine.commit()
    else:
        _ = engine.execute(query, _data[0])
        resp = engine.fetchone() if _is_returning else None
    return resp


def drop_db(conn: Connection, db_name: LiteralString):
    try:
        conn.execute(f"DROP DATABASE {db_name}")
    except InvalidCatalogName:
        pass


def clean_tables(engine: Connection, tables: Iterable[LiteralString], reset_seq: bool = True, cascade: bool = True):
    if not tables:
        return

    _tables = ", ".join(set(tables))
    query = f"TRUNCATE {_tables}"
    if reset_seq:
        query = f"{query} RESTART IDENTITY"
    if cascade:
        query = f"{query} CASCADE"
    engine.execute(query)
    engine.commit()


def get_tables(engine: Connection, schemas: list[str], ignored_tables: Iterable[str] | None = None):
    table_query = """
                  SELECT CONCAT_WS('.', schemaname, tablename) AS table
                  FROM pg_catalog.pg_tables
                  WHERE schemaname = ANY (%s)
                  ORDER BY schemaname, tablename \
                  """
    resp = fetch_all(engine, table_query, schemas)

    # Foreign keys
    _ignored_tables = set(ignored_tables) if ignored_tables else []
    return [x["table"] for x in resp if x["table"] not in _ignored_tables]


def insert_csv(
    cur: Cursor,
    schema: LiteralString,
    table: LiteralString,
    csv_path: Path,
    query: Optional[Query] = None,
    *,
    exclude_columns: Iterable[str] | None = None,
    delimiter: LiteralString = ",",
    block_size: int = 1000,
    on_conflict: LiteralString = "ON CONFLICT DO NOTHING",
):
    _columns = cast(LiteralString, csv_path.open().readline())
    _tmp_table, _tmp_query, _insert_query = get_tmp_table_query(
        schema, table, columns=_columns.split(","), on_conflict=on_conflict
    )
    _query: Query = query or cast(
        LiteralString,
        f"""
    COPY {_tmp_table}({_columns})
    FROM STDIN
    DELIMITER {delimiter!r}
    CSV HEADER
    """,
    )
    cur.execute(_tmp_query)
    if exclude_columns:
        _drop_columns = ",".join(f"DROP COLUMN {x}" for x in exclude_columns)
        _alter_query = f"""
        ALTER TABLE {_tmp_table}
        {_drop_columns}
        """
        cur.execute(cast(LiteralString, _alter_query))
    with csv_path.open() as f:
        with cur.copy(_query) as copy:
            while data := f.read(block_size):
                copy.write(data)
    cur.execute(_insert_query)


def set_seq_max(engine: Connection, seq_name: str, table_name: str):
    # To avoid potential conflicts
    with engine.cursor() as cursor:
        query = cast(LiteralString, f"SELECT SETVAL(%s, (SELECT MAX(id) + 1 FROM {table_name}))")
        cursor.execute(query, (seq_name,))
    engine.commit()
