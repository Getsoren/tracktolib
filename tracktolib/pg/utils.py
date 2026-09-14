import csv
import datetime as dt
import functools
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable, LiteralString, NamedTuple, Sequence, cast

from ..pg_utils import get_conflict_query

try:
    import asyncpg
    from rich.progress import Progress
except ImportError:
    raise ImportError('Please install asyncpg, rich or tracktolib with "pg" to use this module')

from asyncpg.exceptions import (
    CheckViolationError,
    ForeignKeyViolationError,
    UniqueViolationError,
)

from tracktolib.pg_utils import get_tmp_table_query
from tracktolib.utils import get_chunks

logger = logging.Logger("tracktolib-pg")


async def iterate_pg(
    conn: asyncpg.Connection, query: str, *args, from_offset: int = 0, chunk_size: int = 500, timeout: int | None = None
) -> AsyncIterator[list[asyncpg.Record]]:
    async with conn.transaction():
        cur: asyncpg.connection.cursor.Cursor = await conn.cursor(query, *args)
        if from_offset:
            await cur.forward(from_offset, timeout=timeout)
        while data := await cur.fetch(chunk_size, timeout=timeout):
            yield data


_GET_TABLE_INFOS_QUERY = """
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns WHERE table_schema = $1 AND table_name = $2;
"""


def _str_to_date(value: str) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def _str_max_size(value: str, *, max_size: int | None = None) -> str:
    _value = value.strip()
    if max_size is not None and len(_value) > max_size:
        raise ValueError(f"Got size {len(_value)} but max size is {max_size} for {_value!r}")
    return _value


def _str_to_datetime(value: str) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value else None


def _str_to_point(value: str) -> tuple[float, ...] | None:
    return tuple(float(x) for x in value.split(",")) if value else None


def _str_to_bool(value: str) -> bool:
    match value.strip().lower():
        case "true" | "t" | "yes" | "y" | "on" | "1":
            return True
        case "false" | "f" | "no" | "n" | "off" | "0":
            return False
        case _:
            raise ValueError(f"Invalid boolean value: {value!r}")


def _get_type(data_type: str, char_max_length: int | None):
    match data_type:
        case "integer":
            return int
        case "timestamp without time zone":
            return _str_to_datetime
        case "timestamp with time zone":
            return _str_to_datetime
        case "date":
            return _str_to_date
        case "boolean":
            return _str_to_bool
        case "point":
            return _str_to_point

    return functools.partial(_str_max_size, max_size=char_max_length)


async def get_table_infos(conn: asyncpg.Connection, schema: str, table: str):
    infos = await conn.fetch(_GET_TABLE_INFOS_QUERY, schema, table)
    return {
        info["column_name"]: _get_type(data_type=info["data_type"], char_max_length=info["character_maximum_length"])
        for info in infos
    }


def _fmt_record_tuple(record: dict, data_types: dict, columns: Sequence[str]) -> tuple:
    _record = []
    for col_name in columns:
        value = record[col_name]
        try:
            _record.append(data_types[col_name](value) if value not in {"", "-"} and value is not None else None)
        except ValueError:
            logger.error(f"Could not convert field {col_name!r} with value {value!r}")
            raise

    return tuple(_record)


async def upsert_csv(
    conn: asyncpg.Connection,
    csv_path: Path,
    schema: LiteralString,
    table: LiteralString,
    *,
    chunk_size: int = 5_000,
    show_progress: bool = False,
    nb_lines: int | None = None,
    on_conflict_keys: Iterable[LiteralString] | None = None,
    delimiter: str = ",",
    col_names: list[LiteralString] | None = None,
    skip_header: bool = False,
):
    infos = await get_table_infos(conn, schema, table)

    on_conflict_str = "ON CONFLICT DO NOTHING"
    if on_conflict_keys is not None:
        on_conflict_str = get_conflict_query(columns=infos.keys(), update_columns=on_conflict_keys)

    with csv_path.open("r") as f:
        reader = csv.DictReader(f, delimiter=delimiter, fieldnames=col_names)
        if skip_header:
            next(reader)
        _columns = col_names if col_names else cast(list[LiteralString], [x.lower() for x in (reader.fieldnames or [])])

        missing_cols = set(_columns) - set(infos.keys())
        if missing_cols:
            raise ValueError(f"Could not find the following columns in the table: {','.join(missing_cols)}")

        async with conn.transaction():
            _tmp_table, _tmp_query, _insert_query = get_tmp_table_query(
                schema, table, columns=_columns, on_conflict=on_conflict_str
            )
            logger.info(f"Creating tmp table: {_tmp_table!r}")
            await conn.execute(_tmp_query)
            logger.info(f"Inserting data from {csv_path!r} to {_tmp_table!r}")

            with Progress(disable=not show_progress) as progress:
                task1 = progress.add_task("[red]Inserting csv chunks....", total=nb_lines)
                for records in get_chunks(reader, size=chunk_size, as_list=False):
                    _data = [_fmt_record_tuple(x, infos, _columns) for x in records]
                    await conn.copy_records_to_table(table_name=_tmp_table, columns=_columns, records=_data)
                    progress.update(task1, advance=chunk_size)
            logger.info(f'Inserting data from {_tmp_table} to "{schema}.{table}"')
            await conn.execute(_insert_query)


class PGError(NamedTuple):
    key: str
    reason: str


@dataclass
class PGException(Exception):
    reason: str


@contextmanager
def safe_pg_context(errors: list[PGError]):
    try:
        yield
    except (UniqueViolationError, CheckViolationError, ForeignKeyViolationError) as e:
        for error in errors:
            if error.key in e.args[0]:
                raise PGException(reason=error.reason)
        raise e


def safe_pg(errors: list[PGError]):
    """
    Decorator to handle errors from PG.
    When an error is encountered,
    this will check if the error is in the list of errors to handle
    and display a custom error message.
    """

    def wrapper(fn):
        @functools.wraps(fn)
        async def _fn(*args, **kwargs):
            with safe_pg_context(errors):
                return await fn(*args, **kwargs)

        return _fn

    return wrapper
