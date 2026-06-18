# ============================================================
#  wipe.py  —  Sistema de Gestión de Wipe  •  Miner 7Days Bot
# ============================================================
#
#  Comandos:
#    !wipeG  — Panel de gestión (solo moderadores)
#    !wipe   — Muestra la cuenta atrás pública
#
#  Para activar, añade en on_ready() de main.py:
#    if "wipe" not in bot.extensions:
#        await bot.load_extension("wipe")
# ============================================================

import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
import time
from datetime import datetime, timezone, timedelta
import pytz
from config import CANALES as _CFG_CANALES
from config import ROLES                  
import ntplib
import asyncio as _asyncio
import pytz as _pytz
# ─── CONFIGURACIÓN ──────────────────────────────────────────────────────────
#  ↓ Cambia este ID por el canal donde quieres los avisos de wipe
CANAL_AVISOS_ID: int = _CFG_CANALES["wipe_avisos"]   # 7days-info

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
WIPE_JSON = os.path.join(BASE_DIR, "Cache", "wipe.json")
TIME_CACHE_JSON = os.path.join(BASE_DIR, "Cache", "time_cache.json")

TZ_ES = "Europe/Madrid"

# Zonas horarias que se guardan en time_cache.json como referencia
_ZONAS_CACHE = {
    "España":    "Europe/Madrid",
    "México":    "America/Mexico_City",
    "Colombia":  "America/Bogota",
    "Argentina": "America/Argentina/Buenos_Aires",
}

# ─── MENSAJES ACTIVOS DE CUENTA ATRÁS ───────────────────────────────────────
#  El loop de actualización en tiempo real busca aquí los mensajes a editar.
#  Estructura: { message_id: {"msg": discord.Message, "autor": discord.Member,
#                             "tz_str": str, "tz_label": str} }
_wipe_msgs: dict = {}

# Referencia al loop del cog — se asigna en cog_load
_loop_ref = None

def _loop_arrancar():
    """Arranca el loop solo si no está corriendo ya."""
    if _loop_ref and not _loop_ref.is_running():
        _loop_ref.start()

def _loop_parar():
    """Para el loop y limpia los mensajes registrados."""
    global _wipe_msgs
    _wipe_msgs.clear()
    if _loop_ref and _loop_ref.is_running():
        _loop_ref.stop()

# ─── CACHÉ DE TIEMPO (en memoria) ───────────────────────────────────────────
#  dt_utc : último datetime UTC obtenido de una API externa
#  mono   : valor de time.monotonic() en ese momento
#  Con ambos podemos estimar la hora actual sin tocar el reloj de Windows:
#    ahora_utc ≈ dt_utc + timedelta(seconds=time.monotonic() - mono)
_tcache: dict = {"dt_utc": None, "mono": None}

# ─── PERMISOS ────────────────────────────────────────────────────────────────
def _tiene_permiso(member: discord.Member) -> bool:
    ids_miembro = {r.id for r in member.roles}
    return bool(ids_miembro & set(ROLES.values()))

# ─── WIPE.JSON ───────────────────────────────────────────────────────────────
def _leer_wipe() -> dict | None:
    """Devuelve el wipe activo o None si no existe / está inactivo."""
    if not os.path.exists(WIPE_JSON):
        return None
    try:
        with open(WIPE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data.get("active") else None
    except Exception:
        return None

def _guardar_wipe(wipe_utc_iso: str, created_at_iso: str | None = None) -> None:
    """Guarda (o sobreescribe) el wipe activo en cache/wipe.json."""
    # La carpeta cache debe existir; si no, la crea
    cache_dir = os.path.dirname(WIPE_JSON)
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    data = {
        "active":     True,
        "wipe_utc":   wipe_utc_iso,
        "created_at": created_at_iso,  # Siempre viene desde la API, nunca del reloj local
    }
    with open(WIPE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[WIPE] JSON actualizado → {WIPE_JSON}")

def _desactivar_wipe() -> None:
    """Marca el wipe como inactivo sin borrar el registro histórico."""
    if not os.path.exists(WIPE_JSON):
        return
    try:
        with open(WIPE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["active"] = False
        with open(WIPE_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[WIPE] Wipe desactivado en JSON.")
    except Exception as e:
        print(f"[WIPE] Error al desactivar: {e}")

# ─── TIEMPO REAL — MULTI-API + NTP + CACHÉ (sin reloj de Windows) ───────────
#
#  Fuentes en orden:
#    1. worldtimeapi.org
#    2. timeapi.io
#    3. worldclockapi.com
#    4. NTP pool.ntp.org  (pip install ntplib)
#
#  Si todas fallan se usa la caché:
#    A) Caché en memoria  →  dt_utc + segundos transcurridos via time.monotonic()
#       time.monotonic() NO es el reloj de Windows; es un contador interno
#       del proceso que solo mide tiempo transcurrido desde que arrancó Python.
#    B) Caché en disco    →  útil tras reiniciar el bot
#
#  Si no hay caché de ningún tipo se lanza _NoTimeError.
#  El comando !wipe captura eso y muestra la fecha sin cuenta atrás,
#  sin mostrar ningún error al usuario.

class _NoTimeError(Exception):
    """No se pudo obtener la hora de ninguna fuente ni de la caché."""

_TIME_APIS = [
    {
        "name":  "worldtimeapi.org",
        "url":   "https://worldtimeapi.org/api/timezone/UTC",
        "parse": lambda d: datetime.fromtimestamp(d["unixtime"], tz=timezone.utc),
    },
    {
        "name":  "timeapi.io",
        "url":   "https://timeapi.io/api/time/current/zone?timeZone=UTC",
        "parse": lambda d: datetime(
            d["year"], d["month"], d["day"],
            d["hour"], d["minute"], d["seconds"],
            tzinfo=timezone.utc,
        ),
    },
    {
        "name":  "worldclockapi.com",
        "url":   "http://worldclockapi.com/api/json/utc/now",
        "parse": lambda d: datetime.strptime(
            d["currentDateTime"], "%Y-%m-%dT%H:%MZ"
        ).replace(tzinfo=timezone.utc),
    },
]
_API_TIMEOUT = aiohttp.ClientTimeout(total=5)


def _tcache_guardar(dt_utc: datetime) -> None:
    """Actualiza la caché en memoria y persiste en disco.
    Guarda UTC + las variantes de España, México, Colombia y Argentina.
    El archivo se crea automáticamente si no existe.
    """
    _tcache["dt_utc"] = dt_utc
    _tcache["mono"]   = time.monotonic()
    try:
        os.makedirs(os.path.dirname(TIME_CACHE_JSON), exist_ok=True)
        payload: dict = {"utc_iso": dt_utc.isoformat()}
        for label, tz_str in _ZONAS_CACHE.items():
            try:
                tz = pytz.timezone(tz_str)
                payload[label] = dt_utc.astimezone(tz).isoformat()
            except Exception:
                pass  # Si una zona falla no rompemos el resto
        with open(TIME_CACHE_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WIPE][TIME] No se pudo guardar time_cache.json: {e}")


def _tcache_leer_disco() -> "datetime | None":
    """Lee la última hora conocida del disco (para cuando el bot reinicia)."""
    try:
        with open(TIME_CACHE_JSON, "r", encoding="utf-8") as f:
            return datetime.fromisoformat(json.load(f)["utc_iso"])
    except Exception:
        return None


async def _hora_utc_api() -> datetime:
    """
    Devuelve la hora UTC actual desde fuentes externas.
    Nunca usa el reloj de Windows. Lanza _NoTimeError si todo falla.
    """
    # ── 1-3. APIs HTTP ───────────────────────────────────────
    async with aiohttp.ClientSession() as session:
        for api in _TIME_APIS:
            try:
                async with session.get(api["url"], timeout=_API_TIMEOUT, ssl=True) as r:
                    if r.status != 200:
                        raise ValueError(f"HTTP {r.status}")
                    data = await r.json(content_type=None)
                    dt = api["parse"](data)
                    _tcache_guardar(dt)
                    print(f"[WIPE][TIME] OK → {api['name']}")
                    return dt
            except Exception as e:
                print(f"[WIPE][TIME] {api['name']} falló: {e}")

    # ── 4. NTP ───────────────────────────────────────────────
    try:
        

        def _ntp() -> datetime:
            c = ntplib.NTPClient()
            r = c.request("pool.ntp.org", version=3, timeout=5)
            return datetime.fromtimestamp(r.tx_time, tz=timezone.utc)

        dt = await _asyncio.get_event_loop().run_in_executor(None, _ntp)
        _tcache_guardar(dt)
        print("[WIPE][TIME] OK → NTP pool.ntp.org")
        return dt
    except Exception as e:
        print(f"[WIPE][TIME] NTP falló: {e}")

    # ── 5A. Caché en memoria + monotonic ────────────────────
    #  time.monotonic() mide segundos transcurridos en el proceso,
    #  NO depende del reloj de Windows ni de NTP.
    if _tcache["dt_utc"] is not None:
        elapsed = time.monotonic() - _tcache["mono"]
        dt = _tcache["dt_utc"] + timedelta(seconds=elapsed)
        print(f"[WIPE][TIME] Usando caché memoria (+{elapsed:.0f}s)")
        return dt

    # ── 5B. Caché en disco (tras reinicio del bot) ───────────
    dt_disco = _tcache_leer_disco()
    if dt_disco is not None:
        _tcache["dt_utc"] = dt_disco
        _tcache["mono"]   = time.monotonic()
        print("[WIPE][TIME] Usando caché disco (reinicio detectado)")
        return dt_disco

    # ── Sin ninguna fuente — lanzar error interno ────────────
    raise _NoTimeError()

# ─── UTILIDADES DE CÁLCULO Y FORMATO ────────────────────────────────────────
def _cuenta_atras(wipe_utc: datetime, ahora_utc: datetime) -> tuple[str, bool]:
    """
    Devuelve (texto_cuenta_atras, ya_terminó).
    """
    diff = wipe_utc - ahora_utc
    if diff.total_seconds() <= 0:
        return "¡El wipe ya debería haber ocurrido!", True
    s = int(diff.total_seconds())
    d, r   = divmod(s, 86400)
    h, r   = divmod(r, 3600)
    m, s   = divmod(r, 60)
    partes = []
    if d: partes.append(f"{d}d")
    if h: partes.append(f"{h}h")
    if m: partes.append(f"{m}min")
    partes.append(f"{s}seg")
    return " ".join(partes), False

def _fmt_fecha_tz(wipe_utc: datetime, tz_str: str) -> str:
    try:
        tz = pytz.timezone(tz_str)
        return wipe_utc.astimezone(tz).strftime("%d/%m/%Y a las %H:%M")
    except Exception:
        return wipe_utc.strftime("%d/%m/%Y %H:%M UTC")

# ─── CONSTRUCTORES DE EMBEDS ─────────────────────────────────────────────────
def _embed_wipe_publico(
    wipe: dict,
    ahora_utc: "datetime | None",   # None cuando todas las fuentes de tiempo fallan
    tz_str: str,
    tz_label: str,
    autor: discord.Member,
) -> discord.Embed:
    """Embed del !wipe para el canal público."""
    wipe_utc    = datetime.fromisoformat(wipe["wipe_utc"])
    fecha_local = _fmt_fecha_tz(wipe_utc, tz_str)

    embed = discord.Embed(
        title="🔄 **WIPE DEL SERVIDOR**",
        description=(
            f"**Hey! {autor.mention}**\n"
            "¡Se acerca el wipe! Prepárate para empezar de nuevo."
        ),
        color=0xFF4500,
    )
    embed.add_field(
        name=f"📅 Fecha del Wipe ({tz_label})",
        value=f"```{fecha_local}```",
        inline=False,
    )

    if ahora_utc is None:
        # No hay hora verificada — mostrar la fecha sin cuenta atrás, sin errores
        embed.add_field(
            name="⏳ Cuenta Atrás",
            value="```⏳ Sincronizando hora...```",
            inline=False,
        )
        embed.set_footer(text="7 Days to Die • Selecciona tu zona horaria 👇")
    else:
        cuenta, pasado = _cuenta_atras(wipe_utc, ahora_utc)
        if pasado:
            embed.add_field(
                name="⏳ Cuenta Atrás",
                value="```🔔 ¡El wipe ya debería haber ocurrido!```",
                inline=False,
            )
        else:
            embed.add_field(
                name="⏳ Cuenta Atrás",
                value=f"```{cuenta}```",
                inline=False,
            )
        embed.set_footer(text="7 Days to Die • Hora verificada en tiempo real  •  Selecciona tu zona horaria 👇")

    embed.add_field(
        name="🆕 ¿Qué trae de nuevo?",
        value=(
            "• 🌍 Mapa completamente limpio\n"
            "• 🏠 Bases desde cero\n"
            "• ⚙️ Ajustes de dificultad mejorados"
        ),
        inline=False,
    )
    return embed

def _embed_sin_wipe(autor: discord.Member) -> discord.Embed:
    """Embed cuando no hay wipe programado."""
    embed = discord.Embed(
        title="🔄 WIPE DEL SERVIDOR",
        description=(
            f"**Hey! {autor.mention}**\n"
            "Actualmente **no hay ningún wipe programado**.\n"
            "¡Disfruta del servidor tranquilamente! 😄"
        ),
        color=0x8B0000,
    )
    embed.set_footer(text="7 Days to Die • Sin wipe programado")
    return embed

def _embed_gestion(tiene_wipe: bool, fecha_es: str = None) -> discord.Embed:
    """Embed del panel de gestión (!wipeG)."""
    if tiene_wipe:
        embed = discord.Embed(
            title="🔄 Gestión del Wipe",
            description=(
                f"**Wipe activo:** `{fecha_es or 'N/A'}` *(hora España)*\n\n"
                "Usa los botones para editar la **fecha**, la **hora**,\n"
                "cancelar el wipe o anunciar su llegada cuando corresponda."
            ),
            color=0xFF4500,
        )
    else:
        embed = discord.Embed(
            title="🔄 Gestión del Wipe",
            description=(
                "No hay ningún wipe programado actualmente.\n\n"
                "Pulsa **➕ Crear Wipe** para programar uno."
            ),
            color=0x8B0000,
        )
    embed.set_footer(text="7 Days to Die • Panel de Gestión — Solo moderadores")
    return embed

# ─── MODAL ───────────────────────────────────────────────────────────────────
class _ModalWipe(discord.ui.Modal):
    """Modal para crear o editar la fecha / hora del wipe."""

    def __init__(
        self,
        modo: str,                                    # "crear" | "fecha" | "hora"
        management_msg: discord.Message,
        canal_avisos: discord.TextChannel | None,
    ):
        titulos = {
            "crear": "🔄 Crear Wipe",
            "fecha": "📅 Editar Fecha del Wipe",
            "hora":  "🕐 Editar Hora del Wipe",
        }
        super().__init__(title=titulos.get(modo, "Wipe"))
        self.modo           = modo
        self.management_msg = management_msg
        self.canal_avisos   = canal_avisos

        if modo in ("crear", "fecha"):
            default_fecha = ""
            if modo == "fecha":
                _w = _leer_wipe()
                if _w:
                    
                    _dt = datetime.fromisoformat(_w["wipe_utc"]).astimezone(_pytz.timezone(TZ_ES))
                    default_fecha = _dt.strftime("%d/%m/%Y")
            self.f_fecha = discord.ui.TextInput(
                label="Fecha (DD/MM/YYYY) — zona horaria España",
                placeholder="Ej: 25/05/2026",
                default=default_fecha,
                min_length=10,
                max_length=10,
            )
            self.add_item(self.f_fecha)

        if modo in ("crear", "hora"):
            default_hora = ""
            if modo == "hora":
                _w = _leer_wipe()
                if _w:
                    
                    _dt = datetime.fromisoformat(_w["wipe_utc"]).astimezone(_pytz.timezone(TZ_ES))
                    default_hora = _dt.strftime("%H:%M")
            self.f_hora = discord.ui.TextInput(
                label="Hora (HH:MM) — zona horaria España",
                placeholder="Ej: 18:00",
                default=default_hora,
                min_length=5,
                max_length=5,
            )
            self.add_item(self.f_hora)

    # ── Validación interna ───────────────────────────────────
    @staticmethod
    def _parse_fecha(s: str) -> tuple[int, int, int]:
        partes = s.strip().split("/")
        if len(partes) != 3 or not all(p.isdigit() for p in partes):
            raise ValueError("Formato incorrecto. Usa **DD/MM/YYYY** (ej: `25/05/2026`)")
        d, m, y = int(partes[0]), int(partes[1]), int(partes[2])
        if not (1 <= d <= 31):
            raise ValueError("El día debe estar entre 01 y 31.")
        if not (1 <= m <= 12):
            raise ValueError("El mes debe estar entre 01 y 12.")
        if not (2024 <= y <= 2099):
            raise ValueError("El año debe estar entre 2024 y 2099.")
        return d, m, y

    @staticmethod
    def _parse_hora(s: str) -> tuple[int, int]:
        partes = s.strip().split(":")
        if len(partes) != 2 or not all(p.isdigit() for p in partes):
            raise ValueError("Formato incorrecto. Usa **HH:MM** (ej: `18:00`)")
        h, mi = int(partes[0]), int(partes[1])
        if not (0 <= h <= 23):
            raise ValueError("La hora debe estar entre 00 y 23.")
        if not (0 <= mi <= 59):
            raise ValueError("Los minutos deben estar entre 00 y 59.")
        return h, mi

    # ── Submit ───────────────────────────────────────────────
    async def on_submit(self, interaction: discord.Interaction):
        # Diferimos para poder llamar a la API sin agotar el tiempo de respuesta
        await interaction.response.defer(ephemeral=True)

        wipe_actual = _leer_wipe()
        tz_es       = pytz.timezone(TZ_ES)

        # ── Obtener hora actual desde API (sin reloj local) ──
        try:
            ahora_utc = await _hora_utc_api()
        except _NoTimeError:
            await interaction.followup.send(
                "❌ **No se pudo verificar la hora.** Todas las fuentes fallaron.\n"
                "Intenta de nuevo en unos instantes.",
                ephemeral=True,
            )
            return

        try:
            # ── Resolver fecha y hora ────────────────────────
            if self.modo == "crear":
                d, m, y = self._parse_fecha(self.f_fecha.value)
                h, mi   = self._parse_hora(self.f_hora.value)

            elif self.modo == "fecha":
                d, m, y = self._parse_fecha(self.f_fecha.value)
                if wipe_actual:
                    dt_ex = datetime.fromisoformat(wipe_actual["wipe_utc"]).astimezone(tz_es)
                    h, mi = dt_ex.hour, dt_ex.minute
                else:
                    h, mi = 0, 0

            else:  # modo == "hora"
                h, mi = self._parse_hora(self.f_hora.value)
                if wipe_actual:
                    dt_ex = datetime.fromisoformat(wipe_actual["wipe_utc"]).astimezone(tz_es)
                    d, m, y = dt_ex.day, dt_ex.month, dt_ex.year
                else:
                    # Usar la hora de la API convertida a España en lugar del reloj local
                    hoy     = ahora_utc.astimezone(tz_es)
                    d, m, y = hoy.day, hoy.month, hoy.year

            # ── Construir datetime España → UTC ─────────────
            try:
                dt_es = tz_es.localize(datetime(y, m, d, h, mi, 0))
            except ValueError as e:
                raise ValueError(f"Fecha inválida: {e}")

            dt_utc = dt_es.astimezone(timezone.utc)

            if dt_utc <= ahora_utc:
                raise ValueError("La fecha y hora deben ser en el **futuro**.")

        except ValueError as e:
            await interaction.followup.send(f"❌ **Error de validación:** {e}", ephemeral=True)
            return

        # ── Guardar ─────────────────────────────────────────
        created_at = wipe_actual.get("created_at") if (wipe_actual and self.modo != "crear") else ahora_utc.isoformat()
        _guardar_wipe(dt_utc.isoformat(), created_at)
        fecha_es = dt_es.strftime("%d/%m/%Y a las %H:%M")

        # ── Actualizar el panel de gestión ───────────────────
        nuevo_embed = _embed_gestion(tiene_wipe=True, fecha_es=fecha_es)
        nueva_vista = _GestionView(management_msg=self.management_msg, canal_avisos=self.canal_avisos)
        await interaction.edit_original_response(embed=nuevo_embed, view=nueva_vista)

        # ── Aviso al canal solo si es creación nueva ─────────
        if self.modo == "crear" and self.canal_avisos:
            embed_aviso = discord.Embed(
                title="🔄 ¡Cuenta atrás iniciada para el Wipe!",
                description=(
                    "Se ha programado un wipe del servidor.\n"
                    "Usa **`!wipe`** para ver la cuenta atrás."
                ),
                color=0xFF4500,
            )
            embed_aviso.add_field(
                name="📅 Fecha programada (España)",
                value=f"```{fecha_es}```",
                inline=False,
            )
            embed_aviso.set_footer(text="7 Days to Die • Wipe System")
            await self.canal_avisos.send(embed=embed_aviso)

        # ── Confirmación efímera ─────────────────────────────
        accion = "programado" if self.modo == "crear" else "actualizado"
        await interaction.followup.send(
            f"✅ Wipe {accion} correctamente para `{fecha_es}` (hora España).",
            ephemeral=True,
        )

# ─── VIEWS ───────────────────────────────────────────────────────────────────

class _GestionView(discord.ui.View):
    """
    Panel de gestión del wipe.
    timeout=None → los botones nunca expiran mientras el bot esté activo.
    """

    def __init__(self, management_msg: discord.Message, canal_avisos: discord.TextChannel | None):
        super().__init__(timeout=None)
        self.management_msg = management_msg
        self.canal_avisos   = canal_avisos
        self._construir()

    def _construir(self):
        """Construye los botones según el estado actual del wipe."""
        self.clear_items()
        wipe = _leer_wipe()

        if not wipe:
            # ── Sin wipe: solo botón de crear ─────────────────
            btn_crear = discord.ui.Button(
                label="➕ Crear Wipe",
                style=discord.ButtonStyle.success,
                row=0,
            )
            btn_crear.callback = self._cb_crear
            self.add_item(btn_crear)

        else:
            # ── Wipe activo: editar / cancelar / anunciar ─────
            btn_fecha = discord.ui.Button(
                label="📅 Editar Fecha",
                style=discord.ButtonStyle.primary,
                row=0,
            )
            btn_hora = discord.ui.Button(
                label="🕐 Editar Hora",
                style=discord.ButtonStyle.primary,
                row=0,
            )
            btn_cancelar = discord.ui.Button(
                label="🗑️ Cancelar Wipe",
                style=discord.ButtonStyle.danger,
                row=1,
            )
            btn_anunciar = discord.ui.Button(
                label="📢 Anunciar Llegada",
                style=discord.ButtonStyle.secondary,
                row=1,
            )

            btn_fecha.callback    = self._cb_fecha
            btn_hora.callback     = self._cb_hora
            btn_cancelar.callback = self._cb_cancelar
            btn_anunciar.callback = self._cb_anunciar

            for b in (btn_fecha, btn_hora, btn_cancelar, btn_anunciar):
                self.add_item(b)

    # ── Callbacks ────────────────────────────────────────────
    async def _cb_crear(self, interaction: discord.Interaction):
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(
            _ModalWipe(modo="crear", management_msg=self.management_msg, canal_avisos=self.canal_avisos)
        )

    async def _cb_fecha(self, interaction: discord.Interaction):
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(
            _ModalWipe(modo="fecha", management_msg=self.management_msg, canal_avisos=self.canal_avisos)
        )

    async def _cb_hora(self, interaction: discord.Interaction):
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(
            _ModalWipe(modo="hora", management_msg=self.management_msg, canal_avisos=self.canal_avisos)
        )

    async def _cb_cancelar(self, interaction: discord.Interaction):
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        embed_conf = discord.Embed(
            title="⚠️ ¿Cancelar el wipe?",
            description=(
                "Esta acción cancelará el wipe programado\n"
                "y avisará al canal de avisos.\n\n"
                "**¿Estás seguro?**"
            ),
            color=0xFF0000,
        )
        await interaction.response.send_message(
            embed=embed_conf,
            view=_ConfirmCancelView(
                management_msg=self.management_msg,
                canal_avisos=self.canal_avisos,
            ),
            ephemeral=True,
        )

    async def _cb_anunciar(self, interaction: discord.Interaction):
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return

        # Diferir para poder llamar a la API sin agotar el tiempo de respuesta
        await interaction.response.defer(ephemeral=True)

        wipe = _leer_wipe()
        if not wipe:
            await interaction.followup.send("❌ No hay wipe activo.", ephemeral=True)
            return

        try:
            ahora_utc = await _hora_utc_api()
        except _NoTimeError:
            await interaction.followup.send(
                "❌ **No se pudo verificar la hora.** Todas las fuentes fallaron.\n"
                "Intenta de nuevo en unos instantes.",
                ephemeral=True,
            )
            return
        wipe_utc  = datetime.fromisoformat(wipe["wipe_utc"])
        _, pasado = _cuenta_atras(wipe_utc, ahora_utc)

        if not pasado:
            await interaction.followup.send(
                "⏳ El wipe **todavía no ha llegado**. Espera a que pase la fecha programada.",
                ephemeral=True,
            )
            return

        # ── Enviar anuncio de llegada ────────────────────────
        if self.canal_avisos:
            fecha_es = _fmt_fecha_tz(wipe_utc, TZ_ES)
            embed = discord.Embed(
                title="🔄 ¡EL WIPE HA LLEGADO!",
                description=(
                    "@everyone\n"
                    "¡Ha llegado el momento del wipe!\n"
                    "El servidor será reiniciado. ¡Prepárense para empezar de nuevo!"
                ),
                color=0xFF4500,
            )
            embed.add_field(
                name="📅 Fecha del Wipe (España)",
                value=f"```{fecha_es}```",
                inline=False,
            )
            embed.set_footer(text="7 Days to Die • ¡Hasta la próxima temporada!")
            await self.canal_avisos.send("@everyone", embed=embed)

        # ── Desactivar wipe, parar loop y actualizar panel ───
        _desactivar_wipe()
        _loop_parar()
        try:
            await self.management_msg.edit(
                embed=_embed_gestion(tiene_wipe=False),
                view=_GestionView(management_msg=self.management_msg, canal_avisos=self.canal_avisos),
            )
        except discord.NotFound:
            pass

        await interaction.followup.send("✅ Anuncio enviado. Wipe marcado como completado. Puedes crear uno nuevo con ➕ Crear Wipe.", ephemeral=True)


class _ConfirmCancelView(discord.ui.View):
    """
    Mensaje efímero de confirmación para la cancelación del wipe.
    timeout=None → no expira.
    """

    def __init__(self, management_msg: discord.Message, canal_avisos: discord.TextChannel | None):
        super().__init__(timeout=None)
        self.management_msg = management_msg
        self.canal_avisos   = canal_avisos

    @discord.ui.button(label="✅ Sí, cancelar wipe", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return

        _desactivar_wipe()
        _loop_parar()
        try:
            await self.management_msg.edit(
                embed=_embed_gestion(tiene_wipe=False),
                view=_GestionView(management_msg=self.management_msg, canal_avisos=self.canal_avisos),
            )
        except discord.NotFound:
            pass  # El panel ya fue borrado

        # ── Aviso al canal ───────────────────────────────────
        if self.canal_avisos:
            embed_aviso = discord.Embed(
                title="❌ Wipe Cancelado",
                description="El wipe programado ha sido **cancelado** por el equipo de moderación.",
                color=0x8B0000,
            )
            embed_aviso.set_footer(text="7 Days to Die • Wipe System")
            await self.canal_avisos.send(embed=embed_aviso)

        # ── Actualizar el mensaje de confirmación ────────────
        await interaction.response.edit_message(
            content="✅ Wipe cancelado correctamente.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="❌ No, mantener", style=discord.ButtonStyle.secondary)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Cancelación abortada. El wipe sigue activo.",
            embed=None,
            view=None,
        )


class _ZonaHorariaView(discord.ui.View):
    """
    Botones de zona horaria para el !wipe público.
    timeout=None → no expiran nunca.
    Cada botón envía un embed efímero con la hora local del wipe.
    """

    def __init__(self, autor: discord.Member):
        super().__init__(timeout=None)
        self.autor = autor

    async def _enviar_tz(
        self,
        interaction: discord.Interaction,
        tz_str: str,
        tz_label: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        wipe = _leer_wipe()
        if not wipe:
            await interaction.followup.send("❌ El wipe fue cancelado.", ephemeral=True)
            return

        try:
            ahora_utc = await _hora_utc_api()
        except _NoTimeError:
            ahora_utc = None

        embed = _embed_wipe_publico(
            wipe, ahora_utc, tz_str=tz_str, tz_label=tz_label, autor=interaction.user
        )
        # Los mensajes efímeros de webhook expiran a los 15 min y no se pueden editar
        # por eso NO se registran en _wipe_msgs — se envían solo como consulta puntual
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🇦🇷 Argentina", style=discord.ButtonStyle.secondary, row=0)
    async def tz_argentina(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._enviar_tz(interaction, "America/Argentina/Buenos_Aires", "🇦🇷 Argentina")

    @discord.ui.button(label="🇲🇽 México", style=discord.ButtonStyle.secondary, row=0)
    async def tz_mexico(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._enviar_tz(interaction, "America/Mexico_City", "🇲🇽 México")

    @discord.ui.button(label="🇨🇴 Colombia", style=discord.ButtonStyle.secondary, row=0)
    async def tz_colombia(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._enviar_tz(interaction, "America/Bogota", "🇨🇴 Colombia")

# ─── COG ─────────────────────────────────────────────────────────────────────
class WipeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_load(self):
        global _loop_ref
        _loop_ref = self._loop_actualizar  # exponer al resto del módulo
        self._loop_refrescar_cache.start() # refresco de caché cada 6h desde el inicio

    def cog_unload(self):
        self._loop_actualizar.cancel()
        self._loop_refrescar_cache.cancel()

    def _canal_avisos(self, guild: discord.Guild) -> discord.TextChannel | None:
        return guild.get_channel(CANAL_AVISOS_ID)

    # ── Loop: actualiza todos los mensajes de cuenta atrás cada 2s ──────────
    @tasks.loop(minutes=1)
    async def _loop_actualizar(self):
        if not _wipe_msgs:
            self._loop_actualizar.stop()
            return

        wipe = _leer_wipe()

        if not wipe:
            _loop_parar()
            return

        try:
            ahora_utc = await _hora_utc_api()
        except _NoTimeError:
            ahora_utc = None

        muertos = []
        for mid, datos in list(_wipe_msgs.items()):
            try:
                embed = _embed_wipe_publico(
                    wipe,
                    ahora_utc,
                    tz_str=datos["tz_str"],
                    tz_label=datos["tz_label"],
                    autor=datos["autor"],
                )
                await datos["msg"].edit(embed=embed)
            except (discord.NotFound, discord.Forbidden):
                muertos.append(mid)   # El mensaje fue borrado o sin permisos
            except Exception as e:
                print(f"[WIPE][LOOP] Error editando mensaje {mid}: {e}")

        for mid in muertos:
            _wipe_msgs.pop(mid, None)

        # Si ya no queda ningún mensaje activo, parar el loop
        if not _wipe_msgs:
            self._loop_actualizar.stop()

    @_loop_actualizar.before_loop
    async def _antes_del_loop(self):
        await self.bot.wait_until_ready()

    # ── Loop: refresca time_cache.json cada 6 horas ──────────────────────────
    @tasks.loop(hours=6)
    async def _loop_refrescar_cache(self):
        """Mantiene time_cache.json actualizado cada 6 horas,
        independientemente de si hay un wipe activo o no."""
        try:
            await _hora_utc_api()
            print("[WIPE][CACHE] time_cache.json refrescado (tarea 6h).")
        except _NoTimeError:
            print("[WIPE][CACHE] Refresco 6h fallido: ninguna fuente disponible.")

    @_loop_refrescar_cache.before_loop
    async def _antes_del_loop_cache(self):
        await self.bot.wait_until_ready()

    # ── !wipeG ───────────────────────────────────────────────
    @commands.command(name="wipeG")
    async def wipe_gestion(self, ctx: commands.Context):
        """Panel de gestión del wipe — solo moderadores."""
        if not _tiene_permiso(ctx.author):
            await ctx.send("❌ No tienes permisos para usar este comando.", delete_after=5)
            return

        wipe     = _leer_wipe()
        canal    = self._canal_avisos(ctx.guild)
        fecha_es = None

        if wipe:
            wipe_utc = datetime.fromisoformat(wipe["wipe_utc"])
            fecha_es = _fmt_fecha_tz(wipe_utc, TZ_ES)

        embed = _embed_gestion(tiene_wipe=bool(wipe), fecha_es=fecha_es)

        # Enviamos el panel y después le asignamos la vista
        # (necesitamos el mensaje para pasarlo a la vista)
        msg  = await ctx.send(embed=embed)
        view = _GestionView(management_msg=msg, canal_avisos=canal)
        await msg.edit(view=view)

    # ── !wipe ────────────────────────────────────────────────
    @commands.command(name="wipe")
    async def wipe_cmd(self, ctx: commands.Context):
        """Muestra la cuenta atrás del próximo wipe del servidor."""
        wipe = _leer_wipe()

        if not wipe:
            await ctx.send(embed=_embed_sin_wipe(ctx.author))
            return

        msg_temp = await ctx.send("⏳ Consultando hora en tiempo real...")

        try:
            ahora_utc = await _hora_utc_api()
        except _NoTimeError:
            ahora_utc = None

        embed = _embed_wipe_publico(
            wipe, ahora_utc, tz_str=TZ_ES, tz_label="🇪🇸 España", autor=ctx.author
        )

        await msg_temp.delete()
        msg = await ctx.send(embed=embed, view=_ZonaHorariaView(autor=ctx.author))

        # Registrar el mensaje y arrancar el loop si no estaba corriendo
        _wipe_msgs[msg.id] = {
            "msg":      msg,
            "autor":    ctx.author,
            "tz_str":   TZ_ES,
            "tz_label": "🇪🇸 España",
        }
        _loop_arrancar()


# ─── SETUP ───────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(WipeCog(bot))