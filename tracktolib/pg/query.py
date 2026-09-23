import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Literal, TypeAlias, overload

from ..pg_utils import get_conflict_query

try:
    import asyncpg
except ImportError:
    raise ImportError('Please install tracktolib with "pg" to use this module')

from tracktolib.utils import fill_dict


class SQLExpr(str):
    """Raw SQL expression inlined into the query instead of bound as a parameter."""


def _get_insert_query[K: str](table: str, columns: Iterable[K], values: str) -> str:
    _columns = ", ".join(columns)
    return f"INSERT INTO {table} AS t ({_columns}) VALUES ({values})"


def _get_returning_query[K: str](query: str, returning: Iterable[K]) -> str:
    _returning = ", ".join(returning)
    return f"{query} RETURNING {_returning}"


def _get_on_conflict_query[K: str](
    query: str,
    columns: Iterable[K],
    update_columns: Iterable[K] | None,
    ignore_columns: Iterable[K] | None,
    constraint: K | None,
    on_conflict: K | None,
    where: K | None,
    merge_columns: Iterable[K] | None,
    update_where: str | None = None,
) -> str:
    _on_conflict = get_conflict_query(
        columns=columns,
        update_columns=update_columns,
        ignore_columns=ignore_columns,
        constraint=constraint,
        on_conflict=on_conflict,
        where=where,
        merge_columns=merge_columns,
        update_where=update_where,
    )
    return f"{query} {_on_conflict}"


type ReturningFn[K: str] = Callable[[Iterable[K] | None, K | None], None]
type ConflictFn[K: str] = Callable[[Iterable[K] | None, Iterable[K] | None, str | None], None]

type _Connection = asyncpg.Connection | asyncpg.pool.Pool


@dataclass
class PGReturningQuery[K: str]:
    returning_ids: Iterable[K] | None = None
    query: str | None = None

    @classmethod
    def load(cls, *, keys: Iterable[K] | None = None, key: K | None = None, query: str | None = None):
        if not query and not keys and not key:
            raise ValueError("Please specify either key or keys")

        _keys = [key] if key else keys
        # self._check_keys(_keys)
        return cls(returning_ids=_keys, query=query)


@dataclass
class PGConflictQuery[K: str]:
    keys: Iterable[K] | None = None
    ignore_keys: Iterable[K] | None = None
    query: str | None = None
    constraint: str | None = None
    where: str | None = None
    """JSONB keys to merge (like jsonb1 || newjsonb2)"""
    merge_keys: Iterable[K] | None = None
    """Guard on DO UPDATE (e.g. `t.owner_id = EXCLUDED.owner_id`); conflicting rows failing it are skipped"""
    update_where: str | None = None

    def __post_init__(self):
        _has_keys = 1 if (self.keys or self.ignore_keys) else 0
        _has_constraint = 1 if self.constraint else 0
        if self.query and sum([_has_keys, _has_constraint]) > 0:
            raise ValueError("Please choose either keys, ignore_keys, constraint OR query")


@dataclass
class PGQuery[K: str, V]:
    table: str
    items: list[dict[K, V]]

    fill: bool = field(kw_only=True, default=False)
    quote_columns: bool = field(kw_only=True, default=False)

    def __post_init__(self):
        if self.fill:
            self.items = fill_dict(self.items, default=None)

    @property
    def keys(self) -> list[K]:
        return sorted(self.items[0].keys())

    @property
    def columns(self):
        return [f'"{x}"' for x in self.keys] if self.quote_columns else self.keys

    def iter_values(self, keys: list[K] | None = None) -> Iterator[tuple]:
        _keys = keys if keys is not None else self.keys
        for _item in self.items:
            yield tuple(v for k in _keys if not isinstance(v := _item[k], SQLExpr))

    @property
    def query(self) -> str:
        raise NotImplementedError()

    def _check_keys(self, keys: list[K]):
        invalid_keys = set(keys) - set(self.keys)
        if invalid_keys:
            _invalid_keys = ", ".join(f"{x!r}" for x in invalid_keys)
            raise ValueError(f"Invalid key(s) found: {_invalid_keys}")

    @property
    def values(self):
        return self._get_values()

    def _get_values(self):
        return next(self.iter_values()) if len(self.items) == 1 else list(self.iter_values())

    def _check_batch_expressions(self):
        first = {k: v for k, v in self.items[0].items() if isinstance(v, SQLExpr)}
        for item in self.items[1:]:
            expressions = {k: v for k, v in item.items() if isinstance(v, SQLExpr)}
            if expressions != first:
                raise ValueError("Inconsistent SQLExpr columns or expressions across rows for executemany")

    async def run(self, conn: _Connection, timeout: float | None = None):
        if len(self.items) == 1:
            await conn.execute(self.query, *self.values, timeout=timeout)  # type: ignore
        else:
            await conn.executemany(self.query, self.values, timeout=timeout)  # type: ignore

    def _get_fetch_values(self):
        # fetch* bind values positionally, so a batch can only be fetched when INSERT RETURNING flattens it
        if len(self.items) != 1:
            raise ValueError("Fetching batch results requires an INSERT with RETURNING")
        return self.values

    async def fetch(self, conn: _Connection, timeout: float | None = None) -> list[asyncpg.Record]:
        return await conn.fetch(self.query, *self._get_fetch_values(), timeout=timeout)

    async def fetchrow(self, conn: _Connection, timeout: float | None = None) -> asyncpg.Record | None:
        return await conn.fetchrow(self.query, *self._get_fetch_values(), timeout=timeout)

    async def fetchval(self, conn: _Connection, *, column: int = 0, timeout: float | None = None):
        return await conn.fetchval(self.query, *self._get_fetch_values(), timeout=timeout, column=column)

    async def exists(self, conn: _Connection, *, timeout: float | None = None) -> bool:
        _exists = await conn.fetchval(f"SELECT EXISTS({self.query})", *self._get_fetch_values(), timeout=timeout)
        return _exists or False


@dataclass
class PGInsertQuery(PGQuery):
    returning: PGReturningQuery | None = None
    on_conflict: PGConflictQuery | None = None

    @property
    def has_conflict(self):
        return self.on_conflict is not None

    @property
    def is_returning(self):
        return self.returning is not None

    def _get_values_query(self) -> str:
        """Generate the VALUES clause for the query."""
        if len(self.items) == 1 or not self.is_returning:
            self._check_batch_expressions()
            counter, parts = 0, []
            for k in self.keys:
                v = self.items[0][k]
                if isinstance(v, SQLExpr):
                    parts.append(v)
                else:
                    counter += 1
                    parts.append(f"${counter}")
            return ", ".join(parts)
        else:
            # Multiple rows with returning: single VALUES list with flat params
            counter, value_groups = 0, []
            for item in self.items:
                group = []
                for k in self.keys:
                    v = item[k]
                    if isinstance(v, SQLExpr):
                        group.append(v)
                    else:
                        counter += 1
                        group.append(f"${counter}")
                value_groups.append(f"({', '.join(group)})")
            return ", ".join(value_groups)

    @property
    def query(self) -> str:
        _columns = self.columns
        _values = self._get_values_query()

        if len(self.items) > 1 and self.is_returning:
            # For multi-row insert with returning, build full VALUES clause
            _columns_str = ", ".join(_columns)
            query = f"INSERT INTO {self.table} AS t ({_columns_str}) VALUES {_values}"
        else:
            query = _get_insert_query(self.table, _columns, _values)

        # Conflict
        if self.on_conflict:
            query = _get_on_conflict_query(
                query,
                _columns,
                self.on_conflict.keys,
                self.on_conflict.ignore_keys,
                self.on_conflict.constraint,
                self.on_conflict.query,
                self.on_conflict.where,
                self.on_conflict.merge_keys,
                self.on_conflict.update_where,
            )

        # Returning
        if self.returning is not None:
            if self.returning.returning_ids is None:
                raise ValueError("No returning ids found")
            query = _get_returning_query(query, self.returning.returning_ids)

        return query

    def _get_flat_values(self) -> list:
        """Get all values as a flat list for multi-row insert with returning."""
        return [val for item_values in self.iter_values() for val in item_values]

    def _get_fetch_values(self):
        """Flatten multi-row INSERT RETURNING values, since fetch* bind them positionally."""
        if self.is_returning:
            return self._get_flat_values()
        return super()._get_fetch_values()


def get_update_fields(
    item: dict,
    keys: list[str],
    *,
    start_from: int = 0,
    ignore_keys: list[str] | None = None,
    quote_columns: bool = False,
    merge_keys: list[str] | None = None,
) -> tuple[str, list]:
    values, fields, where_values = [], [], []
    counter = 0
    _merge_keys = set(merge_keys or [])
    _ignore_keys = ignore_keys or []

    for k in keys:
        v = item[k]
        if k in _ignore_keys:
            where_values.append(v)
            continue
        _col = f'"{k}"' if quote_columns else k
        if isinstance(v, SQLExpr):
            fields.append(
                f"{_col} = {v}" if k not in _merge_keys else f"{_col} = COALESCE(t.{_col}, JSONB_BUILD_OBJECT()) || {v}"
            )
        else:
            values.append(v)
            _counter = counter + start_from + 1
            fields.append(
                f"{_col} = ${_counter}"
                if k not in _merge_keys
                else f"{_col} = COALESCE(t.{_col}, JSONB_BUILD_OBJECT()) || ${_counter}"
            )
            counter += 1
    return ",\n".join(fields), values + where_values


@dataclass
class PGUpdateQuery(PGQuery):
    """
    Postgresql UPDATE query generator
    """

    """
    Value to start the arguments from:
    For instance, with a value of 10, the first argument will be $11
    """
    start_from: int | None = None
    """Keys to use for the WHERE clause. Theses fields will not be updated"""
    where_keys: list[str] | None = None
    """Where condition for the update query"""
    where: str | None = None
    returning: str | list[str] | None = None
    """If True, the query will return all the updated fields"""
    return_keys: bool = False
    """Values to update using merge (like {}::jsonb || {}::jsonb)"""
    merge_keys: list[str] | None = None
    """If True, the query is for many items and values will be a list of tuples"""
    is_many: bool = False

    _update_fields: str | None = field(init=False, default=None)
    _values: list | None = field(init=False, default=None)

    def __post_init__(self):
        self._check_batch_expressions()
        if self.where_keys:
            self._check_keys(self.where_keys)
            # Ordering the keys
            self.where_keys = [k for k in self.keys if k in self.where_keys]

        self._update_fields, self._values = get_update_fields(
            self.items[0],
            self.keys,
            start_from=self.start_from or 0,
            ignore_keys=self.where_keys,
            quote_columns=self.quote_columns,
            merge_keys=self.merge_keys,
        )
        if self.returning and self.return_keys:
            raise ValueError("Please choose either returning or return_keys")

    @property
    def values(self):
        if self._values is None:
            raise ValueError("No values found")
        if len(self.items) == 1 and not self.is_many:
            return self._values
        _where_keys = self.where_keys or []
        _keys_not_where = [k for k in self.keys if k not in _where_keys]
        values = list(self.iter_values(keys=_keys_not_where + _where_keys))
        return values

    def _get_where_query(self) -> str:
        if self.where:
            return self.where
        elif self.where_keys is not None:
            if self.start_from is not None:
                start_from = self.start_from
            else:
                _where_set = set(self.where_keys)
                start_from = sum(
                    1 for k in self.keys if k not in _where_set and not isinstance(self.items[0][k], SQLExpr)
                )
            return "WHERE " + " AND ".join(f"{k} = ${i + start_from + 1}" for i, k in enumerate(self.where_keys))
        return ""

    def _get_fetch_values(self):
        if self.is_many:
            raise ValueError("Fetching batch UPDATE results is not supported")
        return super()._get_fetch_values()

    @property
    def query(self) -> str:
        if not self._update_fields:
            raise ValueError("No update fields found")

        query = f"""
        UPDATE {self.table} t
            SET {self._update_fields}
        {self._get_where_query()}
        """
        if self.returning:
            query = _get_returning_query(query.strip(), self.returning)
        elif self.return_keys:
            # where_keys is None with a raw where clause: return every column
            returning = self.keys if not self.where_keys else [k for k in self.keys if k not in self.where_keys]
            query = _get_returning_query(query.strip(), returning)
        return query


OnConflict: TypeAlias = PGConflictQuery | str


def insert_pg[K: str](
    table: str,
    items: list[dict],
    *,
    on_conflict: OnConflict | None = None,
    returning: Iterable[K] | None = None,
    fill: bool = False,
    quote_columns: bool = False,
) -> PGInsertQuery:
    _on_conflict = PGConflictQuery(query=on_conflict) if isinstance(on_conflict, str) else on_conflict
    _returning = PGReturningQuery.load(keys=returning) if returning else None
    return PGInsertQuery(
        table, items, fill=fill, on_conflict=_on_conflict, returning=_returning, quote_columns=quote_columns
    )


type QueryCallback[Q: PGInsertQuery | PGUpdateQuery] = Callable[[Q], None]


async def insert_one(
    conn: _Connection,
    table: str,
    item: dict,
    *,
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    quote_columns: bool = False,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
):
    query = insert_pg(table=table, items=[item], on_conflict=on_conflict, fill=fill, quote_columns=quote_columns)
    if query_callback is not None:
        query_callback(query)
    await query.run(conn)


@overload
async def insert_many(
    conn: _Connection,
    table: str,
    items: list[dict],
    *,
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    quote_columns: bool = False,
    returning: None = None,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> None: ...


@overload
async def insert_many(
    conn: _Connection,
    table: str,
    items: list[dict],
    *,
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    quote_columns: bool = False,
    returning: str | list[str],
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> list[asyncpg.Record]: ...


async def insert_many(
    conn: _Connection,
    table: str,
    items: list[dict],
    *,
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    quote_columns: bool = False,
    returning: str | list[str] | None = None,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> list[asyncpg.Record] | None:
    returning_values = [returning] if isinstance(returning, str) else returning
    query = insert_pg(
        table=table,
        items=items,
        on_conflict=on_conflict,
        fill=fill,
        quote_columns=quote_columns,
        returning=returning_values,
    )
    if query_callback is not None:
        query_callback(query)

    if returning is not None:
        return await conn.fetch(query.query, *query._get_flat_values())
    else:
        await query.run(conn)
        return None


@overload
async def insert_returning(
    conn: _Connection,
    table: str,
    item: dict,
    returning: str,
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> Any | None: ...


@overload
async def insert_returning(
    conn: _Connection,
    table: str,
    item: dict,
    returning: list[str],
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> asyncpg.Record | None: ...


@overload
async def insert_returning(
    conn: _Connection,
    table: str,
    item: list[dict],
    returning: str | list[str],
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> list[asyncpg.Record]: ...


async def insert_returning(
    conn: _Connection,
    table: str,
    item: dict | list[dict],
    returning: list[str] | str,
    on_conflict: OnConflict | None = None,
    fill: bool = False,
    query_callback: QueryCallback[PGInsertQuery] | None = None,
) -> asyncpg.Record | Any | list[asyncpg.Record] | None:
    returning_values = [returning] if isinstance(returning, str) else returning
    items = item if isinstance(item, list) else [item]

    query = insert_pg(table=table, items=items, on_conflict=on_conflict, fill=fill, returning=returning_values)
    if query_callback is not None:
        query_callback(query)

    if len(items) > 1:
        # Multi-row insert: use fetch() with flat values
        return await conn.fetch(query.query, *query._get_flat_values())
    else:
        # Single row insert: use fetchval or fetchrow
        fn = conn.fetchval if len(returning_values) == 1 and returning != "*" else conn.fetchrow
        return await fn(query.query, *query.values)


async def fetch_count(conn: _Connection, query: str, *args) -> int:
    c = await conn.fetchval(f"SELECT COUNT(*) FROM ({query}) t", *args)
    return typing.cast(int, c)


def Conflict[K: str](
    keys: Iterable[K],
    ignore_keys: Iterable[K] | None = None,
) -> PGConflictQuery:
    return PGConflictQuery(keys=keys, ignore_keys=ignore_keys)


async def update_one(
    conn: _Connection,
    table: str,
    item: dict,
    *args,
    keys: list[str] | None = None,
    start_from: int | None = None,
    where: str | None = None,
    merge_keys: list[str] | None = None,
    query_callback: QueryCallback[PGUpdateQuery] | None = None,
):
    query = PGUpdateQuery(
        table=table, items=[item], start_from=start_from, where_keys=keys, where=where, merge_keys=merge_keys
    )
    if query_callback is not None:
        query_callback(query)
    await conn.execute(query.query, *args, *query.values)


@overload
async def update_returning(
    conn: _Connection,
    table: str,
    item: dict,
    *args,
    returning: str,
    return_keys: Literal[False] = False,
    where: str | None = None,
    keys: list[str] | None = None,
    start_from: int | None = None,
    merge_keys: list[str] | None = None,
    query_callback: QueryCallback[PGUpdateQuery] | None = None,
) -> Any | None: ...


@overload
async def update_returning(
    conn: _Connection,
    table: str,
    item: dict,
    *args,
    returning: list[str],
    return_keys: Literal[False] = False,
    where: str | None = None,
    keys: list[str] | None = None,
    start_from: int | None = None,
    merge_keys: list[str] | None = None,
    query_callback: QueryCallback[PGUpdateQuery] | None = None,
) -> asyncpg.Record | None: ...


@overload
async def update_returning(
    conn: _Connection,
    table: str,
    item: dict,
    *args,
    returning: None = None,
    return_keys: Literal[True],
    where: str | None = None,
    keys: list[str] | None = None,
    start_from: int | None = None,
    merge_keys: list[str] | None = None,
    query_callback: QueryCallback[PGUpdateQuery] | None = None,
) -> asyncpg.Record | None: ...


async def update_returning(
    conn: _Connection,
    table: str,
    item: dict,
    *args,
    returning: list[str] | str | None = None,
    return_keys: bool = False,
    where: str | None = None,
    keys: list[str] | None = None,
    start_from: int | None = None,
    merge_keys: list[str] | None = None,
    query_callback: QueryCallback[PGUpdateQuery] | None = None,
) -> Any | asyncpg.Record | None:
    if returning is not None:
        returning_values = [returning] if isinstance(returning, str) else returning
    else:
        returning_values = None
    query = PGUpdateQuery(
        table=table,
        items=[item],
        start_from=start_from,
        where=where,
        where_keys=keys,
        return_keys=return_keys,
        returning=returning_values,
        merge_keys=merge_keys,
    )
    if query_callback is not None:
        query_callback(query)
    fn = conn.fetchval if len(returning_values or []) == 1 else conn.fetchrow
    return await fn(query.query, *args, *query.values)


async def update_many(
    conn: _Connection,
    table: str,
    items: list[dict],
    keys: list[str] | None = None,
    start_from: int | None = None,
    where: str | None = None,
    merge_keys: list[str] | None = None,
    query_callback: QueryCallback[PGUpdateQuery] | None = None,
):
    query = PGUpdateQuery(
        table=table,
        items=items,
        start_from=start_from,
        where_keys=keys,
        where=where,
        merge_keys=merge_keys,
        is_many=True,
    )
    if query_callback is not None:
        query_callback(query)
    await conn.executemany(query.query, query.values)
