import discord
from discord.ui import Button, View
from discord.ext import commands
from discord.ext import tasks
import requests
import difflib
import status7d
import threading
import asyncio
import web_avisos
import random
import asyncio
import os
import pin
import interact
from footer_m import messages
from datetime import datetime
from status7d import nekos_cache, twitch_monitor
import time
from datetime import datetime
import re as _re
from config import CANALES, ROLES, DESARROLLADOR_ID
import json as _json
import sys, os
intents = discord.Intents.default()
intents.members = True
intents.message_content = True


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql"))
import sql.db_manager as _db_niveles
from crear_rangos import init_rangos as _init_rangos
from niveles import init_miembros as _init_miembros
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ── Prefijo secundario ────────────────────────────────────────────────
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cache", "config.json")

def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}

def _save_config(data: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)

def _get_secondary_prefix() -> str | None:
    return _load_config().get("secondary_prefix")

async def get_prefix(bot, message):
    prefixes = ["!"]
    secondary = _get_secondary_prefix()
    if secondary:
        prefixes.append(secondary + " ")  # "miner miner"
        prefixes.append(secondary)        # "minerminer"
    return prefixes


bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.remove_command('help')

# Registrar comandos de interacciones
for tag, data in interact.INTERACCIONES.items():
    cmd_es, frase_con, frase_pasado, label, emoji, msg_bot, frase_sin = data[:7]
    frase_pasado_solo = data[7] if len(data) > 7 else None
    cmd_func = interact.crear_comando_interaccion(tag, cmd_es, frase_con, frase_pasado, label, emoji, msg_bot, frase_sin, frase_pasado_solo)
    bot.command(name=cmd_es)(cmd_func)
    if tag != cmd_es:
        bot.command(name=tag)(cmd_func)
for tag, (cmd_es, frase, emoji, label_boton, frase_pasado) in interact.INTERACCIONES_SOLO.items():
    cmd_func = interact.crear_comando_solo(tag, cmd_es, frase, emoji, label_boton, frase_pasado)
    bot.command(name=cmd_es)(cmd_func)
    if tag != cmd_es:
        bot.command(name=tag)(cmd_func)   

# Configuración Flask

# ── Cargar lista de streamers desde JSON ──────────────────────────
def _cargar_streamers() -> list[dict]:
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cache/streamers.json")
    try:
        with open(_path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception as e:
        print(f"⚠️ No se pudo cargar streamers.json: {e}")
        return []

STREAMERS = _cargar_streamers()
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.strip()

    # ── Solo saluda si el @mención es EXPLÍCITO en el texto y NO es un reply ──
    is_reply = message.reference is not None
    bot_mention      = f'<@{bot.user.id}>'
    bot_mention_nick = f'<@!{bot.user.id}>'
    only_mention = content == bot_mention or content == bot_mention_nick
    explicitly_mentioned = only_mention and not is_reply

    if explicitly_mentioned:
        secondary = _get_secondary_prefix()
        embed = discord.Embed(
            title="👋 ¡Hola!",
            description=(
                f"Hola {message.author.mention}, soy **Yuri Koteawa**, más conocida como **Miner** 🤖\n\n"
                f"Mi prefijo principal es `!`"
                + (f"\nY también puedes usar `{secondary}`" if secondary else "")
            ),
            color=0x8B0000
        )
        embed.set_footer(text="Usa !help para ver todos los comandos disponibles")
        await message.channel.send(embed=embed)
        return

    # Procesar comandos (replies con !comando apuntan al autor del mensaje citado)
    await bot.process_commands(message)

@bot.command(name="setprefix")
async def setprefix(ctx, nuevo_prefijo: str = None):
    """Establece un prefijo secundario. Solo Mod/Admin/Owner."""
    es_owner = ctx.guild and ctx.author.id == ctx.guild.owner_id
    es_mod   = _tiene_permiso_stream(ctx.author)
    if not es_owner and not es_mod:
        return

    if not nuevo_prefijo:
        embed = discord.Embed(
            title="❌ Falta el prefijo",
            description="Debes indicar el prefijo que quieres usar.\nEjemplo: `!setprefix miner`",
            color=0xFF4444
        )
        await ctx.send(embed=embed)
        return

    if len(nuevo_prefijo) > 10:
        embed = discord.Embed(
            title="❌ Prefijo demasiado largo",
            description="El prefijo no puede superar los **10 caracteres**.",
            color=0xFF4444
        )
        await ctx.send(embed=embed)
        return

    config = _load_config()
    config["secondary_prefix"] = nuevo_prefijo
    _save_config(config)

    embed = discord.Embed(
        title="✅ Prefijo secundario actualizado",
        description=(
            f"A partir de ahora el bot responde a **dos** prefijos:\n\n"
            f"🔹 Prefijo principal → `!`\n"
            f"🔸 Prefijo secundario → `{nuevo_prefijo}`\n\n"
            f"Ejemplo: `{nuevo_prefijo}stats` o `{nuevo_prefijo} stats` funciona igual que `!miner`"
        ),
        color=0x8B0000
    )
    embed.set_footer(text=f"Cambiado por {ctx.author.display_name}")
    await ctx.send(embed=embed)    
_footer_pool: list = []
def get_footer():
    
    global _footer_pool
    if not _footer_pool:
        _footer_pool = messages[:]
        random.shuffle(_footer_pool)
    return _footer_pool.pop()
@bot.command()
async def web(ctx):
    """Muestra el enlace a las estadísticas del servidor"""
    embed = discord.Embed(
        title="📊 **ENLACE A LAS STATS EN TIEMPO REAL**",
        description=f"Hey! {ctx.author.mention}\n Da Click 👉 https://kasiri.github.io/7days-stats/",
        color=0x8B0000
    )
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Obtener el directorio actual de forma segura
    
    # Luego construyes la ruta de forma segura (se encarga de las barras / o \ según el OS)
    image_path = os.path.join(BASE_DIR, "images", "Hype.png")
    print(str(image_path))
    file = discord.File(str(image_path), filename="Hype.png")
    embed.set_image(url="attachment://Hype.png")
    await ctx.send(file=file, embed=embed)  
@bot.command()
async def status(ctx):
    """Verifica el estado del servidor"""
    obtaining_msg = await ctx.send("🌐 **Comprobando estado del servidor...**")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    server_up = status7d.check_status()
    
    await obtaining_msg.delete()
    
    if server_up:
        embed = discord.Embed(
            title="✅ **SERVIDOR ACTIVO**",
            description=f"Hey! {ctx.author.mention}",
            color=0x00FF00  # Verde
        )
        embed.add_field(
        name="El servidor está en línea y respondiendo. ",
        value="",
        inline=True
        )
        image_path = os.path.join(BASE_DIR, "images", "Live.jpg")
        file = discord.File(image_path, filename="Live.jpg")
        embed.set_image(url="attachment://Live.jpg")
        embed.set_footer(text="Usa !players para ver jugadores conectados")
    else:
        embed = discord.Embed(
            title="❌ **SERVIDOR CAÍDO**",
            description=f"Hey! {ctx.author.mention}",
            color=0xFF0000  # Rojo
        )
        
        embed.add_field(
        name="El servidor no responde o está fuera de línea.",
        value="",
        inline=True
        )
        image_path = os.path.join(BASE_DIR, "images", "Caido 2.png")
        file = discord.File(image_path, filename="Caido 2.png")
        embed.set_image(url="attachment://Caido 2.png")
        embed.set_footer(text="7 days to Die • Intenta nuevamente en unos minutos")
    
    await ctx.send(file=file, embed=embed)
@bot.command()
async def stats(ctx):
    """Muestra las estadísticas del servidor"""
    msg_temp = await ctx.send("Obteniendo información del servidor...")
    try:
        # Obtener datos del servidor
        data = status7d.get_stats()
        if not data:
            await msg_temp.delete()
            await ctx.send("❌ No se pudo obtener información del servidor.")
            return
        # Extraer información del servidor (no de jugadores)
        # Suponiendo que estos datos están en el mismo nivel que "players"
        day = data.get("day", "N/A")
        time = data.get("time", "N/A")
        nexthordeDay = data.get("nextHordeDay", "N/A")
        nexthordeIn = data.get("nextHordeIn", "N/A")
        # Crear embed estilizado
        embed = discord.Embed(
            title="🌍 **INFORMACIÓN DEL SERVIDOR**",
            description=f"Hey! {ctx.author.mention}",
            color=0x8B0000
        )
        
        # Agregar campos con emotes
        embed.add_field(
            name="📅 **Día Actual**",
            value=f"```\nDía {day}\n```",
            inline=True
        )
        
        embed.add_field(
            name="🕐 **Hora Actual**",
            value=f"```\n{time}\n```",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ **Próxima Horda**",
            value=f"```\nDía {nexthordeDay}\n```",
            inline=True
        )
        
        embed.add_field(
            name="⏳ **Falta**",
            value=f"```\n{nexthordeIn}\n```",
            inline=True
        )
        await msg_temp.delete()
        if data.get("_cached"):
            ts = data.get("_cached_at")
            if ts:
                
                fecha = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")
                embed.set_footer(text=f"⚠️ Datos cacheados del {fecha} (API no disponible)")
        else:
             embed.set_footer(text=f"7 Days To Die • Datos en tiempo real • {get_footer()} ")        
   
        await ctx.send(embed=embed)
        
    except Exception as e:
        await msg_temp.delete()
        await ctx.send("❌ Ocurrió un error al obtener las estadísticas.")
        print(f"❌ Error al obtener datos del servidor: {str(e)}")

@bot.command()
async def player(ctx, *,player_name: str = None):
    """Muestra las estadísticas de un jugador específico"""
    
    if not player_name:
        await ctx.send(f"❌ Hey {ctx.author.mention} Debes especificar el nombre de un jugador. Ejemplo: `!player Fran23135`")
        return
    obtaining_msg = await ctx.send(f"🔍 Buscando estadísticas de **{player_name.strip()}**...")
    
    try:
        # Obtener el ranking
        ranking_data = status7d.get_ranking()
        player_stats = None
        exact_name = None
        # Normalizar el nombre de búsqueda (quitar espacios extra, etc.)
        search_name = player_name.strip()
        
        # 1. Primero buscar coincidencia exacta (case-sensitive)
        player_stats = ranking_data.get(search_name)
        found_key = search_name if player_stats else None
        
        # 2. Si no, buscar coincidencia exacta case-insensitive
        
        if player_name in ranking_data:
         player_stats = ranking_data[player_name]
         exact_name = player_name
        else:
          # Buscar coincidencia case-insensitive
         for key, stats in ranking_data.items():
            if key.lower() == player_name.lower():
                player_stats = stats
                exact_name = key  # Guardamos el nombre CORRECTO del ranking
                break
        
        # 3. Si aún no se encuentra, usar búsqueda difusa
        if not player_stats:
            # Obtener lista de nombres disponibles
            player_names = list(ranking_data.keys())
            
            # Buscar coincidencias similares (umbral 80%)
            matches = difflib.get_close_matches(
                search_name, 
                player_names, 
                n=1, 
                cutoff=0.5
            )
            
            if matches:
                # Usar la mejor coincidencia
                found_key = matches[0]
                player_stats = ranking_data[found_key]
                exact_name = found_key
            else:
                await obtaining_msg.delete()
                # Sugerir nombres similares (con umbral más bajo)
                suggestions = difflib.get_close_matches(
                    search_name, 
                    player_names, 
                    n=3, 
                    cutoff=0.5
                )
                
                if suggestions:
                    suggestions_text = ", ".join(f"`{s}`" for s in suggestions)
                    await ctx.send(f"❌ No se encontró **{search_name}**. ¿Quizás quisiste decir: {suggestions_text}?")
                else:
                    await ctx.send(f"❌ No se encontró **{search_name}** en el ranking.")
                return
        
        # Extraer estadísticas
        display_name = exact_name
        level = player_stats.get("level", 0)
        zombies = player_stats.get("zombies", 0)
        deaths = player_stats.get("deaths", 0)
        score = player_stats.get("score", 0)
        zombies_per_level = zombies / level
        
        ranking_sorted = sorted(
            [(k, v) for k, v in ranking_data.items() if isinstance(v, dict)],
            key=lambda x: x[1].get("level", 0),
            reverse=True
        )
        posicion = next((i + 1 for i, (k, _) in enumerate(ranking_sorted) if k == display_name), None)

        MEDALLAS = {1: "🥇", 2: "🥈", 3: "🥉"}
        medalla = MEDALLAS.get(posicion, "👤")
        pos_texto = f"#{posicion}" if posicion else "N/A"
        
        # Crear embed estilizado
       
        
        # Agregar campos con emotes y formato
        embed = discord.Embed(
        title=f"{medalla} {display_name} ─ {pos_texto}",
        description=f"Hey! {ctx.author.mention}",
        color=0x8B0000
        )
        #embed.set_thumbnail(url=ctx.bot.user.display_avatar.url)
        embed.add_field(
            name="🎚️ **Nivel**",
            value=f"```\n{level}\n```",
            inline=True
        )
        
        embed.add_field(
            name="🧟 **Zombies Matados**",
            value=f"```\n{zombies:,}\n```",
            inline=True
        )
        
        embed.add_field(
            name="💀 **Muertes**",
            value=f"```\n{deaths}\n```",
            inline=True
        )
        
        embed.add_field(
            name="🏆 **Puntaje**",
            value=f"```\n{score:,}\n```",
            inline=True
        )
        embed.add_field(
            name="📊 Zombies / Nivel",
            value=f"```{zombies_per_level:.1f}```" if level > 0 else "```0```",
            inline=True
        )
        
        #embed.set_thumbnail(url=ctx.bot.user.display_avatar.url)
    
         
        # Agregar pie de página
        embed.set_footer(text=f"7 days to Die • {get_footer()}")
        await obtaining_msg.delete()
        await ctx.send(embed=embed)
        
    except Exception as e:
        await obtaining_msg.delete()
        print(f"❌ Error al buscar las estadísticas: {str(e)}")
@bot.command(name="staff")
async def staff(ctx):
    """Muestra el equipo de staff del servidor"""
    embed = discord.Embed(
        title="👥 **EQUIPO DE STAFF**",
        description=f"Hey! {ctx.author.mention}\nEste es el equipo que mantiene el servidor en marcha.",
        color=0x3498DB
    )

    embed.add_field(
        name="👑 Kasiri",
        value="```Owner — Administración - Mantenimiento Técnico y Web - Moderador```",
        inline=False
    )

    embed.add_field(
        name="🛡️ OQ49",
        value="```Administración — Gestión de Mods - Moderador```",
        inline=True
    )


    embed.add_field(
        name="⚙️ Fran23135",
        value="```Desarrollador del Bot - Moderador```",
        inline=True
    )
    embed.add_field(
        name="🔧 Neo (what_a_caramel)",
        value="```Moderador```",
        inline=True
    )
    embed.add_field(
        name="✌️ Wil",
        value="```Administración — Gestión de Mods - Moderador```",
        inline=True
    )
    embed.set_footer(text=f"7 Days to Die • {get_footer()}")
    await ctx.send(embed=embed)


'''
@bot.command()
async def help(ctx):
    """Muestra todos los comandos disponibles del bot"""
    embed = discord.Embed(
        title="🛠️ **COMANDOS DISPONIBLES**",
        description=f"Hey! {ctx.author.mention}\n Lista de todos los comandos del bot y cómo usarlos.",
        color=0x8B0000
    )
        
    
    # Campo para comandos de servidor
    embed.add_field(
        name="🌐 **Comandos del Servidor**",
        value=(
            "`!status` - Verifica si el servidor está activo o caído\n"
            "`!stats` - Muestra información del servidor (día, hora, próximas hordas)\n"
            "`!wipe` - Anuncia el próximo wipe del servidor\n"
            "`!mods` - Muestra los mods de el servidor\n"
            "`!players [filtro]` - Muestra jugadores conectados\n"
            "  Filtros: `nivel`, `zombies`, `muertes`, `ping`, `az`\n"
            "  Ejemplo: `!players ping`"
            
        ),
        inline=False
    )
    
    # Campo para comandos de jugadores
    embed.add_field(
        name="👤 **Comandos de Jugadores**",
        value=(
            "`!player <nombre>` - Muestra estadísticas de un jugador del ranking\n"
            "  Ejemplo: `!player Fran23135`\n"
            "  *Búsqueda flexible: acepta mayúsculas/minúsculas y nombres similares*\n"
            "`!ranking [filtro]` - Muestra el ranking global\n"
            "  Filtros: `nivel`, `zombies`, `muertes`, `az`\n"
            "  Ejemplo: `!ranking zombies`"
        ),
        inline=False
    )
    # Campo para eventos y decoración
    embed.add_field(
        name="🎪 **Eventos y Decoración**",
        value=(
            "`!events` - Muestra los eventos activos e inscríbete o sube pruebas\n"
            "`!decoracion` - Abre el panel para hacer un pedido de decoración para tu base\n"
        ),
        inline=False
    )
    
    # Campo para comandos varios
    embed.add_field(
        name="🎮 **Otros Comandos**",
        value=(
            "`!miner` - Muestra un consejo minero aleatorio y útil\n"
            "`!help` - Muestra este mensaje de ayuda\n"
            "`!creditos` - Muestra los créditos del desarrollador\n"
            "`!web` - Muestra el enlace a las estadísticas en tiempo real\n"
            "`!clips` - Muestra un clip aleatorio de 7 Days to Die del canal de Kasiri\n"
            "`!news` - Muestra las últimas actualizaciones del bot\n"
            "`!staff` - Muestra el equipo del servidor\n"
        ),
        inline=False
    )
    embed.add_field(
        name="🎭 **Interacciones**",
        value=(
            "`!interact` - Explica cómo funciona el sistema de interacciones\n"
            "`!interactlist` - Lista todos los comandos de interacción disponibles\n"
            f"  *{len(_INTERACT_CMDS)} comandos en total, con GIFs de anime*\n"
            "  Ejemplo: `!kick @what_a_caramel`\n"
            "`!battle <@usuario>` / `!pelear <@usuario>` - Reta a otro jugador a una batalla\n"
            "`!trivia` - Inicia una sesión de preguntas sobre 7 Days to Die"

        ),
        inline=False
    )
    
    # Información adicional
    embed.add_field(
        name="📌 **Notas importantes**",
        value=(
            "• Todos los datos son en tiempo real\n"
            "• El ranking se actualiza periódicamente\n"
            "• Los consejos de minería son 100% aleatorios"
        ),
        inline=False
    )
    
    # Pie de página
    embed.set_footer(text=f"Bot desarrollado para 7 Days to Die • {get_footer()}")
    
    await ctx.send(embed=embed)
'''


@bot.command()
async def players(ctx, filtro: str = None):

    FILTROS_VALIDOS = ["nivel", "zombies", "muertes", "ping", "az"]
    FILTROS_LABEL = {
        "nivel":   "por nivel",
        "zombies": "por zombies",
        "muertes": "por muertes",
        "ping":    "por ping",
        "az":      "de A a la Z"
    }

    if filtro and filtro.lower() not in FILTROS_VALIDOS:
        await ctx.send(
            f"❌ Hey! {ctx.author.mention} Filtro inválido. Usa: `nivel`, `zombies`, `muertes`, `ping`, `az`\n"
            f"Ejemplo: `!players ping`"
        )
        return

    filtro = filtro.lower() if filtro and filtro.strip() else None

    try:
        msg_temp = await ctx.send("Obteniendo Estadísticas de los Jugadores...")
        data = status7d.get_stats()
        if not data:
            await msg_temp.delete()
            await ctx.send(f"❌ Hey! {ctx.author.mention} No se pudo obtener información de jugadores.")
            return

        players = data.get("players", [])

        if not players:
            embed = discord.Embed(
                title="👥 Jugadores Conectados",
                description=f"Hey! {ctx.author.mention}\n**No hay jugadores activos.**",
                color=0x8B0000
            )
            if data.get("_cached"):
                ts = data.get("_cached_at")
                if ts:
                    fecha = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")
                    embed.set_footer(text=f"⚠️ Datos cacheados del {fecha} (API no disponible)")
            else:
                embed.set_footer(text=f"Datos en tiempo real • {get_footer()}")
            await msg_temp.delete()
            await ctx.send(embed=embed)
            return

        # ─── Ordenar según filtro ───
        if filtro == "nivel":
            players.sort(key=lambda x: x.get("level",   0), reverse=True)
        elif filtro == "zombies":
            players.sort(key=lambda x: x.get("zombies", 0), reverse=True)
        elif filtro == "muertes":
            players.sort(key=lambda x: x.get("deaths",  0), reverse=True)
        elif filtro == "ping":
            players.sort(key=lambda x: x.get("ping",    0))
        elif filtro == "az":
            players.sort(key=lambda x: x.get("name", "").lower())

        label = f" • {FILTROS_LABEL[filtro]}" if filtro else ""

        table_lines = ["```"]
        table_lines.append(f"{'JUGADOR':<15} {'LVL':<4} {'ZOMBIES':<7} {'MUERTES':<6} {'PING':<4}")
        table_lines.append("-" * 40)

        for player in players:
            name = player.get("name", "?")
            if len(name) > 14:
                name = name[:13].ljust(15)
            else:
                name = name.ljust(15)
            level   = str(player.get("level",   0)).ljust(4)
            zombies = str(player.get("zombies", 0)).ljust(7)
            deaths  = str(player.get("deaths",  0)).ljust(6)
            ping    = str(player.get("ping",    0)).ljust(4)
            table_lines.append(f"{name} {level} {zombies} {deaths} {ping}")

        table_lines.append("```")

        embed = discord.Embed(
            title="🎮 Jugadores Conectados",
            description=f"Hey! {ctx.author.mention}\n" + "\n".join(table_lines),
            color=0x8B0000
        )
        embed.add_field(name=f"👤 Jugadores: {len(players)}", value="", inline=True)

        if data.get("_cached"):
            ts = data.get("_cached_at")
            if ts:
                fecha = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")
                embed.set_footer(text=f"⚠️ Datos cacheados del {fecha} (API no disponible){label}")
        else:
            embed.set_footer(text=f"Datos en tiempo real{label} • {get_footer()}")

        await msg_temp.delete()
        await ctx.send(embed=embed)

    except Exception as e:
        await msg_temp.delete()
        print(f"❌ Error al obtener datos de los jugadores: {str(e)}")
@bot.command()
async def news(ctx):
    embed = discord.Embed(
        title="📋 CHANGELOG — Miner7days",
        description=(
            f"Hey! {ctx.author.mention}\n"
            "```fix\n"
            "  Versión 3.5 — Fixes y Mejoras\n"
            "```"
        ),
        color=0x8B0000
    )

    embed.add_field(
        name="🆕 Nuevas Funcionalidades",
        value=(
            "```diff\n"
            "+ Comando !decolist agregado para mostrar tus pedidos de decoracion Solo MD\n"
            "+ NUEVO sistema de rangos  para el servidor Para interactuar\n"
            "+ Nuevo comando !time para mostrar tu hora actual y zona horaria\n"
            "+ Nuevo comado !perfil para mostrar tu experiencia y perzonalizar tu rango, etc\n"
             
            "```"
        ),
        inline=False
    )

    embed.add_field(
        name="🐞 Corrección de Errores y Ajustes",
        value=(
            "```diff\n"
            "- Optimizaciones minimas"
            "- Correcion y ajustes en comandos\n"
            "- Se corrigo el error en el wipe que mostraba la hora incorrecta y los cambios de zona horaria\n"
            "- Se corrigio el error en trivia cuando recibias premio por perder ahora solo lo recibes una vez\n"
            "- Se corrigieron errores de descripcion en !help y !news\n"
            "- Se corrigio el sistema de avisos de stream que de repente dejaba de avisar\n"
            "- Ajustes en el sistema de pedidos de decoracion, ahora te avisa cuando se aprobo o rechazo tu pedido y avisarte."
            "- Se corigio el error que al responder al bot salia el embed de presentacion del bot\n"
            "```"
        ),
        inline=False
    )
    embed.add_field(
        name="❌ Funciones quitadas",
        value=(
            "```ansi\n"
            "[0;36mSistema de musica no puesto. - fue rechazado\n"
            "[0;36mSistema de eventos no puesto. - al dev no le gusto como quedo xD\n"
            "[0;36mSistema de ejecucion experimental para ejecutar codigo en el bot por md - Descartado solo experimental\n"
            "[0m"
            "```"
        ),
        inline=False
    )

    embed.add_field(
        name="📌 Versión",
        value="```3.5```",
        inline=True
    )

    embed.add_field(
        name="🔧 Desarrollador",
        value="```Fran23135```",
        inline=True
    )

    embed.set_footer(text=f"Bot desarrollado para 7 Days to Die • {get_footer()}")
    await ctx.send(embed=embed)
@bot.command()
async def creditos(ctx):
    embed = discord.Embed(
        title="📄 **Créditos del desarollador**",
        description=(
            f"Hey! {ctx.author.mention}\n"
            "Este bot fue desarrollado para el servidor de 7 Days to Die.\n\n"
            f"🔧 **Desarrollador**: <@{DESARROLLADOR_ID}>\n"
            "🌐 **Versión**: 2.0\n"
            "💡 **Funcionalidades**: Estadísticas en tiempo real, comandos de ayuda, ranking, consejos mineros."
        ),
        color=0x8B0000
    )

    image_path = os.path.join(BASE_DIR, "images", "Rawr.jpg")
    file = discord.File(image_path, filename="Rawr.jpg")
    #set_image = embed.set_image(url="attachment://Rawr.jpg")
    embed.set_footer(text=f"Bot desarrollado para 7 Days to Die • {get_footer()}")
    await ctx.send(file=file, embed=embed)

@bot.command()
async def miner(ctx):
    MINER_TIPS = [
    "🪵 Siempre trae madera contigo.",
    "💣 Si tiras una mina tapala con madera y Mantillo.",
    "☕ Un Cafe siempre viene bien.",
    "⚔️ Tu pico sirve de arma.",
    "🧨 Un minero siempre tira minas.",
    "👻 Ten cuidado con las gritonas...",
    "🔦 No olvides tu modificacion casco con linterna.",
    "🧰 Siempre lleva kits de reparacion.",
    "🏜️ Mina con cuidado en el desierto.",
    "🤫 Siempre mina agachado",
    "🍬 Los caramelos destruyeroca son exquisitos",
    "🧟‍♂️ Si escuchas un gruñido, corre o prepárate para pelear.",
    "⛏️ Las minas pueden ser tu mejor amigo o tu peor enemigo, úsalas sabiamente.",
    "👕 Siempre lleva puesto tu autendo de minero",
    "🥗 Comer y beber es importante tambien para un minero!",
    "🏆 Mejora al maximo **Minero del 69** para  aumentar tu daño a las herramientas de minero",
    "💎 Mejora al maximo **La veta madre** para recolectar mas recursos",
    "🪓 No olvides tus escaleras para subir o bajar por la mina",
    "🔧 La **barrena** es util para destruir todo tipo ode terreno pero el pico es mas util para minar recursos",
    "⛽ En el desierto Hay mucho **Exquisito bituminoso** Ve alla cuando puedas!!",
    "🌳 ¿Necesitas **Hierro** ? Pues en el Bosque de pino Hay mucho!!",
    "🔥 **¿Polvo de Nitrato?** En Bosque quemado hay muchas vetas!!!"
    ]

    tip_index = random.randint(0, len(MINER_TIPS) - 1)
    tip = MINER_TIPS[tip_index]
    
    """Muestra un consejo minero aleatorio"""
    # Elegir un consejo aleatorio
    #tip = random.choice(MINER_TIPS)
    
    # Crear embed
    embed = discord.Embed(
        title="⛏️ **Consejo Minero**",
        description=f"👥 Hey! {ctx.author.mention}\n*{tip}*",
        color=0x8B4513  # Color marrón (tierra)
    )
    
    # Pie de página con indicación de aleatoriedad
    embed.set_footer(text="Consejo #{} de {}".format(tip_index + 1, len(MINER_TIPS)) + f" • {get_footer()}")
    
    await ctx.send(embed=embed)

@bot.command()
async def ranking(ctx, filtro: str = None):
    """Muestra el ranking global con filtro opcional"""
    
    FILTROS_VALIDOS = ["nivel", "zombies", "muertes", "az"]
    FILTROS_LABEL = {
        "nivel":   "ordenados por nivel",
        "zombies": "ordenados por zombies",
        "muertes": "ordenados por muertes",
        "az":      "ordenados de A a la Z"
    }

    # Validar filtro
    if filtro and filtro.lower() not in FILTROS_VALIDOS:
        await ctx.send(
            f"❌ Hey! {ctx.author.mention} Filtro inválido. Usa: `nivel`, `zombies`, `muertes`, `az`\n"
            f"Ejemplo: `!ranking zombies`"
        )
        return

    filtro = filtro.lower() if filtro and filtro.strip() else "nivel"

    obtaining_msg = await ctx.send("📊 Obteniendo ranking global...")
    try:
        ranking_data = status7d.get_ranking()
        if not ranking_data:
            await obtaining_msg.delete()
            await ctx.send("❌ No se pudo obtener el ranking.")
            return

        cached = ranking_data.pop("_cached", False)
        cached_at = ranking_data.pop("_cached_at", None)
        if not ranking_data:
            await obtaining_msg.delete()
            await ctx.send("❌ No se pudo obtener el ranking en este momento.")
            return

        players_list = []
        for name, stats in ranking_data.items():
            players_list.append({
                "name":    name,
                "level":   stats.get("level", 0),
                "zombies": stats.get("zombies", 0),
                "deaths":  stats.get("deaths", 0)
            })

        # ─── Ordenar según filtro ───
        if filtro == "nivel":
            players_list.sort(key=lambda x: x["level"],   reverse=True)
        elif filtro == "zombies":
            players_list.sort(key=lambda x: x["zombies"], reverse=True)
        elif filtro == "muertes":
            players_list.sort(key=lambda x: x["deaths"],  reverse=True)
        elif filtro == "az":
            players_list.sort(key=lambda x: x["name"].lower())

        if not players_list:
            await obtaining_msg.delete()
            embed = discord.Embed(
                title="🏆 **RANKING GLOBAL**",
                description=f"Hey! {ctx.author.mention}\n No hay jugadores en el ranking.",
                color=0xFFD700
            )
            await ctx.send(embed=embed)
            return

        label = FILTROS_LABEL[filtro]

        # SI HAY 25 O MENOS: Mostrar normal
        if len(players_list) <= 25:
            table_lines = ["```"]
            table_lines.append(f"{'#':<3} {'PLAYER':<15} {'LVL':<4} {'ZOMBIES':<7} {'DEATH':<6}")
            table_lines.append("-" * 38)
            for i, player in enumerate(players_list, 1):
                rank = f" {i}." if i <= 9 else f"{i}."
                name = player["name"]
                if len(name) > 14:
                    name = name[:12].ljust(15)
                else:
                    name = name.ljust(15)
                level   = str(player["level"]).ljust(4)
                zombies = str(player["zombies"]).ljust(7)
                deaths  = str(player["deaths"]).ljust(6)
                table_lines.append(f"{rank} {name} {level} {zombies} {deaths}")
            table_lines.append("```")

            embed = discord.Embed(
                title="🏆 **RANKING GLOBAL**",
                description=f"**Hey! {ctx.author.mention}\nTotal de jugadores: {len(players_list)}** ({label})\n\n" + "\n".join(table_lines),
                color=0xFFD700
            )
            if cached:
                fecha = datetime.fromtimestamp(cached_at).strftime("%d/%m/%Y %H:%M:%S")
                embed.set_footer(text=f"⚠️ Datos cacheados del {fecha} • Total de {len(players_list)} jugadores")
            else:
                embed.set_footer(text=f"Total de {len(players_list)} jugadores • {get_footer()}")

            await obtaining_msg.delete()
            await ctx.send(embed=embed)

        # SI HAY MÁS DE 25: Paginación
        else:
            PAGE_SIZE = 25
            total_pages = (len(players_list) + PAGE_SIZE - 1) // PAGE_SIZE

            def create_embed(page_num):
                start_idx = page_num * PAGE_SIZE
                end_idx   = min(start_idx + PAGE_SIZE, len(players_list))
                page_players = players_list[start_idx:end_idx]

                table_lines = ["```"]
                table_lines.append(f"{'#':<3} {'PLAYER':<15} {'LVL':<4} {'ZOMBIES':<7} {'DEATH':<6}")
                table_lines.append("-" * 38)
                for i, player in enumerate(page_players, start=start_idx + 1):
                    rank = f" {i}." if i <= 9 else f"{i}."
                    name = player["name"]
                    if len(name) > 14:
                        name = name[:12].ljust(15)
                    else:
                        name = name.ljust(15)
                    level   = str(player["level"]).ljust(4)
                    zombies = str(player["zombies"]).ljust(7)
                    deaths  = str(player["deaths"]).ljust(6)
                    table_lines.append(f"{rank} {name} {level} {zombies} {deaths}")
                table_lines.append("```")

                embed = discord.Embed(
                    title="🏆 **RANKING GLOBAL**",
                    description=f"**Hey! {ctx.author.mention}\nPágina {page_num + 1}/{total_pages}** (Jugadores {start_idx + 1}-{end_idx} de {len(players_list)} • {label})\n\n" + "\n".join(table_lines),
                    color=0xFFD700
                )
                if cached:
                    fecha = datetime.fromtimestamp(cached_at).strftime("%d/%m/%Y %H:%M:%S")
                    embed.set_footer(text=f"⚠️ Datos cacheados del {fecha} • Total: {len(players_list)} jugadores • Reacciona con ⬅️ ➡️ para navegar")
                else:
                    embed.set_footer(text=f"Total: {len(players_list)} jugadores • Reacciona con ⬅️ ➡️ para navegar")
                return embed

            await obtaining_msg.delete()
            message = await ctx.send(embed=create_embed(0))
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")

            def check(reaction, user):
                return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

            current_page = 0
            timeout = 120

            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=timeout, check=check)
                    if str(reaction.emoji) == "➡️" and current_page < total_pages - 1:
                        current_page += 1
                    elif str(reaction.emoji) == "⬅️" and current_page > 0:
                        current_page -= 1
                    await message.edit(embed=create_embed(current_page))
                    await message.remove_reaction(reaction.emoji, user)
                except asyncio.TimeoutError:
                    try:
                        await message.clear_reactions()
                    except:
                        pass
                    break

    except Exception as e:
        await obtaining_msg.delete()
        await ctx.send(f"❌ Error al obtener el ranking: {str(e)}")
"""
@bot.command()
async def wipe(ctx):
    WIPE_FECHA = "13 de Marzo de 2026" # ← placeholder, no final
    WIPE_COUNTDOWN = "2 días, 8 horas, 48 min, 19 seg"  # ← placeholder, no final
    embed = discord.Embed(
        title="🔄 **WIPE DEL SERVIDOR**",
        description=(
            f"**Hey! {ctx.author.mention}**\n"
            "¡Se acerca el wipe! Prepárate para empezar de nuevo."
        ),
        color=0xFF4500
    )

    embed.add_field(
        name="📅 Fecha del Wipe",
        value=f"```{WIPE_FECHA}```",
        inline=False
    )

    embed.add_field(
        name="⏳ Cuenta Atrás",
        value=f"```{WIPE_COUNTDOWN}```",
        inline=False
    )

    embed.add_field(
        name="🆕 ¿Qué trae de nuevo?",
        value=(
            "• 🌍 Mapa completamente limpio\n"
            "• 🏠 Bases desde cero\n"
            "• ⚙️ Ajustes de dificultad mejorados"
        ),
        inline=False
    )

    embed.set_footer(text=f"7 Days to Die • {get_footer()}")
    await ctx.send(embed=embed)
"""

@bot.command()
async def clips(ctx):
    clip_url = status7d.get_random_clip()
    msg_temp = await ctx.send("🔎Buscando un Clip Random...")
    if not clip_url:
        await ctx.send("❌ No hay clips disponibles.")
        return

    
    await msg_temp.delete()
    await ctx.send(f"Hey! {ctx.author.mention} Aquí tienes tu clip: {clip_url}")

#Volver a actualizar el cursor de clips
@tasks.loop(hours=24)
async def refresh_clips():
    print("Actualizando cursores de clips...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, status7d.scan_clip_pages)
    print("Cursores actualizados.")
@tasks.loop(hours=6)
async def refresh_cache():
    print("🔄 Actualizando cache de stats, players y ranking...")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, status7d.get_stats)
        await loop.run_in_executor(None, status7d.get_ranking)
        print("✅ Cache actualizado correctamente.")
    except Exception as e:
        print(f"❌ Error al actualizar el cache: {str(e)}")
ultimo_aviso_horda_dia = None    # Primer aviso: es día de horda
ultimo_aviso_horda_noche = None  # Segundo aviso: ya es la hora
@tasks.loop(minutes=1)
async def check_horda():
    global ultimo_aviso_horda_dia, ultimo_aviso_horda_noche
    canal = bot.get_channel(int(CANALES["7days-hordas"])) #Cambiar a Canal 7days-hordas o otro
    try:
        # 1. Verificar que el servidor esté activo
        if not status7d.check_status():
            print("⚠️ check_horda: servidor offline, se omite.")
            return
        # 2. Obtener stats
        USE_CACHE_TEST = False  # ← True solo para testing
        if USE_CACHE_TEST:
            data, _ = status7d.load_cache(status7d.CACHE_STATS)
            if not data:
                print("❌ No hay cache para test.")
                return
            print("🧪 Usando cache para test de horda.")
        else:
            try:
                # Ejecutar la solicitud HTTP en un hilo separado para no bloquear el event loop
                r = await asyncio.to_thread(requests.get, status7d.URL_STATS, timeout=15)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                    print(f"❌ check_horda: no se pudo obtener stats: {e}")
                    return
        # ─── 3. Extraer y validar campos ───
        day = data.get("day")
        nextHordeDay = data.get("nextHordeDay")
        time_str = data.get("time", "")

        if day is None or nextHordeDay is None:
            return
        try:
            day          = int(day)
            nextHordeDay = int(nextHordeDay)
            hora         = int(time_str.split(":")[0])
        except Exception as e:
            print(f"⚠️ check_horda: error parseando datos: {e}")
            return
        # 4. Obtener canal 
        if not canal:
            print("❌ check_horda: canal no encontrado.")
            return

        # PRIMER AVISO: inicio del día de horda 
        if day == nextHordeDay and ultimo_aviso_horda_dia != day:
            ultimo_aviso_horda_dia = day
            print(f"📢 Primer aviso de horda → día {day}")

            embed = discord.Embed(
                title="🗓️ ¡¡ HOY ES DÍA DE HORDA !!",
                description=(
                    "## ⚠️ ¡ATENCIÓN @everyone SUPERVIVIENTES!\n\n"
                    "**Esta noche los muertos vienen a por vosotros.**\n\n"
                    "🔧 Prepara tus defensas\n"
                    "🔫 Consigue Municiones!\n"
                    "🥫 Prepara comida y botiquines\n\n"
                    f"📅 **Día actual:** `{day}` — La horda llega esta noche."
                ),
                color=0xFFA500
            )
            image_path = os.path.join(BASE_DIR, "images", "Rawr.jpg")
            file = discord.File(image_path, filename="Rawr.jpg")
            embed.set_image(url="attachment://Rawr.jpg")
            embed.set_footer(text=f"7 Days to Die • {get_footer()}")
            await canal.send(embed=embed, file=file)
            print(f"✅ Primer aviso enviado (día {day}).")

        # ─── SEGUNDO AVISO: 22:00 del día de horda ───
        if day == nextHordeDay and hora >= 22 and ultimo_aviso_horda_noche != day:
            ultimo_aviso_horda_noche = day
            print(f"🚨 Segundo aviso de horda → día {day} hora {hora}")

            embed = discord.Embed(
                title="🚨 ¡¡ LA HORDA ESTÁ AQUÍ!! 🚨",
                description=(
                    "@everyone\n"
                    "## 🧟 ¡¡ ESCONDEOS O DEFENDED !!\n\n"
                    "**Los muertos vivientes están atacando AHORA.**\n\n"
                    "🏰 Ve a tu Antihorda o escondete\n"
                    "🔦 Recarga las armas\n\n"
                    f"📅 **Hora:** `{time_str}` — ¡Buena suerte, superviviente!"
                ),
                color=0xFF0000
            )
            image_path = os.path.join(BASE_DIR, "images", "Susto.png")
            file = discord.File(image_path, filename="Susto.png")
            embed.set_image(url="attachment://Susto.png")
            embed.set_footer(text=f"7 Days to Die • {get_footer()}")
            await canal.send(embed=embed, file=file)
            print(f"✅ Segundo aviso enviado (día {day}).")

    except Exception as e:
        print(f"❌ Error inesperado en check_horda: {str(e)}")

async def run_in_executor_background(loop, func):
    """Ejecuta una función bloqueante en un hilo y captura excepciones."""
    try:
        await loop.run_in_executor(None, func)
    except Exception as e:
        print(f"❌ Error en tarea de fondo ({func.__name__}): {e}")

@tasks.loop(minutes=2)
async def check_streams():
    """Comprueba cada 2 min si algún streamer de la lista ha iniciado stream."""
    canal = bot.get_channel(int(CANALES["streams"]))
    _streams_activos: dict[str, str] = {} 
    if not canal:
        return
    for streamer in STREAMERS:
        login = streamer.get("login", "").lower()
        url   = streamer.get("url")
        if not login:
            continue

        try:
            resultado = await twitch_monitor.check(login)
            if not resultado:
                # Offline → limpiar estado para detectar cuando vuelva
                _streams_activos.pop(login, None)
                continue

            stream    = resultado["stream"]
            stream_id = stream.get("id", "")
            user   = resultado.get("user") or {}

            # Si ya avisamos por este stream_id concreto, saltar
            if _streams_activos.get(login) == stream_id:
                continue

            # Nuevo stream detectado → guardar y continuar con el aviso
            _streams_activos[login] = stream_id

            # ── Datos del stream ──────────────────────────────────
            titulo      = stream.get("title", "Sin título")
            juego       = stream.get("game_name", "Desconocido")
            viewers     = stream.get("viewer_count", 0)
            display     = stream.get("user_name", login)
            thumbnail   = stream.get("thumbnail_url", "")
            # Twitch devuelve {width}x{height} como placeholders
            thumbnail   = thumbnail.replace("{width}", "1280").replace("{height}", "720")
            # Cache buster para que Discord no muestre frame antiguo
            thumbnail   = f"{thumbnail}?t={int(time.time())}"

            avatar      = user.get("profile_image_url", "")
            ahora       = datetime.now().strftime("%d/%m/%Y %H:%M")

            # ── Embed estilo Streamcord ───────────────────────────
            embed = discord.Embed(
                title=f"{titulo}",
                url=url,
                color=0x9146FF,   # morado Twitch
            )
            embed.set_author(
                name=f"🔴 ¡{display} está en directo!",
                url=url,
                icon_url=avatar if avatar else discord.Embed.Empty,
            )
            if not juego:
                juego = "Ninguno"
            embed.add_field(name="🎮 Categoria", value=juego,               inline=True)
            embed.add_field(name="👁️ Viewers",   value=f"{viewers:,}",      inline=True)
            if thumbnail:
                embed.set_image(url=thumbnail)
            embed.set_footer(text=f"Miner7days • {ahora}")
            allowed_mentions = discord.AllowedMentions(everyone=True)
            msg = f"Hey @everyone, {display} Esta en Directo! Ir a verle!"
            await canal.send(msg,allowed_mentions=allowed_mentions)
            await canal.send(embed=embed)
            print(f"✅ [check_streams] Aviso enviado → {display} en vivo")

        except Exception as e:
            print(f"❌ [check_streams] Error con {login}: {e}")

# ── Utilidades para el comando add_streamer ───────────────────────


_TWITCH_RE  = _re.compile(r'^[a-zA-Z0-9_]{4,25}$')
_URL_RE     = _re.compile(r'^https?://[^\s/$.?#][^\s]*$')

def _tiene_permiso_stream(member: discord.Member) -> bool:
    ids_miembro = {r.id for r in member.roles}
    return bool(ids_miembro & set(ROLES.values()))


class _AddStreamerModal(discord.ui.Modal, title="Añadir Streamer"):
    nombre = discord.ui.TextInput(
        label="Nombre de usuario en Twitch",
        placeholder="ejemplo: xQc  (sin @, sin URL)",
        min_length=4,
        max_length=25,
    )
    url = discord.ui.TextInput(
        label="URL del canal",
        placeholder="https://www.twitch.tv/xQc",
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        nombre_val = self.nombre.value.strip()
        url_val    = self.url.value.strip()

        # Validar nombre Twitch
        if not _TWITCH_RE.match(nombre_val):
            await interaction.response.send_message(
                "❌ Nombre inválido. Solo letras, números y `_`, entre 4 y 25 caracteres.",
                ephemeral=True
            )
            return

        # Validar URL
        if not _URL_RE.match(url_val):
            await interaction.response.send_message(
                "❌ URL inválida. Debe empezar con `http://` o `https://`.",
                ephemeral=True
            )
            return

        # Comprobar duplicado
        login = nombre_val.lower()
        if any(s.get("login", "").lower() == login for s in STREAMERS):
            await interaction.response.send_message(
                f"⚠️ `{nombre_val}` ya está en la lista de streamers.",
                ephemeral=True
            )
            return

        # Guardar en streamers.json
        STREAMERS.append({"login": login, "url": url_val})
        _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cache/streamers.json")
        with open(_path, "w", encoding="utf-8") as f:
            _json.dump(STREAMERS, f, ensure_ascii=False, indent=2)

        await interaction.response.send_message(
            f"✅ **{nombre_val}** añadido correctamente a la lista de streamers.",
            ephemeral=True
        )


class _AddStreamerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Añadir Streamer", style=discord.ButtonStyle.primary, emoji="📡")
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _tiene_permiso_stream(interaction.user):
            await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(_AddStreamerModal())

# ── Helpers ──────────────────────────────────────────────────────────
_LIST_PAGE_SIZE = 10

def _save_streamers():
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cache/streamers.json")
    with open(_path, "w", encoding="utf-8") as f:
        _json.dump(STREAMERS, f, ensure_ascii=False, indent=2)

def _build_list_embed(page: int) -> tuple[discord.Embed, int]:
    total = len(STREAMERS)
    pages = max(1, (total + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    start = page * _LIST_PAGE_SIZE
    chunk = STREAMERS[start:start + _LIST_PAGE_SIZE]

    lines = "\n".join(
        f"`{start + i + 1}.` **{s['login']}**"
        for i, s in enumerate(chunk)
    ) or "*(Sin streamers)*"

    embed = discord.Embed(title="📡 Lista de Streamers", description=lines, color=0x9146FF)
    embed.set_footer(text=f"Página {page + 1}/{pages} • {total} streamer(s) en total")
    return embed, pages


# ── Modal de edición (datos pre-rellenos) ────────────────────────────
class _EditModal(discord.ui.Modal):
    def __init__(self, index: int):
        s = STREAMERS[index]
        super().__init__(title=f"Editar: {s['login']}")
        self._index = index

        self.nombre = discord.ui.TextInput(
            label="Nombre de usuario en Twitch",
            default=s["login"],
            min_length=4, max_length=25,
        )
        self.url_input = discord.ui.TextInput(
            label="URL del canal",
            default=s.get("url", ""),
            max_length=100,
        )
        self.add_item(self.nombre)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        nombre_val = self.nombre.value.strip()
        url_val    = self.url_input.value.strip()

        if not nombre_val or not url_val:
            await interaction.response.send_message(
                "❌ Los campos no pueden estar vacíos.", ephemeral=True)
            return
        if not _TWITCH_RE.match(nombre_val):
            await interaction.response.send_message(
                "❌ Nombre inválido. Solo letras, números y `_` (4–25 caracteres).", ephemeral=True)
            return
        if not _URL_RE.match(url_val):
            await interaction.response.send_message(
                "❌ URL inválida. Debe empezar con `http://` o `https://`.", ephemeral=True)
            return

        STREAMERS[self._index] = {"login": nombre_val.lower(), "url": url_val}
        _save_streamers()
        await interaction.response.send_message(
            f"✅ **{nombre_val}** actualizado correctamente.", ephemeral=True)


# ── Vista de confirmación de borrado ─────────────────────────────────
class _ConfirmDeleteView(discord.ui.View):
    def __init__(self, index: int):
        super().__init__(timeout=30)
        self._index = index

    @discord.ui.button(label="Sí, eliminar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._index >= len(STREAMERS):
            await interaction.response.edit_message(
                content="⚠️ El streamer ya no existe en la lista.", embed=None, view=None)
            return
        login = STREAMERS[self._index]["login"]
        STREAMERS.pop(self._index)
        _save_streamers()
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ **{login}** eliminado de la lista.", embed=None, view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="↩️ Eliminación cancelada.", embed=None, view=None)


# ── Vista principal de liststream ────────────────────────────────────
class _ListStreamView(discord.ui.View):
    def __init__(self, page: int = 0):
        super().__init__(timeout=None)
        self.page = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        total  = len(STREAMERS)
        pages  = max(1, (total + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE)
        start  = self.page * _LIST_PAGE_SIZE
        chunk  = STREAMERS[start:start + _LIST_PAGE_SIZE]

        if chunk:
            # ── Select editar ─────────────────────────────────────
            edit_sel = discord.ui.Select(
                placeholder="✏️ Editar streamer...",
                options=[
                    discord.SelectOption(label=s["login"], value=str(start + i), emoji="✏️")
                    for i, s in enumerate(chunk)
                ],
                row=0,
            )
            edit_sel.callback = self._edit_cb
            self.add_item(edit_sel)

            # ── Select eliminar ───────────────────────────────────
            del_sel = discord.ui.Select(
                placeholder="🗑️ Eliminar streamer...",
                options=[
                    discord.SelectOption(label=s["login"], value=str(start + i), emoji="🗑️")
                    for i, s in enumerate(chunk)
                ],
                row=1,
            )
            del_sel.callback = self._delete_cb
            self.add_item(del_sel)

        # ── Paginación ────────────────────────────────────────────
        if pages > 1:
            prev_btn = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0), row=2,
            )
            prev_btn.callback = self._prev_cb
            self.add_item(prev_btn)

            page_btn = discord.ui.Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True, row=2,
            )
            self.add_item(page_btn)

            next_btn = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= pages - 1), row=2,
            )
            next_btn.callback = self._next_cb
            self.add_item(next_btn)

    # ── Callbacks ─────────────────────────────────────────────────
    async def _edit_cb(self, interaction: discord.Interaction):
        if not _tiene_permiso_stream(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        index = int(interaction.data["values"][0])
        await interaction.response.send_modal(_EditModal(index))

    async def _delete_cb(self, interaction: discord.Interaction):
        if not _tiene_permiso_stream(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        index = int(interaction.data["values"][0])
        login = STREAMERS[index]["login"]
        embed = discord.Embed(
            title="⚠️ Confirmar eliminación",
            description=f"¿Seguro que quieres eliminar a **{login}** de la lista de seguimiento?",
            color=0xFF4444,
        )
        await interaction.response.send_message(
            embed=embed, view=_ConfirmDeleteView(index), ephemeral=True)

    async def _prev_cb(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        embed, _ = _build_list_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        embed, _ = _build_list_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

# ── Datos de todos los comandos de interact para el help ─────────────
_INTERACT_CMDS = []

for _tag, _data in interact.INTERACCIONES.items():
    _cmd, _frase_con, _frase_pasado, _label, _emoji, _msg_bot, _frase_sin = _data[:7]
    _INTERACT_CMDS.append({
        "cmd":       _cmd,
        "tag":       _tag,
        "emoji":     _emoji,
        "tipo":      "con_target",
        "frase_con": _frase_con,
        "frase_sin": _frase_sin,
        "label":     _label,
        "msg_bot":   _msg_bot,
    })

for _tag, (_cmd, _frase, _emoji, _label, _frase_pasado) in interact.INTERACCIONES_SOLO.items():
    _INTERACT_CMDS.append({
        "cmd":   _cmd,
        "tag":   _tag,
        "emoji": _emoji,
        "tipo":  "solo",
        "frase": _frase,
        "label": _label,
    })

_INTERACT_PAGE_SIZE = 10


def _build_interact_page_embed(page: int) -> tuple[discord.Embed, int]:
    total = len(_INTERACT_CMDS)
    pages = max(1, (total + _INTERACT_PAGE_SIZE - 1) // _INTERACT_PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    start = page * _INTERACT_PAGE_SIZE
    chunk = _INTERACT_CMDS[start:start + _INTERACT_PAGE_SIZE]

    lines = "\n".join(
        f"{c['emoji']} `!{c['cmd']}`" +
        (f" / `!{c['tag']}`" if c['tag'] != c['cmd'] else "") +
        (" — *con o sin @usuario*" if c["tipo"] == "con_target" else " — *solo*")
        for c in chunk
    )

    embed = discord.Embed(
        title="🎭 Lista de Interacciones",
        description=lines,
        color=0xFF69B4,
    )
    embed.set_footer(text=f"Página {page + 1}/{pages} • {total} comandos en total • Selecciona uno para ver detalles")
    return embed, pages

def _build_cmd_detail_embed(cmd_data: dict) -> discord.Embed:
    alias = f" / `!{cmd_data['tag']}`" if cmd_data['tag'] != cmd_data['cmd'] else ""

    embed = discord.Embed(
        title=f"{cmd_data['emoji']} `!{cmd_data['cmd']}`{alias}",
        color=0xFF69B4,
    )

    if cmd_data["tipo"] == "con_target":
        embed.add_field(
            name="📌 Uso",
            value=(
                f"`!{cmd_data['cmd']}{alias} @usuario` — con objetivo\n"
                f"`!{cmd_data['cmd']}{alias}` — sin objetivo"
            ),
            inline=False,
        )
        embed.add_field(
            name="💬 Efecto con @usuario",
            value=f"[Tú] **{cmd_data['frase_con']}** [usuario].",
            inline=False,
        )
        embed.add_field(
            name="💬 Efecto sin @usuario",
            value=f"[Tú] **{cmd_data['frase_sin']}**.",
            inline=False,
        )
        embed.add_field(
            name="🔘 Botón de respuesta",
            value=f"El usuario mencionado verá el botón **{cmd_data['label']}** y podrá devolver la acción.",
            inline=False,
        )
    else:
        embed.add_field(
            name="📌 Uso",
            value=f"`!{cmd_data['cmd']}{alias}` — solo",
            inline=False,
        )
        embed.add_field(
            name="💬 Efecto",
            value=f"[Tú] **{cmd_data['frase']}**.",
            inline=False,
        )
        embed.add_field(
            name="🔘 Botón de respuesta",
            value=f"Otros pueden pulsar **{cmd_data['label']}** para unirse.",
            inline=False,
        )

    embed.set_footer(text="Todos los comandos generan un GIF animado de anime")
    return embed

# ── Vista paginada de interact list ──────────────────────────────────
class _InteractListView(discord.ui.View):
    def __init__(self, page: int = 0):
        super().__init__(timeout=None)
        self.page = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        total = len(_INTERACT_CMDS)
        pages = max(1, (total + _INTERACT_PAGE_SIZE - 1) // _INTERACT_PAGE_SIZE)
        start = self.page * _INTERACT_PAGE_SIZE
        chunk = _INTERACT_CMDS[start:start + _INTERACT_PAGE_SIZE]

        sel = discord.ui.Select(
            placeholder="🔍 Selecciona un comando para ver detalles...",
            options=[
                discord.SelectOption(
                    label=f"!{c['cmd']}",
                    value=str(start + i),
                    emoji=c["emoji"],
                    description=(
                        f"También: !{c['tag']} • " if c['tag'] != c['cmd'] else ""
                    ) + ("Con/sin @usuario" if c["tipo"] == "con_target" else "Solo"),
                )
                for i, c in enumerate(chunk)
            ],
            row=0,
        )
        sel.callback = self._select_cb
        self.add_item(sel)

        if pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0), row=1,
            )
            prev.callback = self._prev_cb
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True, row=1,
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= pages - 1), row=1,
            )
            nxt.callback = self._next_cb
            self.add_item(nxt)

    async def _select_cb(self, interaction: discord.Interaction):
        index    = int(interaction.data["values"][0])
        cmd_data = _INTERACT_CMDS[index]
        embed    = _build_cmd_detail_embed(cmd_data)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _prev_cb(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        embed, _ = _build_interact_page_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        embed, _ = _build_interact_page_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)


# ── Comandos ─────────────────────────────────────────────────────────
@bot.command(name="interact")
async def cmd_interact(ctx):
    """Explica el sistema de interacciones del bot."""
    embed = discord.Embed(
        title="🎭 Sistema de Interacciones",
        description=(
            "El bot tiene una colección de acciones animadas con GIFs de anime "
            "con las que puedes interactuar con otros usuarios del servidor.\n\n"
            "Hay **dos tipos** de comandos:"
        ),
        color=0xFF69B4,
    )
    embed.add_field(
        name="👥 Con @usuario (o sin él)",
        value=(
            "La mayoría de comandos aceptan una mención opcional.\n"
            "• **Con mención:** la acción va dirigida a ese usuario, que verá un botón para responder.\n"
            "• **Sin mención:** la acción se hace «al aire» o al servidor entero.\n\n"
            "**Ejemplo:** `!kick @what_a_caramel`\n"
            "→ *[Tú] le pega una patada a [what_a_caramel].*\n"
            "→ what_a_caramel verá el botón **¡Patear de vuelta!** 🦵\n\n"
            "**Ejemplo:** `!kick` *(sin mención)*\n"
            "→ *[Tú] patea el aire con toda la frustración del mundo.*"
        ),
        inline=False,
    )
    embed.add_field(
        name="🙋 Solo (sin @usuario)",
        value=(
            "Algunos comandos están pensados únicamente para uno mismo.\n"
            "Otros usuarios pueden pulsar el botón para «unirse» a la acción.\n\n"
            "**Ejemplo:** `!sorber`\n"
            "→ *[Tú] sorbe su bebida mirando pensativamente al vacío.*"
        ),
        inline=False,
    )
    embed.add_field(
        name="💡 Consejo",
        value=(
            "También puedes **responder a un mensaje** con el comando "
            "para que la acción vaya dirigida al autor de ese mensaje.\n\n"
            "Usa `!interactlist` para ver todos los comandos disponibles."
        ),
        inline=False,
    )
    embed.set_footer(text=f"7 Days to Die • {len(_INTERACT_CMDS)} interacciones disponibles")
    await ctx.send(embed=embed)


@bot.command()
async def interactlist(ctx):
    """Lista paginada de todos los comandos de interacción."""
    embed, _ = _build_interact_page_embed(0)
    await ctx.send(embed=embed, view=_InteractListView(0))
# ── Comando ───────────────────────────────────────────────────────────
@bot.command()
async def liststream(ctx):
    """Lista los streamers monitorizados con opciones de editar y eliminar."""
    if not _tiene_permiso_stream(ctx.author):
        await ctx.message.delete()
        await ctx.send("❌ No tienes permisos.", delete_after=5)
        return

    if not STREAMERS:
        await ctx.send("📭 No hay streamers en la lista todavía. Usa `!add_streamer` para añadir uno.")
        return

    embed, _ = _build_list_embed(0)
    await ctx.send(embed=embed, view=_ListStreamView(0))
@bot.command()
async def addstrm(ctx):
    """Abre el panel para añadir un streamer. Solo Mod/Admin."""
    if not _tiene_permiso_stream(ctx.author):
        await ctx.message.delete()
        await ctx.send("❌ No tienes permisos para usar este comando.", delete_after=5)
        return

    embed = discord.Embed(
        title="📡 Gestión de Streamers",
        description=(
            "Pulsa el botón para añadir un nuevo streamer a la lista de seguimiento.\n\n"
            "**Requisitos:**\n"
            "• Nombre: solo letras, números y `_` (4–25 caracteres)\n"
            "• URL: enlace válido al canal de Twitch"
        ),
        color=0x9146FF
    )
    embed.set_footer(text="Solo Moderadores y Admins pueden añadir streamers.")
    await ctx.send(embed=embed, view=_AddStreamerView())

# ── Datos de comandos de moderador para !modcmds ─────────────────────
_MOD_CMDS = [
    {
        "cmd":   "addstrm",
        "emoji": "📡",
        "desc":  "Abre el panel para añadir un nuevo streamer a la lista de seguimiento.",
        "uso":   "`!addstrm`",
        "args":  "Ninguno. Abre un botón que lanza un modal con los campos Nombre y URL.",
    },
    {
        "cmd":   "liststream",
        "emoji": "📋",
        "desc":  "Lista todos los streamers monitorizados con opciones de editarlos o eliminarlos.",
        "uso":   "`!liststream`",
        "args":  "Ninguno. Muestra embed paginado con selects para editar o eliminar.",
    },
    {
        "cmd":   "bugs",
        "emoji": "🐛",
        "desc":  "Muestra los tickets de bug registrados por los usuarios.",
        "uso":   "`!bugs` o `!bugs <número>`",
        "args":  "`<número>` (opcional) — muestra directamente ese ticket por su ID.",
    },
    {
        "cmd":   "tkclose",
        "emoji": "🔒",
        "desc":  "Cierra un ticket con interfaz interactiva, marcándolo como solucionado o no.",
        "uso":   "`!tkclose <número>`",
        "args":  "`<número>` — ID del ticket a cerrar. Obligatorio.",
    },
    {
        "cmd":   "tickets",
        "emoji": "🎫",
        "desc":  "Muestra el panel de tickets activos (abiertos) con menú de selección.",
        "uso":   "`!tickets`",
        "args":  "Ninguno.",
    },
    {
        "cmd":   "tklist",
        "emoji": "📂",
        "desc":  "Panel completo de todos los tickets: abiertos, cerrados, pendientes y resumen.",
        "uso":   "`!tklist` o `!tklist <número>`",
        "args":  "`<número>` (opcional) — muestra directamente ese ticket por su ID.",
    },
    #{
        #"cmd":   "eventlist",
        #"emoji": "🏗️",
       # "desc":  "Gestiona todos los eventos (activos y finalizados) y sus participantes.",
      #  "uso":   "`!eventlist`",
     #   "args":  "Ninguno. Muestra un menú con todos los eventos para ver participantes, pruebas y cerrar/reabrir.",
    #},
    #{
        #"cmd":   "addevent",
       # "emoji": "📝",
      #  "desc":  "Crea un nuevo evento de construcción mediante un formulario web.",
     #   "uso":   "`!addevent`",
    #    "args":  "Ninguno. Lanza un panel con un botón para generar un enlace al editor de eventos y otro para cargar el JSON resultante.",
    #},
    {
        "cmd":   "wipeG",
        "emoji": "🔄",
        "desc":  "Panel de gestión del wipe: programa, cancela y envía avisos al canal.",
        "uso":   "`!wipeG`",
        "args":  "Ninguno. Abre el panel con botones para programar una fecha de wipe, enviar aviso al canal y cancelarlo.",
    },
    {
        "cmd":   "deco",
        "emoji": "🪑",
        "desc":  "Panel de gestión de pedidos de decoración: ver pendientes, aprobar, rechazar y ver historial.",
        "uso":   "`!deco`",
        "args":  "Ninguno. Muestra todos los pedidos pendientes con menú de selección. Usa el botón 'Ver historial' para finalizados y rechazados.",
    }, 
    {
        "cmd":   "avisos",
        "emoji": "💎",
        "desc":  "Panel de gestión para enviar avisos a los jugadores. genera una url por 30 minutos ",
        "uso":   "`!avisos`",
        "args":  "Ninguno. Muestra un embed listo para abrir el panel y envia mensajes efimeros de la url generada y el embed para generar la url",
    },
    {
     "cmd": "setprefix",
     "emoji": "🔑",
     "desc": "Crea un prefix secundario para el bot. Solo Mod/Admin/Owner.",
     "uso": "`!setprefix <prefijo>`",
     "args": "`<prefijo>` — Prefijo secundario. Obligatorio.",
    },
    {
        "cmd":   "modsG",
        "emoji": "🧱",
        "desc":  "Panel de gestión de mods del servidor: añadir, editar, eliminar mods y links de descarga.",
        "uso":   "`!modsG`",
        "args":  "Ninguno. Solo Owner y Moderadores. Abre panel con botones para gestionar la lista de mods y links de descarga directas.",
    },
    {
        "cmd":   "rangosG",
        "emoji": "🛡️",
        "desc":  "Panel de gestión de rangos del servidor: añadir, editar, eliminar rangos",
        "uso":   "`!rangosG`",
        "args":  "Ninguno. Solo Owner y Moderadores. Abre panel con botones para gestionar la lista de rangos.",
    },
    {
        "cmd":   "triviaG",
        "emoji": "❓",
        "desc":  "Panel de gestión de preguntas de trivia: añadir, editar, eliminar preguntas",
        "uso":   "`!triviaG`",
        "args":  "Ninguno. Solo Owner y Moderadores. Abre panel con botones para gestionar la lista de preguntas.",
    },
]
_MOD_PAGE_SIZE = 10


def _build_modcmds_embed(page: int) -> tuple[discord.Embed, int]:
    total = len(_MOD_CMDS)
    pages = max(1, (total + _MOD_PAGE_SIZE - 1) // _MOD_PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    start = page * _MOD_PAGE_SIZE
    chunk = _MOD_CMDS[start:start + _MOD_PAGE_SIZE]

    lines = "\n".join(
        f"{c['emoji']} `!{c['cmd']}` — {c['desc'][:60]}{'…' if len(c['desc']) > 60 else ''}"
        for c in chunk
    )

    embed = discord.Embed(
        title="🛡️ Comandos de Moderador",
        description=lines,
        color=0x8B0000,
    )
    embed.set_footer(text=f"Página {page + 1}/{pages} • {total} comandos • Selecciona uno para ver detalles")
    return embed, pages


class _ModCmdsView(discord.ui.View):
    def __init__(self, page: int = 0):
        super().__init__(timeout=None)
        self.page = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        total = len(_MOD_CMDS)
        pages = max(1, (total + _MOD_PAGE_SIZE - 1) // _MOD_PAGE_SIZE)
        start = self.page * _MOD_PAGE_SIZE
        chunk = _MOD_CMDS[start:start + _MOD_PAGE_SIZE]

        sel = discord.ui.Select(
            placeholder="🔍 Selecciona un comando para ver detalles...",
            options=[
                discord.SelectOption(
                    label=f"!{c['cmd']}",
                    value=str(start + i),
                    emoji=c["emoji"],
                    description=c["desc"][:100],
                )
                for i, c in enumerate(chunk)
            ],
            row=0,
        )
        sel.callback = self._select_cb
        self.add_item(sel)

        if pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0), row=1,
            )
            prev.callback = self._prev_cb
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True, row=1,
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= pages - 1), row=1,
            )
            nxt.callback = self._next_cb
            self.add_item(nxt)
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _tiene_permiso_stream(interaction.user):
            await interaction.response.send_message(
                "🔒 No tienes privilegios para usar este panel.", ephemeral=True
            )
            return False
        return True
    async def _select_cb(self, interaction: discord.Interaction):
        index = int(interaction.data["values"][0])
        c     = _MOD_CMDS[index]
        embed = discord.Embed(
            title=f"{c['emoji']} `!{c['cmd']}`",
            color=0x8B0000,
        )
        embed.add_field(name="📖 Descripción", value=c["desc"],  inline=False)
        embed.add_field(name="📌 Uso",         value=c["uso"],   inline=False)
        embed.add_field(name="⚙️ Argumentos",  value=c["args"],  inline=False)
        embed.set_footer(text="Solo accesible para Moderadores y Admins")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _prev_cb(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        embed, _ = _build_modcmds_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        embed, _ = _build_modcmds_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name="modlist")
async def modlist(ctx):
    """Panel de comandos exclusivos para moderadores."""
    if not _tiene_permiso_stream(ctx.author):
        return  # silencio total si no es mod
    embed, _ = _build_modcmds_embed(0)
    await ctx.send(embed=embed, view=_ModCmdsView(0))

@bot.event
async def on_ready():
    await _db_niveles.init_db()
    await _init_rangos(bot)   # carga rangos_ids.json si ya existe
    await _init_miembros(bot)
 
    # ── NUEVO: cargar cog de niveles ──────────────────────────────────
    if "niveles"      not in bot.extensions:
        await bot.load_extension("niveles")
    if "crear_rangos" not in bot.extensions:
        await bot.load_extension("crear_rangos")
    if "devdb"        not in bot.extensions:
        await bot.load_extension("devdb")
        
    #await bot.load_extension("tess_cog")    
    await bot.load_extension("ticket")
    await bot.load_extension("battle")
    await bot.load_extension("trivia")
    await bot.load_extension("decoracion")
    await bot.load_extension("mods")
    await bot.load_extension("userhelp")
    #await bot.load_extension("music")
    await bot.load_extension("time_cog")
   # if "events" not in bot.extensions:   # ← Guarda antes de cargar
        #await bot.load_extension("events")
    if "wipe" not in bot.extensions:
        await bot.load_extension("wipe")     
    if not hasattr(bot, 'flask_iniciado'):
        web_avisos.iniciar_flask(bot)
        web_avisos.registrar_comando(bot)
        bot.flask_iniciado = True

    # Iniciar loops periódicos si no están corriendo
    if not check_streams.is_running():
        check_streams.start()
    if not refresh_cache.is_running():
        refresh_cache.start()
    if not refresh_clips.is_running():
        refresh_clips.start()
    if not check_horda.is_running():
        check_horda.start()

    print(f"🤖 Bot listo como {bot.user}")
bot.run(pin.TOKEN)
