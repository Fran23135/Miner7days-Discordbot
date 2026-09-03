"""
borrar_rangos.py
Script standalone — NO es un cog.
Ejecútalo directamente: python borrar_rangos.py
Conecta al bot, borra todos los roles definidos en rangos_ids.json y cierra.

Nota: se borra por rol_id (rangos_ids.json), NO comparando nombres de texto.
Comparar por nombre falla si el nombre tiene espacios extra, emojis distintos,
o si fue editado — Discord además recorta espacios al inicio/final al crear
el rol, así que el nombre guardado en config puede no coincidir nunca con el
nombre real del rol. El ID es la única fuente confiable.
"""

import asyncio
import sys
import os
import discord
from pin import TOKEN
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sql"))
from sql.rangos_config import DEFINICIONES, cargar_ids, get_ids_cargados


async def main():
    intents = discord.Intents.default()
    client  = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        guild = client.guilds[0]

        cargar_ids()                 # refresca desde rangos_ids.json
        ids = get_ids_cargados()     # {nivel: rol_id}

        print(f"🔍 {len(ids)} rangos con rol_id registrado en rangos_ids.json.")

        borrados  = 0
        faltantes = 0

        for nivel, rol_id in sorted(ids.items()):
            rol = guild.get_role(rol_id)
            nombre_config = DEFINICIONES.get(nivel, "?")

            if rol is None:
                print(f"  ⚠️  Nivel {nivel} ({nombre_config}): el rol ya no existe en Discord, se omite.")
                faltantes += 1
                continue

            await rol.delete(reason="Limpieza de rangos — borrar_rangos.py")
            print(f"  🗑️  Eliminado: {rol.name}  (nivel {nivel})")
            borrados += 1

        print(f"✅ Hecho. {borrados} roles eliminados, {faltantes} ya no existían. Cerrando bot.")
        await client.close()

    await client.start(TOKEN)


asyncio.run(main())