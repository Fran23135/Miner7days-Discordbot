import discord
import random
import asyncio
from datetime import datetime, timedelta
from discord.ext import commands
from interact import make_embed, INTERACCIONES
from status7d import nekos_cache

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
BATTLE_COOLDOWN = 120       # segundos de cooldown entre los mismos 2 usuarios
ROUNDS_MIN      = 5
ROUNDS_MAX      = 7
ROUNDS_BOT      = 3
BOT_WIN_CHANCE  = 1 - 0.0001  # 99.99 % el bot gana

# Tags de interact.py que se usan en las rondas
BATTLE_TAGS = ["punch", "kick", "slap", "bonk", "shoot", "bite", "yeet"]

# ─────────────────────────────────────────────
#  COOLDOWNS
# ─────────────────────────────────────────────
_cooldowns: dict[frozenset, datetime] = {}

def _cd_key(a: int, b: int) -> frozenset:
    return frozenset({a, b})

def _remaining(a: int, b: int) -> int:
    exp = _cooldowns.get(_cd_key(a, b))
    if exp and datetime.utcnow() < exp:
        return int((exp - datetime.utcnow()).total_seconds())
    return 0

def _set_cd(a: int, b: int):
    _cooldowns[_cd_key(a, b)] = datetime.utcnow() + timedelta(seconds=BATTLE_COOLDOWN)

# ─────────────────────────────────────────────
#  HELPERS DE EMBED
# ─────────────────────────────────────────────
def _frase(tag: str) -> str:
    """Devuelve la frase_con_target del tag de INTERACCIONES."""
    data = INTERACCIONES.get(tag)
    return data[1] if data else "ataca a"

async def _round_embed(attacker, defender) -> discord.Embed:
    tag      = random.choice(BATTLE_TAGS)
    frase    = _frase(tag)
    gif_info = nekos_cache.obtener_gif(tag)
    titulo   = f"⚔️ {attacker.display_name} {frase} {defender.display_name}."
    embed    = discord.Embed(description=f"**{titulo}**", color=random.randint(0x880000, 0xFF4444))
    if gif_info:
        embed.set_image(url=gif_info["url"])
        embed.set_footer(text=f"Anime: {gif_info.get('anime_name', 'Desconocido')} • ⚔️ Batalla")
    return embed

async def _victory_embed(winner, loser) -> discord.Embed:
    # Intenta smug → clap como fallback para el gif de victoria
    gif_info = nekos_cache.obtener_gif("smug") or nekos_cache.obtener_gif("clap")
    embed = discord.Embed(
        title="🏆 ¡La batalla ha terminado!",
        description=(
            f"### ¡{winner.mention} ha ganado! 🎉\n"
            f"**{loser.display_name}** ha quedado en el suelo... 😵"
        ),
        color=0xFFD700,
    )
    if gif_info:
        embed.set_image(url=gif_info["url"])
    embed.set_footer(text="⚔️ Sistema de Batallas  •  7 Days to Die")
    return embed

# ─────────────────────────────────────────────
#  LÓGICA DE RONDAS  (delete + send en lugar de edit)
# ─────────────────────────────────────────────
async def _run_rounds(channel, f1, f2, rounds: int) -> discord.Message:
    attacker, defender = f1, f2
    embed = await _round_embed(attacker, defender)
    msg   = await channel.send(embed=embed)
    await asyncio.sleep(6)

    for _ in range(1, rounds):
        attacker, defender = defender, attacker
        embed = await _round_embed(attacker, defender)
        try:
            await msg.delete()
        except Exception:
            pass
        msg = await channel.send(embed=embed)
        await asyncio.sleep(6)

    return msg

# ─────────────────────────────────────────────
#  VIEWS
# ─────────────────────────────────────────────
class ChallengeEphemeralView(discord.ui.View):
    """Botones Aceptar / Rechazar visibles únicamente para el retado (efímero)."""

    def __init__(self, challenger, challenged, public_view: "ChallengePublicView", cog):
        super().__init__(timeout=60)
        self.challenger  = challenger
        self.challenged  = challenged
        self.public_view = public_view
        self.cog         = cog
        self._done       = False

    @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._done:
            return await interaction.response.edit_message(content="Ya respondiste.", view=None)
        self._done = True
        self.public_view._resolved = True
        self.public_view.stop()
        self.stop()

        await interaction.response.edit_message(content="✅ ¡Aceptaste el combate! ⚔️", view=None)

        # Mensaje global
        await interaction.channel.send(
            f"⚔️ **{self.challenged.display_name}** aceptó el combate ¡a darle! 🔥"
        )
        # Eliminar el mensaje público de desafío
        try:
            await self.public_view.message.delete()
        except Exception:
            pass

        asyncio.create_task(
            self.cog.do_battle(interaction.channel, self.challenger, self.challenged)
        )

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._done:
            return await interaction.response.edit_message(content="Ya respondiste.", view=None)
        self._done = True
        self.public_view._resolved = True
        self.public_view.stop()
        self.stop()

        await interaction.response.edit_message(content="❌ Rechazaste el combate.", view=None)

        await interaction.channel.send(
            f"🏳️ **{self.challenged.display_name}** rechazó el combate."
        )
        try:
            await self.public_view.message.delete()
        except Exception:
            pass


class ChallengePublicView(discord.ui.View):
    """Mensaje público de desafío; solo el retado puede usar el botón."""

    def __init__(self, challenger, challenged, cog):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challenged = challenged
        self.cog        = cog
        self.message    = None   # se asigna después del send
        self._resolved  = False

    async def on_timeout(self):
        if self._resolved or not self.message:
            return
        try:
            await self.message.edit(
                embed=discord.Embed(
                    description=(
                        f"⌛ El desafío de **{self.challenger.display_name}** "
                        f"a **{self.challenged.display_name}** expiró sin respuesta."
                    ),
                    color=0x888888,
                ),
                view=None,
            )
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message(
                "Este desafío no es para ti. 😅", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="⚔️ Responder al desafío", style=discord.ButtonStyle.primary)
    async def respond(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChallengeEphemeralView(self.challenger, self.challenged, self, self.cog)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=(
                    f"⚔️ **{self.challenger.display_name}** te ha retado a batalla.\n"
                    f"¿Aceptas el combate?"
                ),
                color=0xFF6600,
            ),
            view=view,
            ephemeral=True,
        )


class BotChallengeView(discord.ui.View):
    """Confirmación cuando el usuario reta al propio bot."""

    def __init__(self, challenger, cog):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.cog        = cog
        self.message    = None

    async def on_timeout(self):
        if not self.message:
            return
        try:
            await self.message.edit(
                embed=discord.Embed(
                    description="⌛ El desafío expiró. Quizás mejor así...",
                    color=0x888888,
                ),
                view=None,
            )
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message(
                "No es tu desafío. 😅", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="⚔️ ¡Sí, me atrevo!", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message(
            "¡Valiente! Que empiece el combate... ⚔️🔥", ephemeral=True
        )
        await interaction.message.edit(
            embed=discord.Embed(
                description=(
                    f"⚔️ **{self.challenger.display_name}** acepta el duelo contra "
                    f"**{interaction.client.user.display_name}** ¡a darle!"
                ),
                color=0xFF4444,
            ),
            view=None,
        )
        asyncio.create_task(
            self.cog.do_bot_battle(
                interaction.channel, self.challenger, interaction.client.user
            )
        )

    @discord.ui.button(label="❌ Mejor no", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("Cobarde. 🙄", ephemeral=True)
        await interaction.message.edit(
            embed=discord.Embed(
                description=f"🏳️ **{self.challenger.display_name}** decidió no pelear. Cobarde.",
                color=0x888888,
            ),
            view=None,
        )
# ─────────────────────────────────────────────
#  BOT CHALLENGE — efímero igual que user vs user
# ─────────────────────────────────────────────
class BotChallengeEphemeralView(discord.ui.View):
    """Botones Aceptar/Rechazar efímeros cuando se reta al bot."""

    def __init__(self, challenger, public_view: "BotChallengePublicView", cog):
        super().__init__(timeout=60)
        self.challenger  = challenger
        self.public_view = public_view
        self.cog         = cog
        self._done       = False

    @discord.ui.button(label="⚔️ ¡Sí, me atrevo!", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._done:
            return await interaction.response.edit_message(content="Ya respondiste.", view=None)
        self._done = True
        self.public_view._resolved = True
        self.public_view.stop()
        self.stop()

        await interaction.response.edit_message(
            content="✅ ¡Valiente! Que empiece el combate... ⚔️🔥", view=None
        )
        await interaction.channel.send(
            f"⚔️ **{self.challenger.display_name}** aceptó el duelo contra "
            f"**{interaction.client.user.display_name}** ¡a darle! 🔥"
        )
        try:
            await self.public_view.message.delete()
        except Exception:
            pass

        asyncio.create_task(
            self.cog.do_bot_battle(
                interaction.channel, self.challenger, interaction.client.user
            )
        )

    @discord.ui.button(label="❌ Mejor no", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._done:
            return await interaction.response.edit_message(content="Ya respondiste.", view=None)
        self._done = True
        self.public_view._resolved = True
        self.public_view.stop()
        self.stop()

        await interaction.response.edit_message(content="Cobarde. 🙄", view=None)
        await interaction.channel.send(
            f"🏳️ **{self.challenger.display_name}** decidió no pelear. Cobarde."
        )
        try:
            await self.public_view.message.delete()
        except Exception:
            pass


class BotChallengePublicView(discord.ui.View):
    """Mensaje público inicial cuando se reta al bot; solo el retador puede usarlo."""

    def __init__(self, challenger, cog):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.cog        = cog
        self.message    = None
        self._resolved  = False

    async def on_timeout(self):
        if self._resolved or not self.message:
            return
        try:
            await self.message.edit(
                embed=discord.Embed(
                    description="⌛ El desafío expiró. Quizás mejor así...",
                    color=0x888888,
                ),
                view=None,
            )
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message(
                "No es tu desafío. 😅", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="⚔️ Responder", style=discord.ButtonStyle.primary)
    async def respond(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BotChallengeEphemeralView(self.challenger, self, self.cog)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=(
                    f"¿Estás **seguro** que quieres pelear conmigo?\n"
                    f"Soy muy fuerte... 💪😤"
                ),
                color=0xFF2222,
            ),
            view=view,
            ephemeral=True,
        )
# ─────────────────────────────────────────────
#  COG
# ─────────────────────────────────────────────
class BattleCog(commands.Cog, name="Batalla"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Lógica de batalla usuario vs usuario ──
    async def do_battle(self, channel, f1, f2):
        rounds       = random.randint(ROUNDS_MIN, ROUNDS_MAX)
        msg          = await _run_rounds(channel, f1, f2, rounds)
        winner       = random.choice([f1, f2])
        loser        = f2 if winner == f1 else f1
        victory      = await _victory_embed(winner, loser)
        await msg.edit(embed=victory)
        _set_cd(f1.id, f2.id)

    # ── Lógica de batalla usuario vs bot ──────
    async def do_bot_battle(self, channel, challenger, bot_user):
        msg    = await _run_rounds(channel, challenger, bot_user, ROUNDS_BOT)
        if random.random() < BOT_WIN_CHANCE:
            winner, loser = bot_user, challenger
        else:
            winner, loser = challenger, bot_user
        victory = await _victory_embed(winner, loser)
        await msg.edit(embed=victory)

    # ── Comando !battle / !pelear ─────────────
    @commands.command(name="battle", aliases=["pelear"])
    @commands.guild_only()
    async def cmd_battle(self, ctx: commands.Context, target: discord.Member = None):
        """Reta a alguien a una batalla. Uso: !battle @usuario"""

        # Sin mención
        if target is None:
            return await ctx.send(
                "❌ Debes mencionar a alguien.\n"
                "Uso: `!battle @usuario` o `!pelear @usuario`"
            )

        # Auto-reto
        if target == ctx.author:
            return await ctx.send("🤔 ¿Pelearte contigo mismo? Eso no tiene sentido...")

        # ── Reto al bot ──────────────────────
        if target == self.bot.user:
            embed = discord.Embed(
                description=(
                    f"**{ctx.author.display_name}** quiere pelear contra "
                    f"**{self.bot.user.display_name}**...\n"
                    f"Estas Seguro? 😤"
                ),
                color=0xFF2222,
            )
            view = BotChallengePublicView(ctx.author, self)
            msg  = await ctx.send(embed=embed, view=view)
            view.message = msg
            return

        # Otro bot
        if target.bot:
            return await ctx.send("🤖 No puedes batallar contra otros bots.")

        # ── Cooldown ─────────────────────────
        secs = _remaining(ctx.author.id, target.id)
        if secs:
            return await ctx.send(
                f"⏳ **{ctx.author.display_name}** y **{target.display_name}** "
                f"aún tienen cooldown: **{secs}s** restantes."
            )

        # ── Desafío público ───────────────────
        embed = discord.Embed(
            description=(
                f"⚔️ **{ctx.author.display_name}** desafía a **{target.display_name}** a combate!\n"
                f"{target.mention}, ¿aceptas el duelo?"
            ),
            color=0xFF6600,
        )
        view = ChallengePublicView(ctx.author, target, self)
        msg  = await ctx.send(embed=embed, view=view)
        view.message = msg   # referencia para on_timeout y para borrar en aceptar/rechazar


# ─────────────────────────────────────────────
#  SETUP
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(BattleCog(bot))