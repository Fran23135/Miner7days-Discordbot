"""
crear_rangos.py
Se llama automáticamente desde on_ready.
Crea los 10 roles en el servidor si no existen y guarda sus IDs en sql/rangos_ids.json.
Seguro de ejecutar en cada arranque: si el rol ya existe por nombre, lo reutiliza.
"""

import discord
from discord.ext import commands
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sql"))
from sql.rangos_config import DEFINICIONES, NIVELES_CON_RANGO, guardar_ids, cargar_ids, get_ids_cargados

COLOR_RANGO = discord.Color.from_rgb(139, 0, 0)

# Con 10 rangos hoistamos todos: aparecen como secciones en la lista de miembros.
# Si se agregan rangos dinámicamente vía !rangosG, éstos NO se hoistearán
# automáticamente (hoist=False en el cog). Ajusta aquí si quieres cambiar eso.
def _niveles_hoist() -> set[int]:
    """Primer y último rango siempre hoistados; el resto también con 10 rangos."""
    return set(NIVELES_CON_RANGO)


async def init_rangos(bot: commands.Bot) -> None:
    """
    Llamar desde on_ready. Crea roles que falten y persiste IDs.
    Seguro en cada arranque: detecta rangos nuevos aunque el JSON ya exista.
    """
    cargar_ids()
    ids_actuales   = get_ids_cargados()
    pendientes     = [n for n in NIVELES_CON_RANGO if n not in ids_actuales]

    if not pendientes:
        print("✅ [Rangos] Todos los IDs cargados desde rangos_ids.json")
        return

    guild            = bot.guilds[0]
    roles_existentes = {r.name: r for r in guild.roles}
    niveles_hoist    = _niveles_hoist()
    creados          = 0
    reutilizados     = 0

    for nivel in pendientes:
        nombre = DEFINICIONES[nivel]
        if nombre in roles_existentes:
            ids_actuales[nivel] = roles_existentes[nombre].id
            reutilizados += 1
        else:
            nuevo_rol = await guild.create_role(
                name=nombre,
                color=COLOR_RANGO,
                permissions=discord.Permissions.none(),
                hoist=(nivel in niveles_hoist),
                mentionable=False,
                reason=f"Rol de rango automático — nivel {nivel}",
            )
            ids_actuales[nivel] = nuevo_rol.id
            creados += 1

    guardar_ids(ids_actuales)
    print(f"✅ [Rangos] {creados} creados, {reutilizados} reutilizados → rangos_ids.json actualizado")


class CrearRangos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(CrearRangos(bot))