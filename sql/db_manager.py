"""
sql/db_manager.py
Gestión SQLite del sistema de niveles.
El archivo niveles.db se crea solo en esta carpeta al arrancar.
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "niveles.db")
#DB_PATH = os.path.join("/data", "niveles.db")

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                discord_id   TEXT    PRIMARY KEY,
                username     TEXT    NOT NULL,
                nivel        INTEGER NOT NULL DEFAULT 1,
                xp           INTEGER NOT NULL DEFAULT 0,
                xp_total     INTEGER NOT NULL DEFAULT 0,
                last_xp      REAL    NOT NULL DEFAULT 0,
                rol_elegido  INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()
    print("✅ [Niveles] Base de datos lista.")


async def get_usuario(discord_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM usuarios WHERE discord_id = ?", (discord_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_usuario(discord_id: str, username: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO usuarios (discord_id, username)
            VALUES (?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET username = excluded.username
            """,
            (discord_id, username)
        )
        await db.commit()


async def actualizar_xp(
    discord_id: str,
    xp: int,
    nivel: int,
    xp_total: int,
    last_xp: float
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE usuarios
            SET xp = ?, nivel = ?, xp_total = ?, last_xp = ?
            WHERE discord_id = ?
            """,
            (xp, nivel, xp_total, last_xp, discord_id)
        )
        await db.commit()


async def set_nivel_directo(discord_id: str, nivel: int, xp: int = 0) -> None:
    """Fuerza nivel y xp directamente. Usado por dev mode."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE usuarios SET nivel = ?, xp = ? WHERE discord_id = ?",
            (nivel, xp, discord_id)
        )
        await db.commit()


async def set_rol_elegido(discord_id: str, valor: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE usuarios SET rol_elegido = ? WHERE discord_id = ?",
            (valor, discord_id)
        )
        await db.commit()


async def reset_usuario(discord_id: str) -> None:
    """Resetea nivel a 1 y xp a 0."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE usuarios SET nivel = 1, xp = 0, xp_total = 0, rol_elegido = 0 WHERE discord_id = ?",
            (discord_id,)
        )
        await db.commit()


async def top_usuarios(limite: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM usuarios ORDER BY xp_total DESC LIMIT ?", (limite,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_usuarios() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM usuarios") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def todos_usuarios(offset: int = 0, limite: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM usuarios ORDER BY xp_total DESC LIMIT ? OFFSET ?",
            (limite, offset)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def buscar_usuario_nombre(termino: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM usuarios WHERE username LIKE ? LIMIT 5",
            (f"%{termino}%",)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def eliminar_usuario(discord_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM usuarios WHERE discord_id = ?", (discord_id,))
        await db.commit()