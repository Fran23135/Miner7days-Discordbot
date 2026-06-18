"""
niveles.py — Cog del sistema de niveles y rangos
XP por mensajes · cooldown · subida de nivel · roles cada 5 lvl
!perfil con panel de rangos y botón Dev (solo DESARROLLADOR_ID)
!rangosG — panel de gestión de rangos (solo mods / admins)
"""

import time
import random
import discord
from discord.ext import commands
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sql"))
import sql.db_manager as db
from sql.rangos_config import (
    DEFINICIONES,
    NIVELES_CON_RANGO,
    get_rango_actual,
    get_todos_desbloqueados,
    ids_todos_rangos,
    cargar_ids,
    agregar_rango,
    editar_nombre_rango,
    eliminar_rango,
    get_ids_cargados,
    guardar_ids,
)
from config import DESARROLLADOR_ID

# ── Constantes ─────────────────────────────────────────────────────────────────
COOLDOWN_SEGUNDOS = 60
XP_MIN            = 15
XP_MAX            = 25
NIVEL_MAXIMO      = 300
COLOR             = 0x8B0000


def xp_para_nivel(nivel: int) -> int:
    """XP necesaria para subir desde el nivel dado al siguiente. Fórmula MEE6."""
    return 5 * (nivel ** 2) + 50 * nivel + 100


# ══════════════════════════════════════════════════════════════════════════════
#  MODALES DEV
# ══════════════════════════════════════════════════════════════════════════════

class ModalSubirN(discord.ui.Modal, title="Subir niveles"):
    cantidad = discord.ui.TextInput(
        label="¿Cuántos niveles subir?",
        placeholder="Ej: 10  (máx 300)",
        min_length=1, max_length=3,
    )

    def __init__(self, cog, target: discord.Member, view_ref):
        super().__init__()
        self.cog      = cog
        self.target   = target
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = int(self.cantidad.value)
            if n < 1 or n > NIVEL_MAXIMO:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Número inválido (1–300).", ephemeral=True
            )
            return
        await _dev_cambiar_nivel(interaction, self.target, +n)


class ModalBajarN(discord.ui.Modal, title="Bajar niveles"):
    cantidad = discord.ui.TextInput(
        label="¿Cuántos niveles bajar?",
        placeholder="Ej: 5",
        min_length=1, max_length=3,
    )

    def __init__(self, cog, target: discord.Member, view_ref):
        super().__init__()
        self.cog      = cog
        self.target   = target
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = int(self.cantidad.value)
            if n < 1 or n > NIVEL_MAXIMO:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Número inválido (1–300).", ephemeral=True
            )
            return
        await _dev_cambiar_nivel(interaction, self.target, -n)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER DEV — cambiar nivel
# ══════════════════════════════════════════════════════════════════════════════
async def _notificar_subida(member: discord.Member, guild: discord.Guild, usuario_antes: dict, nivel_nuevo: int):
    """Envía la notificación de subida de nivel por DM. Reutilizable por dev mode y on_message."""
    AUTODESTRUYE = 10
    embed = discord.Embed(color=0x8B0000)
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.title = f"⬆️ ¡Subiste al nivel {nivel_nuevo}!"

    if nivel_nuevo in DEFINICIONES:
        rango = get_rango_actual(nivel_nuevo)
        if rango:
            _, nombre_rango, rol_id = rango
            rol = guild.get_role(rol_id)
            if usuario_antes["rol_elegido"]:
                embed.description = (
                    f"🎖️ ¡Desbloqueaste el rango **{nombre_rango}**!\n"
                    f"Tu rango actual se mantiene porque lo elegiste tú.\n"
                    f"Usa `!perfil` → **Restablecer rango** si quieres actualizarlo."
                )
            else:
                embed.description = (
                    f"🎖️ ¡Desbloqueaste el rango **{nombre_rango}**!\n"
                    f"Se ha equipado automáticamente."
                )
                if rol:
                    ids_rango      = ids_todos_rangos()
                    roles_a_quitar = [r for r in member.roles if r.id in ids_rango]
                    if roles_a_quitar:
                        await member.remove_roles(*roles_a_quitar, reason="Auto rango")
                    await member.add_roles(rol, reason=f"Nivel {nivel_nuevo}")
        else:
            embed.description = "¡Sigue así!"
    else:
        embed.description = "¡Sigue participando para ganar más XP!"

    embed.set_footer(text=f"Nivel {nivel_nuevo}  •  🕐 Este mensaje se autodestruye en {AUTODESTRUYE}s")

    try:
        dm = await member.create_dm()
        await dm.send(embed=embed, delete_after=AUTODESTRUYE)
    except discord.Forbidden:
        pass


async def _dev_cambiar_nivel(
    interaction: discord.Interaction,
    target: discord.Member,
    delta: int,
):
    await interaction.response.defer(ephemeral=True)

    uid     = str(target.id)
    usuario = await db.get_usuario(uid)
    if not usuario:
        await interaction.followup.send("❌ El usuario no está en la BD.", ephemeral=True)
        return

    nivel_viejo = usuario["nivel"]
    nivel_nuevo = max(1, min(NIVEL_MAXIMO, nivel_viejo + delta))

    if nivel_nuevo > nivel_viejo:
        xp_ganada    = sum(xp_para_nivel(n) for n in range(nivel_viejo, nivel_nuevo))
        xp_total_new = usuario["xp_total"] + xp_ganada
    else:
        xp_total_new = usuario["xp_total"]

    await db.actualizar_xp(uid, xp=0, nivel=nivel_nuevo, xp_total=xp_total_new, last_xp=usuario["last_xp"])

    if not usuario["rol_elegido"]:
        rango = get_rango_actual(nivel_nuevo)
        if rango:
            _, nombre_r, rol_id = rango
            rol = interaction.guild.get_role(rol_id)
            if rol:
                ids_rango      = ids_todos_rangos()
                roles_a_quitar = [r for r in target.roles if r.id in ids_rango]
                if roles_a_quitar:
                    await target.remove_roles(*roles_a_quitar, reason="Dev: ajuste de nivel")
                await target.add_roles(rol, reason=f"Dev: nivel {nivel_nuevo}")

    for n in range(nivel_viejo + 1, nivel_nuevo + 1):
        await _notificar_subida(target, interaction.guild, usuario, n)

    signo  = "+" if delta > 0 else ""
    xp_txt = f"+{xp_total_new - usuario['xp_total']:,} XP acumulada" if nivel_nuevo > nivel_viejo else "XP histórica sin cambios"
    embed  = discord.Embed(
        title="🛠️ Dev — Nivel ajustado",
        description=(
            f"**{target.display_name}**\n"
            f"Nivel: `{nivel_viejo}` → `{nivel_nuevo}` ({signo}{delta})\n"
            f"XP total: `{usuario['xp_total']:,}` → `{xp_total_new:,}` ({xp_txt})"
        ),
        color=0x8B0000,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW DEV MODE (sin timeout)
# ══════════════════════════════════════════════════════════════════════════════

class DevView(discord.ui.View):
    """Panel de dev en !perfil. Solo visible / usable por DESARROLLADOR_ID."""

    def __init__(self, target: discord.Member):
        super().__init__(timeout=None)
        self.target = target

    def _check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == DESARROLLADOR_ID

    @discord.ui.button(label="▲ +1 Nivel", style=discord.ButtonStyle.success, row=0)
    async def mas_uno(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await _dev_cambiar_nivel(interaction, self.target, +1)

    @discord.ui.button(label="▼ -1 Nivel", style=discord.ButtonStyle.danger, row=0)
    async def menos_uno(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await _dev_cambiar_nivel(interaction, self.target, -1)

    @discord.ui.button(label="▲▲ +N Niveles", style=discord.ButtonStyle.success, row=0)
    async def mas_n(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalSubirN(None, self.target, self))

    @discord.ui.button(label="▼▼ -N Niveles", style=discord.ButtonStyle.danger, row=0)
    async def menos_n(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalBajarN(None, self.target, self))

    @discord.ui.button(label="⭐ MAX", style=discord.ButtonStyle.primary, row=1)
    async def max_nivel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sube al nivel máximo de golpe, sin notificaciones intermedias."""
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        uid     = str(self.target.id)
        usuario = await db.get_usuario(uid)
        if not usuario:
            await interaction.followup.send("❌ El usuario no está en la BD.", ephemeral=True)
            return

        nivel_viejo = usuario["nivel"]
        if nivel_viejo >= NIVEL_MAXIMO:
            await interaction.followup.send(
                f"**{self.target.display_name}** ya está en el nivel máximo ({NIVEL_MAXIMO}).",
                ephemeral=True,
            )
            return

        # XP acumulada hasta nivel máximo (sin notificaciones de subida)
        xp_ganada    = sum(xp_para_nivel(n) for n in range(nivel_viejo, NIVEL_MAXIMO))
        xp_total_new = usuario["xp_total"] + xp_ganada
        await db.actualizar_xp(uid, xp=0, nivel=NIVEL_MAXIMO, xp_total=xp_total_new, last_xp=usuario["last_xp"])

        # Asignar el rango máximo si no tiene uno elegido manualmente
        if not usuario["rol_elegido"]:
            rango = get_rango_actual(NIVEL_MAXIMO)
            if rango:
                _, _, rol_id = rango
                rol = interaction.guild.get_role(rol_id)
                if rol:
                    ids_rango      = ids_todos_rangos()
                    roles_a_quitar = [r for r in self.target.roles if r.id in ids_rango]
                    if roles_a_quitar:
                        await self.target.remove_roles(*roles_a_quitar, reason="Dev: MAX nivel")
                    await self.target.add_roles(rol, reason=f"Dev: nivel {NIVEL_MAXIMO}")

        embed = discord.Embed(
            title="🛠️ Dev — Nivel máximo",
            description=(
                f"**{self.target.display_name}**\n"
                f"Nivel: `{nivel_viejo}` → `{NIVEL_MAXIMO}` ⭐\n"
                f"XP acumulada: `{usuario['xp_total']:,}` → `{xp_total_new:,}`\n"
                f"_(Sin notificaciones intermedias)_"
            ),
            color=COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔄 Reset", style=discord.ButtonStyle.secondary, row=1)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return

        uid = str(self.target.id)
        await db.reset_usuario(uid)

        ids_rango      = ids_todos_rangos()
        roles_a_quitar = [r for r in self.target.roles if r.id in ids_rango]
        if roles_a_quitar:
            await self.target.remove_roles(*roles_a_quitar, reason="Dev: reset completo")
        await db.set_rol_elegido(uid, 0)

        embed = discord.Embed(
            title="🛠️ Dev — Reset completo",
            description=f"**{self.target.display_name}** volvió al nivel 1 sin XP.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SELECT de rangos — se muestra en embed efímero al pulsar el botón
# ══════════════════════════════════════════════════════════════════════════════

class RangoSelectView(discord.ui.View):
    """
    Panel de selección de rango.
    • El select lo puede usar el invoker (propio perfil o dev gestionando a otro).
    • El botón 🛠️ Dev Mode solo aparece y funciona para DESARROLLADOR_ID,
      oculto aquí para que nadie más sepa que existe.
    """

    def __init__(
        self,
        invoker: discord.Member,
        target: discord.Member,
        rangos: list[tuple[int, str, int]],
    ):
        super().__init__(timeout=None)
        self.invoker = invoker
        self.target  = target

        grupos = [rangos[i:i+25] for i in range(0, len(rangos), 25)]

        for idx, grupo in enumerate(grupos):
            opciones = [
                discord.SelectOption(
                    label=nombre,
                    value=str(rol_id),
                    description=f"Nivel {nivel_r}",
                )
                for nivel_r, nombre, rol_id in grupo
            ]
            placeholder = (
                f"Rangos {grupo[0][0]}–{grupo[-1][0]}"
                if len(grupos) > 1
                else "Elige tu rango"
            )
            select = discord.ui.Select(
                placeholder=placeholder,
                options=opciones,
                custom_id=f"rango_select_{idx}_{target.id}",
                row=idx,
            )
            select.callback = self._make_cb()
            self.add_item(select)

        # Botón Dev Mode — solo visible si el invoker es el desarrollador.
        # Aparece junto al select, sin llamar la atención desde el perfil público.
        if invoker.id == DESARROLLADOR_ID:
            dev_btn = discord.ui.Button(
                label="🛠️ Dev Mode",
                style=discord.ButtonStyle.primary,
                row=min(len(grupos), 4),   # fila siguiente a los selects (máx row 4)
            )
            dev_btn.callback = self._dev_cb
            self.add_item(dev_btn)

    def _make_cb(self):
        async def callback(interaction: discord.Interaction):
            # Solo el invoker puede usar el select (él mismo o el dev en modo G)
            if interaction.user.id != self.invoker.id:
                await interaction.response.send_message(
                    "❌ Este panel no es tuyo.", ephemeral=True
                )
                return

            rol_id = int(interaction.data["values"][0])
            nuevo  = interaction.guild.get_role(rol_id)

            if not nuevo:
                await interaction.response.send_message(
                    "⚠️ Rol no encontrado en el servidor.", ephemeral=True
                )
                return

            ids_rango      = ids_todos_rangos()
            roles_a_quitar = [r for r in self.target.roles if r.id in ids_rango]
            if roles_a_quitar:
                await self.target.remove_roles(*roles_a_quitar, reason="Rango elegido manualmente")
            await self.target.add_roles(nuevo, reason=f"Rango manual: {nuevo.name}")
            await db.set_rol_elegido(str(self.target.id), 1)

            embed = discord.Embed(
                description=f"✅ Rango **{nuevo.name}** equipado.",
                color=COLOR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return callback

    async def _dev_cb(self, interaction: discord.Interaction):
        """Botón secreto — solo responde al desarrollador."""
        if interaction.user.id != DESARROLLADOR_ID:
            # Silencio total: cualquier otro que lo pulse no recibe nada
            await interaction.response.defer()
            return
        dev_view = DevView(self.target)
        embed = discord.Embed(
            title=f"🛠️ Dev Mode — {self.target.display_name}",
            description="Ajusta el nivel directamente. Todas las respuestas son efímeras.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, view=dev_view, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW PERFIL — botón de rango + botón dev (sin timeout)
# ══════════════════════════════════════════════════════════════════════════════

class PerfilView(discord.ui.View):

    def __init__(self, invoker: discord.Member, target: discord.Member, rangos: list):
        super().__init__(timeout=None)
        self.invoker = invoker
        self.target  = target
        self.rangos  = rangos

        if rangos:
            rango_btn = discord.ui.Button(
                label="🎖️ Rango",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            rango_btn.callback = self._rango_cb
            self.add_item(rango_btn)

            reset_btn = discord.ui.Button(
                label="🔄 Restablecer rango",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            reset_btn.callback = self._reset_rango_cb
            self.add_item(reset_btn)
        # El botón Dev Mode NO aparece aquí — está oculto dentro del panel de Rango (🎖️)

    async def _rango_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("❌ Este panel no es tuyo.", ephemeral=True)
            return
        es_propio = (self.invoker.id == self.target.id)
        titulo    = "🎖️ Elige tu rango" if es_propio else f"🎖️ Rango de {self.target.display_name}"
        desc      = (
            "Selecciona el rango que quieres mostrar.\nSolo se mostrará el que elijas."
            if es_propio else
            "Selecciona el rango a equipar en este usuario."
        )
        embed = discord.Embed(title=titulo, description=desc, color=COLOR)
        # Pasamos invoker para que el select lo valide y para mostrar el botón Dev si procede
        view = RangoSelectView(self.invoker, self.target, self.rangos)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _reset_rango_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("❌ Este panel no es tuyo.", ephemeral=True)
            return
        uid     = str(self.target.id)
        usuario = await db.get_usuario(uid)
        rango   = get_rango_actual(usuario["nivel"])
        if not rango:
            await interaction.response.send_message("❌ No tienes ningún rango aún.", ephemeral=True)
            return
        _, nombre_r, rol_id = rango
        nuevo = interaction.guild.get_role(rol_id)
        if not nuevo:
            await interaction.response.send_message("⚠️ Rol no encontrado en el servidor.", ephemeral=True)
            return
        ids_rango      = ids_todos_rangos()
        roles_a_quitar = [r for r in self.target.roles if r.id in ids_rango]
        if roles_a_quitar:
            await self.target.remove_roles(*roles_a_quitar, reason="Restablecimiento de rango automático")
        await self.target.add_roles(nuevo, reason=f"Rango restablecido: {nombre_r}")
        await db.set_rol_elegido(uid, 0)
        embed = discord.Embed(
            title="🔄 Rango restablecido",
            description=(
                f"Tu rango ahora es **{nombre_r}** (el correspondiente a tu nivel actual).\n\n"
                f"✅ A partir de ahora tu rango **se actualizará automáticamente** cada vez que subas de nivel."
            ),
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)



# ══════════════════════════════════════════════════════════════════════════════
#  COG PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class Niveles(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if len(message.content.strip()) < 5:
            return

        uid      = str(message.author.id)
        username = str(message.author)
        ahora    = time.time()

        await db.upsert_usuario(uid, username)
        usuario = await db.get_usuario(uid)

        if not usuario["rol_elegido"] and 1 in DEFINICIONES:
            rango_base = get_rango_actual(usuario["nivel"])
            if rango_base:
                _, _, rol_id_base = rango_base
                rol_base = message.guild.get_role(rol_id_base)
                tiene_rango = any(r.id in ids_todos_rangos() for r in message.author.roles)
                if rol_base and not tiene_rango:
                    await message.author.add_roles(rol_base, reason="Rango base nivel 1")

        if ahora - usuario["last_xp"] < COOLDOWN_SEGUNDOS:
            return
        if usuario["nivel"] >= NIVEL_MAXIMO:
            return

        ganado   = random.randint(XP_MIN, XP_MAX)
        xp_nuevo = usuario["xp"] + ganado
        xp_total = usuario["xp_total"] + ganado
        nivel    = usuario["nivel"]
        subio    = False

        while xp_nuevo >= xp_para_nivel(nivel) and nivel < NIVEL_MAXIMO:
            xp_nuevo -= xp_para_nivel(nivel)
            nivel    += 1
            subio     = True

        await db.actualizar_xp(uid, xp_nuevo, nivel, xp_total, ahora)

        if subio:
            await self._gestionar_subida(message, usuario, nivel)

    async def _gestionar_subida(self, message, usuario_antes, nivel_nuevo):
        member  = message.author
        embed   = discord.Embed(color=COLOR)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.title = f"⬆️ ¡Subiste al nivel {nivel_nuevo}!"
        await _notificar_subida(message.author, message.guild, usuario_antes, nivel_nuevo)

        if nivel_nuevo in DEFINICIONES:
            rango = get_rango_actual(nivel_nuevo)
            if rango:
                _, nombre_rango, rol_id = rango
                rol = message.guild.get_role(rol_id)

                if usuario_antes["rol_elegido"]:
                    embed.description = (
                        f"🎖️ ¡Desbloqueaste el rango **{nombre_rango}**!\n"
                        f"Tu rango actual se mantiene porque lo elegiste tú.\n"
                        f"Usa `!perfil` → **Restablecer rango** si quieres actualizarlo."
                    )
                else:
                    embed.description = (
                        f"🎖️ ¡Desbloqueaste el rango **{nombre_rango}**!\n"
                        f"Se ha equipado automáticamente."
                    )
                    if rol:
                        ids_rango      = ids_todos_rangos()
                        roles_a_quitar = [r for r in member.roles if r.id in ids_rango]
                        if roles_a_quitar:
                            await member.remove_roles(*roles_a_quitar, reason="Auto rango")
                        await member.add_roles(rol, reason=f"Nivel {nivel_nuevo}")
            else:
                embed.description = "¡Sigue así!"
        else:
            embed.description = "¡Sigue participando para ganar más XP!"

        AUTODESTRUYE_SEGUNDOS = 10
        embed.set_footer(
            text=f"Nivel {nivel_nuevo}  •  🕐 Este mensaje se autodestruye en {AUTODESTRUYE_SEGUNDOS}s"
        )

        try:
            dm = await member.create_dm()
            await dm.send(embed=embed, delete_after=AUTODESTRUYE_SEGUNDOS)
        except discord.Forbidden:
            await message.channel.send(
                content=f"||{member.mention}||",
                embed=embed,
                delete_after=AUTODESTRUYE_SEGUNDOS,
            )

    @commands.command(name="perfil")
    async def perfil(self, ctx: commands.Context, miembro: discord.Member = None, flag: str = None):
        """
        !perfil              → perfil propio con panel completo
        !perfil <user>       → perfil ajeno, solo embed (sin botones)
        !perfil <user> G     → igual que el anterior para cualquiera que no sea el dev;
                               para el DESARROLLADOR_ID: perfil completo gestionable del usuario
        """
        # ── Determinar target ──────────────────────────────────────────────────
        if miembro is None:
            target = ctx.author
        else:
            target = miembro

        # ── Determinar modo ────────────────────────────────────────────────────
        es_propio  = (target.id == ctx.author.id)
        flag_g_dev = (
            flag is not None
            and flag.upper() == "G"
            and ctx.author.id == DESARROLLADOR_ID
        )
        # Si alguien que NO es el dev pone la G, se ignora silenciosamente
        # y se muestra el perfil del target sin botones (como cualquier !perfil <user>)

        uid = str(target.id)
        await db.upsert_usuario(uid, str(target))
        usuario = await db.get_usuario(uid)

        nivel    = usuario["nivel"]
        xp       = usuario["xp"]
        xp_total = usuario["xp_total"]
        elegido  = bool(usuario["rol_elegido"])

        if nivel < NIVEL_MAXIMO:
            xp_sig   = xp_para_nivel(nivel)
            falta    = xp_sig - xp
            meta     = xp_total + falta
            progreso = min(int((xp / xp_sig) * 20), 20)
            barra    = "█" * progreso + "░" * (20 - progreso)
            xp_txt   = f"`{barra}` {xp_total:,} / {meta:,} XP"
        else:
            xp_txt = "**Nivel máximo alcanzado** ⭐"

        ids_rang     = ids_todos_rangos()
        rol_equipado = next((r for r in target.roles if r.id in ids_rang), None)
        rango_txt    = rol_equipado.name if rol_equipado else "Sin rango aún"

        embed = discord.Embed(
            title=f"📊 Perfil de {target.display_name}",
            color=COLOR,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="🎚️ Nivel",    value=f"`{nivel}`",      inline=True)
        embed.add_field(name="🏆 XP Total", value=f"`{xp_total:,}`", inline=True)
        embed.add_field(name="🎖️ Rango",    value=rango_txt,         inline=True)
        embed.add_field(name="📈 Progreso", value=xp_txt,            inline=False)

        if elegido:
            embed.set_footer(text="Rango equipado manualmente.")
        else:
            embed.set_footer(text="Tu rango se actualiza solo al subir de nivel.")

        # ── Decidir qué view mostrar ───────────────────────────────────────────
        rangos_desc = get_todos_desbloqueados(nivel)

        if es_propio:
            # Perfil propio: panel completo (Rango + Restablecer; Dev oculto en el select)
            view = PerfilView(ctx.author, target, rangos_desc)
        elif flag_g_dev:
            # Dev viendo a otro con !perfil <user> G: panel completo gestionable
            view = PerfilView(ctx.author, target, rangos_desc)
        else:
            # Perfil ajeno (o G ignorada porque no es el dev): solo embed, sin botones
            view = None

        await ctx.send(embed=embed, view=view)


# ══════════════════════════════════════════════════════════════════════════════
#  RANGOS GESTION — helpers internos
# ══════════════════════════════════════════════════════════════════════════════

def _es_privilegiado(member: discord.Member) -> bool:
    """True si el miembro es admin, o tiene manage_guild/manage_roles."""
    p = member.guild_permissions
    return p.administrator or p.manage_guild or p.manage_roles


def _tabla_rangos_actuales() -> str:
    if not NIVELES_CON_RANGO:
        return "_Sin rangos definidos todavía._"
    return "\n".join(
        f"`Niv. {n:>3}` — {DEFINICIONES[n]}"
        for n in NIVELES_CON_RANGO
    )


def _embed_panel() -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Panel de Gestión de Rangos",
        description=(
            f"**{len(DEFINICIONES)} rangos activos** entre el nivel 1 y el 300.\n"
            "Los cambios se aplican en tiempo real.\n\n"
            + _tabla_rangos_actuales()
        ),
        color=COLOR,
    )
    embed.set_footer(text="Solo mods y admins pueden operar este panel.")
    return embed


async def _crear_rango_en_servidor(
    interaction: discord.Interaction,
    nivel: int,
    nombre: str,
) -> None:
    """Valida, agrega a config, crea el rol en Discord y guarda el ID."""
    # Validación previa de permisos (por si acaso)
    if not _es_privilegiado(interaction.user):
        await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
        return

    error = agregar_rango(nivel, nombre)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    nuevo_rol = await interaction.guild.create_role(
        name=nombre,
        color=discord.Color.from_rgb(139, 0, 0),
        permissions=discord.Permissions.none(),
        hoist=False,
        mentionable=False,
        reason=f"Rango creado por {interaction.user} — nivel {nivel}",
    )

    ids = get_ids_cargados()
    ids[nivel] = nuevo_rol.id
    guardar_ids(ids)

    embed = discord.Embed(
        title="✅ Rango creado",
        description=(
            f"**{nombre}**\n"
            f"Se activa en el nivel **{nivel}**.\n"
            f"Rol de Discord: {nuevo_rol.mention}"
        ),
        color=COLOR,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MODALES — Gestión de rangos
# ══════════════════════════════════════════════════════════════════════════════

class ModalCrearNombre(discord.ui.Modal, title="Crear Rango — Nombre"):
    nombre = discord.ui.TextInput(
        label="Nombre del nuevo rango",
        placeholder="Ej: 💫 Héroe  (puedes incluir emoji)",
        min_length=1,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return

        nombre_str = self.nombre.value.strip()
        niveles    = NIVELES_CON_RANGO

        # Construir opciones del Select: un hueco entre cada par de rangos consecutivos
        opciones: list[discord.SelectOption] = []
        for i in range(len(niveles) - 1):
            n_a = niveles[i]
            n_b = niveles[i + 1]
            if n_b - n_a > 1:                       # hay margen para insertar
                mid = (n_a + n_b) // 2
                label = f"Entre niv.{n_a} y niv.{n_b}"
                desc  = (
                    f"{DEFINICIONES[n_a][:20]} → {DEFINICIONES[n_b][:20]}"
                    f"  •  Nivel sugerido: {mid}"
                )
                opciones.append(discord.SelectOption(
                    label=label[:100],
                    description=desc[:100],
                    value=f"{n_a}|{n_b}",
                ))

        view = PosicionView(nombre_str, opciones)

        lineas = _tabla_rangos_actuales()
        embed = discord.Embed(
            title="📍 Posicionar nuevo rango",
            description=(
                f"Nombre elegido: **{nombre_str}**\n\n"
                "Elige en qué **hueco** debe aparecer usando el selector.\n"
                "El nivel asignado será el punto medio del hueco.\n"
                "Si necesitas un nivel exacto, pulsa **🔢 Nivel exacto**.\n\n"
                f"**Rangos actuales:**\n{lineas}"
            ),
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ModalNivelExacto(discord.ui.Modal, title="Nivel exacto"):
    nivel_input = discord.ui.TextInput(
        label="Nivel (1–300)",
        placeholder="Ej: 45",
        min_length=1,
        max_length=3,
    )

    def __init__(self, nombre_rango: str):
        super().__init__()
        self.nombre_rango = nombre_rango

    async def on_submit(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        try:
            nivel = int(self.nivel_input.value)
            if not 1 <= nivel <= 300:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Escribe un número válido entre 1 y 300.", ephemeral=True
            )
            return
        await _crear_rango_en_servidor(interaction, nivel, self.nombre_rango)


class ModalEditarNombre(discord.ui.Modal, title="Editar nombre de rango"):
    nuevo_nombre = discord.ui.TextInput(
        label="Nuevo nombre",
        min_length=1,
        max_length=50,
    )

    def __init__(self, nivel: int, nombre_actual: str):
        super().__init__()
        self.nivel = nivel
        self.nuevo_nombre.placeholder = nombre_actual

    async def on_submit(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return

        nuevo = self.nuevo_nombre.value.strip()
        error = editar_nombre_rango(self.nivel, nuevo)
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        # Actualizar nombre del rol en Discord
        ids = get_ids_cargados()
        if self.nivel in ids:
            rol = interaction.guild.get_role(ids[self.nivel])
            if rol:
                try:
                    await rol.edit(
                        name=nuevo,
                        reason=f"Rango editado por {interaction.user}",
                    )
                except discord.Forbidden:
                    pass   # sin permisos para editar ese rol concreto

        embed = discord.Embed(
            title="✅ Rango actualizado",
            description=f"El rango del nivel **{self.nivel}** ahora se llama **{nuevo}**.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEWS — Gestión de rangos (timeout=None, verifican permisos en cada botón)
# ══════════════════════════════════════════════════════════════════════════════

class PosicionView(discord.ui.View):
    """Selector de posición que aparece tras el modal de nombre."""

    def __init__(self, nombre_rango: str, opciones: list[discord.SelectOption]):
        super().__init__(timeout=None)
        self.nombre_rango = nombre_rango

        if opciones:
            sel = discord.ui.Select(
                placeholder="Elige el hueco donde insertar el rango…",
                options=opciones[:25],
                custom_id=f"pos_select_{nombre_rango[:8].replace(' ', '_')}",
                row=0,
            )
            sel.callback = self._on_select
            self.add_item(sel)
        else:
            # Sin huecos disponibles → solo botón de nivel exacto
            aviso = discord.ui.Button(
                label="⚠️ Sin huecos disponibles",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=0,
            )
            self.add_item(aviso)

        btn_exacto = discord.ui.Button(
            label="🔢 Nivel exacto",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        btn_exacto.callback = self._on_exacto
        self.add_item(btn_exacto)

    async def _on_select(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        n_a, n_b = map(int, interaction.data["values"][0].split("|"))
        mid = (n_a + n_b) // 2
        await _crear_rango_en_servidor(interaction, mid, self.nombre_rango)

    async def _on_exacto(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalNivelExacto(self.nombre_rango))


class EditarSelectView(discord.ui.View):
    """Select con todos los rangos actuales para elegir cuál editar."""

    def __init__(self):
        super().__init__(timeout=None)
        opciones = [
            discord.SelectOption(
                label=f"Niv.{n} — {nombre}"[:100],
                description=f"Nivel {n}",
                value=str(n),
            )
            for n, nombre in sorted(DEFINICIONES.items())
        ]
        grupos = [opciones[i:i+25] for i in range(0, len(opciones), 25)]
        for idx, grupo in enumerate(grupos):
            sel = discord.ui.Select(
                placeholder="Elige el rango a editar…" if idx == 0 else f"Más rangos ({idx + 1})…",
                options=grupo,
                custom_id=f"editar_select_{idx}",
                row=idx,
            )
            sel.callback = self._make_cb()
            self.add_item(sel)

    def _make_cb(self):
        async def cb(interaction: discord.Interaction):
            if not _es_privilegiado(interaction.user):
                await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
                return
            nivel         = int(interaction.data["values"][0])
            nombre_actual = DEFINICIONES.get(nivel, "")
            await interaction.response.send_modal(ModalEditarNombre(nivel, nombre_actual))
        return cb


class EliminarSelectView(discord.ui.View):
    """Select con todos los rangos actuales para elegir cuál eliminar."""

    def __init__(self):
        super().__init__(timeout=None)
        opciones = [
            discord.SelectOption(
                label=f"Niv.{n} — {nombre}"[:100],
                description=f"Nivel {n}",
                value=str(n),
            )
            for n, nombre in sorted(DEFINICIONES.items())
        ]
        grupos = [opciones[i:i+25] for i in range(0, len(opciones), 25)]
        for idx, grupo in enumerate(grupos):
            sel = discord.ui.Select(
                placeholder="Elige el rango a eliminar…" if idx == 0 else f"Más rangos ({idx + 1})…",
                options=grupo,
                custom_id=f"eliminar_select_{idx}",
                row=idx,
            )
            sel.callback = self._make_cb()
            self.add_item(sel)

    def _make_cb(self):
        async def cb(interaction: discord.Interaction):
            if not _es_privilegiado(interaction.user):
                await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
                return
            nivel  = int(interaction.data["values"][0])
            nombre = DEFINICIONES.get(nivel, "?")
            view   = ConfirmarEliminarView(nivel, nombre)
            embed  = discord.Embed(
                title="⚠️ Confirmar eliminación",
                description=(
                    f"¿Eliminar **{nombre}** (nivel {nivel})?\n\n"
                    "Esto borrará el rol de Discord asociado y no puede deshacerse."
                ),
                color=0xFF6B6B,
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return cb


class ConfirmarEliminarView(discord.ui.View):

    def __init__(self, nivel: int, nombre: str):
        super().__init__(timeout=None)
        self.nivel  = nivel
        self.nombre = nombre

    @discord.ui.button(label="✅ Confirmar eliminación", style=discord.ButtonStyle.danger, row=0)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return

        # Eliminar rol de Discord primero
        ids = get_ids_cargados()
        if self.nivel in ids:
            rol = interaction.guild.get_role(ids[self.nivel])
            if rol:
                try:
                    await rol.delete(reason=f"Rango eliminado por {interaction.user}")
                except discord.Forbidden:
                    pass

        error = eliminar_rango(self.nivel)
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🗑️ Rango eliminado",
            description=f"El rango **{self.nombre}** (nivel {self.nivel}) ha sido eliminado.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary, row=0)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_message("❎ Eliminación cancelada.", ephemeral=True)


class PanelRangosView(discord.ui.View):
    """Panel principal — siempre efímero."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Crear Rango", style=discord.ButtonStyle.success, row=0)
    async def crear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalCrearNombre())

    @discord.ui.button(label="✏️ Editar Rango", style=discord.ButtonStyle.primary, row=0)
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        if not DEFINICIONES:
            await interaction.response.send_message("❌ No hay rangos que editar.", ephemeral=True)
            return
        embed = discord.Embed(
            title="✏️ Editar Rango",
            description="Selecciona el rango cuyo nombre deseas cambiar.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, view=EditarSelectView(), ephemeral=True)

    @discord.ui.button(label="🗑️ Eliminar Rango", style=discord.ButtonStyle.danger, row=0)
    async def eliminar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        if not DEFINICIONES:
            await interaction.response.send_message("❌ No hay rangos que eliminar.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🗑️ Eliminar Rango",
            description="Selecciona el rango que deseas eliminar del servidor.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, view=EliminarSelectView(), ephemeral=True)

    @discord.ui.button(label="🔄 Actualizar", style=discord.ButtonStyle.secondary, row=0)
    async def actualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=_embed_panel(), view=self)


class AbrirPanelView(discord.ui.View):
    """Botón público que abre el panel efímero. Sin timeout."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔧 Abrir Panel", style=discord.ButtonStyle.primary)
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message(
                "🔒 Solo moderadores y administradores pueden abrir este panel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=_embed_panel(),
            view=PanelRangosView(),
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  COG — RangosGestion
# ══════════════════════════════════════════════════════════════════════════════

class RangosGestion(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="rangosG")
    async def rangos_g(self, ctx: commands.Context):
        """Panel de gestión de rangos. Solo mods y admins."""
        if not _es_privilegiado(ctx.author):
            await ctx.send(
                "🔒 No tienes permisos para usar este comando.",
                delete_after=5,
            )
            return

        embed = discord.Embed(
            title="🎖️ Gestión de Rangos",
            description=(
                "Desde aquí puedes **crear**, **editar** y **eliminar** "
                "los rangos del servidor.\n\n"
                f"Hay **{len(DEFINICIONES)} rangos** activos, repartidos "
                f"entre el nivel **1** y el **300**.\n\n"
                "Pulsa el botón para abrir el panel de control.\n"
                "Todos los cambios se aplican al instante en Discord."
            ),
            color=COLOR,
        )
        embed.set_footer(text="El panel es visible solo para ti (efímero).")
        await ctx.send(embed=embed, view=AbrirPanelView())


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers de arranque
# ══════════════════════════════════════════════════════════════════════════════

async def init_miembros(bot: commands.Bot) -> None:
    guild    = bot.guilds[0]
    ids_rang = ids_todos_rangos()
    rango_b  = get_rango_actual(1)

    rol_base = None
    if rango_b:
        rol_base = guild.get_role(rango_b[2])

    registrados = 0
    asignados   = 0

    for member in guild.members:
        if member.bot:
            continue
        await db.upsert_usuario(str(member.id), str(member))
        registrados += 1
        tiene_rango = any(r.id in ids_rang for r in member.roles)
        if not tiene_rango and rol_base:
            await member.add_roles(rol_base, reason="Carga inicial: rango Miembro")
            asignados += 1

    print(f"✅ [Miembros] {registrados} registrados, {asignados} con rango base asignado.")


async def setup(bot: commands.Bot):
    cargar_ids()
    await bot.add_cog(Niveles(bot))
    await bot.add_cog(RangosGestion(bot))