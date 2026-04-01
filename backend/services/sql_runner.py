"""Secure SQLite query runner with validation, connection pooling, and LRU caching.

Enforces read-only access by rejecting non-SELECT statements,
blocking dangerous keywords, and denying system table access.
Results are cached with a thread-safe LRU eviction strategy.
A connection pool avoids per-query open/close overhead under concurrency.
"""

import asyncio
import re
import sqlite3
import threading
from collections import OrderedDict
from queue import Empty, Queue

import pandas as pd
from vanna.core.user import RequestContext
from vanna.integrations.sqlite import SqliteRunner
from vanna.tools.run_sql import RunSqlToolArgs


class _ConnectionPool:
    """Thread-safe SQLite connection pool.

    Pre-creates a fixed number of connections and hands them out on demand.
    Each connection has PRAGMA query_only = ON enforced at creation time.
    """

    def __init__(self, database_path: str, pool_size: int = 5, timeout: int = 30):
        self._database_path = database_path
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._pool_size = pool_size
        self._timeout = timeout
        for _ in range(pool_size):
            self._pool.put(self._create_connection())

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._database_path,
            timeout=self._timeout,
            check_same_thread=False,  # safe — guarded by pool queue
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn

    def acquire(self) -> sqlite3.Connection:
        """Get a connection from the pool (blocks up to ``_timeout`` seconds)."""
        try:
            return self._pool.get(timeout=self._timeout)
        except Empty:
            # Pool exhausted — create an overflow connection
            return self._create_connection()

    def release(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool (discards if pool is full)."""
        try:
            self._pool.put_nowait(conn)
        except Exception:
            conn.close()

    def close_all(self) -> None:
        """Drain and close every pooled connection."""
        while not self._pool.empty():
            try:
                self._pool.get_nowait().close()
            except Empty:
                break


class SecureSqliteRunner(SqliteRunner):
    """SQLite runner with SQL injection protection, connection pooling, and query caching.

    Extends Vanna's SqliteRunner to add security validation before
    execution, a reusable connection pool, and a thread-safe in-memory
    LRU cache for repeated queries.
    """

    FORBIDDEN_KEYWORDS = {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "EXEC",
        "EXECUTE",
        "XP_",
        "SP_",
        "GRANT",
        "REVOKE",
        "SHUTDOWN",
    }
    SYSTEM_TABLE_PATTERNS = (
        r"\bsqlite_master\b",
        r"\bsqlite_schema\b",
        r"\bsqlite_temp_master\b",
        r"\bpragma\b",
        r"\binformation_schema\b",
        r"\bpg_catalog\b",
        r"\bsys\.\b",
    )

    def __init__(
        self, database_path: str, cache_size: int = 128, pool_size: int = 5
    ) -> None:
        """Initialise with database path, LRU cache capacity, and pool size."""
        super().__init__(database_path=database_path)
        self._cache_size = cache_size
        self._query_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._cache_lock = threading.Lock()
        # Connection pool — reuses connections instead of open/close per query
        self._pool = _ConnectionPool(
            database_path=database_path, pool_size=pool_size
        )

    def validate_sql(self, sql: str) -> str:
        """Validate and sanitise SQL, returning the cleaned query or raising ValueError."""
        cleaned_sql = sql.strip().replace("```sql", "").replace("```", "").strip()
        if not cleaned_sql:
            raise ValueError(
                "Invalid SQL generated. Please try rephrasing your question."
            )

        normalized_sql = cleaned_sql.upper()
        if not re.match(r"^\s*SELECT\b", normalized_sql):
            raise ValueError("Only SELECT queries are allowed.")

        for keyword in self.FORBIDDEN_KEYWORDS:
            if keyword in normalized_sql:
                raise ValueError(
                    f"Query blocked for safety. Forbidden keyword detected: {keyword}."
                )

        for pattern in self.SYSTEM_TABLE_PATTERNS:
            if re.search(pattern, cleaned_sql, re.IGNORECASE):
                raise ValueError(
                    "Query blocked for safety. Access to system tables is not allowed."
                )

        return cleaned_sql

    async def run_sql(
        self, args: RunSqlToolArgs, context: RequestContext | None = None
    ) -> pd.DataFrame:
        """Execute a validated SELECT query and return results as a DataFrame.

        Uses a connection pool to avoid per-query overhead and offloads
        blocking SQLite I/O to a thread via asyncio.to_thread().
        """
        validated_sql = self.validate_sql(args.sql)

        # Thread-safe cache lookup
        with self._cache_lock:
            cached = self._query_cache.get(validated_sql)
            if cached is not None:
                self._query_cache.move_to_end(validated_sql)
                return cached.copy(deep=True)

        # Offload blocking SQLite I/O to a worker thread
        result = await asyncio.to_thread(self._execute_sync, validated_sql)

        # Thread-safe cache insert
        with self._cache_lock:
            self._query_cache[validated_sql] = result.copy(deep=True)
            if len(self._query_cache) > self._cache_size:
                self._query_cache.popitem(last=False)

        return result

    def _execute_sync(self, sql: str) -> pd.DataFrame:
        """Run the query synchronously using a pooled connection."""
        conn = self._pool.acquire()
        try:
            rows = conn.execute(sql).fetchall()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([dict(row) for row in rows])
        except sqlite3.Error as exc:
            raise ValueError(f"Database query failed: {str(exc)}") from exc
        finally:
            self._pool.release(conn)
