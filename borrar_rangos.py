"""
borrar_rangos.py
Script standalone — NO es un cog.
Ejecútalo directamente: python borrar_rangos.py
Conecta al bot, borra todos los roles definidos en DEFINICIONES y cierra.
"""

import asyncio
import sys
import os
import discord
from pin import TOKEN
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sql"))
from rangos_config import DEFINICIONES

 # o cárgalo desde tu config/json igual que en main.py


async def main():
    intents = discord.Intents.default()
    client  = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        guild            = client.guilds[0]
        nombres_a_borrar = set(DEFINICIONES.values())
        roles_a_borrar   = [r for r in guild.roles if r.name in nombres_a_borrar]

        print(f"🔍 Encontrados {len(roles_a_borrar)} roles de rango. Borrando...")

        for rol in roles_a_borrar:
            await rol.delete(reason="Limpieza de rangos — borrar_rangos.py")
            print(f"  🗑️  Eliminado: {rol.name}")

        print("✅ Hecho. Cerrando bot.")
        await client.close()

    await client.start(TOKEN)


asyncio.run(main())
