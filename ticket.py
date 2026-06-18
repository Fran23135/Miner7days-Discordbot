import discord
from discord.ext import commands
import json
import os
import aiohttp
import asyncio
import base64
from datetime import datetime
import html as _html_mod
from config import ROLES, CANALES as _CFG_CANALES
import pin
import io
import zipfile
import uuid

# ─────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────
MAX_IMAGES            = 5
MAX_MESSAGES          = 5
SESSION_TIMEOUT_HOURS = 24
ALLOWED_IMAGE_EXTS    = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
TICKET_NOTIFY_CHANNEL_ID = _CFG_CANALES["tickets_notify"]


TICKET_CATEGORIES = [
    {"value": "bug_juego",     "label": "🐛 Bug del juego (7 Days to Die)", "emoji": "🐛",
     "description": "Error, glitch o comportamiento inesperado en el juego base."},
    {"value": "bug_tecnico",   "label": "⚙️ Bug técnico / Mods",            "emoji": "⚙️",
     "description": "Problemas con mods, rendimiento, conexión, comandos del bot, etc."},
    {"value": "recomendacion", "label": "💡 Recomendación o idea",           "emoji": "💡",
     "description": "Sugerencias para mejorar el servidor, el bot o la experiencia."},
    {"value": "otros",         "label": "📌 Otros",                          "emoji": "📌",
     "description": "Cualquier otro asunto no listado arriba."}
]

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
TICKETS_FILE      = os.path.join(BASE_DIR, "Cache", "tickets.json")
TICKETS_PER_PAGE  = 1
ALLOWED_ROLE_IDS  = ROLES
NETLIFY_MANIFEST  = os.path.join(BASE_DIR, "Cache", "netlify_manifest.json")
# ─────────────────────────────────────────────
#  HELPERS JSON
# ─────────────────────────────────────────────
def load_tickets() -> list:
    if not os.path.exists(TICKETS_FILE):
        return []
    with open(TICKETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tickets(tickets: list) -> None:
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2, ensure_ascii=False)

def get_next_id(tickets: list) -> int:
    if not tickets:
        return 1
    return max(t["id"] for t in tickets) + 1

# ─────────────────────────────────────────────
#  BASE SEGURA — Ignora interacciones expiradas (error 10062)
# ─────────────────────────────────────────────
class SafeView(discord.ui.View):
    """View base que suprime silenciosamente el error 'Unknown interaction' (10062).
    Ocurre cuando Discord expira el token de interacción (ventana de 3s) antes
    de que el bot pueda responder, normalmente por carga del event loop o latencia."""
    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        if isinstance(error, discord.errors.NotFound) and getattr(error, "code", None) == 10062:
            return
        await super().on_error(interaction, error, item)

class SafeModal(discord.ui.Modal):
    """Modal base con la misma protección contra interacciones expiradas."""
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if isinstance(error, discord.errors.NotFound) and getattr(error, "code", None) == 10062:
            return
        await super().on_error(interaction, error)

# ─────────────────────────────────────────────
#  HELPER — Etiquetas de estado según categoría
# ─────────────────────────────────────────────
def _estado_labels(category: str) -> dict:
    """Devuelve las etiquetas positivo/negativo según la categoría del ticket."""
    if category == "recomendacion":
        return {"pos": "Recomendación aceptada", "neg": "Recomendación descartada"}
    elif category == "otros":
        return {"pos": "Resuelto", "neg": "Descartado"}
    else:  # bug_juego, bug_tecnico
        return {"pos": "Solucionado", "neg": "No solucionado"}
# ─────────────────────────────────────────────
#  VIEW — Confirmar cierre
# ─────────────────────────────────────────────
class ConfirmCloseView(SafeView):
    def __init__(self, cog, ctx, ticket, is_solved, reason):
        super().__init__(timeout=None)
        self.cog       = cog
        self.ctx       = ctx
        self.ticket    = ticket
        self.is_solved = is_solved
        self.reason    = reason

    @discord.ui.button(label="✅ Confirmar cierre", style=discord.ButtonStyle.success)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("No es tu acción.", ephemeral=True)

        self.ticket["status"]         = "cerrado"
        self.ticket["solved"]         = self.is_solved
        self.ticket["reason"]         = self.reason
        self.ticket["closed_by_id"]   = str(self.ctx.author.id)
        self.ticket["closed_by_name"] = str(self.ctx.author)
        self.ticket["closed_at"]      = datetime.utcnow().isoformat()
        self.ticket["pending"]        = False

        tickets = load_tickets()
        for i, t in enumerate(tickets):
            if t["id"] == self.ticket["id"]:
                tickets[i] = self.ticket
                break
        save_tickets(tickets)

        try:
            user      = await self.cog.bot.fetch_user(int(self.ticket["author_id"]))
            labels    = _estado_labels(self.ticket.get("category", ""))
            dm_color  = 0x00CC66 if self.is_solved else 0xFF4444
            dm_icon   = "✅" if self.is_solved else "❌"
            dm_result = f"**{labels['pos'].upper()}**" if self.is_solved else f"**{labels['neg'].upper()}**"
            dm_embed  = discord.Embed(
                title=f"📋 Tu Ticket #{self.ticket['id']} ha sido revisado",
                description=(
                    f"Hola {user.mention}, los moderadores han finalizado tu reporte.\n\n"
                    f"📌 **Ticket:** `#{self.ticket['id']}` — {self.ticket['title']}\n"
                    f"{dm_icon} **Resultado:** {dm_result}\n"
                    f"📋 **Razón:** {self.reason}\n"
                    f"🛡️ **Cerrado por:** {self.ctx.author}"
                ),
                color=dm_color
            )
            dm_embed.set_footer(text="7 Days to Die • Sistema de Tickets")
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"⚠️ No se pudo notificar al usuario: {e}")

        for child in self.children:
            child.disabled = True
        icon = "✅" if self.is_solved else "❌"
        await interaction.response.edit_message(
            content=f"{icon} Ticket `#{self.ticket['id']}` cerrado.",
            view=self
        )

    @discord.ui.button(label="✖ Cancelar", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("No es tu acción.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🚫 Cierre cancelado.", view=self)

# ─────────────────────────────────────────────
#  MODAL — Razón de cierre
# ─────────────────────────────────────────────
class CloseReasonModal(SafeModal, title="📋 Razón de cierre"):
    reason = discord.ui.TextInput(
        label="Explica el motivo del cierre",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: Se corrigió el spawn del lobo en el sector 3...",
        min_length=5,
        max_length=500,
        required=True
    )

    def __init__(self, cog, ctx, ticket, value, label_text):
        modal_title = (
            "⏳ Solicitar más información"
            if value == "pending"
            else "📋 Razón de cierre"
        )
        super().__init__(title=modal_title)
        self.reason.label = (
            "¿Qué información necesitas del usuario?"
            if value == "pending"
            else "Explica el motivo del cierre"
        )
        self.reason.placeholder = (
            "Ej: ¿Puedes indicar en qué zona del mapa ocurre el bug?"
            if value == "pending"
            else "Ej: Se corrigió el spawn del lobo en el sector 3..."
        )
        self.cog        = cog
        self.ctx        = ctx
        self.ticket     = ticket
        self.value      = value
        self.is_solved  = value == "solved"
        self.label_text = label_text

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.reason.value.strip()

        # ── Caso: Pendiente de información ───────────────────────────
        if self.value == "pending":
            tickets = load_tickets()
            for i, t in enumerate(tickets):
                if t["id"] == self.ticket["id"]:
                    tickets[i]["pending"]         = True
                    tickets[i]["pending_reason"]   = reason_text
                    tickets[i]["pending_at"]       = datetime.utcnow().isoformat()
                    tickets[i]["pending_by_name"]  = str(self.ctx.author)
                    self.ticket = tickets[i]
                    break
            save_tickets(tickets)

            try:
                user = await self.cog.bot.fetch_user(int(self.ticket["author_id"]))
                dm_embed = discord.Embed(
                    title=f"⏳ Tu Ticket #{self.ticket['id']} necesita más información",
                    description=(
                        f"Hola {user.mention}, un moderador revisó tu reporte y necesita información adicional.\n\n"
                        f"📌 **Ticket:** `#{self.ticket['id']}` — {self.ticket['title']}\n"
                        f"📋 **Qué se necesita:** {reason_text}\n"
                        f"🛡️ **Solicitado por:** {self.ctx.author}\n\n"
                        f"Pulsa el botón de abajo para añadir la información directamente aquí en el MD."
                    ),
                    color=0xFFA500
                )
                dm_embed.set_footer(text="7 Days to Die • Sistema de Tickets  |  Tu ticket sigue abierto")
                view = PendingInfoView(self.cog, self.ticket)
                await user.send(embed=dm_embed, view=view)
            except Exception as e:
                print(f"⚠️ No se pudo notificar al usuario: {e}")

            await interaction.response.send_message(
                f"⏳ Ticket `#{self.ticket['id']}` marcado como **pendiente**.\n"
                f"Se ha enviado un MD al usuario con un botón para añadir más información.",
                ephemeral=True
            )
            return

        # ── Caso: Cierre (solucionado / no solucionado) ──────────────
        icon   = "✅" if self.is_solved else "❌"
        estado = self.label_text

        confirm_embed = discord.Embed(
            title=f"⚠️ Confirmar cierre del Ticket #{self.ticket['id']}",
            color=0x00CC66 if self.is_solved else 0xFF4444
        )
        confirm_embed.add_field(name="📌 Título",         value=self.ticket["title"],          inline=False)
        confirm_embed.add_field(name="👤 Usuario",        value=self.ticket["author_name"],     inline=True)
        confirm_embed.add_field(name="📅 Creado",         value=self.ticket["created_at"][:10], inline=True)
        confirm_embed.add_field(name=f"{icon} Resultado", value=f"**{estado}**",                inline=False)
        confirm_embed.add_field(name="📋 Razón",          value=reason_text,                    inline=False)
        confirm_embed.set_footer(text="7 Days to Die • Sistema de Tickets  |  ¿Confirmas el cierre?")

        view = ConfirmCloseView(self.cog, self.ctx, self.ticket, self.is_solved, reason_text)
        await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)

# ─────────────────────────────────────────────
#  SELECT — Resultado del ticket
# ─────────────────────────────────────────────
class CloseStatusSelect(discord.ui.Select):
    def __init__(self, cog, ctx, ticket):
        self.cog    = cog
        self.ctx    = ctx
        self.ticket = ticket
        labels = _estado_labels(ticket.get("category", ""))
        options = [
            discord.SelectOption(
                label=labels["pos"],
                description="El ticket fue revisado con resultado positivo.",
                emoji="✅",
                value="solved"
            ),
            discord.SelectOption(
                label=labels["neg"],
                description="El ticket fue revisado con resultado negativo.",
                emoji="❌",
                value="unsolved"
            ),
            discord.SelectOption(
                label="Pendiente de información",
                description="Se necesita más información del usuario para continuar.",
                emoji="⏳",
                value="pending"
            ),
        ]
        super().__init__(
            placeholder="📋 Selecciona el resultado del ticket…",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "❌ Solo el moderador que ejecutó el comando puede usar esto.",
                ephemeral=True
            )
        value      = self.values[0]
        is_solved  = value == "solved"
        labels    = _estado_labels(self.ticket.get("category", ""))
        label_map = {
            "solved":   labels["pos"],
            "unsolved": labels["neg"],
            "pending":  "Pendiente de información"
        }
        label_text = label_map[value]
        modal = CloseReasonModal(self.cog, self.ctx, self.ticket, value, label_text)
        await interaction.response.send_modal(modal)

# ─────────────────────────────────────────────
#  VIEW — Panel de cierre
# ─────────────────────────────────────────────
class TkCloseView(SafeView):
    def __init__(self, cog, ctx, ticket):
        super().__init__(timeout=None)
        self.add_item(CloseStatusSelect(cog, ctx, ticket))

# ─────────────────────────────────────────────
#  VIEW — Botón de información adicional (pendiente)
# ─────────────────────────────────────────────
class PendingInfoView(SafeView):
    def __init__(self, cog, ticket: dict):
        super().__init__(timeout=None)
        self.cog    = cog
        self.ticket = ticket

    @discord.ui.button(label="📝 Añadir información", style=discord.ButtonStyle.primary)
    async def btn_add_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        if str(user_id) != self.ticket["author_id"]:
            return await interaction.response.send_message(
                "❌ Este ticket no te pertenece.", ephemeral=True
            )

        tickets = load_tickets()
        ticket  = next((t for t in tickets if t["id"] == self.ticket["id"]), None)
        if not ticket or not ticket.get("pending"):
            return await interaction.response.send_message(
                "⚠️ Este ticket ya no está pendiente de información.", ephemeral=True
            )
        if ticket["status"] == "cerrado":
            return await interaction.response.send_message(
                "⚠️ Este ticket ya está cerrado.", ephemeral=True
            )

        if user_id in self.cog.active_sessions or user_id in self.cog.pending_sessions:
            return await interaction.response.send_message(
                "⚠️ Ya tienes una sesión activa. Envía `!done` para finalizarla o `!cancel` para cancelarla.",
                ephemeral=True
            )

        # Guardar referencia al mensaje para poder re-habilitar el botón después
        self.cog.pending_sessions[user_id] = {
            "ticket_id":      ticket["id"],
            "ticket":         ticket,
            "new_info":       [],
            "new_images":     [],
            "source_message": interaction.message,
        }

        # Iniciar timeout de 24h para pending_sessions
        if user_id in self.cog.session_timeouts:
            self.cog.session_timeouts[user_id].cancel()
        task = asyncio.create_task(self.cog._pending_timeout(user_id))
        self.cog.session_timeouts[user_id] = task

        # Deshabilitar botón mientras la sesión esté activa
        button.disabled = True
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(
            title="📝 Sesión de información adicional iniciada",
            description=(
                f"**Ticket:** `#{ticket['id']}` — {ticket['title']}\n\n"
                "─────────────────────────\n"
                "Envíame aquí los mensajes e imágenes con la información que falta.\n\n"
                f"📝 **Texto** → máximo **{MAX_MESSAGES}** mensajes\n"
                f"🖼️ **Imágenes** → máximo **{MAX_IMAGES}** imágenes\n\n"
                "─────────────────────────\n"
                "Cuando termines escribe `!done`\n"
                "Para cancelar escribe `!cancel`\n\n"
                f"⏱️ **Esta sesión expira en {SESSION_TIMEOUT_HOURS}h si no envías `!done`.**"
            ),
            color=0xFFA500
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets")
        await interaction.followup.send(embed=embed)
# ─────────────────────────────────────────────
#  NUEVO: Sistema de Revalidación
# ─────────────────────────────────────────────
class RevalidarModal(SafeModal):
    motivo = discord.ui.TextInput(
        label="Motivo de revalidación",
        style=discord.TextStyle.paragraph,
        placeholder="Explica el motivo de la revalidación...",
        min_length=5,
        max_length=500,
        required=True
    )

    def __init__(self, cog, mod_user, ticket, nuevo_estado: str):
        labels    = _estado_labels(ticket.get("category", ""))
        title_map = {
            "solved":   f"✅ Revalidar como {labels['pos']}",
            "unsolved": f"❌ Revalidar como {labels['neg']}",
            "pending":  "⏳ Pedir más información",
        }
        super().__init__(title=title_map.get(nuevo_estado, "🔄 Revalidar ticket"))
        self.motivo.label = (
            "¿Qué información necesitas del usuario?"
            if nuevo_estado == "pending"
            else "Motivo de revalidación"
        )
        self.motivo.placeholder = (
            "Ej: ¿Puedes indicar la zona del mapa donde ocurre?"
            if nuevo_estado == "pending"
            else "Ej: Tras nueva revisión, el problema fue confirmado como resuelto."
        )
        self.cog          = cog
        self.mod_user     = mod_user
        self.ticket       = ticket
        self.nuevo_estado = nuevo_estado

    async def on_submit(self, interaction: discord.Interaction):
        motivo_text = self.motivo.value.strip()
        now         = datetime.utcnow().isoformat()

        tickets = load_tickets()
        ticket_updated = None
        for i, t in enumerate(tickets):
            if t["id"] == self.ticket["id"]:
                if self.nuevo_estado == "pending":
                    tickets[i]["status"]           = "abierto"
                    tickets[i]["solved"]            = None
                    tickets[i]["pending"]           = True
                    tickets[i]["pending_reason"]    = motivo_text
                    tickets[i]["pending_at"]        = now
                    tickets[i]["pending_by_name"]   = str(self.mod_user)
                elif self.nuevo_estado == "solved":
                    tickets[i]["status"]            = "cerrado"
                    tickets[i]["solved"]            = True
                    tickets[i]["reason"]            = motivo_text
                    tickets[i]["closed_by_id"]      = str(self.mod_user.id)
                    tickets[i]["closed_by_name"]    = str(self.mod_user)
                    tickets[i]["closed_at"]         = now
                    tickets[i]["pending"]           = False
                    tickets[i]["pending_reason"]    = None
                elif self.nuevo_estado == "unsolved":
                    tickets[i]["status"]            = "cerrado"
                    tickets[i]["solved"]            = False
                    tickets[i]["reason"]            = motivo_text
                    tickets[i]["closed_by_id"]      = str(self.mod_user.id)
                    tickets[i]["closed_by_name"]    = str(self.mod_user)
                    tickets[i]["closed_at"]         = now
                    tickets[i]["pending"]           = False
                    tickets[i]["pending_reason"]    = None
                ticket_updated = tickets[i]
                break
        save_tickets(tickets)

        # Notificar al usuario por MD
        try:
            user = await self.cog.bot.fetch_user(int(self.ticket["author_id"]))

            if self.nuevo_estado == "pending":
                color      = 0xFFA500
                icon       = "⏳"
                estado_str = "**Pendiente de información**"
                desc_extra = (
                    f"📋 **Información solicitada:** {motivo_text}\n\n"
                    "Pulsa el botón de abajo para añadir la información en este chat."
                )
            elif self.nuevo_estado == "solved":
                color      = 0x00CC66
                icon       = "✅"
                labels     = _estado_labels(self.ticket.get("category", ""))
                estado_str = f"**REVALIDADO — {labels['pos'].upper()}**"
                desc_extra = f"📋 **Motivo de revalidación:** {motivo_text}"
            else:
                color      = 0xFF4444
                icon       = "❌"
                labels     = _estado_labels(self.ticket.get("category", ""))
                estado_str = f"**REVALIDADO — {labels['neg'].upper()}**"
                desc_extra = f"📋 **Motivo de revalidación:** {motivo_text}"

            dm_embed = discord.Embed(
                title=f"🔄 Tu Ticket #{self.ticket['id']} ha sido revalidado",
                description=(
                    f"Hola {user.mention}, un moderador ha **revalidado** tu ticket.\n\n"
                    f"📌 **Ticket:** `#{self.ticket['id']}` — {self.ticket['title']}\n"
                    f"{icon} **Nuevo estado:** {estado_str}\n"
                    f"{desc_extra}\n"
                    f"🛡️ **Revalidado por:** {self.mod_user}"
                ),
                color=color
            )
            dm_embed.set_footer(text="7 Days to Die • Sistema de Tickets  |  Revalidación")

            if self.nuevo_estado == "pending" and ticket_updated:
                view = PendingInfoView(self.cog, ticket_updated)
                await user.send(embed=dm_embed, view=view)
            else:
                await user.send(embed=dm_embed)
        except Exception as e:
            print(f"⚠️ No se pudo notificar al usuario en revalidación: {e}")

        labels = _estado_labels(self.ticket.get("category", ""))
        estado_display = {
            "solved":   f"✅ {labels['pos']}",
            "unsolved": f"❌ {labels['neg']}",
            "pending":  "⏳ Pendiente de información",
        }.get(self.nuevo_estado, "?")

        await interaction.response.send_message(
            f"✅ Ticket `#{self.ticket['id']}` revalidado como **{estado_display}**.\n"
            "Se ha notificado al usuario por MD.",
            ephemeral=True
        )


class RevalidarSelect(discord.ui.Select):
    def __init__(self, cog, mod_user, ticket: dict):
        self.cog      = cog
        self.mod_user = mod_user
        self.ticket   = ticket

        was_solved = ticket.get("solved")
        options = []

        labels = _estado_labels(ticket.get("category", ""))
        if was_solved:
            options.append(discord.SelectOption(
                label=f"Marcar como {labels['neg']}",
                description="El problema persiste o la solución fue incorrecta.",
                emoji="❌",
                value="unsolved"
            ))
        else:
            options.append(discord.SelectOption(
                label=f"Marcar como {labels['pos']}",
                description="El problema ya está correctamente resuelto.",
                emoji="✅",
                value="solved"
            ))

        options.append(discord.SelectOption(
            label="Pedir más información",
            description="Reabrir el ticket como pendiente de información del usuario.",
            emoji="⏳",
            value="pending"
        ))

        super().__init__(
            placeholder="🔄 Selecciona la acción de revalidación…",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        nuevo_estado = self.values[0]
        modal = RevalidarModal(self.cog, self.mod_user, self.ticket, nuevo_estado)
        await interaction.response.send_modal(modal)


class RevalidarView(SafeView):
    def __init__(self, cog, mod_user, ticket: dict):
        super().__init__(timeout=None)
        self.add_item(RevalidarSelect(cog, mod_user, ticket))

# ─────────────────────────────────────────────
#  VIEW — Ver ticket online + Revalidar
# ─────────────────────────────────────────────
class TicketHTMLView(SafeView):
    def __init__(self, cog, ticket: dict, is_mod: bool = False):
        super().__init__(timeout=None)
        self.cog    = cog
        self.ticket = ticket
        self._busy  = False
        self.is_mod = is_mod

        if is_mod and ticket.get("status") == "cerrado":
            self.btn_revalidar.label = "🔄 Revalidar ticket"
        else:
            self.remove_item(self.btn_revalidar)

    @discord.ui.button(label="🌐 Ver ticket completo online", style=discord.ButtonStyle.blurple)
    async def btn_view_online(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            html_content = await asyncio.to_thread(self.cog._generate_ticket_html, self.ticket)
        except Exception as e:
            return await interaction.followup.send(f"❌ Error al generar el HTML: {e}", ephemeral=True)

        url = await self.cog._upload_ticket_html(html_content)
        if url:
            await interaction.followup.send(
                f"🌐 **Ticket completo disponible aquí:**\n{url}\n\n⏳ El enlace es temporal.",
                ephemeral=True
            )
        else:
            self._busy      = False
            button.disabled = False
            await interaction.followup.send(
                "❌ No se pudo subir el HTML. Intenta más tarde.", ephemeral=True
            )
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="🔄 Revalidar ticket", style=discord.ButtonStyle.secondary)
    async def btn_revalidar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        tickets = load_tickets()
        ticket  = next((t for t in tickets if t["id"] == self.ticket["id"]), None)
        if not ticket or ticket.get("status") != "cerrado":
            return await interaction.response.send_message(
                "⚠️ Este ticket ya no está cerrado.", ephemeral=True
            )
        labels        = _estado_labels(ticket.get("category", ""))
        estado_actual = f"✅ {labels['pos']}" if ticket.get("solved") else f"❌ {labels['neg']}"
        embed = discord.Embed(
            title=f"🔄 Revalidar Ticket #{ticket['id']}",
            description=(
                f"**Título:** {ticket['title']}\n"
                f"**Estado actual:** {estado_actual}\n\n"
                "Selecciona la acción en el menú de abajo."
            ),
            color=0x7289DA
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets  |  Revalidación")
        view = RevalidarView(self.cog, interaction.user, ticket)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
# ─────────────────────────────────────────────
#  MODAL — Categoría "Otros"
# ─────────────────────────────────────────────
class OtherCategoryModal(SafeModal, title="Especificar categoría"):
    custom = discord.ui.TextInput(
        label="¿Cuál es el motivo de tu ticket?",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: Problema con la tienda de puntos, sugerencia de reglas, etc.",
        min_length=3,
        max_length=200,
        required=True
    )

    def __init__(self, cog, ctx, title):
        super().__init__()
        self.cog   = cog
        self.ctx   = ctx
        self.title = title

    async def on_submit(self, interaction: discord.Interaction):
        cog             = self.cog
        ctx             = self.ctx
        title           = self.title
        category        = "otros"
        custom_category = self.custom.value.strip()

        if ctx.author.id in cog.active_sessions:
            await ctx.send(
                "⚠️ Ya tienes una sesión de ticket abierta.\n"
                "Escribe `!done` para finalizarla o `!cancel` para cancelarla."
            )
            return

        if ctx.author.id in cog.session_timeouts:
            cog.session_timeouts[ctx.author.id].cancel()

        task = asyncio.create_task(cog._session_timeout(ctx.author.id))
        cog.session_timeouts[ctx.author.id] = task

        cog.active_sessions[ctx.author.id] = {
            "title":           title,
            "description":     [],
            "images":          [],
            "category":        category,
            "custom_category": custom_category
        }

        embed = discord.Embed(
            title="🎫 Ticket Iniciado",
            description=(
                f"**Título registrado:** `{title}`\n"
                f"**Categoría:** {cog._get_category_label(category, custom_category)}\n\n"
                "─────────────────────────\n"
                "Ahora cuéntame todo sobre el bug.\n\n"
                f"📝 Envía **mensajes de texto** (máx. **{MAX_MESSAGES}**)\n"
                f"🖼️ Sube **capturas de pantalla** (máx. **{MAX_IMAGES}**)\n\n"
                "─────────────────────────\n"
                "Cuando termines escribe `!done`\n"
                "Para cancelar escribe `!cancel`\n\n"
                f"⏱️ **Esta sesión expira en {SESSION_TIMEOUT_HOURS}h si no envías `!done`.**"
            ),
            color=0x8B0000
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets")
        await ctx.send(embed=embed)
        await interaction.response.edit_message(
            content="✅ Categoría seleccionada. Ahora envía la descripción.",
            view=None, embed=None
        )

# ─────────────────────────────────────────────
#  VIEW — Selección de categoría
# ─────────────────────────────────────────────
class CategorySelectView(SafeView):
    def __init__(self, cog, ctx, title):
        super().__init__(timeout=None)
        self.cog   = cog
        self.ctx   = ctx
        self.title = title
        select = discord.ui.Select(
            placeholder="🔽 Selecciona la categoría de tu ticket...",
            options=[
                discord.SelectOption(
                    label=cat["label"],
                    value=cat["value"],
                    emoji=cat["emoji"],
                    description=cat["description"][:100]
                ) for cat in TICKET_CATEGORIES
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("No es tu interacción.", ephemeral=True)
        value = interaction.data["values"][0]
        if value == "otros":
            await interaction.response.send_modal(
                OtherCategoryModal(self.cog, self.ctx, self.title)
            )
        else:
            cog             = self.cog
            ctx             = self.ctx
            title           = self.title
            category        = value
            custom_category = None

            if ctx.author.id in cog.active_sessions:
                await ctx.send(
                    "⚠️ Ya tienes una sesión de ticket abierta.\n"
                    "Escribe `!done` para finalizarla o `!cancel` para cancelarla."
                )
                return

            if ctx.author.id in cog.session_timeouts:
                cog.session_timeouts[ctx.author.id].cancel()

            task = asyncio.create_task(cog._session_timeout(ctx.author.id))
            cog.session_timeouts[ctx.author.id] = task

            cog.active_sessions[ctx.author.id] = {
                "title":           title,
                "description":     [],
                "images":          [],
                "category":        category,
                "custom_category": custom_category
            }

            # ANTES:
            embed = discord.Embed(
                title="🎫 Ticket Iniciado",
                description=(
                    f"**Título registrado:** `{title}`\n"
                    f"**Categoría:** {cog._get_category_label(category, custom_category)}\n\n"
                    "─────────────────────────\n"
                    "Ahora cuéntame todo sobre el bug.\n\n"
                    f"📝 Envía **mensajes de texto** (máx. **{MAX_MESSAGES}**)\n"
                    f"🖼️ Sube **capturas de pantalla** (máx. **{MAX_IMAGES}**)\n\n"
                    "─────────────────────────\n"
                    "Cuando termines escribe `!done`\n"
                    "Para cancelar escribe `!cancel`"
                ),
                color=0x8B0000
            )
            embed.set_footer(text="7 Days to Die • Sistema de Tickets")

# DESPUÉS:
            embed = discord.Embed(
                title="🎫 Ticket Iniciado",
                description=(
                    f"**Título registrado:** `{title}`\n"
                    f"**Categoría:** {cog._get_category_label(category, custom_category)}\n\n"
                    "─────────────────────────\n"
                    "Ahora cuéntame todo sobre el bug.\n\n"
                    f"📝 Envía **mensajes de texto** (máx. **{MAX_MESSAGES}**)\n"
                    f"🖼️ Sube **capturas de pantalla** (máx. **{MAX_IMAGES}**)\n\n"
                    "─────────────────────────\n"
                    "Cuando termines escribe `!done`\n"
                    "Para cancelar escribe `!cancel`\n\n"
                    f"⏱️ **Esta sesión expira en {SESSION_TIMEOUT_HOURS}h si no envías `!done`.**"
                ),
                color=0x8B0000
            )
            embed.set_footer(text="7 Days to Die • Sistema de Tickets")
            await ctx.send(embed=embed)
            await interaction.response.edit_message(
                content="✅ Categoría seleccionada. Ahora envía la descripción.",
                view=None, embed=None
            )

# ─────────────────────────────────────────────
#  SELECT / VIEW — Tickets activos (!tickets)
# ─────────────────────────────────────────────
class TicketSelect(discord.ui.Select):
    def __init__(self, cog, tickets, total, page, page_size):
        self.cog        = cog
        self.total      = total
        self.page       = page
        self.ticket_map = {str(t["id"]): t for t in tickets}
        options = []
        for t in tickets:
            title = t["title"][:60] + "…" if len(t["title"]) > 60 else t["title"]
            options.append(discord.SelectOption(
                label=f"#{t['id']} — {title}",
                description=f"👤 {t['author_name'][:28]} • 📅 {t['created_at'][:10]}",
                value=str(t["id"]),
                emoji="🟠"
            ))
        super().__init__(
            placeholder=f"🎫 Página {page + 1} — Tickets activos…",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        ticket = self.ticket_map.get(self.values[0])
        if not ticket:
            return await interaction.response.send_message("Ticket no encontrado.", ephemeral=True)
        embed = self.cog._make_ticket_embed(ticket, self.total)
        view  = TicketHTMLView(self.cog, ticket, is_mod=True)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class TicketView(SafeView):
    def __init__(self, cog, tickets, total, page=0, page_size=15):
        super().__init__(timeout=None)
        self.cog         = cog
        self.all_tickets = tickets
        self.total       = total
        self.page        = page
        self.page_size   = page_size
        self.total_pages = max(1, (len(tickets) + page_size - 1) // page_size)
        self._build()

    def _build(self):
        self.clear_items()
        start        = self.page * self.page_size
        end          = min(start + self.page_size, len(self.all_tickets))
        page_tickets = self.all_tickets[start:end]
        self.add_item(TicketSelect(self.cog, page_tickets, self.total, self.page, self.page_size))

        if self.total_pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0)
            )
            prev.callback = self.prev_page
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self.page + 1} / {self.total_pages}",
                style=discord.ButtonStyle.secondary, disabled=True
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= self.total_pages - 1)
            )
            nxt.callback = self.next_page
            self.add_item(nxt)

    async def prev_page(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        self.page -= 1
        self._build()
        await interaction.response.edit_message(embed=self._make_summary_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        self.page += 1
        self._build()
        await interaction.response.edit_message(embed=self._make_summary_embed(), view=self)

    def _make_summary_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🎫 Panel de Tickets Activos", color=0x00AAFF)
        embed.add_field(
            name="📊 Resumen",
            value=f"**{len(self.all_tickets)}** abierto(s) de **{self.total}** totales",
            inline=False
        )
        lines = []
        start = self.page * self.page_size
        end   = min(start + self.page_size, len(self.all_tickets))
        for t in self.all_tickets[start:end]:
            title_short = t["title"][:45] + "…" if len(t["title"]) > 45 else t["title"]
            lines.append(
                f"🟠 `#{t['id']}` **{title_short}**\n"
                f"　👤 {t['author_name']} • 📅 {t['created_at'][:10]}"
            )
        embed.add_field(name="📋 Tickets en esta página", value="\n".join(lines) or "—", inline=False)
        embed.add_field(
            name="ℹ️ Instrucciones",
            value=f"Página {self.page + 1} de {self.total_pages}. Usa el menú desplegable para ver detalles.",
            inline=False
        )
        embed.set_footer(text=f"7 Days to Die • Sistema de Tickets  |  Activos: {len(self.all_tickets)}")
        return embed

# ─────────────────────────────────────────────
#  SELECT / VIEW — Todos los tickets (!tklist)
# ─────────────────────────────────────────────
class AllTicketSelect(discord.ui.Select):
    def __init__(self, cog, tickets: list, total: int, page: int, page_size: int):
        self.cog        = cog
        self.total      = total
        self.page       = page
        self.page_size  = page_size
        self.ticket_map = {str(t["id"]): t for t in tickets}
        options = []
        for t in tickets:
            if t.get("pending"):
                emoji  = "⏳"; estado = "Pendiente"
            elif t["status"] == "abierto":
                emoji  = "🟠"; estado = "Abierto"
            elif t.get("solved"):
                emoji  = "✅"; estado = "Solucionado"
            else:
                emoji  = "❌"; estado = "No solucionado"
            title = t["title"][:55] + "…" if len(t["title"]) > 55 else t["title"]
            options.append(discord.SelectOption(
                label=f"#{t['id']} — {title}",
                description=f"{estado} • 👤 {t['author_name'][:20]} • 📅 {t['created_at'][:10]}",
                value=str(t["id"]),
                emoji=emoji
            ))
        super().__init__(
            placeholder=f"🎫 Página {page + 1} — Selecciona un ticket…",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ticket = self.ticket_map.get(self.values[0])
        if not ticket:
            return await interaction.followup.send("❌ Ticket no encontrado.", ephemeral=True)
        embed = self.cog._make_ticket_embed(ticket, self.total)
        view  = TicketHTMLView(self.cog, ticket, is_mod=True)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AllTicketsView(SafeView):
    def __init__(self, cog, tickets: list, page: int = 0, page_size: int = 15):
        super().__init__(timeout=None)
        self.cog         = cog
        self.tickets     = tickets
        self.page        = page
        self.page_size   = page_size
        self.total_pages = max(1, (len(tickets) + page_size - 1) // page_size)
        self._build()

    def _build(self):
        self.clear_items()
        start        = self.page * self.page_size
        end          = min(start + self.page_size, len(self.tickets))
        page_tickets = self.tickets[start:end]
        self.add_item(AllTicketSelect(self.cog, page_tickets, len(self.tickets), self.page, self.page_size))

        if self.total_pages > 1:
            prev_btn = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0)
            )
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

            page_indicator = discord.ui.Button(
                label=f"{self.page + 1} / {self.total_pages}",
                style=discord.ButtonStyle.secondary, disabled=True
            )
            self.add_item(page_indicator)

            next_btn = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= self.total_pages - 1)
            )
            next_btn.callback = self.next_page
            self.add_item(next_btn)

    async def prev_page(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        self.page -= 1
        self._build()
        await interaction.response.edit_message(embed=self._make_summary_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        self.page += 1
        self._build()
        await interaction.response.edit_message(embed=self._make_summary_embed(), view=self)

    def _make_summary_embed(self) -> discord.Embed:
        abiertos          = [t for t in self.tickets if t["status"] == "abierto"]
        cerrados_solved   = [t for t in self.tickets if t["status"] == "cerrado" and t.get("solved")]
        cerrados_unsolved = [t for t in self.tickets if t["status"] == "cerrado" and not t.get("solved")]
        pendientes        = [t for t in self.tickets if t.get("pending")]
        embed = discord.Embed(title="📋 Panel de Todos los Tickets", color=0x7289DA)
        embed.add_field(
            name="📊 Resumen",
            value=(
                f"🟠 **Abiertos:** {len(abiertos)}\n"
                f"⏳ **Pendientes:** {len(pendientes)}\n"
                f"✅ **Cerrados (Solucionados):** {len(cerrados_solved)}\n"
                f"❌ **Cerrados (No solucionados):** {len(cerrados_unsolved)}\n"
                f"📦 **Total:** {len(self.tickets)}"
            ),
            inline=False
        )
        embed.add_field(
            name="ℹ️ Instrucciones",
            value=f"Página {self.page + 1} de {self.total_pages}. Usa el menú para ver detalles del ticket.",
            inline=False
        )
        embed.set_footer(text=f"7 Days to Die • Sistema de Tickets  |  Total: {len(self.tickets)} tickets")
        return embed

# ─────────────────────────────────────────────
#  SELECT / VIEW — Tickets del usuario (!tkstatus)
# ─────────────────────────────────────────────
class UserTicketSelect(discord.ui.Select):
    def __init__(self, cog, tickets: list, total: int):
        self.cog        = cog
        self.total      = total
        self.ticket_map = {str(t["id"]): t for t in tickets}
        options = []
        for t in tickets:
            if t.get("pending"):
                emoji  = "⏳"; estado = "Pendiente"
            elif t["status"] == "abierto":
                emoji  = "🟠"; estado = "Abierto"
            elif t.get("solved"):
                emoji  = "✅"; estado = "Solucionado"
            else:
                emoji  = "❌"; estado = "No solucionado"
            title = t["title"][:60] + "…" if len(t["title"]) > 60 else t["title"]
            options.append(discord.SelectOption(
                label=f"#{t['id']} — {title}",
                description=f"{estado} • 📅 {t['created_at'][:10]}",
                value=str(t["id"]),
                emoji=emoji
            ))
        super().__init__(
            placeholder="🎫 Selecciona un ticket para ver su estado…",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        ticket = self.ticket_map.get(self.values[0])
        if not ticket:
            return await interaction.response.send_message("❌ Ticket no encontrado.", ephemeral=True)
        embed = self.cog._build_status_embed(ticket)
        await interaction.response.send_message(
            embed=embed,
            view=TicketHTMLView(self.cog, ticket, is_mod=False),
            ephemeral=True
        )


class UserTicketView(SafeView):
    def __init__(self, cog, tickets: list, total: int):
        super().__init__(timeout=None)
        self.add_item(UserTicketSelect(cog, tickets, total))

# ─────────────────────────────────────────────
#  VIEW — Paginador de !bugs
# ─────────────────────────────────────────────
class BugsPaginatorView(SafeView):
    def __init__(self, cog, tickets: list):
        super().__init__(timeout=None)
        self.cog     = cog
        self.tickets = tickets
        self.index   = 0
        self._update_buttons()

    def current_embed(self) -> discord.Embed:
        return self.cog._make_ticket_embed(self.tickets[self.index], len(self.tickets))

    def _update_buttons(self):
        self.btn_prev.disabled    = len(self.tickets) <= 1
        self.btn_next.disabled    = len(self.tickets) <= 1
        self.btn_counter.label    = f"{self.index + 1} / {len(self.tickets)}"

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        self.index = (self.index - 1) % len(self.tickets)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def btn_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog._user_is_mod(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para usar esto.", ephemeral=True)
            return
        self.index = (self.index + 1) % len(self.tickets)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)
# ─────────────────────────────────────────────
#  VIEW — Paginador de !tkstatus (usuario)
# ─────────────────────────────────────────────
class UserTicketPaginatorView(SafeView):
    def __init__(self, cog, tickets: list, total_all: int, page: int = 0, page_size: int = 15):
        super().__init__(timeout=None)
        self.cog         = cog
        self.tickets     = tickets   # ordenados: pendientes → abiertos → cerrados
        self.total_all   = total_all
        self.page        = page
        self.page_size   = page_size
        self.total_pages = max(1, (len(tickets) + page_size - 1) // page_size)
        self._build()

    def _build(self):
        self.clear_items()
        start        = self.page * self.page_size
        end          = min(start + self.page_size, len(self.tickets))
        page_tickets = self.tickets[start:end]
        self.add_item(UserTicketSelect(self.cog, page_tickets, self.total_all))

        if self.total_pages > 1:
            prev_btn = discord.ui.Button(
                label="◀ Anterior", style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0), row=1
            )
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

            self.add_item(discord.ui.Button(
                label=f"{self.page + 1} / {self.total_pages}",
                style=discord.ButtonStyle.secondary, disabled=True, row=1
            ))

            next_btn = discord.ui.Button(
                label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                disabled=(self.page >= self.total_pages - 1), row=1
            )
            next_btn.callback = self.next_page
            self.add_item(next_btn)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(view=self)
# ─────────────────────────────────────────────
#  COG PRINCIPAL
# ─────────────────────────────────────────────

class TicketCog(commands.Cog, name="Tickets"):
    def __init__(self, bot: commands.Bot):
        self.bot              = bot
        self.active_sessions:  dict = {}   # {user_id: {"title", "description", "images", ...}}
        self.session_timeouts: dict = {}
        self._seen_messages:   set  = set()
        self.pending_sessions: dict = {}   # {user_id: {"ticket_id", "new_info", "new_images"}}
    async def cog_load(self):
        os.makedirs(os.path.dirname(NETLIFY_MANIFEST), exist_ok=True)
        asyncio.create_task(self._netlify_cleanup_loop())

    async def _netlify_cleanup_loop(self):
        while True:
            await asyncio.sleep(3600)
            await self._netlify_cleanup()
    def _expired_embed(self, is_pending: bool = False) -> discord.Embed:
     if is_pending:
        embed = discord.Embed(
            title="⏰ Sesión expirada",
            description=(
                "Tu sesión para enviar información adicional **expiró por inactividad** (24h).\n\n"
                "¿No quisiste mandar más información o simplemente se te olvidó? No hay problema.\n"
                "Pulsa de nuevo el botón en el mensaje anterior para abrir una nueva sesión."
            ),
            color=0xFF8C00
        )
     else:
         embed = discord.Embed(
            title="⏰ Sesión expirada",
            description=(
                "Tu sesión de ticket **expiró por inactividad** (24h) y fue cancelada.\n\n"
                "Cuando quieras intentarlo de nuevo usa `!ticket <título>` para empezar desde el inicio."
            ),
            color=0xFF8C00
        )
     embed.set_footer(text="7 Days to Die • Sistema de Tickets")
     return embed
    
    async def _netlify_cleanup(self):
        
        if not os.path.exists(NETLIFY_MANIFEST):
            return
        with open(NETLIFY_MANIFEST, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        now     = datetime.utcnow()
        changed = False
        for h, entry in list(manifest.items()):
            created = datetime.fromisoformat(entry["created_at"])
            if (now - created).total_seconds() > 86400:
                del manifest[h]
                changed = True
                print(f"🗑️ Netlify: eliminado {entry['filename']}")

        if not changed:
            return

        with open(NETLIFY_MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        await self._netlify_deploy_all(manifest)

    async def _netlify_deploy_all(self, manifest: dict) -> bool:
        token   = pin.NETLIFY_TOKEN
        site_id = pin.NETLIFY_SITE_ID
        if not token or not site_id:
            return False

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if not manifest:
                zf.writestr("index.html", "<html><body></body></html>")
            for entry in manifest.values():
                if "html" in entry:
                    zf.writestr(entry["filename"], entry["html"])
        zip_buffer.seek(0)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type":  "application/zip"
                    },
                    data=zip_buffer.read(),
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as r:
                    print(f"🔄 Netlify deploy → {r.status}")
                    return r.status in (200, 201)
        except Exception as e:
            print(f"⚠️ Netlify deploy: {e}")
            return False



    async def _upload_ticket_html(self, html_content: str) -> str:
        html_bytes = html_content.encode("utf-8")

        async def try_litterbox(session):
            try:
                data = aiohttp.FormData()
                data.add_field("reqtype", "fileupload")
                data.add_field("time", "24h")
                data.add_field("fileToUpload",
                               io.BytesIO(html_bytes),
                               filename="ticket.html",
                               content_type="text/html")
                async with session.post(
                    "https://litterbox.catbox.moe/resources/internals/api.php",
                    data=data, timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    print(f"🔄 litterbox → {r.status}")
                    if r.status == 200:
                        link = (await r.text()).strip()
                        if link.startswith("https://"):
                            return link
            except Exception as e:
                print(f"⚠️ litterbox: {e}")
            return None

        async def try_pagedrop_io(session):
            try:
                async with session.post(
                    "https://pagedrop.io/api/upload",
                    json={"html": html_content, "ttl": "1d"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    print(f"🔄 pagedrop.io → {r.status}")
                    if r.status in (200, 201):
                        result = await r.json(content_type=None)
                        data = result.get("data") or {}
                        url = data.get("url", "")
                        if url.startswith("https://"):
                            return url
            except Exception as e:
                print(f"⚠️ pagedrop.io: {e}")
            return None

        async def try_pagedrop_dev(session):
            try:
                async with session.post(
                    "https://pagedrop.dev/api/v1/sites",
                    json={"html": html_content, "ttl": "1d"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    print(f"🔄 pagedrop.dev → {r.status}")
                    if r.status in (200, 201):
                        result = await r.json(content_type=None)
                        data = result.get("data") or {}
                        url = data.get("url", "")
                        if url.startswith("https://"):
                            return url
            except Exception as e:
                print(f"⚠️ pagedrop.dev: {e}")
            return None
        async def try_netlify(session):
            token    = pin.NETLIFY_TOKEN
            site_id  = pin.NETLIFY_SITE_ID
            base_url = pin.NETLIFY_BASE_URL
            if not token or not site_id or not base_url:
                print("⚠️ Netlify: credenciales no configuradas")
                return None
            try:
                file_hash = uuid.uuid4().hex[:12]
                filename  = f"ticket_{file_hash}.html"

                manifest = {}
                if os.path.exists(NETLIFY_MANIFEST):
                    with open(NETLIFY_MANIFEST, "r", encoding="utf-8") as f:
                        manifest = json.load(f)

                manifest[file_hash] = {
                    "filename":   filename,
                    "created_at": datetime.utcnow().isoformat(),
                    "url":        f"{base_url.rstrip('/')}/{filename}",
                    "html":       html_content
                }
                with open(NETLIFY_MANIFEST, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for entry in manifest.values():
                        if "html" in entry:
                            zf.writestr(entry["filename"], entry["html"])
                zip_buffer.seek(0)

                async with session.post(
                    f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type":  "application/zip"
                    },
                    data=zip_buffer.read(),
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as r:
                    print(f"🔄 Netlify deploy → {r.status}")
                    if r.status in (200, 201):
                        deploy_data = await r.json()
                        deploy_id   = deploy_data.get("id")
                        target_url  = manifest[file_hash]["url"]

                        # Esperar a que el deploy esté live (es asíncrono en Netlify)
                        if deploy_id:
                            for _ in range(30):  # máx ~90s
                                await asyncio.sleep(3)
                                async with session.get(
                                    f"https://api.netlify.com/api/v1/deploys/{deploy_id}",
                                    headers={"Authorization": f"Bearer {token}"},
                                    timeout=aiohttp.ClientTimeout(total=15)
                                ) as status_r:
                                    if status_r.status == 200:
                                        status_data  = await status_r.json()
                                        deploy_state = status_data.get("state")
                                        print(f"🔄 Netlify state → {deploy_state}")
                                        if deploy_state == "ready":
                                            return target_url
                                        elif deploy_state in ("error", "failed"):
                                            print("❌ Netlify deploy falló")
                                            return None
                            print("⚠️ Netlify deploy: timeout esperando estado ready")
                            return None
                        return target_url  # fallback si no hay deploy_id
            except Exception as e:
                print(f"⚠️ Netlify: {e}")
            return None
        async with aiohttp.ClientSession() as session:
            for nombre, intento in [
                ("litterbox",    try_litterbox),
                ("pagedrop.io",  try_pagedrop_io),
                ("pagedrop.dev", try_pagedrop_dev),
                ("netlify",      try_netlify),
                
            ]:
                print(f"🔄 Intentando {nombre}...")
                url = await intento(session)
                if url:
                    print(f"✅ HTML subido en {nombre}: {url}")
                    return url

        print("❌ Todos los servicios fallaron.")
        return "❌ No se pudo generar el enlace. Intenta más tarde."
    # ──────────────────────────────────────────
    #  ImgBB upload
    # ──────────────────────────────────────────
    async def _upload_to_imgbb(self, image_bytes: bytes, filename: str) -> str | None:
        """Sube imagen a ImgBB y devuelve la URL directa, o None si falla."""
        api_key = pin.IMGBB_API
        if not api_key:
            print("⚠️ IMGBB_API no configurada en .env")
            return None
        try:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            data = aiohttp.FormData()
            data.add_field("key",   api_key)
            data.add_field("image", b64)
            data.add_field("name",  os.path.splitext(filename)[0])
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.imgbb.com/1/upload",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result["data"]["url"]
                    print(f"⚠️ ImgBB respondió {resp.status}")
        except Exception as e:
            print(f"⚠️ ImgBB upload falló ({filename}): {e}")
        return None

    # ──────────────────────────────────────────
    #  UTILIDADES INTERNAS
    # ──────────────────────────────────────────
    def _user_is_mod(self, member: discord.Member) -> bool:
        allowed_ids = ALLOWED_ROLE_IDS.values()
        return any(role.id in allowed_ids for role in member.roles)

    def _get_category_label(self, category, custom_category=None):
        for cat in TICKET_CATEGORIES:
            if cat["value"] == category:
                if category == "otros" and custom_category:
                    return f"{cat['emoji']} Otros: {custom_category}"
                return cat["label"]
        return "Desconocida"

    def _make_ticket_embed(self, ticket: dict, total: int) -> discord.Embed:
        labels       = _estado_labels(ticket.get("category", ""))
        is_open   = ticket["status"] == "abierto"
        is_solved = ticket.get("solved")

        if is_open:
            color        = 0xFFA500;  status_icon = "🟠"; status_label = "Abierto"
        elif is_solved:
            color        = 0x00CC66;  status_icon = "✅"; status_label = f"Cerrado · {labels['pos']}"
        else:
            color        = 0xFF4444;  status_icon = "❌"; status_label = f"Cerrado · {labels['neg']}"

        embed = discord.Embed(
            title=f"🎫  Ticket #{ticket['id']}  —  {ticket['title']}",
            color=color
        )
        embed.add_field(name="👤 Usuario",             value=ticket["author_name"],                inline=True)
        embed.add_field(name=f"{status_icon} Estado",  value=status_label,                         inline=True)
        embed.add_field(name="📅 Creado",              value=ticket["created_at"][:10],             inline=True)

        desc = ticket.get("description") or "*(sin descripción)*"
        if len(desc) > 1020:
            desc = desc[:1017] + "..."
        embed.add_field(name="📝 Descripción del bug", value=desc, inline=False)

        images = ticket.get("images", [])
        if images:
            img_links = "\n".join(f"• [{img['filename']}]({img['url']})" for img in images)
            if len(img_links) > 1020:
                img_links = img_links[:1017] + "..."
            embed.add_field(name=f"🖼️ Imágenes ({len(images)})", value=img_links, inline=False)
            embed.set_image(url=images[0]["url"])

        if ticket.get("reason"):
            embed.add_field(name="📋 Razón de cierre", value=ticket["reason"], inline=False)

        if ticket.get("closed_at"):
            embed.add_field(name="🔒 Cerrado el", value=ticket["closed_at"][:10], inline=True)
            if ticket.get("closed_by_name"):
                embed.add_field(name="🛡️ Cerrado por", value=ticket["closed_by_name"], inline=True)

        category_val = ticket.get("category")
        if category_val:
            custom      = ticket.get("custom_category")
            cat_display = self._get_category_label(category_val, custom)
            embed.add_field(name="📂 Categoría", value=cat_display, inline=False)

        embed.set_footer(text=f"Ticket {ticket['id']} de {total} totales  •  7 Days to Die")
        return embed

    # ──────────────────────────────────────────
    #  LISTENER — Captura mensajes en sesión DM
    # ──────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author.id not in self.active_sessions and message.author.id not in self.pending_sessions:
            return

        # Evitar procesar el mismo mensaje dos veces
        if message.id in self._seen_messages:
            return
        self._seen_messages.add(message.id)
        if len(self._seen_messages) > 500:
            self._seen_messages = set(list(self._seen_messages)[-250:])

        # Ignorar si es un comando
        prefix = self.bot.command_prefix
        if not callable(prefix):
            prefixes = (prefix,) if isinstance(prefix, str) else tuple(prefix)
            if message.content.startswith(prefixes):
                return

        # ── Sesión pendiente (info adicional) ────────────────────────
        if message.author.id in self.pending_sessions:
            psession = self.pending_sessions[message.author.id]

            if message.content.strip():
                if len(psession["new_info"]) >= MAX_MESSAGES:
                    await message.channel.send(
                        f"⚠️ Límite de **{MAX_MESSAGES}** mensajes alcanzado. "
                        "Escribe `!done` para finalizar o `!cancel` para cancelar."
                    )
                else:
                    psession["new_info"].append(message.content.strip())
                    await message.add_reaction("✅")

            for att in message.attachments:
                ext = os.path.splitext(att.filename)[1].lower()
                if ext not in ALLOWED_IMAGE_EXTS:
                    await message.channel.send(
                        f"⚠️ `{att.filename}` no es una imagen válida.\n"
                        "Formatos aceptados: `jpg, jpeg, png, gif, webp, bmp, tiff`"
                    )
                    continue
                if len(psession["new_images"]) >= MAX_IMAGES:
                    await message.channel.send(
                        f"⚠️ Límite de **{MAX_IMAGES}** imágenes alcanzado. "
                        f"Ignorando: `{att.filename}`"
                    )
                    continue
                # Subir a ImgBB
                try:
                    async with aiohttp.ClientSession() as sess:
                        async with sess.get(att.url) as resp:
                            img_bytes = await resp.read()
                    imgbb_url = await self._upload_to_imgbb(img_bytes, att.filename)
                    final_url = imgbb_url if imgbb_url else att.url
                    psession["new_images"].append({"filename": att.filename, "url": final_url})
                    await message.add_reaction("🖼️")
                except Exception as e:
                    print(f"⚠️ Error procesando imagen {att.filename}: {e}")
                    await message.channel.send(f"⚠️ No se pudo procesar `{att.filename}`. Intenta de nuevo.")
            return

        # ── Sesión normal (nuevo ticket) ─────────────────────────────
        session = self.active_sessions[message.author.id]

        if message.content.strip():
            if len(session["description"]) >= MAX_MESSAGES:
                await message.channel.send(
                    f"⚠️ Límite de **{MAX_MESSAGES}** mensajes alcanzado. "
                    "Escribe `!done` para finalizar o `!cancel` para cancelar."
                )
            else:
                session["description"].append(message.content.strip())
                await message.add_reaction("✅")

        for att in message.attachments:
            ext = os.path.splitext(att.filename)[1].lower()
            if ext not in ALLOWED_IMAGE_EXTS:
                await message.channel.send(
                    f"⚠️ `{att.filename}` no es una imagen válida y fue rechazada.\n"
                    "Formatos aceptados: `jpg, jpeg, png, gif, webp, bmp, tiff`"
                )
                continue
            if len(session["images"]) >= MAX_IMAGES:
                await message.channel.send(
                    f"⚠️ Límite de **{MAX_IMAGES}** imágenes alcanzado. "
                    f"Ignorando: `{att.filename}`"
                )
                continue
            # Subir a ImgBB
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(att.url) as resp:
                        img_bytes = await resp.read()
                imgbb_url = await self._upload_to_imgbb(img_bytes, att.filename)
                final_url = imgbb_url if imgbb_url else att.url
                session["images"].append({"filename": att.filename, "url": final_url})
                await message.add_reaction("🖼️")
            except Exception as e:
                print(f"⚠️ Error procesando imagen {att.filename}: {e}")
                await message.channel.send(f"⚠️ No se pudo procesar `{att.filename}`. Intenta de nuevo.")

    async def _session_timeout(self, user_id: int):
     await asyncio.sleep(SESSION_TIMEOUT_HOURS * 3600)
     if user_id in self.active_sessions:
        del self.active_sessions[user_id]
        self.session_timeouts.pop(user_id, None)
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(embed=self._expired_embed(is_pending=False))
        except Exception:
            pass
    async def _pending_timeout(self, user_id: int):
     await asyncio.sleep(SESSION_TIMEOUT_HOURS * 3600)
     if user_id in self.pending_sessions:
        session = self.pending_sessions.pop(user_id)
        # Re-habilitar el botón del mensaje original
        msg = session.get("source_message")
        if msg:
            try:
                view = PendingInfoView(self, session["ticket"])
                await msg.edit(view=view)
            except Exception:
                pass
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(embed=self._expired_embed(is_pending=True))
        except Exception:
            pass    

    # ──────────────────────────────────────────
    #  !ticket <titulo> — Solo MD
    # ──────────────────────────────────────────
    @commands.command(name="ticket")
    async def cmd_ticket(self, ctx: commands.Context, *, title: str = None):
        """Abre un ticket de bug. Úsalo en MD con el bot."""
        if not isinstance(ctx.channel, discord.DMChannel):
            try:
                await ctx.message.delete()
            except Exception:
                pass
            notice = await ctx.send(
                "❌ El comando `!ticket` es **exclusivo de mensajes directos**.\n"
                "Envíame un MD y úsalo allí 📩"
            )
            await asyncio.sleep(8)
            await notice.delete()
            return

        if not title:
            await ctx.send(
                "❌ Debes indicar un título.\n"
                "Uso: `!ticket <título del bug>`"
            )
            return

        if ctx.author.id in self.active_sessions:
            await ctx.send(
                "⚠️ Ya tienes una sesión de ticket abierta.\n"
                "Escribe `!done` para finalizarla o `!cancel` para cancelarla."
            )
            return

        embed = discord.Embed(
            title="🎫 Selecciona una categoría",
            description=(
                f"**Título:** `{title}`\n\n"
                "Elige la categoría que mejor describa tu ticket usando el menú desplegable.\n"
                "Si seleccionas **Otros**, podrás escribir un motivo personalizado."
            ),
            color=0x8B0000
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets")
        await ctx.send(embed=embed, view=CategorySelectView(self, ctx, title))

    # ──────────────────────────────────────────
    #  !done — Finaliza la sesión y crea el ticket
    # ──────────────────────────────────────────
    @commands.command(name="done")
    async def cmd_done(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.DMChannel):
            return

        # ── Helper interno para enviar con reintento ante 503 ────────
        async def _safe_send(embed: discord.Embed) -> bool:
            for attempt in range(3):
                try:
                    await ctx.send(embed=embed)
                    return True
                except discord.errors.DiscordServerError:
                    if attempt < 2:
                        await asyncio.sleep(4)
            return False

        # ── Caso: sesión de información adicional ────────────────────
        if ctx.author.id in self.pending_sessions:
            psession = self.pending_sessions.pop(ctx.author.id)
            self.session_timeouts.pop(ctx.author.id, None)

            if not psession["new_info"] and not psession["new_images"]:
                await ctx.send(
                    "❌ No añadiste ningún texto ni imagen.\n"
                    "La sesión fue cancelada. Pulsa de nuevo el botón del MD para reintentar."
                )
                return

            # Guardar en JSON
            saved = False
            try:
                tickets = load_tickets()
                for i, t in enumerate(tickets):
                    if t["id"] == psession["ticket_id"]:
                        sep        = f"\n\n{'─'*30}\n📅 Información adicional — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n{'─'*30}\n"
                        extra_text = "\n".join(psession["new_info"])
                        tickets[i]["description"]  = (tickets[i].get("description") or "") + sep + extra_text
                        tickets[i]["images"].extend(psession["new_images"])
                        tickets[i]["pending"]       = False
                        tickets[i]["pending_reason"] = None
                        break
                save_tickets(tickets)
                saved = True
            except Exception as e:
                print(f"⚠️ Error guardando info adicional: {e}")

            if saved:
                embed = discord.Embed(
                    title="✅ Información adicional enviada",
                    description=(
                        f"Tu información ha sido añadida al ticket `#{psession['ticket_id']}`.\n\n"
                        f"📝 **Mensajes añadidos:** {len(psession['new_info'])}\n"
                        f"🖼️ **Imágenes añadidas:** {len(psession['new_images'])}\n\n"
                        "Los moderadores podrán ver la nueva información y continuarán con la revisión."
                    ),
                    color=0x00CC66
                )
                embed.set_footer(text="7 Days to Die • Sistema de Tickets")
                sent = await _safe_send(embed)
                if not sent:
                    # 503 pero sí se guardó
                    err = discord.Embed(
                        title="⚠️ Discord tuvo un problema al responder",
                        description=(
                            f"Tu información **sí fue guardada** correctamente en el ticket `#{psession['ticket_id']}`.\n\n"
                            "El error fue del lado de Discord al enviarte este mensaje de confirmación, "
                            "no afectó el guardado.\n\n"
                            "Los moderadores ya pueden ver tu información."
                        ),
                        color=0xFFA500
                    )
                    err.set_footer(text="7 Days to Die • Sistema de Tickets")
                    try:
                        await ctx.send(embed=err)
                    except Exception:
                        pass
            else:
                err = discord.Embed(
                    title="❌ Error al guardar la información",
                    description=(
                        "Hubo un problema al guardar tu información adicional y **no fue registrada**.\n\n"
                        "Pulsa de nuevo el botón en el mensaje anterior para intentarlo otra vez."
                    ),
                    color=0xFF4444
                )
                err.set_footer(text="7 Days to Die • Sistema de Tickets")
                try:
                    await ctx.send(embed=err)
                except Exception:
                    pass
            return

        # ── Caso: sesión normal (nuevo ticket) ───────────────────────
        if ctx.author.id not in self.active_sessions:
            await ctx.send("❌ No tienes ninguna sesión de ticket abierta.")
            return

        session = self.active_sessions.pop(ctx.author.id)
        self.session_timeouts.pop(ctx.author.id, None)

        if not session["description"] and not session["images"]:
            await ctx.send(
                "❌ No añadiste ningún texto ni imagen.\n"
                "El ticket ha sido cancelado. Usa `!ticket <título>` para intentarlo de nuevo."
            )
            return

        # Guardar en JSON
        ticket_id = None
        saved     = False
        try:
            tickets   = load_tickets()
            ticket_id = get_next_id(tickets)
            now       = datetime.utcnow().isoformat()

            new_ticket = {
                "id":              ticket_id,
                "title":           session["title"][:100],
                "author_id":       str(ctx.author.id),
                "author_name":     str(ctx.author),
                "description":     "\n".join(session["description"]),
                "images":          session["images"],
                "category":        session.get("category"),
                "custom_category": session.get("custom_category"),
                "status":          "abierto",
                "solved":          None,
                "reason":          None,
                "closed_by_id":    None,
                "closed_by_name":  None,
                "created_at":      now,
                "closed_at":       None,
                "pending":         False,
                "pending_reason":  None,
            }
            tickets.append(new_ticket)
            save_tickets(tickets)
            saved = True
        except Exception as e:
            print(f"⚠️ Error guardando ticket: {e}")

        if not saved:
            err = discord.Embed(
                title="❌ Error al crear el ticket",
                description=(
                    "Hubo un problema al guardar tu ticket y **no fue registrado**.\n\n"
                    "Intenta de nuevo con `!ticket <título>`."
                ),
                color=0xFF4444
            )
            err.set_footer(text="7 Days to Die • Sistema de Tickets")
            try:
                await ctx.send(embed=err)
            except Exception:
                pass
            return

        # Notificar al canal de mods
        notify_channel = self.bot.get_channel(TICKET_NOTIFY_CHANNEL_ID)
        if notify_channel:
            mencion_roles = f"<@&{ALLOWED_ROLE_IDS['ADMIN']}> <@&{ALLOWED_ROLE_IDS['MOD']}>"
            cat_label     = self._get_category_label(
                new_ticket.get("category"),
                new_ticket.get("custom_category")
            )
            notify_embed = discord.Embed(
                title=f"🎫 Nuevo Ticket #{ticket_id}",
                description=(
                    f"**{ctx.author}** ha enviado un nuevo ticket y espera revisión.\n\n"
                    f"📌 **Título:** {new_ticket['title']}\n"
                    f"📂 **Categoría:** {cat_label}\n"
                    f"📝 **Mensajes:** {len(session['description'])}\n"
                    f"🖼️ **Imágenes:** {len(session['images'])}"
                ),
                color=0xFFA500,
            )
            notify_embed.add_field(
                name="🛠️ Comandos",
                value=(
                    f"`!bugs {ticket_id}` — ver el ticket completo\n"
                    f"`!tkclose {ticket_id}` — cerrar el ticket\n"
                    f"`!tickets` — ver todos los tickets abiertos"
                ),
                inline=False,
            )
            notify_embed.set_footer(text=f"7 Days to Die • Tickets  |  ID: {ticket_id}")
            try:
                await notify_channel.send(mencion_roles, embed=notify_embed)
            except Exception as e:
                print(f"⚠️ No se pudo notificar al canal de tickets: {e}")

        # Confirmar al usuario
        embed = discord.Embed(
            title="✅ ¡Ticket creado correctamente!",
            description=(
                f"Tu reporte ha sido registrado y los moderadores lo revisarán pronto.\n\n"
                f"🔢 **Número de ticket:** `#{ticket_id}`\n"
                f"📌 **Título:** `{session['title']}`\n"
                f"📝 **Mensajes incluidos:** {len(session['description'])}\n"
                f"🖼️ **Imágenes adjuntas:** {len(session['images'])}\n\n"
                f"Usa `!tkstatus {ticket_id}` para consultar el estado en cualquier momento."
            ),
            color=0x00CC66
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets")
        sent = await _safe_send(embed)
        if not sent:
            err = discord.Embed(
                title="⚠️ Discord tuvo un problema al responder",
                description=(
                    f"Tu ticket **sí fue creado** correctamente con el número `#{ticket_id}`.\n\n"
                    "El error fue del lado de Discord al enviarte este mensaje de confirmación, "
                    "no afectó el registro del ticket.\n\n"
                    f"Usa `!tkstatus {ticket_id}` para verificarlo cuando quieras."
                ),
                color=0xFFA500
            )
            err.set_footer(text="7 Days to Die • Sistema de Tickets")
            try:
                await ctx.send(embed=err)
            except Exception:
                pass
    # ──────────────────────────────────────────
    #  !cancel — Cancela la sesión activa
    # ──────────────────────────────────────────
    @commands.command(name="cancel")
    async def cmd_cancel(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.DMChannel):
            return

        if ctx.author.id in self.pending_sessions:
            session = self.pending_sessions.pop(ctx.author.id)
            self.session_timeouts.pop(ctx.author.id, None)

            # Re-habilitar el botón del mensaje original
            msg = session.get("source_message")
            if msg:
                try:
                    view = PendingInfoView(self, session["ticket"])
                    await msg.edit(view=view)
                except Exception:
                    pass

            await ctx.send("🚫 Sesión de información adicional cancelada.\nPuedes pulsar el botón de nuevo cuando quieras.")
            return

        if ctx.author.id not in self.active_sessions:
            await ctx.send("❌ No tienes ninguna sesión de ticket abierta.")
            return

        self.active_sessions.pop(ctx.author.id)
        self.session_timeouts.pop(ctx.author.id, None)
        await ctx.send("🚫 Sesión de ticket cancelada.")
    # ──────────────────────────────────────────
    #  !tkstatus [numero] — Estado de tickets (Solo MD)
    # ──────────────────────────────────────────
    @commands.command(name="tkstatus")
    async def cmd_tkstatus(self, ctx: commands.Context, ticket_num: int = None):
     """Consulta el estado de tus tickets. Úsalo en MD con el bot."""
     if not isinstance(ctx.channel, discord.DMChannel):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        notice = await ctx.send(
            "❌ El comando `!tkstatus` es **exclusivo de mensajes directos**.\n"
            "Envíame un MD y úsalo allí 📩"
        )
        await asyncio.sleep(8)
        await notice.delete()
        return

     tickets    = load_tickets()
     my_tickets = [t for t in tickets if t["author_id"] == str(ctx.author.id)]

     if not my_tickets:
        await ctx.send("📭 No tienes ningún ticket registrado.")
        return

     # ── Con número: muestra ese ticket directamente ──────────────────
     if ticket_num is not None:
        ticket = next((t for t in my_tickets if t["id"] == ticket_num), None)
        if not ticket:
            await ctx.send(f"❌ No existe el ticket `#{ticket_num}` o no te pertenece.")
            return
        embed = self._build_status_embed(ticket)
        await ctx.send(embed=embed, view=TicketHTMLView(self, ticket, is_mod=False))
        return

     # ── Sin argumento: resumen + lista paginada ───────────────────────
     abiertos        = [t for t in my_tickets if t["status"] == "abierto" and not t.get("pending")]
     pendientes      = [t for t in my_tickets if t.get("pending")]
     solucionados    = [t for t in my_tickets if t["status"] == "cerrado" and t.get("solved")]
     no_solucionados = [t for t in my_tickets if t["status"] == "cerrado" and not t.get("solved")]

     embed = discord.Embed(
        title="🎫 Tus Tickets — Resumen",
        description=f"Tienes **{len(my_tickets)}** ticket(s) en total.",
        color=0x7289DA
     )
     embed.add_field(
        name="📊 Estado actual",
        value=(
            f"🟠 **Abiertos:** {len(abiertos)}\n"
            f"⏳ **Pendientes de info:** {len(pendientes)}\n"
            f"✅ **Solucionados:** {len(solucionados)}\n"
            f"❌ **No solucionados:** {len(no_solucionados)}"
        ),
        inline=False
     )
     embed.add_field(
        name="ℹ️ Instrucciones",
        value=(
            "Selecciona un ticket del menú para ver su estado detallado.\n"
            "También puedes usar `!tkstatus <número>` para ir directo a uno."
        ),
        inline=False
     )
     embed.set_footer(text="7 Days to Die • Sistema de Tickets  |  Solo visible para ti")

     # Pendientes → abiertos → cerrados
     sorted_tickets = pendientes + abiertos + solucionados + no_solucionados

     view = UserTicketPaginatorView(self, sorted_tickets, len(tickets))
     await ctx.send(embed=embed, view=view)
    def _build_status_embed(self, ticket: dict) -> discord.Embed:
        is_open   = ticket["status"] == "abierto"
        is_solved = ticket.get("solved")
        pending   = ticket.get("pending", False)
        labels = _estado_labels(ticket.get("category", ""))

        if pending:
            color, icon, label = 0xFFA500, "⏳", "Pendiente — esperando más información"
        elif is_open:
            color, icon, label = 0xFFA500, "🟠", "Abierto — en espera de revisión"
        elif is_solved:
            color, icon, label = 0x00CC66, "✅", f"Cerrado — **{labels['pos']}** ✅"
        else:
            color, icon, label = 0xFF4444, "❌", f"Cerrado — **{labels['neg']}** ❌"

        embed = discord.Embed(title=f"🎫 Estado del Ticket #{ticket['id']}", color=color)
        embed.add_field(name="📌 Título",      value=ticket["title"],           inline=False)
        embed.add_field(name=f"{icon} Estado", value=label,                     inline=False)
        embed.add_field(name="📅 Creado el",   value=ticket["created_at"][:10], inline=True)

        if ticket.get("closed_at"):
            embed.add_field(name="🔒 Cerrado el", value=ticket["closed_at"][:10], inline=True)

        if pending and ticket.get("pending_reason"):
            embed.add_field(name="📋 Información solicitada", value=ticket["pending_reason"], inline=False)
        elif ticket.get("reason"):
            embed.add_field(name="📋 Razón del moderador", value=ticket["reason"], inline=False)

        category_val = ticket.get("category")
        if category_val:
            custom      = ticket.get("custom_category")
            cat_display = self._get_category_label(category_val, custom)
            embed.add_field(name="📂 Categoría", value=cat_display, inline=False)

        embed.set_footer(text="7 Days to Die • Sistema de Tickets")
        return embed

    # ──────────────────────────────────────────
    #  !bugs [numero] — Solo moderadores
    # ──────────────────────────────────────────
    @commands.command(name="bugs")
    @commands.guild_only()
    async def cmd_bugs(self, ctx: commands.Context, ticket_num: int = None):
        """Muestra los tickets de bug. Solo moderadores."""
        if not self._user_is_mod(ctx.author):
            return

        tickets = load_tickets()
        if not tickets:
            await ctx.send("📭 No hay tickets registrados aún.")
            return

        if ticket_num is not None:
            ticket = next((t for t in tickets if t["id"] == ticket_num), None)
            if not ticket:
                await ctx.send(f"❌ No existe el ticket `#{ticket_num}`.")
                return
            embed = self._make_ticket_embed(ticket, len(tickets))
            view  = TicketHTMLView(self, ticket, is_mod=True)
            await ctx.send(embed=embed, view=view)
            return

        view = BugsPaginatorView(self, tickets)
        await ctx.send(embed=view.current_embed(), view=view)

    # ──────────────────────────────────────────
    #  !tkclose <num> — Solo moderadores
    # ──────────────────────────────────────────
    @commands.command(name="tkclose")
    @commands.guild_only()
    async def cmd_tkclose(self, ctx: commands.Context, ticket_num: int = None):
        """Cierra un ticket con interfaz interactiva. Solo moderadores."""
        if not self._user_is_mod(ctx.author):
            return

        if ticket_num is None:
            embed = discord.Embed(
                title="❌ Uso incorrecto",
                description="**Uso:** `!tkclose <número de ticket>`\n**Ejemplo:** `!tkclose 5`",
                color=0xFF4444
            )
            return await ctx.send(embed=embed)

        tickets = load_tickets()
        ticket  = next((t for t in tickets if t["id"] == ticket_num), None)

        if not ticket:
            return await ctx.send(f"❌ No existe el ticket `#{ticket_num}`.")

        if ticket["status"] == "cerrado":
            icon   = "✅" if ticket.get("solved") else "❌"
            estado = "Solucionado" if ticket.get("solved") else "No solucionado"
            return await ctx.send(
                f"⚠️ El ticket `#{ticket_num}` ya está cerrado.\n"
                f"{icon} Estado: **{estado}**"
            )

        embed = discord.Embed(title=f"🔒 Cerrar Ticket #{ticket['id']}", color=0xFFA500)
        embed.add_field(name="📌 Título",    value=ticket["title"],          inline=False)
        embed.add_field(name="👤 Usuario",   value=ticket["author_name"],    inline=True)
        embed.add_field(name="📅 Creado",    value=ticket["created_at"][:10], inline=True)

        desc = ticket.get("description") or "*(sin descripción)*"
        if len(desc) > 300:
            desc = desc[:297] + "..."
        embed.add_field(name="📝 Descripción", value=desc, inline=False)

        images = ticket.get("images", [])
        if images:
            embed.add_field(
                name=f"🖼️ Imágenes ({len(images)})",
                value="\n".join(f"• [{img['filename']}]({img['url']})" for img in images[:3]),
                inline=False
            )

        embed.add_field(
            name="─────────────────────────",
            value="Selecciona el **resultado** del ticket en el menú de abajo.",
            inline=False
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets")
        view = TkCloseView(self, ctx, ticket)
        await ctx.send(embed=embed, view=view)

    # ──────────────────────────────────────────
    #  !tickets — Solo moderadores
    # ──────────────────────────────────────────
    @commands.command(name="tickets")
    @commands.guild_only()
    async def cmd_tickets(self, ctx: commands.Context):
        """Muestra lista de tickets ACTIVOS (solo moderadores)."""
        if not self._user_is_mod(ctx.author):
            return

        tickets = load_tickets()
        active  = [t for t in tickets if t["status"] == "abierto"]

        if not active:
            return await ctx.send("📭 No hay tickets activos.")

        embed = discord.Embed(title="🎫 Panel de Tickets Activos", color=0x00AAFF)
        embed.add_field(
            name="📊 Resumen",
            value=f"**{len(active)}** abierto(s) de **{len(tickets)}** totales",
            inline=False
        )
        lines = []
        for t in active[:10]:
            title_short = t["title"][:45] + "…" if len(t["title"]) > 45 else t["title"]
            lines.append(
                f"🟠 `#{t['id']}` **{title_short}**\n"
                f"　👤 {t['author_name']} • 📅 {t['created_at'][:10]}"
            )
        embed.add_field(name="📋 Tickets abiertos", value="\n".join(lines) or "—", inline=False)
        embed.add_field(
            name="ℹ️ Instrucciones",
            value="Usa el menú desplegable de abajo para seleccionar un ticket y ver sus detalles completos.",
            inline=False
        )
        embed.set_footer(text="7 Days to Die • Sistema de Tickets  |  Selecciona del menú ↓")
        view = TicketView(self, active, len(tickets), page=0, page_size=15)
        await ctx.send(embed=embed, view=view)

    # ──────────────────────────────────────────
    #  !tklist [numero] — Panel completo
    # ──────────────────────────────────────────
    @commands.command(name="tklist")
    @commands.guild_only()
    async def cmd_tklist(self, ctx: commands.Context, ticket_num: int = None):
        """Muestra el panel de TODOS los tickets (solo moderadores)."""
        if not self._user_is_mod(ctx.author):
            return

        tickets = load_tickets()
        if not tickets:
            return await ctx.send("📭 No hay tickets registrados.")

        if ticket_num is not None:
            ticket = next((t for t in tickets if t["id"] == ticket_num), None)
            if not ticket:
                return await ctx.send(f"❌ No existe el ticket `#{ticket_num}`.")
            embed = self._make_ticket_embed(ticket, len(tickets))
            view  = TicketHTMLView(self, ticket, is_mod=True)
            return await ctx.send(embed=embed, view=view)

        abiertos          = [t for t in tickets if t["status"] == "abierto"]
        cerrados_solved   = [t for t in tickets if t["status"] == "cerrado" and t.get("solved")]
        cerrados_unsolved = [t for t in tickets if t["status"] == "cerrado" and not t.get("solved")]
        pendientes        = [t for t in tickets if t.get("pending")]

        embed = discord.Embed(title="📋 Panel de Todos los Tickets", color=0x7289DA)
        embed.add_field(
            name="📊 Resumen",
            value=(
                f"🟠 **Abiertos:** {len(abiertos)}\n"
                f"⏳ **Pendientes:** {len(pendientes)}\n"
                f"✅ **Cerrados (Solucionados):** {len(cerrados_solved)}\n"
                f"❌ **Cerrados (No solucionados):** {len(cerrados_unsolved)}\n"
                f"📦 **Total:** {len(tickets)}"
            ),
            inline=False
        )
        embed.add_field(
            name="ℹ️ Instrucciones",
            value="Usa el menú desplegable de abajo para seleccionar un ticket y ver sus detalles completos.",
            inline=False
        )
        embed.set_footer(text=f"7 Days to Die • Sistema de Tickets  |  Total: {len(tickets)} tickets")
        view = AllTicketsView(self, tickets, page=0, page_size=15)
        await ctx.send(embed=embed, view=view)

    # ──────────────────────────────────────────
    #  Generar HTML del ticket
    # ──────────────────────────────────────────
    def _generate_ticket_html(self, ticket: dict) -> str:
        """Genera un HTML estilizado y completo del ticket."""
        images     = ticket.get("images", [])
        desc       = ticket.get("description", "") or "<em>(sin descripción)</em>"
        paragraphs = "".join(
            f"<p>{_html_mod.escape(p)}</p>"
            for p in desc.split("\n") if p.strip()
        ) or f"<p>{desc}</p>"

        _lb    = _estado_labels(ticket.get("category", ""))
        status_map = {
            ("abierto",  None):  ("🟠", "Abierto",                         "#FFA500"),
            ("cerrado",  True):  ("✅", f"Cerrado · {_lb['pos']}",         "#00CC66"),
            ("cerrado",  False): ("❌", f"Cerrado · {_lb['neg']}",         "#FF4444"),
        }
        key             = (ticket["status"], ticket.get("solved"))
        icon, label, color = status_map.get(key, ("❓", "Desconocido", "#888"))

        imgs_html = ""
        if images:
            cards = "\n".join(
                f'<div class="img-card">'
                f'<a href="{img["url"]}" target="_blank">'
                f'<img src="{img["url"]}" alt="{_html_mod.escape(img["filename"])}" loading="lazy">'
                f'</a>'
                f'<span>{_html_mod.escape(img["filename"])}</span>'
                f'</div>'
                for img in images
            )
            imgs_html = f"""
        <section class="section">
            <h2>🖼️ Imágenes adjuntas ({len(images)})</h2>
            <div class="img-grid">{cards}</div>
        </section>"""

        reason_html = ""
        if ticket.get("reason"):
            reason_html = f"""
        <section class="section">
            <h2>📋 Razón de cierre</h2>
            <p class="reason">{_html_mod.escape(ticket['reason'])}</p>
        </section>"""

        closed_html = ""
        if ticket.get("closed_at"):
            closer      = (
                f" • 🛡️ Cerrado por: <b>{_html_mod.escape(ticket.get('closed_by_name', 'Desconocido'))}</b>"
                if ticket.get("closed_by_name") else ""
            )
            closed_html = f"<span class='meta-item'>🔒 Cerrado: <b>{ticket['closed_at'][:10]}</b>{closer}</span>"

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ticket #{ticket['id']} — {_html_mod.escape(ticket['title'])}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0f0f17;color:#e0e0e0;font-family:'Segoe UI',sans-serif;min-height:100vh;padding:2rem 1rem}}
  .container{{max-width:860px;margin:0 auto}}
  header{{background:linear-gradient(135deg,#1a1a2e,#16213e);border-left:5px solid {color};border-radius:10px;padding:1.5rem 2rem;margin-bottom:1.5rem}}
  header h1{{font-size:1.5rem;color:#fff;margin-bottom:.5rem}}
  .status{{display:inline-block;background:{color}22;color:{color};border:1px solid {color};border-radius:20px;padding:.25rem .75rem;font-size:.85rem;font-weight:600;margin-bottom:1rem}}
  .meta{{display:flex;flex-wrap:wrap;gap:.75rem;font-size:.85rem;color:#aaa}}
  .meta-item b{{color:#ddd}}
  .section{{background:#1a1a2e;border-radius:10px;padding:1.5rem 2rem;margin-bottom:1.25rem;border:1px solid #2a2a4a}}
  .section h2{{font-size:1rem;color:#7289da;margin-bottom:1rem;border-bottom:1px solid #2a2a4a;padding-bottom:.5rem}}
  .section p{{line-height:1.7;color:#ccc;margin-bottom:.5rem}}
  .reason{{background:#2a1a1a;border-left:3px solid #ff4444;padding:.75rem 1rem;border-radius:6px;color:#ffaaaa}}
  .img-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem}}
  .img-card{{background:#0f0f17;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden;text-align:center}}
  .img-card img{{width:100%;height:160px;object-fit:cover;display:block;transition:opacity .2s}}
  .img-card img:hover{{opacity:.85}}
  .img-card span{{display:block;font-size:.75rem;color:#888;padding:.4rem;word-break:break-all}}
  footer{{text-align:center;color:#555;font-size:.8rem;margin-top:2rem}}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🎫 Ticket #{ticket['id']} — {_html_mod.escape(ticket['title'])}</h1>
    <div class="status">{icon} {label}</div>
    <div class="meta">
      <span class="meta-item">👤 <b>{_html_mod.escape(ticket['author_name'])}</b></span>
      <span class="meta-item">📅 Creado: <b>{ticket['created_at'][:10]}</b></span>
      {closed_html}
    </div>
  </header>

  <section class="section">
    <h2>📝 Descripción del bug</h2>
    {paragraphs}
  </section>

  {imgs_html}
  {reason_html}

  <footer>7 Days to Die • Sistema de Tickets • Generado el {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</footer>
</div>
</body>
</html>"""

# ─────────────────────────────────────────────
#  SETUP (requerido por load_extension)
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))