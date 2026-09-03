"""
crear_rangos.py
Se llama automáticamente desde on_ready.
Crea los roles en el servidor si no existen y guarda sus IDs en sql/rangos_ids.json.
Seguro de ejecutar en cada arranque: si el rol ya existe por nombre, lo reutiliza.
"""

import discord
from discord.ext import commands
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sql"))
from sql.rangos_config import (
    DEFINICIONES,
    NIVELES_CON_RANGO,
    guardar_ids,
    cargar_ids,
    get_ids_cargados,
    eliminar_rango,
    editar_nombre_rango,
)

COLOR_RANGO = discord.Color.from_rgb(139, 0, 0)

# Con 10 rangos hoistamos todos: aparecen como secciones en la lista de miembros.
# Si se agregan rangos dinámicamente vía !rangosG, éstos NO se hoistearán
# automáticamente (hoist=False en el cog). Ajusta aquí si quieres cambiar eso.
def _niveles_hoist() -> set[int]:
    """Primer y último rango siempre hoistados; el resto también con 10 rangos."""
    return set(NIVELES_CON_RANGO)


def _reconciliar_con_discord(guild: discord.Guild) -> tuple[list[int], list[int]]:
    """
    rangos_ids.json / rangos_definiciones.json son la fuente de verdad EN DISCO,
    pero pueden quedar desincronizados con el estado real de Discord si el bot
    se cayó a mitad de una edición/eliminación hecha desde !rangosG (o si
    alguien tocó un rol manualmente). Esto repara ambos casos, comparando cada
    rango con rol asignado contra el rol real:

      - Si el rol ya no existe en el servidor → se elimina el rango del JSON.
      - Si el rol existe pero su nombre no coincide con el JSON → se actualiza
        el JSON para reflejar el nombre real del rol.

    Esto NO reinicializa nada ni toca rangos sin rol_id — nunca "resetea" a los
    defaults; eso solo pasa si el archivo de definiciones no existe en disco
    (ver rangos_config._cargar_definiciones), comportamiento que no se toca aquí.

    Devuelve (niveles_eliminados, niveles_renombrados).
    """
    ids = get_ids_cargados()
    eliminados   = []
    renombrados  = []

    for nivel, rol_id in list(ids.items()):
        rol = guild.get_role(rol_id)

        if rol is None:
            eliminar_rango(nivel)
            eliminados.append(nivel)
            continue

        nombre_json = DEFINICIONES.get(nivel)
        if nombre_json is not None and nombre_json.strip() != rol.name.strip():
            editar_nombre_rango(nivel, rol.name)
            renombrados.append(nivel)

    return eliminados, renombrados


async def init_rangos(bot: commands.Bot) -> None:
    """
    Llamar desde on_ready. Primero reconcilia los JSON contra el estado real
    de Discord (por si el bot se cayó a mitad de una edición/eliminación), y
    luego crea los roles que aún falten y persiste sus IDs.

    El ID de cada rango se guarda INMEDIATAMENTE después de crear/reutilizar
    ese rol concreto (no todo junto al final). Así, si algo interrumpe el
    proceso a mitad de camino (reconexión, rate limit, error puntual), no se
    pierde el progreso de los rangos ya procesados y no quedan huecos.

    Los nombres se comparan ya recortados (.strip()) porque Discord recorta
    espacios al inicio/final del nombre de un rol al crearlo — comparar sin
    recortar puede hacer que un rango ya creado no se reconozca como
    existente y se termine creando un duplicado.
    """
    cargar_ids()
    guild = bot.guilds[0]

    eliminados, renombrados = _reconciliar_con_discord(guild)
    if eliminados or renombrados:
        print(
            f"🔧 [Rangos] Sincronizado al arrancar: "
            f"{len(eliminados)} rango(s) eliminado(s) {eliminados}, "
            f"{len(renombrados)} renombrado(s) {renombrados}."
        )

    ids_actuales = get_ids_cargados()
    pendientes   = [n for n in NIVELES_CON_RANGO if n not in ids_actuales]

    if not pendientes:
        print("✅ [Rangos] Todos los IDs cargados y sincronizados desde rangos_ids.json")
        return

    roles_existentes = {r.name.strip(): r for r in guild.roles}
    niveles_hoist    = _niveles_hoist()
    creados          = 0
    reutilizados     = 0
    fallidos         = []

    for nivel in pendientes:
        nombre = DEFINICIONES[nivel].strip()
        rol_existente = roles_existentes.get(nombre)

        if rol_existente:
            ids_actuales[nivel] = rol_existente.id
            reutilizados += 1
        else:
            try:
                nuevo_rol = await guild.create_role(
                    name=nombre,
                    color=COLOR_RANGO,
                    permissions=discord.Permissions.none(),
                    hoist=(nivel in niveles_hoist),
                    mentionable=False,
                    reason=f"Rol de rango automático — nivel {nivel}",
                )
            except discord.HTTPException as e:
                # Un fallo puntual en este rango NO debe abortar los demás.
                print(f"❌ [Rangos] No se pudo crear el rol del nivel {nivel} ('{nombre}'): {e}")
                fallidos.append(nivel)
                continue

            ids_actuales[nivel] = nuevo_rol.id
            roles_existentes[nombre] = nuevo_rol   # evita duplicar si el nombre se repite en otro nivel
            creados += 1

        # Guardado incremental: si algo truena más adelante en el bucle,
        # lo ya procesado hasta aquí no se pierde.
        guardar_ids(ids_actuales)

    resumen = f"✅ [Rangos] {creados} creados, {reutilizados} reutilizados → rangos_ids.json actualizado"
    if fallidos:
        resumen += f" — ⚠️ fallaron los niveles {fallidos}, se reintentarán en el próximo arranque"
    print(resumen)


class CrearRangos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(CrearRangos(bot))