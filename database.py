"""
Database write tool — generic SQL insertion
Supports: PostgreSQL (asyncpg), SQLite (aiosqlite), MySQL (aiomysql)
Connection string format determines driver used
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _detect_db_type(conn_str: str) -> str:
    if conn_str.startswith(("postgresql://", "postgres://")):
        return "postgresql"
    elif conn_str.startswith("sqlite"):
        return "sqlite"
    elif conn_str.startswith(("mysql://", "mariadb://")):
        return "mysql"
    return "unknown"


async def write_to_database(
    connection_string: str,
    table: str,
    data: dict[str, Any],
    record_id: str,
) -> dict:
    """
    Insert a row into a SQL database table.
    Handles column creation for new fields automatically (SQLite only).
    """
    db_type = _detect_db_type(connection_string)

    if db_type == "postgresql":
        return await _write_postgresql(connection_string, table, data, record_id)
    elif db_type == "sqlite":
        return await _write_sqlite(connection_string, table, data, record_id)
    elif db_type == "mysql":
        return await _write_mysql(connection_string, table, data, record_id)
    else:
        return {"success": False, "error": f"Unsupported database type in connection string: {connection_string[:30]}"}


async def _write_postgresql(conn_str: str, table: str, data: dict, record_id: str) -> dict:
    try:
        import asyncpg
    except ImportError:
        return {"success": False, "error": "asyncpg not installed. Run: pip install asyncpg"}

    try:
        conn = await asyncpg.connect(conn_str, timeout=10)
        try:
            # Build parameterized INSERT
            cols = list(data.keys()) + ["_datamoa_record_id"]
            vals = list(data.values()) + [record_id]
            placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
            col_list = ", ".join(f'"{c}"' for c in cols)
            sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
            await conn.execute(sql, *vals)
            return {
                "success": True,
                "destination": f"postgresql:{table}",
                "record_id": record_id,
                "written_fields": data,
            }
        finally:
            await conn.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _write_sqlite(conn_str: str, table: str, data: dict, record_id: str) -> dict:
    try:
        import aiosqlite
    except ImportError:
        # Fallback to sync sqlite3
        import sqlite3
        db_path = conn_str.replace("sqlite:///", "").replace("sqlite://", "")
        try:
            conn = sqlite3.connect(db_path)
            _ensure_sqlite_table(conn, table, data, record_id)
            cols = list(data.keys()) + ["_datamoa_record_id"]
            vals = list(data.values()) + [record_id]
            placeholders = ", ".join("?" * len(cols))
            col_list = ", ".join(f'"{c}"' for c in cols)
            conn.execute(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})', vals)
            conn.commit()
            conn.close()
            return {"success": True, "destination": f"sqlite:{table}", "record_id": record_id, "written_fields": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    db_path = conn_str.replace("sqlite:///", "").replace("sqlite://", "")
    try:
        async with aiosqlite.connect(db_path) as db:
            # Ensure table and columns exist
            await db.execute(
                f'CREATE TABLE IF NOT EXISTS "{table}" ("_datamoa_record_id" TEXT)'
            )
            # Add any missing columns
            cursor = await db.execute(f'PRAGMA table_info("{table}")')
            existing = {row[1] for row in await cursor.fetchall()}
            for col in data.keys():
                if col not in existing:
                    await db.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" TEXT')

            cols = list(data.keys()) + ["_datamoa_record_id"]
            vals = [str(v) if v is not None else "" for v in data.values()] + [record_id]
            placeholders = ", ".join("?" * len(cols))
            col_list = ", ".join(f'"{c}"' for c in cols)
            await db.execute(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})', vals)
            await db.commit()

        return {"success": True, "destination": f"sqlite:{table}", "record_id": record_id, "written_fields": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _ensure_sqlite_table(conn, table: str, data: dict, record_id: str):
    import sqlite3
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ("_datamoa_record_id" TEXT)')
    cursor = conn.execute(f'PRAGMA table_info("{table}")')
    existing = {row[1] for row in cursor.fetchall()}
    for col in data.keys():
        if col not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" TEXT')
    conn.commit()


async def _write_mysql(conn_str: str, table: str, data: dict, record_id: str) -> dict:
    try:
        import aiomysql
    except ImportError:
        return {"success": False, "error": "aiomysql not installed. Run: pip install aiomysql"}

    try:
        # Parse MySQL connection string
        match = re.match(r"mysql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)", conn_str)
        if not match:
            return {"success": False, "error": "Invalid MySQL connection string format"}
        user, password, host, port, db = match.groups()
        port = int(port) if port else 3306

        conn = await aiomysql.connect(host=host, port=port, user=user, password=password, db=db)
        try:
            async with conn.cursor() as cursor:
                cols = list(data.keys()) + ["_datamoa_record_id"]
                vals = list(data.values()) + [record_id]
                placeholders = ", ".join(["%s"] * len(cols))
                col_list = ", ".join(f"`{c}`" for c in cols)
                sql = f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders})"
                await cursor.execute(sql, vals)
            await conn.commit()
            return {"success": True, "destination": f"mysql:{table}", "record_id": record_id, "written_fields": data}
        finally:
            conn.close()
    except Exception as e:
        return {"success": False, "error": str(e)}
