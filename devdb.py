"""
devdb.py — Panel secreto de gestión de la base de datos
Comando: !devdb
Solo DESARROLLADOR_ID puede invocarlo. Si no es él: pass silencioso.
El embed principal NO es efímero. El panel de gestión SÍ (con botones sin timeout).
El botón de gestión lo pueden usar DESARROLLADOR_ID o cualquier Admin del servidor.
"""

import discord
from discord.ext import commands
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "sql"))
import sql.db_manager as db
from config import DESARROLLADOR_ID

COLOR = 0x8B0000
PAGE  = 8   # usuarios por página en la lista


# ══════════════════════════════════════════════════════════════════════════════
#  MODAL — Buscar usuario
# ══════════════════════════════════════════════════════════════════════════════

class ModalBuscar(discord.ui.Modal, title="Buscar usuario"):
    termino = discord.ui.TextInput(
        label="Nombre o parte del nombre",
        placeholder="Ej: Kasi",
        min_length=1, max_length=32,
    )

    async def on_submit(self, interaction: discord.Interaction):
        resultados = await db.buscar_usuario_nombre(self.termino.value)
        if not resultados:
            await interaction.response.send_message(
                f"❌ No se encontró ningún usuario con `{self.termino.value}`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🔍 Resultados para '{self.termino.value}'",
            color=COLOR,
        )
        for u in resultados:
            embed.add_field(
                name=f"📌 {u['username']}",
                value=(
                    f"ID: `{u['discord_id']}`\n"
                    f"Nivel: `{u['nivel']}` | XP total: `{u['xp_total']:,}`\n"
                    f"Rol elegido: {'Sí' if u['rol_elegido'] else 'No'}"
                ),
                inline=False,
            )
        view = AccionesUsuarioView(resultados[0]["discord_id"], resultados[0]["username"])
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — Acciones sobre un usuario concreto (sin timeout)
# ══════════════════════════════════════════════════════════════════════════════

class AccionesUsuarioView(discord.ui.View):
    def __init__(self, discord_id: str, username: str):
        super().__init__(timeout=None)
        self.discord_id = discord_id
        self.username   = username

    def _check(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == DESARROLLADOR_ID
            or interaction.user.guild_permissions.administrator
        )

    @discord.ui.button(label="🔄 Reset usuario", style=discord.ButtonStyle.danger, row=0)
    async def reset_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await db.reset_usuario(self.discord_id)
        embed = discord.Embed(
            description=f"✅ **{self.username}** reseteado a nivel 1.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🗑️ Eliminar de BD", style=discord.ButtonStyle.danger, row=0)
    async def eliminar_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await db.eliminar_usuario(self.discord_id)
        embed = discord.Embed(
            description=f"🗑️ **{self.username}** eliminado de la base de datos.",
            color=COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📋 Ver datos completos", style=discord.ButtonStyle.secondary, row=0)
    async def ver_datos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        u = await db.get_usuario(self.discord_id)
        if not u:
            await interaction.response.send_message("❌ Usuario no encontrado.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🗃️ Datos de {u['username']}", color=COLOR)
        embed.add_field(name="Discord ID",   value=f"`{u['discord_id']}`",  inline=True)
        embed.add_field(name="Nivel",        value=f"`{u['nivel']}`",        inline=True)
        embed.add_field(name="XP (nivel)",   value=f"`{u['xp']:,}`",         inline=True)
        embed.add_field(name="XP Total",     value=f"`{u['xp_total']:,}`",   inline=True)
        embed.add_field(name="Rol elegido",  value="Sí" if u["rol_elegido"] else "No", inline=True)
        embed.add_field(name="Last XP unix", value=f"`{u['last_xp']:.0f}`",  inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — Lista paginada (sin timeout)
# ══════════════════════════════════════════════════════════════════════════════

class ListaUsuariosView(discord.ui.View):
    def __init__(self, pagina: int = 0):
        super().__init__(timeout=None)
        self.pagina = pagina

    def _check(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == DESARROLLADOR_ID
            or interaction.user.guild_permissions.administrator
        )

    async def _render(self, interaction: discord.Interaction):
        total   = await db.count_usuarios()
        paginas = max(1, (total + PAGE - 1) // PAGE)
        self.pagina = max(0, min(self.pagina, paginas - 1))

        usuarios = await db.todos_usuarios(offset=self.pagina * PAGE, limite=PAGE)

        embed = discord.Embed(
            title=f"🗃️ Usuarios en BD — Página {self.pagina + 1}/{paginas}",
            color=COLOR,
        )
        for u in usuarios:
            embed.add_field(
                name=f"`{u['username']}`",
                value=(
                    f"ID: `{u['discord_id']}`\n"
                    f"Nv. `{u['nivel']}` | XP nivel `{u['xp']:,}` | XP total `{u['xp_total']:,}`\n"
                    f"Rol elegido: {'✅' if u['rol_elegido'] else '❌'}"
                ),
                inline=False,
            )
        embed.set_footer(text=f"Total: {total} usuarios registrados")

        self.clear_items()
        prev = discord.ui.Button(
            label="◀", style=discord.ButtonStyle.secondary,
            disabled=(self.pagina == 0),
        )
        prev.callback = self._prev
        self.add_item(prev)

        nxt = discord.ui.Button(
            label="▶", style=discord.ButtonStyle.secondary,
            disabled=(self.pagina >= paginas - 1),
        )
        nxt.callback = self._next
        self.add_item(nxt)

        return embed

    async def _prev(self, interaction: discord.Interaction):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        self.pagina -= 1
        embed = await self._render(interaction)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next(self, interaction: discord.Interaction):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        self.pagina += 1
        embed = await self._render(interaction)
        await interaction.response.edit_message(embed=embed, view=self)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — Panel de gestión principal (sin timeout, efímero)
# ══════════════════════════════════════════════════════════════════════════════

class GestionView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    def _check(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == DESARROLLADOR_ID
            or interaction.user.guild_permissions.administrator
        )

    @discord.ui.button(label="📋 Ver todos los usuarios", style=discord.ButtonStyle.secondary, row=0)
    async def ver_todos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        view  = ListaUsuariosView(pagina=0)
        embed = await view._render(interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔍 Buscar usuario", style=discord.ButtonStyle.primary, row=0)
    async def buscar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalBuscar())

    @discord.ui.button(label="📊 Estadísticas BD", style=discord.ButtonStyle.secondary, row=0)
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return

        total = await db.count_usuarios()
        top   = await db.top_usuarios(1)
        lider = top[0] if top else None

        embed = discord.Embed(title="📊 Estadísticas de la BD", color=COLOR)
        embed.add_field(name="👥 Usuarios registrados", value=f"`{total}`",    inline=True)
        if lider:
            embed.add_field(
                name="🏆 Líder de XP",
                value=f"`{lider['username']}` — Nv.`{lider['nivel']}` | `{lider['xp_total']:,}` XP",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — Botón principal del embed no efímero (sin timeout)
# ══════════════════════════════════════════════════════════════════════════════

class DevDBMainView(discord.ui.View):
    """Permanece en el canal. Solo abre el panel de gestión (efímero)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🗃️ Gestionar base de datos", style=discord.ButtonStyle.primary)
    async def abrir_gestion(self, interaction: discord.Interaction, button: discord.ui.Button):
        es_dev   = interaction.user.id == DESARROLLADOR_ID
        es_admin = interaction.user.guild_permissions.administrator
        if not es_dev and not es_admin:
            await interaction.response.send_message("🔒 Sin acceso.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🗃️ Gestión de Base de Datos",
            description="Panel de administración del sistema de niveles.",
            color=COLOR,
        )
        await interaction.response.send_message(
            embed=embed,
            view=GestionView(),
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════════════════════

class DevDB(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="devdb")
    async def devdb(self, ctx: commands.Context):
        if ctx.author.id != DESARROLLADOR_ID:
            return   # silencio total

        total = await db.count_usuarios()
        top   = await db.top_usuarios(1)
        lider = top[0] if top else None

        embed = discord.Embed(
            title="🗃️ Panel de Base de Datos — Sistema de Niveles",
            color=COLOR,
        )
        embed.add_field(name="👥 Usuarios en BD", value=f"`{total}`", inline=True)
        if lider:
            embed.add_field(
                name="🏆 Líder actual",
                value=f"`{lider['username']}` — Nv.`{lider['nivel']}`",
                inline=True,
            )
        embed.set_footer(text="Acceso: Desarrollador y Admins del servidor.")

        # Embed NO efímero, con botón de acceso al panel
        await ctx.send(embed=embed, view=DevDBMainView())


async def setup(bot: commands.Bot):
    await bot.add_cog(DevDB(bot))