import datetime as dt

import asyncpg
import pytest

from tracktolib.pg import Conflict, PGConflictQuery, SQLExpr
from tracktolib.pg_sync import fetch_all, insert_one
from tracktolib.tests import assert_equals


def test_insert_one_query():
    from tracktolib.pg import PGInsertQuery

    query = PGInsertQuery("schema.table", [{"foo": 1}]).query
    assert query == "INSERT INTO schema.table AS t (foo) VALUES ($1)"


def test_insert_many_query():
    from tracktolib.pg import PGInsertQuery

    query = PGInsertQuery("schema.table", [{"foo": 1}, {"foo": 2}]).query
    assert query == "INSERT INTO schema.table AS t (foo) VALUES ($1)"


@pytest.mark.parametrize(
    "items,expected_query,expected_values",
    [
        pytest.param(
            [{"foo": 1, "ts": SQLExpr("NOW()")}],
            "INSERT INTO schema.table AS t (foo, ts) VALUES ($1, NOW())",
            [(1,)],
            id="insert_one_sql_expr",
        ),
        pytest.param(
            [{"foo": 1, "ts": SQLExpr("NOW()")}, {"foo": 2, "ts": SQLExpr("NOW()")}],
            "INSERT INTO schema.table AS t (foo, ts) VALUES ($1, NOW())",
            [(1,), (2,)],
            id="insert_many_sql_expr",
        ),
    ],
)
def test_insert_sql_expr_query(items, expected_query, expected_values):
    from tracktolib.pg import PGInsertQuery

    q = PGInsertQuery("schema.table", items)
    assert q.query == expected_query
    assert list(q.iter_values()) == expected_values


@pytest.mark.parametrize(
    "items,expected_query,expected_flat_values",
    [
        pytest.param(
            [{"foo": 1, "ts": SQLExpr("NOW()")}, {"foo": 2, "ts": SQLExpr("NOW()")}],
            "INSERT INTO schema.table AS t (foo, ts) VALUES ($1, NOW()), ($2, NOW()) RETURNING id",
            [1, 2],
            id="multi_row_returning_sql_expr",
        ),
    ],
)
def test_insert_many_returning_sql_expr_query(items, expected_query, expected_flat_values):
    from tracktolib.pg import PGInsertQuery, PGReturningQuery

    _returning = PGReturningQuery.load(keys=["id"])
    q = PGInsertQuery("schema.table", items, returning=_returning)
    assert q.query == expected_query
    assert q._get_flat_values() == expected_flat_values


def test_insert_many_inconsistent_sqlexpr_raises():
    from tracktolib.pg import PGInsertQuery

    items = [
        {"foo": 1, "created": dt.datetime(2024, 1, 1), "ts": SQLExpr("NOW()")},
        {"foo": 2, "created": dt.datetime(2024, 6, 1), "ts": dt.datetime(2024, 6, 1)},
    ]
    with pytest.raises(ValueError, match="Inconsistent SQLExpr"):
        PGInsertQuery("schema.table", items).query


@pytest.mark.parametrize(
    "items,expected_query,expected_flat_values",
    [
        pytest.param(
            [{"foo": 1}, {"foo": 2}],
            "INSERT INTO schema.table AS t (foo) VALUES ($1), ($2) RETURNING id",
            [1, 2],
            id="single_column",
        ),
        pytest.param(
            [{"bar": "a", "foo": 1}, {"bar": "b", "foo": 2}],
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2), ($3, $4) RETURNING id",
            ["a", 1, "b", 2],
            id="multiple_columns",
        ),
    ],
)
def test_insert_many_returning_query(items, expected_query, expected_flat_values):
    from tracktolib.pg import PGInsertQuery, PGReturningQuery

    _returning = PGReturningQuery.load(keys=["id"])
    q = PGInsertQuery("schema.table", items, returning=_returning)
    assert q.query == expected_query
    assert q._get_flat_values() == expected_flat_values


def compare_strings(str1: str, str2: str):
    str1 = " ".join(x.strip() for x in str1.split("\n"))
    str2 = " ".join(x.strip() for x in str2.split("\n"))

    assert str1.strip() == str2.strip()


@pytest.mark.parametrize(
    "data,on_conflict,returning,expected,quote_columns",
    [
        (
            {"foo": 1},
            {"keys": ["id"]},
            None,
            "INSERT INTO schema.table AS t (foo) VALUES ($1) "
            "ON CONFLICT (id) DO UPDATE SET foo = COALESCE(EXCLUDED.foo, t.foo)",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"keys": ["id"]},
            None,
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2) "
            "ON CONFLICT (id) DO UPDATE SET bar = COALESCE(EXCLUDED.bar, t.bar), "
            "foo = COALESCE(EXCLUDED.foo, t.foo)",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"keys": ["id"], "where": "id = 2"},
            None,
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2) "
            "ON CONFLICT (id) WHERE id = 2 DO UPDATE SET bar = COALESCE(EXCLUDED.bar, t.bar), "
            "foo = COALESCE(EXCLUDED.foo, t.foo)",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"keys": ["id"], "ignore_keys": ["foo"]},
            None,
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2) "
            "ON CONFLICT (id) DO UPDATE SET bar = COALESCE(EXCLUDED.bar, t.bar)",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"query": "ON CONFLICT DO NOTHING"},
            None,
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"query": "ON CONFLICT DO NOTHING"},
            None,
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"query": "ON CONFLICT DO NOTHING"},
            {"key": "bar"},
            "INSERT INTO schema.table AS t (bar, foo) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING bar",
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"constraint": "my_constraint"},
            None,
            """
                INSERT INTO schema.table AS t (bar, foo)
                VALUES ($1, $2)
                ON CONFLICT ON CONSTRAINT my_constraint
                    DO UPDATE SET bar = COALESCE(EXCLUDED.bar, t.bar),
                                  foo = COALESCE(EXCLUDED.foo, t.foo)
                """,
            False,
        ),
        (
            {"foo": 1, "bar": 2},
            {"constraint": "my_constraint"},
            None,
            """
                INSERT INTO schema.table AS t ("bar", "foo")
                VALUES ($1, $2)
                ON CONFLICT ON CONSTRAINT my_constraint
                    DO UPDATE SET "bar" = COALESCE(EXCLUDED."bar", t."bar"),
                                  "foo" = COALESCE(EXCLUDED."foo", t."foo")
                """,
            True,
        ),
        (
            {"foo": 1, "bar": 2},
            {"merge_keys": ["foo"], "keys": ["bar"]},
            None,
            """
                INSERT INTO schema.table AS t (bar, foo)
                VALUES ($1, $2)
                ON CONFLICT (bar)
                    DO UPDATE SET foo = COALESCE(t.foo, JSONB_BUILD_OBJECT()) || EXCLUDED.foo
                """,
            False,
        ),
    ],
)
def test_pg_insert_query(data, on_conflict, returning, expected, quote_columns):
    from tracktolib.pg import PGConflictQuery, PGInsertQuery, PGReturningQuery

    _returning = PGReturningQuery.load(**returning) if returning else None
    query = PGInsertQuery(
        "schema.table",
        [data],
        on_conflict=PGConflictQuery(**on_conflict),
        returning=_returning,
        quote_columns=quote_columns,
    ).query

    compare_strings(query, expected)


@pytest.mark.parametrize("async_engine", ["connection", "pool"])
@pytest.mark.usefixtures("setup_tables")
async def test_insert_one(aengine, apool, engine, async_engine):
    from tracktolib.pg import insert_one

    _engine = aengine if async_engine == "connection" else apool

    await insert_one(_engine, "foo.foo", {"foo": 1})

    db_data = fetch_all(engine, "SELECT bar, foo FROM foo.foo")
    assert db_data == [{"bar": None, "foo": 1}]


@pytest.mark.parametrize("quote_columns", [True, False])
@pytest.mark.parametrize("async_engine", ["connection", "pool"])
@pytest.mark.usefixtures("setup_tables")
async def test_insert_many(aengine, apool, engine, async_engine, quote_columns):
    from tracktolib.pg import insert_many

    _engine = aengine if async_engine == "connection" else apool

    await insert_many(_engine, "foo.foo", [{"foo": 1}, {"bar": "hello"}], fill=True, quote_columns=quote_columns)

    db_data = fetch_all(engine, "SELECT bar, foo FROM foo.foo ORDER BY foo")
    assert db_data == [{"bar": None, "foo": 1}, {"bar": "hello", "foo": None}]


@pytest.fixture()
def insert_data(engine):
    from tracktolib.pg_sync import insert_many

    data = [{"id": 1, "foo": 10, "bar": "baz"}, {"id": 2, "foo": 20, "bar": None}]
    insert_many(engine, "foo.foo", data)


@pytest.mark.parametrize(
    "setup_fn, insert_params, expected_query, expected",
    [
        pytest.param(
            None,
            {"table": "foo.foo", "item": {"id": 1, "foo": 1}, "on_conflict": Conflict(keys=["id"])},
            "SELECT bar, foo FROM foo.foo WHERE id = 1",
            [{"bar": "baz", "foo": 1}],
            id="on_conflict",
        ),
        pytest.param(
            None,
            {
                "table": "foo.foo",
                "item": {"id": 1, "foo": 1, "bar": "baz"},
                "on_conflict": PGConflictQuery(keys=["id"], update_where="t.bar = EXCLUDED.bar"),
            },
            "SELECT bar, foo FROM foo.foo WHERE id = 1",
            [{"bar": "baz", "foo": 1}],
            id="on conflict update_where match",
        ),
        pytest.param(
            None,
            {
                "table": "foo.foo",
                "item": {"id": 1, "foo": 1, "bar": "other"},
                "on_conflict": PGConflictQuery(keys=["id"], update_where="t.bar = EXCLUDED.bar"),
            },
            "SELECT bar, foo FROM foo.foo WHERE id = 1",
            [{"bar": "baz", "foo": 10}],
            id="on conflict update_where mismatch",
        ),
        pytest.param(
            lambda engine: (insert_one(engine, "foo.baz", {"id": 0, "baz": {"foo": 1}})),
            {
                "table": "foo.baz",
                "item": {"id": 0, "baz": {"bar": "hello"}},
                "on_conflict": PGConflictQuery(keys=["id"], merge_keys=["baz"]),
            },
            "SELECT bar, baz FROM foo.baz WHERE id = 0",
            [{"bar": None, "baz": {"foo": 1, "bar": "hello"}}],
            id="on conflict merge",
        ),
        pytest.param(
            lambda engine: (insert_one(engine, "foo.baz", {"id": 0, "bar": {"foo": 1}})),
            {
                "table": "foo.baz",
                "item": {"id": 0, "bar": {"foo": 2}},
                "on_conflict": PGConflictQuery(keys=["id"], merge_keys=["baz"]),
            },
            "SELECT bar, baz FROM foo.baz WHERE id = 0",
            [{"bar": {"foo": 2}, "baz": None}],
            id="on conflict merge no left",
        ),
        pytest.param(
            lambda engine: (insert_one(engine, "foo.baz", {"id": 0, "baz": {"foo": 2}})),
            {
                "table": "foo.baz",
                "item": {"id": 0, "baz": None},
                "on_conflict": PGConflictQuery(keys=["id"], merge_keys=["baz"]),
            },
            "SELECT bar, baz FROM foo.baz WHERE id = 0",
            [{"bar": None, "baz": None}],
            id="on conflict merge set None",
        ),
    ],
)
@pytest.mark.usefixtures("setup_tables", "insert_data")
async def test_insert_conflict_one(aengine, engine, setup_fn, insert_params, expected_query, expected):
    from tracktolib.pg import insert_one
    from tracktolib.pg_sync import fetch_all

    if setup_fn is not None:
        setup_fn(engine)

    await insert_one(aengine, **insert_params)
    db_data = fetch_all(engine, expected_query)
    assert db_data == expected


@pytest.mark.usefixtures("setup_tables", "insert_data")
async def test_insert_conflict_many(aengine, engine):
    from tracktolib.pg import Conflict, insert_many

    data = [{"id": 1, "foo": 1}, {"id": 2, "bar": "hello"}]
    await insert_many(aengine, "foo.foo", data, fill=True, on_conflict=Conflict(keys=["id"], ignore_keys=["foo"]))
    db_data = fetch_all(engine, "SELECT bar, foo FROM foo.foo ORDER BY foo")
    assert [{"bar": "baz", "foo": 10}, {"bar": "hello", "foo": 20}] == db_data


@pytest.mark.parametrize("on_conflict", [None, "ON CONFLICT DO NOTHING"])
@pytest.mark.usefixtures("setup_tables")
async def test_insert_one_returning_one(aengine, engine, on_conflict):
    from tracktolib.pg import insert_returning

    new_id = await insert_returning(aengine, "foo.foo", {"id": 1, "foo": 1}, returning="id", on_conflict=on_conflict)
    assert new_id is not None

    db_data = fetch_all(engine, "SELECT bar, foo FROM foo.foo WHERE id = %s", new_id)
    assert db_data == [{"bar": None, "foo": 1}]


@pytest.mark.usefixtures("setup_tables")
async def test_insert_one_returning_many(aengine, engine):
    from tracktolib.pg import insert_returning

    returned_value = await insert_returning(aengine, "foo.foo", {"id": 1, "foo": 1}, returning=["id", "bar"])
    assert returned_value is not None
    returned_value = dict(returned_value)
    assert returned_value.pop("id") is not None
    assert returned_value == {"bar": None}
    returned_values = await insert_returning(aengine, "foo.foo", {"id": 2, "foo": 2}, returning="*")
    assert returned_values is not None
    assert_equals(dict(returned_values), {"id": 2, "foo": 2, "bar": None})


@pytest.mark.parametrize(
    "items, returning, expected_returned",
    [
        pytest.param(
            [{"id": 1, "foo": 10}, {"id": 2, "foo": 20}, {"id": 3, "foo": 30}],
            "id",
            [{"id": 1}, {"id": 2}, {"id": 3}],
            id="single_returning_column",
        ),
        pytest.param(
            [{"id": 1, "foo": 10, "bar": "a"}, {"id": 2, "foo": 20, "bar": "b"}],
            ["id", "bar"],
            [{"id": 1, "bar": "a"}, {"id": 2, "bar": "b"}],
            id="multiple_returning_columns",
        ),
    ],
)
@pytest.mark.usefixtures("setup_tables")
async def test_insert_many_returning(aengine, engine, items, returning, expected_returned):
    from tracktolib.pg import insert_returning

    returned_values = await insert_returning(aengine, "foo.foo", items, returning=returning)
    assert returned_values is not None
    assert len(returned_values) == len(expected_returned)
    assert [dict(r) for r in returned_values] == expected_returned


@pytest.fixture()
def insert_iterate_data(engine):
    from tracktolib.pg_sync import insert_many

    data = [{"id": i, "foo": 10, "bar": "baz"} for i in range(10)]
    insert_many(engine, "foo.foo", data)


@pytest.mark.usefixtures("setup_tables", "insert_iterate_data")
async def test_iterate_pg(aengine):
    from tracktolib.pg import iterate_pg
    from tracktolib.tests import assert_equals

    output = []
    query = "SELECT id FROM foo.foo"
    async for c in iterate_pg(aengine, query, from_offset=2, chunk_size=3):
        output.append([dict(x) for x in c])

    expected = [[{"id": 2}, {"id": 3}, {"id": 4}], [{"id": 5}, {"id": 6}, {"id": 7}], [{"id": 8}, {"id": 9}]]
    assert_equals(output, expected)


@pytest.mark.usefixtures("setup_tables")
async def test_upload_csv(aengine, static_dir, engine):
    from tracktolib.pg import upsert_csv
    from tracktolib.tests import assert_equals

    file = static_dir / "test.csv"
    file2 = static_dir / "test2.csv"

    await upsert_csv(aengine, file, schema="foo", table="bar")
    db = fetch_all(engine, "SELECT * FROM foo.bar ORDER BY foo")
    expected = [{"bar": "2", "foo": 1}]
    assert_equals(db, expected)
    # Run again works with on conflict ignore
    await upsert_csv(aengine, file, schema="foo", table="bar")
    # Run again works with update
    await upsert_csv(aengine, file, schema="foo", table="bar", on_conflict_keys=["foo"])
    # Run again works with update and other file
    await upsert_csv(
        aengine,
        file2,
        schema="foo",
        table="bar",
        on_conflict_keys=["foo"],
        delimiter=";",
        col_names=["foo", "bar"],
        skip_header=True,
    )
    db = fetch_all(engine, "SELECT * FROM foo.bar ORDER BY foo")
    expected = [{"bar": "11", "foo": 1}, {"bar": "22", "foo": 2}]
    assert_equals(db, expected)


@pytest.mark.usefixtures("setup_tables", "insert_iterate_data")
async def test_fetch_count(aengine):
    from tracktolib.pg import fetch_count

    count = await fetch_count(aengine, "SELECT 1 FROM foo.foo")
    assert count == 10


@pytest.mark.parametrize(
    "data,params,expected",
    [
        pytest.param(
            [{"foo": 1}],
            {"start_from": 0, "where": None, "returning": None},
            {"query": "UPDATE schema.table t SET foo = $1", "values": [1]},
            id="no where - no returning",
        ),
        pytest.param(
            [{"foo": 1}],
            {"start_from": 1, "where": "WHERE bar = $1", "returning": None},
            {"query": "UPDATE schema.table t SET foo = $2 WHERE bar = $1", "values": [1]},
            id="where - no returning",
        ),
        pytest.param(
            [{"foo": 1}],
            {"returning": ["foo"]},
            {"query": "UPDATE schema.table t SET foo = $1 RETURNING foo", "values": [1]},
            id="no where - returning",
        ),
        pytest.param(
            [{"foo": 1, "id": 1}],
            {"where_keys": ["id"]},
            {"query": "UPDATE schema.table t SET foo = $1 WHERE id = $2", "values": [1, 1]},
            id="where - no returning - keys",
        ),
        pytest.param(
            [{"foo": 1, "id": 1}],
            {"where_keys": ["id"], "return_keys": True},
            {"query": "UPDATE schema.table t SET foo = $1 WHERE id = $2 RETURNING foo", "values": [1, 1]},
            id="where - returning - keys",
        ),
        pytest.param(
            [{"foo": 2, "id": 1, "bar": 3}],
            {"where_keys": ["id", "bar"], "return_keys": True},
            {
                "query": "UPDATE schema.table t SET foo = $1 WHERE bar = $2 AND id = $3 RETURNING foo",
                "values": [2, 3, 1],
            },
            id="where - returning - multiple keys",
        ),
        pytest.param(
            [{"foo": 2, "id": 1, "bar": 3}],
            {"where_keys": ["bar", "id"], "return_keys": True},
            {
                "query": "UPDATE schema.table t SET foo = $1 WHERE bar = $2 AND id = $3 RETURNING foo",
                "values": [2, 3, 1],
            },
            id="where - returning - multiple keys different order",
        ),
        pytest.param(
            [{"bar": {"foo": 1}}],
            {"merge_keys": ["bar"]},
            {
                "query": "UPDATE schema.table t SET bar = COALESCE(t.bar, JSONB_BUILD_OBJECT()) || $1",
                "values": [{"foo": 1}],
            },
            id="merge keys - no where",
        ),
        pytest.param(
            [{"foo": 10, "id": 1, "zar": 100}, {"foo": 20, "id": 2, "zar": 22}],
            {"where_keys": ["id"]},
            {
                "query": "UPDATE schema.table t SET foo = $1, zar = $2 WHERE id = $3",
                "values": [(10, 100, 1), (20, 22, 2)],
            },
            id="multiple rows - only first",
        ),
        pytest.param(
            [{"foo": 10, "id": 1, "zar": 100}],
            {"is_many": True},
            {
                "query": "UPDATE schema.table t SET foo = $1, id = $2, zar = $3",
                "values": [(10, 1, 100)],
            },
            id="one row - only first",
        ),
        pytest.param(
            [{"foo": SQLExpr("NOW()"), "id": 1}],
            {"where_keys": ["id"]},
            {
                "query": "UPDATE schema.table t SET foo = NOW() WHERE id = $1",
                "values": [1],
            },
            id="sql_expr in set",
        ),
        pytest.param(
            [{"foo": SQLExpr("NOW()"), "bar": 2, "id": 1}],
            {"where_keys": ["id"]},
            {
                "query": "UPDATE schema.table t SET bar = $1, foo = NOW() WHERE id = $2",
                "values": [2, 1],
            },
            id="sql_expr mixed with regular values",
        ),
        pytest.param(
            [{"foo": SQLExpr("NOW()"), "id": 1}],
            {"where_keys": ["id"], "returning": ["foo"]},
            {
                "query": "UPDATE schema.table t SET foo = NOW() WHERE id = $1 RETURNING foo",
                "values": [1],
            },
            id="all set values are sql_expr",
        ),
    ],
)
def test_pg_update_query(data, params, expected):
    from tracktolib.pg import PGUpdateQuery

    query = PGUpdateQuery("schema.table", data, **params)
    compare_strings(query.query, expected["query"])
    assert query.values == expected["values"]


@pytest.mark.parametrize(
    "setup_fn,params,expected_query,expected",
    [
        pytest.param(
            None,
            {"table": "foo.foo", "item": {"foo": 1, "id": 1}, "keys": ["id"]},
            "SELECT * FROM foo.foo WHERE id = 1",
            [{"bar": "baz", "foo": 1, "id": 1}],
            id="default",
        ),
        pytest.param(
            lambda engine: insert_one(engine, "foo.baz", {"id": 0, "baz": {"foo": 1}}),
            {"table": "foo.baz", "item": {"baz": {"hello": "world"}, "id": 0}, "keys": ["id"], "merge_keys": ["baz"]},
            "SELECT * FROM foo.baz WHERE id = 0",
            [{"bar": None, "baz": {"foo": 1, "hello": "world"}, "id": 0}],
            id="merge keys",
        ),
        pytest.param(
            lambda engine: insert_one(engine, "foo.baz", {"id": 0, "baz": {"foo": 1}}),
            {"table": "foo.baz", "item": {"bar": {"foo": 2}, "id": 0}, "keys": ["id"], "merge_keys": ["baz"]},
            "SELECT * FROM foo.baz WHERE id = 0",
            [{"bar": {"foo": 2}, "baz": {"foo": 1}, "id": 0}],
            id="merge keys missing key",
        ),
    ],
)
@pytest.mark.usefixtures("setup_tables", "insert_data")
async def test_update_one(aengine, engine, setup_fn, params, expected_query, expected):
    from tracktolib.pg import update_one

    if setup_fn:
        setup_fn(engine)

    await update_one(aengine, **params)
    db_data = fetch_all(engine, expected_query)
    assert db_data == expected


@pytest.mark.usefixtures("setup_tables", "insert_data")
async def test_update_one_keys(aengine, engine):
    from tracktolib.pg import update_one

    await update_one(aengine, "foo.foo", {"foo": 2, "id": 1}, keys=["id"])


@pytest.mark.parametrize(
    "param_args,params_kwargs,expected",
    [
        ([{"foo": 1}, 1], {"returning": "foo", "start_from": 1, "where": "WHERE id =$1"}, 1),
        ([{"foo": 2, "id": 1}], {"returning": "foo", "keys": ["id"]}, 2),
        ([{"foo": 2, "id": 1}], {"returning": "foo", "keys": ["id"]}, 2),
        ([{"foo": 2, "id": 1}], {"return_keys": True, "keys": ["id"]}, {"foo": 2}),
    ],
)
@pytest.mark.usefixtures("setup_tables", "insert_data")
async def test_update_one_returning(aengine, engine, param_args, params_kwargs, expected):
    from tracktolib.pg import update_returning

    value = await update_returning(aengine, "foo.foo", *param_args, **params_kwargs)
    assert value if not isinstance(value, asyncpg.Record) else dict(value) == expected


async def check_update_one_types(aengine):
    """This won't be called, only used to check types"""
    from tracktolib.pg import update_returning

    await update_returning(aengine, "foo.foo", {"foo": 1}, returning="foo")
    await update_returning(aengine, "foo.foo", {"foo": 1}, return_keys=True)


async def test_safe_pg(aengine):
    from tracktolib.pg import PGError, PGException, insert_one, safe_pg, safe_pg_context

    @safe_pg([PGError("bar_unique", "Another bar value exists")])
    async def insert_bar():
        await insert_one(aengine, "foo.generated", {"bar": "foo"})

    await insert_bar()
    with pytest.raises(PGException):
        await insert_bar()

    with pytest.raises(PGException):
        with safe_pg_context([PGError("bar_unique", "Another bar value exists")]):
            await insert_bar()


@pytest.mark.parametrize(
    "setup_fn,params,expected_query,expected",
    [
        pytest.param(
            None,
            {"table": "foo.foo", "items": [{"id": 1, "foo": 1}, {"id": 2, "foo": 22}], "keys": ["id"]},
            "SELECT bar, foo, id FROM foo.foo WHERE id IN (1, 2) ORDER BY id",
            [{"bar": "baz", "foo": 1, "id": 1}, {"bar": None, "foo": 22, "id": 2}],
            id="default",
        ),
        pytest.param(
            None,
            {
                "table": "foo.foo",
                "items": [
                    {"id": 1, "foo": 1},
                ],
                "keys": ["id"],
            },
            "SELECT bar, foo, id FROM foo.foo WHERE id IN (1, 2) ORDER BY id",
            [{"bar": "baz", "foo": 1, "id": 1}, {"bar": None, "foo": 20, "id": 2}],
            id="update one item",
        ),
    ],
)
@pytest.mark.usefixtures("setup_tables", "insert_data")
async def test_update_many(aengine, engine, setup_fn, params, expected_query, expected):
    from tracktolib.pg import update_many

    if setup_fn:
        setup_fn(engine)

    await update_many(aengine, **params)
    db_data = fetch_all(engine, expected_query)
    assert db_data == expected
