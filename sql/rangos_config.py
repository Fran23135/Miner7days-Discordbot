"""
sql/rangos_config.py
Define los 10 rangos base del sistema (nivel 1–300).
Los nombres y niveles se persisten en rangos_definiciones.json (editable en caliente).
Los IDs de Discord se cargan del archivo rangos_ids.json que genera crear_rangos.py.
"""

import json
import os

# ── Rutas ─────────────────────────────────────────────────────────────────────
_DIR          = os.path.dirname(os.path.abspath(__file__))
_IDS_PATH     = os.path.join(_DIR, "rangos_ids.json")
_DEFS_PATH    = os.path.join(_DIR, "rangos_definiciones.json")

# ── Definiciones base (fallback si no existe rangos_definiciones.json) ────────
_DEFINICIONES_DEFAULT: dict[int, str] = {
    1:   "🔰 Miembro",
    5:   "⛏️ Seguidor",
    10:  "🧱 Aprendiz",
    20:  "💫 Calvo",
    30:  "🧟 Zombie",
    60:  "🔩 Master ",
    90:  "🔧 Pinchos",
    120: "⚡ Looter",
    150: "🔥 Tryhard",
    180: "💀 Veterano",
    210: "🌑 Wil",
    250: "💎 Miner",
    300: "⭐ Legendary",
}

# ── Objetos vivos — se mutan en sitio para que los imports externos sean válidos
DEFINICIONES: dict[int, str]  = {}
NIVELES_CON_RANGO: list[int]  = []
_rangos_ids: dict[int, int]   = {}


# ══════════════════════════════════════════════════════════════════════════════
#  Persistencia — DEFINICIONES
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_definiciones() -> None:
    """Carga rangos_definiciones.json (o los defaults) en DEFINICIONES y NIVELES_CON_RANGO."""
    if os.path.exists(_DEFS_PATH):
        with open(_DEFS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        DEFINICIONES.clear()
        DEFINICIONES.update({int(k): v for k, v in raw.items()})
    else:
        DEFINICIONES.clear()
        DEFINICIONES.update(_DEFINICIONES_DEFAULT)
        _guardar_definiciones()          # crea el archivo por primera vez
    NIVELES_CON_RANGO.clear()
    NIVELES_CON_RANGO.extend(sorted(DEFINICIONES.keys()))


def _guardar_definiciones() -> None:
    with open(_DEFS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {str(k): v for k, v in sorted(DEFINICIONES.items())},
            f, indent=2, ensure_ascii=False,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Persistencia — IDs de Discord
# ══════════════════════════════════════════════════════════════════════════════

def cargar_ids() -> bool:
    """Carga rangos_ids.json. Devuelve True si OK, False si no existe aún."""
    if not os.path.exists(_IDS_PATH):
        return False
    with open(_IDS_PATH, "r") as f:
        raw = json.load(f)
    _rangos_ids.clear()
    _rangos_ids.update({int(k): int(v) for k, v in raw.items()})
    return True


def guardar_ids(ids: dict[int, int]) -> None:
    """Guarda nivel→rol_id y sincroniza _rangos_ids en memoria."""
    _rangos_ids.clear()
    _rangos_ids.update(ids)
    with open(_IDS_PATH, "w") as f:
        json.dump({str(k): v for k, v in sorted(ids.items())}, f, indent=2)


def get_ids_cargados() -> dict[int, int]:
    """Devuelve una copia del mapa nivel→rol_id actualmente en memoria."""
    return dict(_rangos_ids)


# ══════════════════════════════════════════════════════════════════════════════
#  CRUD de rangos (modifican DEFINICIONES, NIVELES_CON_RANGO y el JSON)
# ══════════════════════════════════════════════════════════════════════════════

def agregar_rango(nivel: int, nombre: str) -> str | None:
    """
    Agrega un nuevo rango.
    Devuelve None si OK, o un mensaje de error string si falla.
    ⚠️ No crea el rol de Discord — eso lo hace el cog.
    """
    if not 1 <= nivel <= 300:
        return "El nivel debe estar entre 1 y 300."
    if nivel in DEFINICIONES:
        return f"Ya existe un rango en el nivel **{nivel}** ({DEFINICIONES[nivel]})."
    DEFINICIONES[nivel] = nombre
    NIVELES_CON_RANGO.clear()
    NIVELES_CON_RANGO.extend(sorted(DEFINICIONES.keys()))
    _guardar_definiciones()
    return None


def editar_nombre_rango(nivel: int, nombre: str) -> str | None:
    """
    Cambia el nombre de un rango existente.
    Devuelve None si OK, o mensaje de error.
    ⚠️ El nombre del rol de Discord se actualiza desde el cog.
    """
    if nivel not in DEFINICIONES:
        return f"No existe ningún rango en el nivel **{nivel}**."
    DEFINICIONES[nivel] = nombre
    _guardar_definiciones()
    return None


def eliminar_rango(nivel: int) -> str | None:
    """
    Elimina un rango de DEFINICIONES, NIVELES_CON_RANGO y rangos_ids.json.
    Devuelve None si OK, o mensaje de error.
    ⚠️ El rol de Discord se elimina desde el cog antes de llamar aquí.
    """
    if nivel not in DEFINICIONES:
        return f"No existe ningún rango en el nivel **{nivel}**."
    del DEFINICIONES[nivel]
    NIVELES_CON_RANGO.clear()
    NIVELES_CON_RANGO.extend(sorted(DEFINICIONES.keys()))
    _guardar_definiciones()
    if nivel in _rangos_ids:
        del _rangos_ids[nivel]
        guardar_ids(dict(_rangos_ids))
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers de consulta
# ══════════════════════════════════════════════════════════════════════════════

def get_rango_actual(nivel: int) -> tuple[int, str, int] | None:
    """(nivel_rango, nombre, rol_id) del rango más alto desbloqueado. None si ninguno."""
    resultado = None
    for n in NIVELES_CON_RANGO:
        if nivel >= n and n in _rangos_ids:
            resultado = (n, DEFINICIONES[n], _rangos_ids[n])
        elif nivel < n:
            break
    return resultado


def get_todos_desbloqueados(nivel: int) -> list[tuple[int, str, int]]:
    """Lista completa de (nivel_rango, nombre, rol_id) desbloqueados."""
    return [
        (n, DEFINICIONES[n], _rangos_ids[n])
        for n in NIVELES_CON_RANGO
        if nivel >= n and n in _rangos_ids
    ]


def ids_todos_rangos() -> set[int]:
    """IDs de todos los roles de rango. Para quitar el actual al reasignar."""
    return set(_rangos_ids.values())


# ── Inicialización al importar ─────────────────────────────────────────────────
_cargar_definiciones()