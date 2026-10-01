"""Application-level read-only facade, NOT a replacement for DB privileges/RLS.

Only SELECT builders can be constructed. Mutation, RPC, auth, storage and raw
client access are deliberately not exposed. Explicit SQL read-only credentials
remain a deployment gate; the underlying SDK still uses the configured key.
"""
from app.core.recovery import block_legacy_write

_FILTERS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike",
                     "is_", "in_", "contains", "contained_by", "overlaps",
                     "match", "filter", "or_", "order", "limit", "range",
                     "single", "maybe_single"})


class ReadOnlyQuery:
    def __init__(self, query):
        self._query = query

    def execute(self):
        return self._query.execute()

    def __getattr__(self, name):
        if name == "not_":
            return ReadOnlyQuery(self._query.not_)
        if name not in _FILTERS:
            block_legacy_write(f"database query operation {name}")

        def apply_filter(*args, **kwargs):
            return ReadOnlyQuery(getattr(self._query, name)(*args, **kwargs))
        return apply_filter


class ReadOnlyTable:
    def __init__(self, client, name: str):
        self._client = client
        self._name = name

    def select(self, *args, **kwargs):
        return ReadOnlyQuery(self._client.table(self._name).select(*args, **kwargs))

    def __getattr__(self, name):
        block_legacy_write(f"database table operation {name}")


class ReadOnlySupabase:
    def __init__(self, client):
        self._client = client

    def table(self, name: str):
        return ReadOnlyTable(self._client, name)

    def __getattr__(self, name):
        block_legacy_write(f"database client operation {name}")
