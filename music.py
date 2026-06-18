"""
music.py — Cog de música para Miner 7Days Bot
Comandos: !play, !song, !queue / !cola, !volume, !musicG
"""

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import yt_dlp
import asyncio
import imageio_ffmpeg
import json
import os
from config import ROLES, DESARROLLADOR_ID

# ── Rutas ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(BASE_DIR, "Cache")
QUEUE_FILE = os.path.join(CACHE_DIR, "music_queue.json")
PERMS_FILE = os.path.join(CACHE_DIR, "music_perms.json")
os.makedirs(CACHE_DIR, exist_ok=True)

# ── Constantes ─────────────────────────────────────────────────────────────
COLOR        = 0x8B0000
MAX_DURATION = 600  # 10 minutos en segundos
FFMPEG_EXE   = imageio_ffmpeg.get_ffmpeg_exe()

YTDLP_OPTS = {
    "quiet": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "cookiefile": os.path.join(BASE_DIR, "cookies.txt"),
    "format": "bestaudio/best",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "opus",
    }],
}
print(f"[DEBUG] cookiefile path: {os.path.join(BASE_DIR, 'cookies.txt')}")
print(f"[DEBUG] cookiefile exists: {os.path.exists(os.path.join(BASE_DIR, 'cookies.txt'))}")
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# ══════════════════════════════════════════════════════════════════════════
#  HELPERS JSON
# ══════════════════════════════════════════════════════════════════════════

def _cargar_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _guardar_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════════════════════════════════════
#  PERMISOS
# ══════════════════════════════════════════════════════════════════════════

def _sincronizar_roles(guild: discord.Guild) -> None:
    print(f"\n[PERMS] ═══════════════════════════════════════")
    print(f"[PERMS] _sincronizar_roles() → guild: {guild.name} (id={guild.id})")

    # ── 1. Asegurar archivo en disco ──────────────────────────────────────
    if not os.path.exists(PERMS_FILE):
        print(f"[PERMS] Archivo NO existe → creando en {PERMS_FILE}")
        _guardar_json(PERMS_FILE, {"usuarios": [], "por_rol": [], "denylist": []})
    else:
        print(f"[PERMS] Archivo existe en {PERMS_FILE}")

    with open(PERMS_FILE, "r", encoding="utf-8") as f:
        perms = json.load(f)
    print(f"[PERMS] Contenido actual del JSON: {json.dumps(perms)}")

    # ── 2. Recorrer roles definidos en config ─────────────────────────────
    actuales          = set()
    roles_encontrados = 0

    print(f"[PERMS] Roles definidos en config: {list(ROLES.keys())}")

    for key, role_id in ROLES.items():
        role = guild.get_role(role_id)
        if not role:
            print(f"[PERMS]   ✗ Rol '{key}' (id={role_id}) → NO encontrado en este guild")
            continue

        miembros = role.members
        print(f"[PERMS]   ✓ Rol '{key}' (id={role_id}) → encontrado | miembros: {len(miembros)}")
        for m in miembros:
            print(f"[PERMS]       + {m.display_name} (id={m.id})")
            actuales.add(m.id)

        roles_encontrados += 1

    # DESARROLLADOR_ID siempre en por_rol — simbólico e inexpulsable
    actuales.add(DESARROLLADOR_ID)
    print(f"[PERMS] Roles encontrados: {roles_encontrados} | IDs recolectados: {actuales}")
    print(f"[PERMS] -> DESARROLLADOR_ID={DESARROLLADOR_ID} incluido siempre (simbolico)")

    # ── 3. Guardar o salir ────────────────────────────────────────────────
    if roles_encontrados == 0:
        print(f"[PERMS] ⚠ Ningún rol encontrado en este guild → no se modifica por_rol")
        print(f"[PERMS] ═══════════════════════════════════════\n")
        return

    ya_en_lista = {int(u) for u in perms.get("por_rol", [])}

    nuevos = [uid for uid in actuales if uid not in ya_en_lista]
    for uid in nuevos:
        perms["por_rol"].append(uid)
        print(f"[PERMS] → Agregando nuevo uid={uid} a por_rol")

    antes = len(perms["por_rol"])
    perms["por_rol"] = [u for u in perms["por_rol"] if int(u) in actuales or int(u) == DESARROLLADOR_ID]
    despues = len(perms["por_rol"])
    if antes != despues:
        print(f"[PERMS] → Eliminados {antes - despues} uids que ya no tienen el rol")

    print(f"[PERMS] por_rol final: {perms['por_rol']}")
    print(f"[PERMS] Escribiendo en disco → {PERMS_FILE}")

    with open(PERMS_FILE, "w", encoding="utf-8") as f:
        json.dump(perms, f, ensure_ascii=False, indent=2)

    # Verificar que se escribió bien
    with open(PERMS_FILE, "r", encoding="utf-8") as f:
        verificacion = json.load(f)
    print(f"[PERMS] Verificación post-escritura: {json.dumps(verificacion)}")
    print(f"[PERMS] ═══════════════════════════════════════\n")


def _cargar_perms(guild: discord.Guild | None = None) -> dict:
    print(f"[PERMS] _cargar_perms() llamado | guild={'sí: ' + guild.name if guild else 'None'}")

    # Garantizar que el archivo existe en disco
    if not os.path.exists(PERMS_FILE):
        print(f"[PERMS] Archivo no existe → creando estructura vacía en disco")
        _guardar_json(PERMS_FILE, {"usuarios": [], "por_rol": [], "denylist": []})

    # Sincronizar roles al archivo antes de leer
    if guild is not None:
        _sincronizar_roles(guild)

    # Leer y devolver lo que está en disco — nunca un dict hardcodeado
    with open(PERMS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[PERMS] _cargar_perms() devuelve: {json.dumps(data)}")
    return data


def _guardar_perms(data: dict) -> None:
    _guardar_json(PERMS_FILE, data)


def _es_rol_musica(member: discord.Member) -> bool:
    """
    Comprueba si el miembro tiene algún rol de música en Discord.
    Usado SOLO para _tiene_permiso_gestion (gestión del bot).
    NO se usa para validar acceso a !play.
    """
    role_ids = {r.id for r in member.roles}
    return any(ROLES.get(r) in role_ids for r in ("ADMIN", "MOD", "Moderador"))


def _tiene_permiso_musica(member: discord.Member) -> bool:
    """
    Permiso para usar !play, !song, !queue, !volume.
    NADIE entra sin estar en el JSON — ni mods ni admins.
    Antes de revisar, sincroniza automáticamente los roles al JSON.
    """
    if member.id == DESARROLLADOR_ID:
        return True

    # Sincroniza roles al JSON y lee el estado actualizado
    perms = _cargar_perms(member.guild)

    # Vetado explícitamente → siempre denegado, sin importar roles
    if str(member.id) in [str(u) for u in perms.get("denylist", [])]:
        return False

    # Autorizado si está en por_rol (cargado desde roles) O en usuarios (manual)
    autorizados = (
        {str(u) for u in perms.get("por_rol", [])} |
        {str(u) for u in perms.get("usuarios",  [])}
    )
    return str(member.id) in autorizados


def _tiene_permiso_gestion(member: discord.Member) -> bool:
    """
    Permiso para gestionar el bot (saltar, quitar cola, panel de permisos).
    Aquí sí se comprueba el rol de Discord directamente — los mods
    siempre pueden gestionar aunque no hayan hecho !play nunca.
    """
    if member.id == DESARROLLADOR_ID:
        return True
    return _es_rol_musica(member)


def _puede_agregar_perms(actor: discord.Member) -> bool:
    """Solo ADMIN y DESARROLLADOR pueden agregar usuarios a la lista."""
    if actor.id == DESARROLLADOR_ID:
        return True
    return ROLES.get("ADMIN") in {r.id for r in actor.roles}


def _puede_modificar_perms(actor: discord.Member, target: discord.Member) -> bool:
    """ADMIN/DESARROLLADOR pueden quitar a cualquiera. MOD solo puede quitar usuarios normales."""
    if actor.id == DESARROLLADOR_ID:
        return True
    role_ids_actor  = {r.id for r in actor.roles}
    role_ids_target = {r.id for r in target.roles}
    es_admin      = ROLES.get("ADMIN") in role_ids_actor
    es_mod_target = any(ROLES.get(r) in role_ids_target for r in ("MOD", "Moderador", "ADMIN"))
    if es_admin:
        return True
    return not es_mod_target


def _listar_usuarios_con_acceso(guild: discord.Guild) -> list:
    """
    Lista todos los usuarios con acceso (por rol o manual).
    Sincroniza los roles antes de leer para mostrar datos actualizados.
    """
    perms    = _cargar_perms(guild)   # sincroniza antes de listar
    denylist = [str(u) for u in perms.get("denylist", [])]
    manuales = [str(u) for u in perms.get("usuarios",  [])]
    por_rol  = [str(u) for u in perms.get("por_rol",   [])]
    resultado = {}

    for uid in por_rol:
        m = guild.get_member(int(uid))
        resultado[uid] = {
            "id":     int(uid),
            "nombre": m.display_name if m else f"ID:{uid}",
            "tipo":   "rol",
            "vetado": uid in denylist,
        }

    for uid in manuales:
        if uid not in resultado:
            m = guild.get_member(int(uid))
            resultado[uid] = {
                "id":     int(uid),
                "nombre": m.display_name if m else f"ID:{uid}",
                "tipo":   "manual",
                "vetado": uid in denylist,
            }

    return list(resultado.values())

# ══════════════════════════════════════════════════════════════════════════
#  COLA JSON
# ══════════════════════════════════════════════════════════════════════════

def cola_cargar() -> list:
    return _cargar_json(QUEUE_FILE, [])

def cola_guardar(cola: list) -> None:
    _guardar_json(QUEUE_FILE, cola)

def cola_agregar(entry: dict) -> None:
    cola = cola_cargar()
    cola.append(entry)
    cola_guardar(cola)

def cola_quitar_primero() -> dict | None:
    cola = cola_cargar()
    if not cola:
        return None
    entry = cola.pop(0)
    cola_guardar(cola)
    return entry

def cola_eliminar_indice(idx: int) -> bool:
    cola = cola_cargar()
    if idx < 0 or idx >= len(cola):
        return False
    cola.pop(idx)
    cola_guardar(cola)
    return True

# ══════════════════════════════════════════════════════════════════════════
#  yt-dlp
# ══════════════════════════════════════════════════════════════════════════

def _extraer_info(query: str) -> dict:
    with yt_dlp.YoutubeDL(YTDLP_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return info

# ══════════════════════════════════════════════════════════════════════════
#  VIEWS
# ══════════════════════════════════════════════════════════════════════════

class PanelReproductor(View):
    """Panel efímero del mini reproductor — solo lo ve quien pidió la canción."""

    def __init__(self, cog: "Music", solicitante_id: int):
        super().__init__(timeout=None)
        self.cog            = cog
        self.solicitante_id = solicitante_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.solicitante_id:
            await interaction.response.send_message("❌ Este panel no es tuyo.", ephemeral=True)
            return False
        return True

    def _embed(self) -> discord.Embed:
        actual = self.cog.actual
        if not actual:
            return discord.Embed(description="No hay nada reproduciéndose.", color=COLOR)
        vc = self.cog._vc
        if vc and vc.is_playing():
            estado = "▶️ Reproduciendo"
        elif vc and vc.is_paused():
            estado = "⏸ Pausado"
        else:
            estado = "⏹ Detenido"
        m, s = divmod(actual.get("duracion", 0), 60)
        embed = discord.Embed(title="🎛 Mini Reproductor", color=COLOR)
        embed.add_field(name="🎵 Canción", value=f"[{actual['titulo']}]({actual['webpage']})", inline=False)
        embed.add_field(name="Estado",    value=estado, inline=True)
        embed.add_field(name="Duración",  value=f"{m}:{s:02d}", inline=True)
        embed.add_field(name="🔊 Volumen", value=f"{int(self.cog.volumen * 100)}%", inline=True)
        embed.set_footer(text=f"Pedida por {actual['solicitante_nombre']}")
        if actual.get("thumbnail"):
            embed.set_thumbnail(url=actual["thumbnail"])
        return embed

    @discord.ui.button(label="⏸ Pausar", style=discord.ButtonStyle.secondary, custom_id="repr_pause")
    async def pausar(self, interaction: discord.Interaction, button: Button):
        vc = self.cog._vc
        if vc and vc.is_playing():
            vc.pause()
            button.label = "▶️ Reanudar"
        elif vc and vc.is_paused():
            vc.resume()
            button.label = "⏸ Pausar"
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="⏹ Detener", style=discord.ButtonStyle.danger, custom_id="repr_stop")
    async def detener(self, interaction: discord.Interaction, button: Button):
        vc = self.cog._vc
        if vc:
            vc.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="⏹ Detenido.", color=COLOR), view=None
        )

    @discord.ui.button(label="🔉 -10%", style=discord.ButtonStyle.secondary, custom_id="repr_vol_down")
    async def vol_down(self, interaction: discord.Interaction, button: Button):
        self.cog.volumen = max(0.0, self.cog.volumen - 0.1)
        if self.cog._vc and self.cog._vc.source:
            self.cog._vc.source.volume = self.cog.volumen
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="🔊 +10%", style=discord.ButtonStyle.secondary, custom_id="repr_vol_up")
    async def vol_up(self, interaction: discord.Interaction, button: Button):
        self.cog.volumen = min(2.0, self.cog.volumen + 0.1)
        if self.cog._vc and self.cog._vc.source:
            self.cog._vc.source.volume = self.cog.volumen
        await interaction.response.edit_message(embed=self._embed(), view=self)


class BotonAbrirPanel(View):
    """Mensaje público con el botón para abrir el panel efímero."""

    def __init__(self, cog: "Music", solicitante_id: int):
        super().__init__(timeout=None)
        self.cog            = cog
        self.solicitante_id = solicitante_id

    @discord.ui.button(label="🎛 Abrir mi panel", style=discord.ButtonStyle.primary, custom_id="abrir_panel")
    async def abrir(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.solicitante_id:
            await interaction.response.send_message("❌ Este panel no es tuyo.", ephemeral=True)
            return
        view  = PanelReproductor(self.cog, self.solicitante_id)
        embed = view._embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ── Modal agregar usuario ──────────────────────────────────────────────────

class ModalAgregarUsuario(Modal, title="Agregar usuario a música"):
    entrada = TextInput(
        label="Nombre de usuario o ID de Discord",
        placeholder="ejemplo: pancho  o  123456789012345678",
        max_length=100,
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        valor  = self.entrada.value.strip()
        guild  = interaction.guild
        member = None

        if valor.isdigit():
            member = guild.get_member(int(valor))
        else:
            member = discord.utils.find(
                lambda m: m.name.lower() == valor.lower() or m.display_name.lower() == valor.lower(),
                guild.members,
            )

        if not member:
            await interaction.response.send_message(
                f"❌ No encontré a `{valor}` en el servidor.", ephemeral=True
            )
            return

        # Lee sin sincronizar — solo consulta la lista manual
        perms = _cargar_perms()
        if str(member.id) in [str(u) for u in perms.get("usuarios", [])]:
            await interaction.response.send_message(
                f"⚠️ `{member.display_name}` ya tiene permiso.", ephemeral=True
            )
            return

        perms["usuarios"].append(member.id)
        _guardar_perms(perms)
        await interaction.response.send_message(
            f"✅ `{member.display_name}` agregado.", ephemeral=True
        )


# ── Panel de permisos ──────────────────────────────────────────────────────

class PanelPermisos(View):

    def __init__(self, cog: "Music", actor: discord.Member):
        super().__init__(timeout=None)
        self.cog   = cog
        self.actor = actor

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _tiene_permiso_gestion(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return False
        return True

    def _embed(self, guild: discord.Guild) -> discord.Embed:
        embed    = discord.Embed(title="🔐 Permisos de Música", color=COLOR)
        usuarios = _listar_usuarios_con_acceso(guild)
        lineas   = []
        for u in usuarios:
            tipo  = "🎭 rol" if u["tipo"] == "rol" else "✋ manual"
            veto  = " ~~vetado~~" if u["vetado"] else ""
            lineas.append(f"• **{u['nombre']}** ({tipo}){veto} — `{u['id']}`")
        embed.description = "\n".join(lineas) if lineas else "No hay usuarios con acceso."
        embed.set_footer(text="🎭 = acceso por rol  |  ✋ = añadido manualmente")
        return embed

    @discord.ui.button(label="➕ Agregar", style=discord.ButtonStyle.success, custom_id="perms_add")
    async def agregar(self, interaction: discord.Interaction, button: Button):
        if not _puede_agregar_perms(interaction.user):
            await interaction.response.send_message(
                "❌ Solo los **Admin** pueden agregar usuarios a la lista.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ModalAgregarUsuario(self.cog))

    @discord.ui.button(label="➖ Quitar / Vetar", style=discord.ButtonStyle.danger, custom_id="perms_remove")
    async def quitar(self, interaction: discord.Interaction, button: Button):
        guild    = interaction.guild
        usuarios = _listar_usuarios_con_acceso(guild)
        if not usuarios:
            await interaction.response.send_message("⚠️ No hay usuarios con acceso.", ephemeral=True)
            return

        opciones = []
        for u in usuarios:
            if u["id"] == interaction.user.id:
                continue  # no puedes quitarte a ti mismo
            if u["id"] == DESARROLLADOR_ID:
                continue  # el desarrollador es inexpulsable
            target = guild.get_member(u["id"])
            if target and not _puede_modificar_perms(interaction.user, target):
                continue  # sin permiso para quitarlo, no lo muestres
            estado = " [vetado]" if u["vetado"] else ""
            opciones.append(discord.SelectOption(
                label=f"{u['nombre']}{estado}"[:100],
                description=f"Acceso por {u['tipo']}",
                value=str(u["id"]),
            ))

        if not opciones:
            await interaction.response.send_message("⚠️ No hay usuarios que puedas quitar.", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="Selecciona a quien quitar...", options=opciones)

        async def _cb(inter: discord.Interaction):
            uid_q  = int(select.values[0])
            target = guild.get_member(uid_q)
            p      = _cargar_perms()

            if target and _es_rol_musica(target):
                # Tiene rol: lo agrega a la denylist para revocarle acceso
                if str(uid_q) not in [str(x) for x in p.get("denylist", [])]:
                    p.setdefault("denylist", []).append(uid_q)
                msg = f"✅ `{target.display_name}` vetado — ya no puede usar música aunque tenga el rol."
            else:
                # Es manual: simplemente se quita de la lista
                p["usuarios"] = [u for u in p.get("usuarios", []) if str(u) != str(uid_q)]
                nombre = target.display_name if target else str(uid_q)
                msg = f"✅ `{nombre}` quitado de la lista."

            _guardar_perms(p)
            await inter.response.send_message(msg, ephemeral=True)

        select.callback = _cb
        v = View(timeout=None)
        v.add_item(select)
        await interaction.response.send_message(view=v, ephemeral=True)

    @discord.ui.button(label="🚫 Ver vetados", style=discord.ButtonStyle.danger, custom_id="perms_denylist")
    async def ver_vetados(self, interaction: discord.Interaction, button: Button):
        if not _puede_agregar_perms(interaction.user):
            await interaction.response.send_message(
                "❌ Solo **Admin** puede gestionar la lista de vetados.", ephemeral=True
            )
            return
        view  = PanelDenylist(self.cog)
        embed = view._embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔄 Actualizar", style=discord.ButtonStyle.secondary, custom_id="perms_refresh")
    async def refrescar(self, interaction: discord.Interaction, button: Button):
        _sincronizar_roles(interaction.guild)
        await interaction.response.edit_message(embed=self._embed(interaction.guild), view=self)


# ── Panel denylist ─────────────────────────────────────────────────────────

class PanelDenylist(View):
    """Panel efímero que muestra la lista de vetados y permite restaurar acceso."""

    def __init__(self, cog: "Music"):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _puede_agregar_perms(interaction.user):
            await interaction.response.send_message("🔒 Solo Admin puede gestionar vetados.", ephemeral=True)
            return False
        return True

    def _embed(self, guild: discord.Guild) -> discord.Embed:
        perms    = _cargar_perms()
        denylist = perms.get("denylist", [])
        embed    = discord.Embed(title="🚫 Usuarios Vetados", color=COLOR)
        if not denylist:
            embed.description = "No hay usuarios vetados."
        else:
            lineas = []
            for uid in denylist:
                m      = guild.get_member(int(uid))
                nombre = m.display_name if m else f"ID:{uid}"
                lineas.append(f"🚫 **{nombre}** — `{uid}`")
            embed.description = "\n".join(lineas)
        embed.set_footer(text="Selecciona un usuario para restaurarle el acceso.")
        return embed

    @discord.ui.button(label="↩️ Restaurar acceso", style=discord.ButtonStyle.success, custom_id="deny_restore")
    async def restaurar(self, interaction: discord.Interaction, button: Button):
        perms    = _cargar_perms()
        denylist = perms.get("denylist", [])
        if not denylist:
            await interaction.response.send_message("⚠️ No hay usuarios vetados.", ephemeral=True)
            return
        guild    = interaction.guild
        opciones = []
        for uid in denylist:
            m      = guild.get_member(int(uid))
            nombre = m.display_name if m else f"ID:{uid}"
            opciones.append(discord.SelectOption(label=nombre[:100], value=str(uid)))

        select = discord.ui.Select(placeholder="Restaurar acceso a...", options=opciones)

        async def _cb(inter: discord.Interaction):
            uid_r = str(select.values[0])
            p     = _cargar_perms()
            p["denylist"] = [u for u in p.get("denylist", []) if str(u) != uid_r]
            _guardar_perms(p)
            # Actualiza el embed del panel
            await inter.response.edit_message(embed=self._embed(guild), view=self)

        select.callback = _cb
        v = View(timeout=None)
        v.add_item(select)
        await interaction.response.send_message(view=v, ephemeral=True)

    @discord.ui.button(label="🔄 Actualizar", style=discord.ButtonStyle.secondary, custom_id="deny_refresh")
    async def refrescar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=self._embed(interaction.guild), view=self)


# ── Botón único público para !musicG ──────────────────────────────────────

class BotonGestion(View):
    """Botón público único — abre el panel de gestión en mensaje efímero."""

    def __init__(self, cog: "Music"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🎛 Gestión de Música", style=discord.ButtonStyle.primary, custom_id="abrir_gestion")
    async def abrir(self, interaction: discord.Interaction, button: Button):
        if not _tiene_permiso_gestion(interaction.user):
            await interaction.response.send_message(
                "🔒 Solo **Mods** y **Admin** pueden abrir el panel de gestión.", ephemeral=True
            )
            return
        view  = PanelGestion(self.cog)
        embed = view._embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ── Panel gestión !musicG ──────────────────────────────────────────────────

class PanelGestion(View):

    def __init__(self, cog: "Music"):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _tiene_permiso_gestion(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return False
        return True

    def _embed(self) -> discord.Embed:
        embed  = discord.Embed(title="🎛 Gestión de Música", color=COLOR)
        actual = self.cog.actual
        embed.add_field(
            name="▶️ Reproduciendo ahora",
            value=f"[{actual['titulo']}]({actual['webpage']}) — **{actual['solicitante_nombre']}**"
            if actual else "Nada",
            inline=False,
        )
        cola   = cola_cargar()
        if cola:
            lineas = [
                f"`{i+1}.` [{e['titulo']}]({e['webpage']}) — {e['solicitante_nombre']}"
                for i, e in enumerate(cola)
            ]
            embed.add_field(name="📋 Cola", value="\n".join(lineas), inline=False)
        else:
            embed.add_field(name="📋 Cola", value="Vacía", inline=False)
        return embed

    @discord.ui.button(label="⏭ Saltar actual", style=discord.ButtonStyle.danger, custom_id="gest_skip")
    async def saltar(self, interaction: discord.Interaction, button: Button):
        vc = self.cog._vc
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.edit_message(embed=self._embed(), view=self)
        else:
            await interaction.response.send_message("⚠️ No hay nada reproduciéndose.", ephemeral=True)

    @discord.ui.button(label="🗑 Quitar de cola", style=discord.ButtonStyle.secondary, custom_id="gest_del")
    async def quitar_cola(self, interaction: discord.Interaction, button: Button):
        cola = cola_cargar()
        if not cola:
            await interaction.response.send_message("⚠️ La cola está vacía.", ephemeral=True)
            return

        opciones = [
            discord.SelectOption(
                label=f"{i+1}. {e['titulo'][:50]}",
                description=f"Pedida por {e['solicitante_nombre']}",
                value=str(i),
            )
            for i, e in enumerate(cola)
        ]

        select = discord.ui.Select(placeholder="Selecciona canción a quitar...", options=opciones)

        async def _cb(inter: discord.Interaction):
            idx   = int(select.values[0])
            cola2 = cola_cargar()
            if idx < len(cola2):
                titulo = cola2[idx]["titulo"]
                cola_eliminar_indice(idx)
                await inter.response.send_message(f"✅ `{titulo}` quitada de la cola.", ephemeral=True)
            else:
                await inter.response.send_message("⚠️ Esa canción ya no está en la cola.", ephemeral=True)

        select.callback = _cb
        v = View(timeout=None)
        v.add_item(select)
        await interaction.response.send_message(view=v, ephemeral=True)

    @discord.ui.button(label="🔐 Permisos", style=discord.ButtonStyle.primary, custom_id="gest_perms")
    async def ver_permisos(self, interaction: discord.Interaction, button: Button):
        _sincronizar_roles(interaction.guild)
        view  = PanelPermisos(self.cog, interaction.user)
        embed = view._embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔄 Actualizar", style=discord.ButtonStyle.secondary, custom_id="gest_refresh")
    async def refrescar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=self._embed(), view=self)


# ══════════════════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════════════════

class Music(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot         = bot
        self.actual      = None                       # dict de la canción en curso
        self.volumen     = 1.0                        # 0.0 – 2.0
        self._vc: discord.VoiceClient | None = None
        self._msg_pub: discord.Message | None = None  # mensaje público con botón panel
        self._procesando = False

    async def cog_load(self):
        """Al cargar el cog, espera a que el bot esté listo y sincroniza roles."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            _sincronizar_roles(guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Re-sincroniza si alguien gana o pierde un rol de música."""
        if before.roles != after.roles:
            _sincronizar_roles(after.guild)

    # ── Permiso base ───────────────────────────────────────────────────────

    async def _check_permiso(self, ctx: commands.Context) -> bool:
        if not _tiene_permiso_musica(ctx.author):
            await ctx.send(embed=discord.Embed(
                description="🔒 No tienes permiso para usar los comandos de música.", color=COLOR,
            ))
            return False
        return True

    # ── Conexión al canal de voz ───────────────────────────────────────────

    async def _get_vc(self, ctx: commands.Context) -> discord.VoiceClient | None:
        if not ctx.author.voice:
            await ctx.send(embed=discord.Embed(
                description="❌ Debes estar en un canal de voz.", color=COLOR,
            ))
            return None
        canal = ctx.author.voice.channel
        if self._vc is None or not self._vc.is_connected():
            self._vc = await canal.connect()
        elif self._vc.channel != canal:
            await self._vc.move_to(canal)
        return self._vc

    # ── Motor de reproducción ──────────────────────────────────────────────

    async def _reproducir_siguiente(self, canal_texto: discord.TextChannel):
        if self._procesando:
            return
        self._procesando = True

        entry = cola_quitar_primero()
        if not entry:
            self.actual      = None
            self._procesando = False
            if self._msg_pub:
                try:
                    await self._msg_pub.delete()
                except Exception:
                    pass
                self._msg_pub = None
            return

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(None, _extraer_info, entry["webpage"])
        except Exception as e:
            await canal_texto.send(embed=discord.Embed(
                description=f"❌ Error al extraer audio: `{e}`", color=COLOR,
            ))
            self._procesando = False
            await self._reproducir_siguiente(canal_texto)
            return

        self.actual = {
            "titulo":            info.get("title", "Desconocido"),
            "webpage":           info.get("webpage_url", entry["webpage"]),
            "duracion":          info.get("duration", 0),
            "thumbnail":         info.get("thumbnail"),
            "solicitante_id":    entry["solicitante_id"],
            "solicitante_nombre": entry["solicitante_nombre"],
        }

        fuente = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(info["url"], executable=FFMPEG_EXE, **FFMPEG_OPTS),
            volume=self.volumen,
        )

        def _after(error):
            self.actual      = None
            self._procesando = False
            asyncio.run_coroutine_threadsafe(
                self._reproducir_siguiente(canal_texto), self.bot.loop
            )

        self._vc.play(fuente, after=_after)

        # Eliminar mensaje anterior si existe
        if self._msg_pub:
            try:
                await self._msg_pub.delete()
            except Exception:
                pass

        m, s = divmod(self.actual["duracion"], 60)
        embed = discord.Embed(title="▶️ Reproduciendo ahora", color=COLOR)
        embed.add_field(name="🎵 Canción",  value=f"[{self.actual['titulo']}]({self.actual['webpage']})", inline=False)
        embed.add_field(name="⏱ Duración", value=f"{m}:{s:02d}", inline=True)
        embed.add_field(name="👤 Pedida por", value=self.actual["solicitante_nombre"], inline=True)
        if self.actual.get("thumbnail"):
            embed.set_thumbnail(url=self.actual["thumbnail"])

        view          = BotonAbrirPanel(self, entry["solicitante_id"])
        self._msg_pub = await canal_texto.send(embed=embed, view=view)
        self._procesando = False

    # ── Comandos ───────────────────────────────────────────────────────────

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str):
        """Agrega una canción a la cola. Máx. 10 minutos."""
        if not await self._check_permiso(ctx):
            return

        vc = await self._get_vc(ctx)
        if vc is None:
            return

        msg = await ctx.send(embed=discord.Embed(
            description="🔍 Buscando información del audio...", color=COLOR,
        ))

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(None, _extraer_info, query)
        except Exception as e:
            await msg.edit(embed=discord.Embed(
                title="❌ Error al buscar", description=f"```{e}```", color=COLOR,
            ))
            return

        duracion = info.get("duration", 0)
        if duracion > MAX_DURATION:
            await msg.edit(embed=discord.Embed(
                title="❌ Video demasiado largo",
                description=f"Límite: **10 minutos**. Este dura `{duracion // 60}:{duracion % 60:02d}`.",
                color=COLOR,
            ))
            return

        entry = {
            "titulo":            info.get("title", "Desconocido"),
            "webpage":           info.get("webpage_url", query),
            "thumbnail":         info.get("thumbnail"),
            "duracion":          duracion,
            "solicitante_id":    ctx.author.id,
            "solicitante_nombre": ctx.author.display_name,
        }
        cola_agregar(entry)

        m, s = divmod(duracion, 60)
        embed = discord.Embed(title="✅ Canción agregada a la cola", color=COLOR)
        embed.add_field(name="🎵", value=f"[{entry['titulo']}]({entry['webpage']})", inline=False)
        embed.add_field(name="⏱ Duración", value=f"{m}:{s:02d}", inline=True)
        embed.set_footer(text=f"Pedida por {ctx.author.display_name}")
        if entry.get("thumbnail"):
            embed.set_thumbnail(url=entry["thumbnail"])
        await msg.edit(embed=embed)

        if not vc.is_playing() and not vc.is_paused():
            await self._reproducir_siguiente(ctx.channel)

    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx: commands.Context, valor: int):
        """Ajusta el volumen (0-200). Solo quien pidió la canción actual."""
        if not await self._check_permiso(ctx):
            return
        if self.actual and ctx.author.id != self.actual["solicitante_id"]:
            await ctx.send(embed=discord.Embed(
                description="❌ Solo quien pidió la canción puede cambiar el volumen.", color=COLOR,
            ))
            return
        valor        = max(0, min(200, valor))
        self.volumen = valor / 100
        if self._vc and self._vc.source:
            self._vc.source.volume = self.volumen
        await ctx.send(embed=discord.Embed(
            description=f"🔊 Volumen ajustado a **{valor}%**", color=COLOR,
        ))

    @commands.command(name="song")
    async def song(self, ctx: commands.Context):
        """Muestra la canción actual."""
        if not await self._check_permiso(ctx):
            return
        if not self.actual:
            await ctx.send(embed=discord.Embed(
                description="🎵 No hay ninguna canción reproduciéndose.", color=COLOR,
            ))
            return
        vc     = self._vc
        estado = "▶️ Reproduciendo" if (vc and vc.is_playing()) else "⏸ Pausado"
        m, s   = divmod(self.actual["duracion"], 60)
        embed  = discord.Embed(title="🎵 Canción actual", color=COLOR)
        embed.add_field(name="Título",     value=f"[{self.actual['titulo']}]({self.actual['webpage']})", inline=False)
        embed.add_field(name="Estado",     value=estado, inline=True)
        embed.add_field(name="Duración",   value=f"{m}:{s:02d}", inline=True)
        embed.add_field(name="Volumen",    value=f"{int(self.volumen * 100)}%", inline=True)
        embed.add_field(name="Pedida por", value=self.actual["solicitante_nombre"], inline=True)
        if self.actual.get("thumbnail"):
            embed.set_thumbnail(url=self.actual["thumbnail"])
        await ctx.send(embed=embed)

    @commands.command(name="queue", aliases=["cola", "q"])
    async def queue(self, ctx: commands.Context):
        """Muestra la cola de canciones."""
        if not await self._check_permiso(ctx):
            return
        cola  = cola_cargar()
        embed = discord.Embed(title="📋 Cola de canciones", color=COLOR)
        if self.actual:
            embed.add_field(
                name="▶️ Ahora",
                value=f"[{self.actual['titulo']}]({self.actual['webpage']}) — {self.actual['solicitante_nombre']}",
                inline=False,
            )
        if not cola:
            embed.add_field(name="En cola", value="No hay canciones en cola.", inline=False)
        else:
            lineas = [
                f"`{i+1}.` [{e['titulo']}]({e['webpage']}) — {e['solicitante_nombre']}"
                for i, e in enumerate(cola)
            ]
            embed.add_field(name="En cola", value="\n".join(lineas), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="musicG")
    async def musicG(self, ctx: commands.Context):
        """Publica el botón de gestión de música. Solo Mods y Admin."""
        if not _tiene_permiso_gestion(ctx.author):
            return
        embed = discord.Embed(
            title="🎛 Panel de Gestión de Música",
            description="Solo **Mods** y **Admin** pueden abrir el panel.",
            color=COLOR,
        )
        await ctx.send(embed=embed, view=BotonGestion(self))

    # ── Errores ────────────────────────────────────────────────────────────

    @play.error
    async def play_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(
                title="❌ Falta la URL o el nombre",
                description="Uso: `!play <url o nombre de canción>`",
                color=COLOR,
            ))
        else:
            raise error

    @volume.error
    async def volume_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=discord.Embed(
                description="❌ Uso correcto: `!volume 50` (número entre 0 y 200)", color=COLOR,
            ))
        else:
            raise error


# ── Setup ──────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
