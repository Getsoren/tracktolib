from typing import Iterable, LiteralString, cast


def get_tmp_table_query(
    schema: LiteralString,
    table: LiteralString,
    columns: Iterable[LiteralString] | None = None,
    on_conflict: LiteralString = "ON CONFLICT DO NOTHING",
):
    tmp_table_name = f"{schema}_{table}_tmp"
    create_tmp_table_query = f"""
    CREATE TEMP TABLE {tmp_table_name}
    (LIKE {schema}.{table} INCLUDING DEFAULTS)
    ON COMMIT DROP;
    """

    if columns:
        _columns = ",".join(columns)
        insert_query = f"""
            INSERT INTO {schema}.{table} as t({_columns})
            SELECT {_columns}
            FROM {tmp_table_name}
            {on_conflict};
        """
    else:
        insert_query = f"""
            INSERT INTO {schema}.{table}
            SELECT *
            FROM {tmp_table_name}
            {on_conflict};
        """
    return tmp_table_name, create_tmp_table_query, insert_query


def get_conflict_query(
    columns: Iterable[str],
    update_columns: Iterable[str] | None = None,
    ignore_columns: Iterable[str] | None = None,
    constraint: str | None = None,
    on_conflict: str | None = None,
    where: str | None = None,
    merge_columns: Iterable[str] | None = None,
    update_where: str | None = None,
) -> LiteralString:
    if on_conflict:
        return cast(LiteralString, on_conflict)

    if constraint:
        query = f"ON CONFLICT ON CONSTRAINT {constraint}"
    elif update_columns:
        update_columns_str = ", ".join(sorted(update_columns))
        query = f"ON CONFLICT ({update_columns_str})"
        if where:
            query += f" WHERE {where}"
    else:
        raise NotImplementedError("update_keys or constraint must be set")

    _update_columns = update_columns or []
    _ignore_columns = ignore_columns or []
    _merge_columns = merge_columns or []

    if set(_merge_columns) & set(_update_columns):
        raise ValueError("Duplicate keys found between merge and update")
    if set(_merge_columns) & set(_ignore_columns):
        raise ValueError("Merge column cannot be ignored")

    _ignore_columns = [*_update_columns, *_ignore_columns, *_merge_columns]
    fields = ", ".join(f"{x} = COALESCE(EXCLUDED.{x}, t.{x})" for x in columns if x not in _ignore_columns)
    if merge_columns:
        fields = fields + ", " if fields else fields
        fields += ", ".join(f"{x} = COALESCE(t.{x}, JSONB_BUILD_OBJECT()) || EXCLUDED.{x}" for x in merge_columns)
    if not fields:
        raise ValueError("No fields set")

    query = f"{query} DO UPDATE SET {fields}"
    if update_where:
        query += f" WHERE {update_where}"
    return cast(LiteralString, query)
