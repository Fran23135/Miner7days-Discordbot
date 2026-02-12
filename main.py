import discord
from discord.ext import commands
import requests
import difflib
from pin import TOKEN
import status7d
import threading
import asyncio
from flask import Flask, app, render_template, render_template_string, request, jsonify
import random
import asyncio
import os
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# Configuración Flask
CANALES = {
    "test": "1470570838544617728",
    "chat-7days": "1459685355048407262",
    "7days-info": "1459660523049193582"
}

MENSAJES_PREDEFINIDOS = {
    "servidor_activo": {
        "titulo": "✅ **SERVIDOR ACTIVO**",
        "mensaje": "El servidor ha vuelto a estar en línea y está funcionando correctamente.",
        "color": "00FF00"
    },
    "servidor_caido": {
        "titulo": "❌ **SERVIDOR CAÍDO**",
        "mensaje": "El servidor está fuera de línea temporalmente. Estamos trabajando para solucionarlo.",
        "color": "FF0000"
    },
    "servidor_caera": {
        "titulo": "⚠️ **AVISO DE REINICIO**",
        "mensaje": "El servidor se reiniciará en {tiempo} .",
        "color": "FFA500"
    },
    "wipe_server": {
        "titulo": "🔄 **WIPE DEL SERVIDOR**",
        "mensaje": "Se realizará un wipe del servidor el {fecha}. ¡Prepárense para empezar de nuevo!",
        "color": "FF00FF"
    }
}

# Crear la app Flask
app = Flask(__name__)

@app.route('/')
def index():
    try:
        # Obtener la ruta absoluta del directorio actual
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, 'avisos.html')
        
        print(f"🔍 Buscando archivo HTML en: {html_path}")
        
        if not os.path.exists(html_path):
            return f"❌ Error: No se encuentra avisos.html en {html_path}", 404
            
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return render_template_string(html_content, 
                                     canales=CANALES, 
                                     mensajes=MENSAJES_PREDEFINIDOS)
    except Exception as e:
        return f"❌ Error al cargar la página: {str(e)}", 500

@app.route('/enviar_aviso', methods=['POST'])
def enviar_aviso():
    try:
        datos = request.form
        tageo = datos.get('tageo', 'none')
        tageo_custom = datos.get('tageo_custom', '')
        canal_id = datos['canal']
        titulo = datos['titulo']
        mensaje = datos['mensaje']
        color = datos.get('color', '8B0000')
        imagen_url = datos.get('imagen_url', '')
        
        print(f"📨 Recibido aviso para canal {canal_id}: {titulo}")
        
        # Verificar que el bot esté listo
        if bot.is_ready():
            canal = bot.get_channel(int(canal_id))
            if canal:
                # Construir el mensaje con el tag correspondiente
                tag_texto = ""
                if tageo == 'everyone':
                    tag_texto = "@everyone"
                elif tageo == 'here':
                    tag_texto = "@here"
                elif tageo == 'custom' and tageo_custom:
                    tag_texto = tageo_custom
                
                if tag_texto:
                    mensaje_completo = f"{tag_texto}\n{mensaje}"
                else:
                    mensaje_completo = mensaje
           #  if canal:
                # mensaje_completo = f"@everyone\n\n{mensaje}"
                
                # Manejar archivo subido
                imagen_archivo = request.files.get('imagen')
                imagen_path = None
                
                if imagen_archivo and imagen_archivo.filename:
                    # Guardar archivo temporalmente
                    import uuid
                    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_uploads')
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir)
                    
                    filename = f"{uuid.uuid4()}_{imagen_archivo.filename}"
                    imagen_path = os.path.join(temp_dir, filename)
                    imagen_archivo.save(imagen_path)
                    print(f"💾 Imagen guardada temporalmente en: {imagen_path}")
                
                # Usar asyncio para enviar el mensaje
                asyncio.run_coroutine_threadsafe(
                    enviar_mensaje_discord(canal, titulo, mensaje_completo, color, imagen_url, imagen_path),
                    bot.loop
                )
                return jsonify({"success": True, "message": "✅ Aviso preparado para enviar"})
            else:
                return jsonify({"error": f"❌ Canal no encontrado: {canal_id}"}), 404
        else:
            return jsonify({"error": "❌ Bot no conectado"}), 500
            
    except Exception as e:
        return jsonify({"error": f"❌ Error: {str(e)}"}), 500

async def enviar_mensaje_discord(canal, titulo, mensaje, color, imagen_url="", imagen_path=None):
    """Envía un mensaje embed a Discord con imagen adjunta o URL"""
    try:
        embed = discord.Embed(
            title=titulo,
            description=mensaje,
            color=int(color, 16)
        )
        
        # Primero verificar si hay archivo subido
        if imagen_path and os.path.exists(imagen_path):
            try:
                # Adjuntar la imagen como archivo
                file = discord.File(imagen_path, filename="imagen.png")
                embed.set_image(url="attachment://imagen.png")
                await canal.send(embed=embed, file=file)
                
                # Limpiar archivo temporal después de enviar
                os.remove(imagen_path)
                print(f"✅ Imagen adjuntada y enviada desde archivo")
                
            except Exception as file_error:
                print(f"❌ Error al adjuntar imagen: {file_error}")
                # Fallback a URL si hay error con archivo
                if imagen_url:
                    embed.set_image(url=imagen_url)
                    await canal.send(embed=embed)
        elif imagen_url:
            # Usar URL de imagen si no hay archivo
            embed.set_image(url=imagen_url)
            await canal.send(embed=embed)
        else:
            # Sin imagen
            await canal.send(embed=embed)
            
        print(f"✅ Aviso enviado al canal {canal.name}")
        
        # Limpiar directorio temporal si existe
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_uploads')
        if os.path.exists(temp_dir):
            try:
                # Intentar eliminar archivos temporales viejos (>5 minutos)
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        # Verificar si el archivo es viejo
                        import time
                        if os.path.getmtime(file_path) < time.time() - 300:  # 5 minutos
                            os.remove(file_path)
            except:
                pass
                
    except Exception as e:
        print(f"❌ Error al enviar mensaje a Discord: {str(e)}")
        
        # Limpiar archivo temporal en caso de error
        if imagen_path and os.path.exists(imagen_path):
            try:
                os.remove(imagen_path)
            except:
                pass
# Función para iniciar Flask en un hilo separado
def iniciar_flask():
    print("🌐 Iniciando servidor web en http://127.0.0.1:80")
    
    # Crear directorio para uploads temporales
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_uploads')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"📁 Directorio temporal creado: {temp_dir}")
    
    # Importante: desactivar reloader y usar threaded=True
    app.run(debug=False, port=8000, host='0.0.0.0', use_reloader=False, threaded=True)


@bot.command()
async def web(ctx):
    """Muestra el enlace a las estadísticas del servidor"""
    
    embed = discord.Embed(
        title="📊 **ENLACE A LAS STATS EN TIEMPO REAL**",
        description=f"Hey! {ctx.author.mention}\n Da Click 👉 https://kasiri.github.io/7days-stats/",
        color=0x8B0000
    )
    
    await ctx.send(embed=embed)  
@bot.command()
async def status(ctx):
    """Verifica el estado del servidor"""
    obtaining_msg = await ctx.send("🌐 **Comprobando estado del servidor...**")
    
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
        embed.set_footer(text="Intenta nuevamente en unos minutos")
    
    await ctx.send(embed=embed)
@bot.command()
async def stats(ctx):
    """Muestra las estadísticas del servidor"""
    msg_temp = await ctx.send("Obteniendo información del servidor...")
    try:
        # Obtener datos del servidor
        data = status7d.get_stats()
        
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

        await ctx.send(embed=embed)
        
    except Exception as e:
        await msg_temp.delete()
        print(f"❌ Error al obtener datos del servidor: {str(e)}")

@bot.command()
async def player(ctx, *,player_name: str):
    """Muestra las estadísticas de un jugador específico"""
    if not player_name:
        await ctx.send("❌ Debes especificar el nombre de un jugador. Ejemplo: `!player Fran23135`")
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
        
        # Crear embed estilizado
        embed = discord.Embed(
            title=f"👤 **{display_name}**",
            description=f"Hey! {ctx.author.mention}\n",
            color=0x8B0000
        )
        
        # Agregar campos con emotes y formato
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
        # Calcular promedio de zombies por nivel
        if level > 0:
            zombies_per_level = zombies / level
            embed.add_field(
                name="📊 **Zombies/Nivel**",
                value=f"```\n{zombies_per_level:.1f}\n```",
                inline=True
            )
        else:
            embed.add_field(
                name="📊 **Zombies/Nivel**",
                value=f"```\n0\n```",
                inline=True
            ) 
    
         
        # Agregar pie de página
        embed.set_footer(text="Estadísticas globales del ranking")
        
        await obtaining_msg.delete()
        await ctx.send(embed=embed)
        
    except Exception as e:
        await obtaining_msg.delete()
        await ctx.send(f"❌ Error al buscar las estadísticas: {str(e)}")

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
            "`!players` - Muestra tabla de jugadores conectados en tiempo real"
            
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
            "`!ranking` - Muestra el ranking global ordenado por nivel"
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
            "`!web` - Muestra el enlace a las estadísticas en tiempo real"
            
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
    embed.set_footer(text="Bot desarrollado para 7 Days to Die • ¡Diviértete!")
    
    await ctx.send(embed=embed)


@bot.command()
async def players(ctx):
    try:
     msg_temp = await ctx.send("Obteniendo Estadísticas del los Jugadores...")
     data = status7d.get_stats()
     print(data) 
    
     players = data.get("players", [])
 
     if not players:
        embed = discord.Embed(
            title="👥 Jugadores Conectados",
            description=f"Hey! {ctx.author.mention}\n**No hay jugadores activos.**",
            color=0x8B0000
        )
         
        await ctx.send(embed=embed)
        return

     # Crear tabla compacta
     table_lines = ["```"]
     table_lines.append(f"{'JUGADOR':<14} {'NIVEL':<4} {'ZOMBIES':<8} {'MUERTES':<8} {' PING':<5}")
     table_lines.append("-" * 45)
    
     for player in players:
        name = player.get("name", "?")[:12].ljust(12)
        if len(name) < 12:
            name = name.ljust(12)
        
        level = str(player.get("level", 0))[:3].rjust(3)
        zombies = str(player.get("zombies", 0))[:6].rjust(6)
        deaths = str(player.get("deaths", 0))[:6].rjust(6)
        ping = str(player.get("ping", 0))[:4].rjust(4)
        
        table_lines.append(f"{name}   {level}   {zombies}   {deaths}    {ping}")
    
     table_lines.append("```")
    
     # Crear embed simple
     embed = discord.Embed(
        title="🎮 Jugadores Conectados",
        description=f"Hey! {ctx.author.mention}\n" + "\n".join(table_lines),
        color=0x8B0000

     )
     embed.add_field(
            name=f"👤 Jugadores: {len(players)}",
            value="",
            inline=True
        )
    
     await msg_temp.delete()
     await ctx.send(embed=embed)
    
    except Exception as e:
        await msg_temp.delete()
        print(f"❌ Error al obtener datos del los jugadores: {str(e)}")

@bot.command()
async def creditos(ctx):
    DESARROLLADOR_ID = 521156020580646925
    embed = discord.Embed(
        title="📄 **Créditos del desarollador**",
        description=(
            f"Hey! {ctx.author.mention}\n"
            "Este bot fue desarrollado para el servidor de 7 Days to Die.\n\n"
            f"🔧 **Desarrollador**: <@{DESARROLLADOR_ID}>\n"
            "🌐 **Versión**: 1.0\n"
            "💡 **Funcionalidades**: Estadísticas en tiempo real, comandos de ayuda, ranking, consejos mineros."
        ),
        color=0x8B0000
    )
    embed.set_footer(text="Bot desarrollado para 7 Days to Die • ¡Diviértete!")
    await ctx.send(embed=embed)

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
    "👕 Siempre lleva puesto tu autendo de minero"
    ]


    
    """Muestra un consejo minero aleatorio"""
    # Elegir un consejo aleatorio
    tip = random.choice(MINER_TIPS)
    
    # Crear embed
    embed = discord.Embed(
        title="⛏️ **Consejo Minero**",
        description=f"👥 Hey! {ctx.author.mention}\n*{tip}*",
        color=0x8B4513  # Color marrón (tierra)
    )
    
    # Pie de página con indicación de aleatoriedad
    embed.set_footer(text="Consejo #{} de {}".format(random.randint(1, len(MINER_TIPS)), len(MINER_TIPS)))
    
    await ctx.send(embed=embed)

@bot.command()
async def ranking(ctx):
    """Muestra el ranking global ordenado por nivel"""
    obtaining_msg = await ctx.send("📊 Obteniendo ranking global...")
    
    try:
        # Obtener el ranking
        ranking_data = status7d.get_ranking()
        
        if not ranking_data:
            await obtaining_msg.delete()
            await ctx.send("❌ No se pudo obtener el ranking en este momento.")
            return
        
        # Convertir a lista y ordenar por nivel (descendente)
        players_list = []
        for name, stats in ranking_data.items():
            players_list.append({
                "name": name,
                "level": stats.get("level", 0),
                "zombies": stats.get("zombies", 0),
                "deaths": stats.get("deaths", 0)
            })
        
        # Ordenar por nivel descendente
        players_list.sort(key=lambda x: x["level"], reverse=True)
        
        if not players_list:
            await obtaining_msg.delete()
            embed = discord.Embed(
                title="🏆 **RANKING GLOBAL**",
                description=f"Hey! {ctx.author.mention}\n No hay jugadores en el ranking.",
                color=0xFFD700
            )
            await ctx.send(embed=embed)
            return
        
        # SI HAY 25 O MENOS: Mostrar normal
        if len(players_list) <= 25:
            # Crear tabla perfectamente alineada
            table_lines = ["```"]
            table_lines.append(f"{'#':<3} {'JUGADOR':<20} {'NVL':<5} {'ZOMBIES':<10} {'MUERTES':<9}")
            table_lines.append("-" * 50)
            
            for i, player in enumerate(players_list, 1):
                # Formatear el puesto
                if i <= 9:
                    rank = f" {i}."
                else:
                    rank = f"{i}."
                
                # Truncar nombre si es muy largo
                name = player["name"]
                if len(name) > 19:
                    name = name[:16] + "..."
                else:
                    name = name.ljust(20)
                
                # Formatear números
                level = str(player["level"]).ljust(5)
                zombies = str(player["zombies"]).ljust(10)
                deaths = str(player["deaths"]).ljust(9)
                
                # Crear línea perfectamente alineada
                table_lines.append(f"{rank} {name} {level} {zombies} {deaths}")
            
            table_lines.append("```")
            
            # Crear embed
            embed = discord.Embed(
                title="🏆 **RANKING GLOBAL**",
                description=f"**Hey! {ctx.author.mention}\nTotal de jugadores: {len(players_list)}** (ordenados por nivel)\n\n" + "\n".join(table_lines),
                color=0xFFD700
            )
            
            embed.set_footer(text=f"Total de  {len(players_list)} jugadores")
            
            await obtaining_msg.delete()
            await ctx.send(embed=embed)
            
        # SI HAY MÁS DE 25: Hacer paginación
        else:
            PAGE_SIZE = 25
            total_pages = (len(players_list) + PAGE_SIZE - 1) // PAGE_SIZE
            
            # Crear función para generar embed de una página específica
            def create_embed(page_num):
                start_idx = page_num * PAGE_SIZE
                end_idx = min(start_idx + PAGE_SIZE, len(players_list))
                page_players = players_list[start_idx:end_idx]
                
                # Crear tabla para la página actual
                table_lines = ["```"]
                table_lines.append(f"{'#':<3} {'JUGADOR':<20} {'NVL':<5} {'ZOMBIES':<10} {'MUERTES':<9}")
                table_lines.append("-" * 50)
                
                for i, player in enumerate(page_players, start=start_idx + 1):
                    # Formatear el puesto
                    if i <= 9:
                        rank = f" {i}."
                    else:
                        rank = f"{i}."
                    
                    # Truncar nombre si es muy largo
                    name = player["name"]
                    if len(name) > 19:
                        name = name[:16] + "..."
                    else:
                        name = name.ljust(20)
                    
                    # Formatear números
                    level = str(player["level"]).ljust(5)
                    zombies = str(player["zombies"]).ljust(10)
                    deaths = str(player["deaths"]).ljust(9)
                    
                    # Crear línea perfectamente alineada
                    table_lines.append(f"{rank} {name} {level} {zombies} {deaths}")
                
                table_lines.append("```")
                
                # Crear embed
                embed = discord.Embed(
                    title="🏆 **RANKING GLOBAL**",
                    description=f"**Hey! {ctx.author.mention}\nPágina {page_num + 1}/{total_pages}** (Jugadores {start_idx + 1}-{end_idx} de {len(players_list)})\n\n" + "\n".join(table_lines),
                    color=0xFFD700
                )
                
                embed.set_footer(text=f"Total: {len(players_list)} jugadores • Reacciona con ⬅️ ➡️ para navegar")
                return embed
            
            # Enviar primera página
            await obtaining_msg.delete()
            message = await ctx.send(embed=create_embed(0))
            
            # Agregar reacciones para navegación
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            # Definir check para reacciones válidas
            def check(reaction, user):
                return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]
            
            current_page = 0
            
            # Tiempo de espera para reacciones (2 minutos)
            timeout = 120
            
            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=timeout, check=check)
                    
                    # Cambiar página según reacción
                    if str(reaction.emoji) == "➡️" and current_page < total_pages - 1:
                        current_page += 1
                    elif str(reaction.emoji) == "⬅️" and current_page > 0:
                        current_page -= 1
                    
                    # Actualizar embed
                    await message.edit(embed=create_embed(current_page))
                    
                    # Quitar la reacción del usuario
                    await message.remove_reaction(reaction.emoji, user)
                    
                except asyncio.TimeoutError:
                    # Eliminar reacciones después del timeout
                    try:
                        await message.clear_reactions()
                    except:
                        pass
                    break
        
    except Exception as e:
        await obtaining_msg.delete()
        await ctx.send(f"❌ Error al obtener el ranking: {str(e)}")





@bot.event
async def on_ready():
    if not hasattr(bot, 'flask_iniciado'):
        flask_thread = threading.Thread(target=iniciar_flask, daemon=True)
        flask_thread.start()
        bot.flask_iniciado = True


bot.run(os.getenv('TOKEN'))


