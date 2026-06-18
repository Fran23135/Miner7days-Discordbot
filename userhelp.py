import discord
from discord.ext import commands

# ─────────────────────────────────────────────
#  SECCIONES — igual que el !help original
# ─────────────────────────────────────────────
_SECTIONS = {
    "servidor": {
        "label":   "🌐 Servidor",
        "emoji":   "🌐",
        "color":   0x2C7BB5,
        "title":   "🌐 Comandos del Servidor",
        "cmds": [
            {
                "cmd": "status", "emoji": "🟢",
                "desc": "Verifica si el servidor de 7 Days to Die está activo o caído en este momento.",
                "uso":  "`!status`",
                "args": "Ninguno.",
            },
            {
                "cmd": "stats", "emoji": "🌍",
                "desc": "Muestra información del servidor: día actual, hora del juego, próxima horda y cuánto falta.",
                "uso":  "`!stats`",
                "args": "Ninguno.",
            },
            {
                "cmd": "wipe", "emoji": "💥",
                "desc": "Muestra la fecha del próximo wipe del servidor.",
                "uso":  "`!wipe`",
                "args": "Ninguno.",
            },
            {
                "cmd": "mods", "emoji": "🧩",
                "desc": "Lista los mods activos del servidor con nombres y links de descarga.",
                "uso":  "`!mods`",
                "args": "Ninguno.",
            },
            {
                "cmd": "players", "emoji": "👥",
                "desc": "Muestra los jugadores conectados ahora. Ordénalos con filtros opcionales.",
                "uso":  "`!players` o `!players <filtro>`",
                "args": "`<filtro>` (opcional): `nivel`, `zombies`, `muertes`, `ping`, `az`.",
            },
            {
                "cmd": "web", "emoji": "🌐",
                "desc": "Enlace directo a la web de estadísticas del servidor en tiempo real.",
                "uso":  "`!web`",
                "args": "Ninguno.",
            },
            {
                "cmd": "decoracion", "emoji": "🪑",
                "desc": "Abre el panel para hacer un pedido de decoración para tu base.",
                "uso":  "`!decoracion`",
                "args": "Ninguno.",
            },
        ],
    },

    "jugadores": {
        "label":   "👤 Jugadores",
        "emoji":   "👤",
        "color":   0x8B0000,
        "title":   "👤 Comandos de Jugadores",
        "cmds": [
            {
                "cmd": "player", "emoji": "🎮",
                "desc": "Estadísticas de un jugador del ranking: nivel, zombies, muertes y puntaje.",
                "uso":  "`!player <nombre>`",
                "args": "`<nombre>` — Nombre del jugador. Acepta mayúsculas/minúsculas y nombres similares.",
            },
            {
                "cmd": "ranking", "emoji": "🏆",
                "desc": "Ranking global de jugadores. Puedes ordenarlo con distintos filtros.",
                "uso":  "`!ranking` o `!ranking <filtro>`",
                "args": "`<filtro>` (opcional): `nivel`, `zombies`, `muertes`, `az`.",
            },
        ],
    },

    #"eventos": {
       # "label":   "🎪 Eventos",
       # "emoji":   "🎪",
        #"color":   0xFF8C00,
        #"title":   "🎪 Eventos y Decoración",
         #"cmds": [
           # {
           #     "cmd": "events", "emoji": "🏗️",
           #     "desc": "Muestra los eventos activos. Puedes inscribirte y subir tus pruebas desde aquí.",
           #     "uso":  "`!events`",
           #     "args": "Ninguno.",
           # },
        # ],
     #},

    "otros": {
        "label":   "🎮 Otros",
        "emoji":   "🎮",
        "color":   0x5865F2,
        "title":   "🎮 Otros Comandos",
        "cmds": [
            {
                "cmd": "miner", "emoji": "⛏️",
                "desc": "Muestra un consejo minero aleatorio y útil para el juego.",
                "uso":  "`!miner`",
                "args": "Ninguno.",
            },
            {
                "cmd": "help", "emoji": "❓",
                "desc": "Muestra este panel de ayuda con todos los comandos disponibles.",
                "uso":  "`!help`",
                "args": "Ninguno.",
            },
            {
                "cmd": "creditos", "emoji": "📜",
                "desc": "Muestra los créditos del desarrollador del bot.",
                "uso":  "`!creditos`",
                "args": "Ninguno.",
            },
            {
                "cmd": "web", "emoji": "🌐",
                "desc": "Enlace directo a la web de estadísticas del servidor en tiempo real.",
                "uso":  "`!web`",
                "args": "Ninguno.",
            },
            {
                "cmd": "clips", "emoji": "🎬",
                "desc": "Muestra un clip aleatorio de 7 Days to Die del canal de Kasiri en Twitch.",
                "uso":  "`!clips`",
                "args": "Ninguno.",
            },
            {
                "cmd": "news", "emoji": "📰",
                "desc": "Muestra las últimas actualizaciones y novedades del bot.",
                "uso":  "`!news`",
                "args": "Ninguno.",
            },
            {
                "cmd": "staff", "emoji": "👑",
                "desc": "Muestra el equipo de staff del servidor: roles y nombres.",
                "uso":  "`!staff`",
                "args": "Ninguno.",
            },
            {
                "cmd": "perfil", "emoji": "💫",
                "desc": "Muestra tu perfil para ver la experiencia y el nivel.",
                "uso":  "`!perfil <@usuario>` o `!perfil <nombre> o !perfil`",
                "args": "<@usuario> o <nombre> (opcionales).",
            },
            {
                "cmd": "decolist", "emoji": "🪴",
                "desc": "Muestra la lista de tus pedidos de decoración  y su estado.",
                "uso":  "`!Decolist`",
                "args": "Ninguno.",
                "dm_only": True,
            },
            {
                "cmd": "time", "emoji": "⏱️",
                "desc": "Muestra la hora actual del usuario y en otras zonas horarias",
                "uso":  "`!time`",
                "args": "Ninguno.",
            },
        ],
    },

    "interacciones": {
        "label":   "🎭 Interacciones",
        "emoji":   "🎭",
        "color":   0xFF69B4,
        "title":   "🎭 Interacciones",
        "cmds": [
            {
                "cmd": "interact", "emoji": "🎭",
                "desc": "Explica cómo funciona el sistema de interacciones animadas con GIFs de anime.",
                "uso":  "`!interact`",
                "args": "Ninguno.",
            },
            {
                "cmd": "interactlist", "emoji": "📋",
                "desc": "Lista paginada de todos los comandos de interacción disponibles.",
                "uso":  "`!interactlist`",
                "args": "Ninguno.",
            },
            {
                "cmd": "battle", "emoji": "⚔️",
                "desc": "Reta a otro jugador a una batalla de usuarios. El ganador lo decide el azar.",
                "uso":  "`!battle <@usuario>` o `!pelear <@usuario>`",
                "args": "`<@usuario>` — Mención al jugador que quieres retar. Obligatorio.",
            },
            {
                "cmd": "trivia", "emoji": "🧠",
                "desc": "Inicia una sesión de preguntas y respuestas sobre 7 Days to Die.",
                "uso":  "`!trivia`",
                "args": "Ninguno.",
            },
        ],
    },

    "ticket": {
        "label":   "🎫 Ticket",
        "emoji":   "🎫",
        "color":   0x00CC66,
        "title":   "🎫 Sistema de Tickets",
        "cmds": [
            {
                "cmd": "ticket", "emoji": "🎫",
                "desc": "Abre un nuevo ticket de bug o sugerencia para el staff.",
                "uso":  "`!ticket <título>`",
                "args": "`<título>` — Breve descripción del asunto. Obligatorio.",
                "dm_only": True,
            },
            {
                "cmd": "tkstatus", "emoji": "📊",
                "desc": "Consulta el estado de todos tus tickets: abiertos, solucionados, pendientes.",
                "uso":  "`!tkstatus` o `!tkstatus <número>`",
                "args": "`<número>` (opcional) — ID del ticket a consultar directamente.",
                "dm_only": True,
            },
        ],
    },
}

_SECTION_ORDER = ["servidor", "jugadores", "otros", "interacciones", "ticket"]
_PAGE_SIZE     = 10


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def _build_section_embed(section_key: str, page: int) -> tuple[discord.Embed, int]:
    sec   = _SECTIONS[section_key]
    cmds  = sec["cmds"]
    total = len(cmds)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    start = page * _PAGE_SIZE
    chunk = cmds[start:start + _PAGE_SIZE]

    lines = "\n".join(
        f"{c['emoji']} `!{c['cmd']}`"
        + ("  📩 *solo MD*" if c.get("dm_only") else "")
        + f" — {c['desc']}"
        for c in chunk
    )
    embed = discord.Embed(title=sec["title"], description=lines, color=sec["color"])
    footer_extra = "  |  📩 = exclusivo de MD" if any(c.get("dm_only") for c in chunk) else ""
    embed.set_footer(
        text=f"Página {page + 1}/{pages} • {total} comandos"
             f"{footer_extra} • Selecciona uno del menú para ver detalles"
    )
    return embed, pages


def _build_cmd_detail_embed(c: dict, section_color: int) -> discord.Embed:
    color = 0x00CC66 if c.get("dm_only") else section_color
    embed = discord.Embed(title=f"{c['emoji']} `!{c['cmd']}`", color=color)
    embed.add_field(name="📖 Descripción", value=c["desc"],  inline=False)
    embed.add_field(name="📌 Uso",         value=c["uso"],   inline=False)
    embed.add_field(name="⚙️ Argumentos",  value=c["args"],  inline=False)
    if c.get("dm_only"):
        embed.add_field(
            name="📩 Exclusivo de Mensajes Directos",
            value=(
                "Este comando **solo funciona enviándole un MD al bot**.\n"
                "Haz clic en el nombre del bot → **Enviar mensaje**."
            ),
            inline=False,
        )
    embed.set_footer(text="7 Days to Die • Miner Bot")
    return embed


# ─────────────────────────────────────────────
#  VIEW
# ─────────────────────────────────────────────
class HelpView(discord.ui.View):
    def __init__(self, section_key: str = "servidor", page: int = 0):
        super().__init__(timeout=None)
        self.section_key = section_key
        self.page        = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        sec   = _SECTIONS[self.section_key]
        cmds  = sec["cmds"]
        total = len(cmds)
        pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self.page = max(0, min(self.page, pages - 1))
        start = self.page * _PAGE_SIZE
        chunk = cmds[start:start + _PAGE_SIZE]

        # ── Row 0: dropdown de comandos de esta página ─────────────────
        sel = discord.ui.Select(
            placeholder="🔍 Selecciona un comando para ver detalles…",
            options=[
                discord.SelectOption(
                    label=f"!{c['cmd']}" + (" (MD)" if c.get("dm_only") else ""),
                    value=str(start + i),
                    emoji=c["emoji"],
                    description=c["desc"],
                )
                for i, c in enumerate(chunk)
            ],
            row=0,
        )
        sel.callback = self._select_cb
        self.add_item(sel)

        # ── Row 1: paginación (solo si hay más de 1 página) ────────────
        if pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0), row=1,
            )
            prev.callback = self._prev_cb
            self.add_item(prev)

            self.add_item(discord.ui.Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True, row=1,
            ))

            nxt = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= pages - 1), row=1,
            )
            nxt.callback = self._next_cb
            self.add_item(nxt)

        # ── Row 2: selector de sección ─────────────────────────────────
        section_sel = discord.ui.Select(
            placeholder="📂 Cambiar sección…",
            options=[
                discord.SelectOption(
                    label=_SECTIONS[k]["label"],
                    value=k,
                    emoji=_SECTIONS[k]["emoji"],
                    default=(k == self.section_key),
                )
                for k in _SECTION_ORDER
            ],
            row=2,
        )
        section_sel.callback = self._section_cb
        self.add_item(section_sel)

    # ── callbacks ────────────────────────────────────────────────────
    async def _select_cb(self, interaction: discord.Interaction):
        try:
            sec   = _SECTIONS[self.section_key]
            index = int(interaction.data["values"][0])
            embed = _build_cmd_detail_embed(sec["cmds"][index], sec["color"])
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            pass

    async def _prev_cb(self, interaction: discord.Interaction):
        try:
            self.page -= 1
            self._rebuild()
            embed, _ = _build_section_embed(self.section_key, self.page)
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.NotFound:
            pass

    async def _next_cb(self, interaction: discord.Interaction):
        try:
            self.page += 1
            self._rebuild()
            embed, _ = _build_section_embed(self.section_key, self.page)
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.NotFound:
            pass

    async def _section_cb(self, interaction: discord.Interaction):
        try:
            self.section_key = interaction.data["values"][0]
            self.page        = 0
            self._rebuild()
            embed, _ = _build_section_embed(self.section_key, self.page)
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.NotFound:
            pass


# ─────────────────────────────────────────────
#  COG
# ─────────────────────────────────────────────
class UserHelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help")
    async def cmd_help(self, ctx: commands.Context):
        """Muestra todos los comandos disponibles del bot."""
        embed, _ = _build_section_embed("servidor", 0)
        await ctx.send(embed=embed, view=HelpView("servidor", 0))


async def setup(bot: commands.Bot):
    await bot.add_cog(UserHelpCog(bot))