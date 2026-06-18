"""
time_cog.py — Cog de hora mundial para Miner 7Days Bot
Comando: !time / !hora

Detecta la zona horaria via IP (ip-api.com) sin depender de Windows.
Hora actual via timeapi.io.
Sin timeouts en botones.
"""

import discord
from discord.ext import commands
from discord.ui import View, Button
import aiohttp

COLOR = 0x8B0000

# ══════════════════════════════════════════════════════════════════════════
#  ZONAS FIJAS — botones disponibles
# ══════════════════════════════════════════════════════════════════════════

ZONAS_FIJAS = [
    {
        "id":     "mexico",
        "label":  "🇲🇽 México",
        "tz":     "America/Mexico_City",
        "nombre": "México · Ciudad de México",
        # Si la IP detectada empieza con alguno de estos → coincide con México
        "match":  [
            "America/Mexico_City", "America/Cancun", "America/Monterrey",
            "America/Mazatlan", "America/Chihuahua", "America/Hermosillo",
            "America/Tijuana", "America/Bahia_Banderas", "America/Merida",
            "America/Matamoros",
        ],
    },
    {
        "id":     "espana",
        "label":  "🇪🇸 España",
        "tz":     "Europe/Madrid",
        "nombre": "España · Madrid",
        "match":  ["Europe/Madrid", "Atlantic/Canary"],
    },
    {
        "id":     "colombia",
        "label":  "🇨🇴 Colombia",
        "tz":     "America/Bogota",
        "nombre": "Colombia · Bogotá",
        "match":  ["America/Bogota"],
    },
    {
        "id":     "argentina",
        "label":  "🇦🇷 Argentina",
        "tz":     "America/Argentina/Buenos_Aires",
        "nombre": "Argentina · Buenos Aires",
        "match":  [
            "America/Argentina/Buenos_Aires", "America/Argentina/Cordoba",
            "America/Argentina/Mendoza", "America/Argentina/Rosario",
            "America/Argentina/", "America/Buenos_Aires",
        ],
    },
]

DIAS_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}

# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _zona_para_tz(tz: str) -> dict | None:
    """Retorna la zona fija que coincide con el timezone detectado, o None."""
    for zona in ZONAS_FIJAS:
        for candidato in zona["match"]:
            if tz == candidato or tz.startswith(candidato):
                return zona
    return None


async def _get_ip_timezone() -> str:
    """
    Detecta la zona horaria via IP pública del bot usando ip-api.com.
    Gratis, sin API key, sin dependencia de Windows.
    Si falla retorna UTC.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://ip-api.com/json/",
                timeout=aiohttp.ClientTimeout(total=6),
            ) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    tz = data.get("timezone", "").strip()
                    if tz:
                        return tz
    except Exception as e:
        print(f"[TIME] ip-api.com falló: {e}")
    return "UTC"


async def _get_time(tz: str) -> dict | None:
    """
    Obtiene la hora actual para una zona horaria via timeapi.io.
    Retorna el dict JSON o None si falla.
    """
    url = f"https://timeapi.io/api/Time/current/zone?timeZone={tz}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
    except Exception as e:
        print(f"[TIME] timeapi.io falló para {tz}: {e}")
    return None


def _build_embed(data: dict | None, zona_nombre: str, tz: str, fmt24: bool) -> discord.Embed:
    """Construye el embed de hora. Funciona para el mensaje principal y los efímeros."""
    if data is None:
        return discord.Embed(
            title="❌ Error",
            description="No se pudo obtener la hora. Inténtalo de nuevo.",
            color=COLOR,
        )

    hora   = data.get("hour",    0)
    minuto = data.get("minute",  0)
    seg    = data.get("seconds", 0)
    dia    = data.get("dayOfWeek", "")
    anio   = data.get("year",  "?")
    mes    = data.get("month", "?")
    d      = data.get("day",   "?")

    if fmt24:
        hora_str = f"{hora:02d}:{minuto:02d}:{seg:02d}"
    else:
        periodo = "AM" if hora < 12 else "PM"
        h12     = hora % 12 or 12
        hora_str = f"{h12:02d}:{minuto:02d}:{seg:02d} {periodo}"

    dia_es = DIAS_ES.get(dia, dia)
    fecha  = f"{d:02d}/{mes:02d}/{anio}" if isinstance(d, int) else f"{d}/{mes}/{anio}"

    embed = discord.Embed(title="🕐 Hora actual", color=COLOR)
    embed.add_field(
        name="📍 Zona horaria",
        value=f"**{zona_nombre}**\n`{tz}`",
        inline=False,
    )
    embed.add_field(name="🕐 Hora",  value=f"**`{hora_str}`**", inline=True)
    embed.add_field(name="📅 Fecha", value=f"{dia_es} {fecha}", inline=True)
    embed.set_footer(text=f"Formato {'24h' if fmt24 else '12h'} • ip-api.com + timeapi.io")
    return embed


# ══════════════════════════════════════════════════════════════════════════
#  VIEW EFÍMERO — para cuando pulsas un botón de zona
# ══════════════════════════════════════════════════════════════════════════

class ZonaView(View):
    """View en el mensaje efímero de una zona específica. Sin timeout."""

    def __init__(self, tz: str, zona_nombre: str, fmt24: bool):
        super().__init__(timeout=None)
        self.tz          = tz
        self.zona_nombre = zona_nombre
        self.fmt24       = fmt24
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        label = "🕐 Ver en 12h" if self.fmt24 else "🕐 Ver en 24h"
        btn   = Button(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"zona_toggle_{self.tz.replace('/', '_')}",
        )
        btn.callback = self._toggle_cb
        self.add_item(btn)

    async def _toggle_cb(self, interaction: discord.Interaction):
        self.fmt24 = not self.fmt24
        self._rebuild()
        data  = await _get_time(self.tz)
        embed = _build_embed(data, self.zona_nombre, self.tz, self.fmt24)
        await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════
#  VIEW PRINCIPAL — mensaje público del !time
# ══════════════════════════════════════════════════════════════════════════

class TimeView(View):
    """
    View principal. Sin timeout.
    Muestra botones de zona (excepto la detectada) + toggle 12h/24h.
    """

    def __init__(self, tz_detectada: str, zona_detectada: dict | None, fmt24: bool = True):
        super().__init__(timeout=None)
        self.tz_detectada   = tz_detectada
        self.zona_detectada = zona_detectada
        self.fmt24          = fmt24
        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        # ── Botones de zona (saltar la que ya se muestra) ──────────────────
        for zona in ZONAS_FIJAS:
            if zona is self.zona_detectada:
                continue  # ya estás aquí, no tiene sentido el botón

            def _make_cb(z: dict):
                async def _cb(interaction: discord.Interaction):
                    data  = await _get_time(z["tz"])
                    embed = _build_embed(data, z["nombre"], z["tz"], self.fmt24)
                    view  = ZonaView(z["tz"], z["nombre"], self.fmt24)
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return _cb

            btn          = Button(label=zona["label"], style=discord.ButtonStyle.primary)
            btn.callback = _make_cb(zona)
            self.add_item(btn)

        # ── Toggle formato ─────────────────────────────────────────────────
        label  = "🕐 Ver en 12h" if self.fmt24 else "🕐 Ver en 24h"
        toggle = Button(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id="time_toggle_fmt",
        )
        toggle.callback = self._toggle_cb
        self.add_item(toggle)

    async def _toggle_cb(self, interaction: discord.Interaction):
        self.fmt24 = not self.fmt24
        self._rebuild()

        zona_nombre = self.zona_detectada["nombre"] if self.zona_detectada else self.tz_detectada
        data  = await _get_time(self.tz_detectada)
        embed = _build_embed(data, zona_nombre, self.tz_detectada, self.fmt24)
        await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════════════════

class TimeCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="time", aliases=["hora"])
    async def time_cmd(self, ctx: commands.Context):
        """Muestra la hora actual detectando la zona horaria via IP."""

        # Mensaje de espera mientras consulta las APIs
        wait_embed = discord.Embed(
            description="🌐 Detectando zona horaria...",
            color=COLOR,
        )
        msg = await ctx.send(embed=wait_embed)

        # 1. Detectar zona horaria via IP
        tz             = await _get_ip_timezone()
        zona_detectada = _zona_para_tz(tz)

        # 2. Obtener hora actual para esa zona
        data = await _get_time(tz)

        # 3. Nombre legible
        zona_nombre = zona_detectada["nombre"] if zona_detectada else tz

        # 4. Construir embed y view
        embed = _build_embed(data, zona_nombre, tz, fmt24=True)
        view  = TimeView(tz, zona_detectada, fmt24=True)

        await msg.edit(embed=embed, view=view)


# ── Setup ──────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(TimeCog(bot))
