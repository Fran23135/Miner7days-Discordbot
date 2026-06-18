# ─────────────────────────────────────────────────────────────────────────────
# web_avisos.py  —  Servidor Flask de avisos desacoplado de main.py
# Uso en main.py:
#     import web_avisos
#     web_avisos.iniciar_flask(bot)
#     web_avisos.registrar_comando(bot)   ← añade !avisos
# ─────────────────────────────────────────────────────────────────────────────

import os
import uuid
import time
import random
import asyncio
import threading
import json as _json
from config import ROLES
import discord
from flask import Flask, request, jsonify, render_template_string
from pyngrok import ngrok
from config import CANALES
from pin import NGROK_TOKEN
# ── Instancia Flask ───────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Referencia al bot ─────────────────────────────────────────────────────────
_bot = None
_NGROK_TOKEN = NGROK_TOKEN
# ── Rutas ─────────────────────────────────────────────────────────────────────
_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
_TEMP_DIR  = os.path.join(_BASE_DIR, "temp_uploads")
_HTML_PATH = os.path.join(_BASE_DIR, "html", "avisos.html")

# ── Tunnel ngrok ──────────────────────────────────────────────────────────────
_tunel        = None        # tunnel activo de pyngrok
_tunel_url    = ""          # URL pública actual
_tunel_expira = 0.0         # timestamp unix de expiración
_tunel_lock   = threading.Lock()
_DURACION_SEG = 30 * 60     # 30 minutos

def _abrir_tunel() -> str:
    """Abre (o reutiliza) un túnel ngrok. Devuelve la URL pública."""
    global _tunel, _tunel_url, _tunel_expira

    with _tunel_lock:
        ahora = time.time()

        # Si el túnel sigue activo devuelve la misma URL
        if _tunel and _tunel_url and ahora < _tunel_expira:
            return _tunel_url

        # Cerrar túnel anterior si existe
        if _tunel:
            try:
                ngrok.disconnect(_tunel.public_url)
            except Exception:
                pass
            _tunel = None

        if _NGROK_TOKEN:
            ngrok.set_auth_token(_NGROK_TOKEN)

        _tunel       = ngrok.connect(5000, "http")
        _tunel_url   = _tunel.public_url
        _tunel_expira = ahora + _DURACION_SEG

        # Hilo que cierra el túnel al expirar
        def _cerrar_al_expirar():
            time.sleep(_DURACION_SEG)
            global _tunel, _tunel_url, _tunel_expira
            with _tunel_lock:
                if _tunel:
                    try:
                        ngrok.disconnect(_tunel.public_url)
                    except Exception:
                        pass
                    _tunel       = None
                    _tunel_url   = ""
                    _tunel_expira = 0.0
            print("🔌 Túnel ngrok cerrado por expiración")

        threading.Thread(target=_cerrar_al_expirar, daemon=True).start()
        print(f"🌐 Túnel ngrok abierto: {_tunel_url}")
        return _tunel_url





# ── Mensajes predefinidos ─────────────────────────────────────────────────────
MENSAJES_PREDEFINIDOS = {
    "servidor_activo": {
        "titulo": "✅ **SERVIDOR ACTIVO**",
        "mensaje": "El servidor ha vuelto a estar en línea y está funcionando correctamente.",
        "color": "00FF00",
    },
    "servidor_caido": {
        "titulo": "❌ **SERVIDOR CAÍDO**",
        "mensaje": "El servidor está fuera de línea temporalmente. Estamos trabajando para solucionarlo.",
        "color": "FF0000",
    },
    "servidor_caera": {
        "titulo": "⚠️ **AVISO DE REINICIO**",
        "mensaje": "El servidor se reiniciará en {tiempo} .",
        "color": "FFA500",
    },
    "wipe_server": {
        "titulo": "🔄 **WIPE DEL SERVIDOR**",
        "mensaje": "Se realizará un wipe del servidor el {fecha}. ¡Prepárense para empezar de nuevo!",
        "color": "FF00FF",
    },
}


# ── Rutas Flask ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    try:
        if not os.path.exists(_HTML_PATH):
            return f"❌ Error: No se encuentra avisos.html en {_HTML_PATH}", 404
        with open(_HTML_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()
        return render_template_string(
            html_content,
            canales=CANALES,
            mensajes=MENSAJES_PREDEFINIDOS,
        )
    except Exception as e:
        return f"❌ Error al cargar la página: {str(e)}", 500


@app.route("/enviar_aviso", methods=["POST"])
def enviar_aviso():
    try:
        datos        = request.form
        tageo        = datos.get("tageo", "none")
        tageo_custom = datos.get("tageo_custom", "")
        canal_id     = datos["canal"]
        titulo       = datos["titulo"]
        mensaje      = datos["mensaje"]
        color        = datos.get("color", "8B0000")
        imagen_url   = datos.get("imagen_url", "")

        if not _bot or not _bot.is_ready():
            return jsonify({"error": "❌ Bot no conectado"}), 500

        canal = _bot.get_channel(int(canal_id))
        if not canal:
            return jsonify({"error": f"❌ Canal no encontrado: {canal_id}"}), 404

        tag_map = {"everyone": "@everyone", "here": "@here"}
        tag_texto = tag_map.get(tageo, tageo_custom if tageo == "custom" else "")
        mensaje_completo = f"{tag_texto}\n{mensaje}" if tag_texto else mensaje

        imagen_archivo = request.files.get("imagen")
        imagen_path    = None
        if imagen_archivo and imagen_archivo.filename:
            os.makedirs(_TEMP_DIR, exist_ok=True)
            filename    = f"{uuid.uuid4()}_{imagen_archivo.filename}"
            imagen_path = os.path.join(_TEMP_DIR, filename)
            imagen_archivo.save(imagen_path)

        asyncio.run_coroutine_threadsafe(
            _enviar_mensaje_discord(canal, titulo, mensaje_completo, color, imagen_url, imagen_path),
            _bot.loop,
        )
        return jsonify({"success": True, "message": "✅ Aviso preparado para enviar"})

    except Exception as e:
        return jsonify({"error": f"❌ Error: {str(e)}"}), 500


# ── Coroutine de envío ────────────────────────────────────────────────────────

async def _enviar_mensaje_discord(
    canal, titulo: str, mensaje: str, color: str,
    imagen_url: str = "", imagen_path: str | None = None,
):
    try:
        embed = discord.Embed(
            title=titulo,
            description=mensaje,
            color=int(color, 16),
        )
        if imagen_path and os.path.exists(imagen_path):
            try:
                file = discord.File(imagen_path, filename="imagen.png")
                embed.set_image(url="attachment://imagen.png")
                await canal.send(embed=embed, file=file)
                os.remove(imagen_path)
            except Exception as file_error:
                print(f"❌ Error al adjuntar imagen: {file_error}")
                if imagen_url:
                    embed.set_image(url=imagen_url)
                    await canal.send(embed=embed)
        elif imagen_url:
            embed.set_image(url=imagen_url)
            await canal.send(embed=embed)
        else:
            await canal.send(embed=embed)

        print(f"✅ Aviso enviado al canal {canal.name}")
        _limpiar_temp()

    except Exception as e:
        print(f"❌ Error al enviar mensaje a Discord: {e}")
        if imagen_path and os.path.exists(imagen_path):
            try:
                os.remove(imagen_path)
            except Exception:
                pass


def _limpiar_temp():
    if not os.path.exists(_TEMP_DIR):
        return
    try:
        for fname in os.listdir(_TEMP_DIR):
            fpath = os.path.join(_TEMP_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < time.time() - 300:
                os.remove(fpath)
    except Exception:
        pass


# ── Vistas Discord ────────────────────────────────────────────────────────────

def _es_mod(member: discord.Member) -> bool:
    """True si el miembro es owner o tiene alguno de los roles de CANALES/ROLES."""
    
    if member.guild and member.id == member.guild.owner_id:
        return True
    ids = {r.id for r in member.roles}
    return bool(ids & set(ROLES.values()))


class _VistaAcceso(discord.ui.View):
    """Vista efímera: botón para generar la URL temporal."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔗 Generar URL temporal", style=discord.ButtonStyle.success)
    async def generar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permiso.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            url = await asyncio.get_event_loop().run_in_executor(None, _abrir_tunel)
        except Exception as e:
            await interaction.followup.send(f"❌ Error al abrir el túnel: {e}", ephemeral=True)
            return

        minutos_restantes = max(1, int((_tunel_expira - time.time()) / 60))

        embed = discord.Embed(
            title="🔗 URL temporal generada",
            description=(
                f"**Accede al panel de avisos aquí:**\n\n"
                f"🌐 {url}\n\n"
                f"⏱️ Expira en **{minutos_restantes} min**.\n"
                f"🔒 No compartas este enlace."
            ),
            color=0x00AA55,
        )
        embed.set_footer(text="El túnel se cierra automáticamente al expirar.")

        button.disabled = True
        button.label    = "✅ URL generada"
        #await interaction.message.edit(view=self)
        await interaction.followup.send(embed=embed, ephemeral=True)


class _VistaAvisos(discord.ui.View):
    """Vista pública con botón de acceso al panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🛠️ Acceder al Panel",
        style=discord.ButtonStyle.danger,
        custom_id="avisos_panel_btn",
    )
    async def acceder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_mod(interaction.user):
            await interaction.response.send_message(
                "❌ Solo moderadores pueden acceder al panel de avisos.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔐 Acceso al Panel de Avisos",
            description=(
                "Pulsa el botón para generar una URL temporal y privada al panel web.\n\n"
                "📌 Solo visible para ti.\n"
                "⏱️ La URL dura **30 minutos** desde que la generas.\n"
                "🔄 Puedes generar una nueva cuando expire."
            ),
            color=0x8B0000,
        )
        await interaction.response.send_message(embed=embed, view=_VistaAcceso(), ephemeral=True)


# ── Registro del comando !avisos ──────────────────────────────────────────────

def registrar_comando(bot_instance) -> None:
    """
    Registra el comando !avisos en el bot.
    Llamar UNA vez desde on_ready() en main.py:

        web_avisos.registrar_comando(bot)
    """

    @bot_instance.command(name="avisos")
    async def cmd_avisos(ctx):
        if not _es_mod(ctx.author):
            return  # silencio total

        embed = discord.Embed(
            title="📢 Sistema de Avisos",
            description=(
                "Panel de gestión de avisos del servidor.\n\n"
                "Envía notificaciones a cualquier canal con embeds personalizados, "
                "imágenes, tageos y plantillas predefinidas.\n\n"
                "🔒 **Acceso restringido a Moderadores y Admins.**"
            ),
            color=0x8B0000,
        )
        embed.add_field(
            name="📋 Funciones disponibles",
            value=(
                "• Servidor activo / caído\n"
                "• Aviso de reinicio o wipe\n"
                "• Imagen adjunta o por URL\n"
                "• Tageo personalizado por canal"
            ),
            inline=False,
        )
        embed.set_footer(text="Pulsa el botón para obtener tu enlace de acceso.")
        await ctx.send(embed=embed, view=_VistaAvisos())


# ── Punto de entrada público ──────────────────────────────────────────────────

def iniciar_flask(bot_instance) -> None:
    """
    Arranca Flask en un hilo daemon.
    Llamar una sola vez desde on_ready() en main.py.
    """
    global _bot
    _bot = bot_instance

    os.makedirs(_TEMP_DIR, exist_ok=True)

    def _run():
        print("🌐 Servidor Flask en http://0.0.0.0:8080")
        app.run(debug=False, port=8080, host="0.0.0.0", use_reloader=False, threaded=True)

    threading.Thread(target=_run, daemon=True).start()