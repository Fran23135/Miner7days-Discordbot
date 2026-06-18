"""
decoracion.py — Sistema de pedidos de decoración para Miner7days.

Usuarios:
  !decoracion  — Muestra embed con botón para hacer un pedido
  !decolist    — (solo MD) Lista tus pedidos y su estado

Mods:
  !deco        — Panel de gestión de pedidos (en revisión / pendientes / historial)

Flujo de estados:
  en_revision  →  pendiente (aprobado)  →  finalizado
                ↘  rechazado
"""

import discord
from discord.ext import commands
from discord.ui import View, Button
from discord.ui.label import Label
from discord.ui.file_upload import FileUpload
import json, os, re, aiohttp, random, string
from datetime import datetime
from config import ROLES, CANALES
from pin import IMGBB_API

# ─────────────────────────────────────────────────────────────────────
# RUTAS Y CONSTANTES
# ─────────────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "Cache")
DECO_FILE = os.path.join(CACHE_DIR, "decoracion.json")

VALID_IMG  = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
_PAGE_SIZE = 15

# ─────────────────────────────────────────────────────────────────────
# JSON HELPERS
# ─────────────────────────────────────────────────────────────────────
def _migrar(data: dict) -> bool:
    """Rellena campos nuevos en pedidos viejos. Devuelve True si hubo cambios."""
    cambios = False
    for p in data.get("pedidos", []):
        if "approved_at" not in p:
            if p.get("status") in ("pendiente", "finalizado"):
                p["approved_at"] = p.get("created_at", "—")
                p["approved_by"] = "Sistema (migración)"
            else:
                p["approved_at"] = None
                p["approved_by"] = None
            cambios = True
        if "delivery_notes" not in p:
            p["delivery_notes"] = None
            cambios = True
        if "revalidaciones" not in p:
            p["revalidaciones"] = []
            cambios = True
        if "revalidado" not in p:
            p["revalidado"] = False
            cambios = True
        if "images" not in p:
            p["images"] = []
            cambios = True
        if "reason" not in p:
            p["reason"] = None
            cambios = True
        if "closed_at" not in p:
            p["closed_at"] = None
            cambios = True
        if "closed_by" not in p:
            p["closed_by"] = None
            cambios = True
    return cambios

def _load() -> dict:
    if not os.path.exists(DECO_FILE):
        return {"pedidos": []}
    with open(DECO_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if _migrar(data):
        _save(data)
    return data

def _save(data: dict) -> None:
    with open(DECO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _next_id(pedidos: list) -> int:
    return max((p["id"] for p in pedidos), default=0) + 1

def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")

# ─────────────────────────────────────────────────────────────────────
# PERMISOS
# ─────────────────────────────────────────────────────────────────────
def _es_mod(member: discord.Member) -> bool:
    ids = {r.id for r in member.roles}
    return bool(ids & set(ROLES.values()))

# ─────────────────────────────────────────────────────────────────────
# PARSEO DE ITEMS  (-nombre / -nombre -nombre)
# ─────────────────────────────────────────────────────────────────────
def _parsear_items(text: str) -> list[str] | None:
    matches = re.findall(r"-([^-\n]+)", text)
    items   = [m.strip() for m in matches if m.strip()]
    return items if items else None

# ─────────────────────────────────────────────────────────────────────
# IMGBB UPLOAD
# ─────────────────────────────────────────────────────────────────────
async def _upload_imgbb(url: str, filename: str, content_type: str = "image/png") -> str | None:
    nombre = "deco_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as resp:
                img_bytes = await resp.read()
        async with aiohttp.ClientSession() as s:
            form = aiohttp.FormData()
            form.add_field("key",   IMGBB_API)
            form.add_field("name",  nombre)
            form.add_field("image", img_bytes,
                           filename=filename,
                           content_type=content_type or "image/png")
            async with s.post("https://api.imgbb.com/1/upload", data=form) as r:
                res = await r.json()
                if res.get("success"):
                    return res["data"]["url"]
    except Exception as e:
        print(f"[decoracion] imgbb error: {e}")
    return None

# ─────────────────────────────────────────────────────────────────────
# EMBED DE PEDIDO  (mod + usuario)
# ─────────────────────────────────────────────────────────────────────
def _pedido_embed(p: dict, total: int) -> discord.Embed:
    _STATUS = {
        "en_revision": ("🔵", 0x5865F2, "En revisión"),
        "pendiente":   ("🟠", 0xFFA500, "Aprobado — Pendiente de entrega"),
        "finalizado":  ("✅", 0x00CC66, "Finalizado"),
        "rechazado":   ("❌", 0xFF4444, "Rechazado"),
    }
    icon, color, label = _STATUS.get(p["status"], ("❓", 0x7289DA, p["status"]))

    # Pedido revalidado vuelve a pendiente pero se diferencia visualmente
    if p.get("revalidado") and p["status"] == "pendiente":
        icon  = "🔄"
        color = 0x5865F2
        label = "Pendiente (Revalidado)"

    embed = discord.Embed(
        title=f"🪑 Pedido de Decoración #{p['id']}",
        color=color,
    )
    embed.add_field(name="👤 Discord",          value=p["user_name"],   inline=True)
    embed.add_field(name="🎮 Nombre en 7 Days", value=p["ingame_name"], inline=True)
    embed.add_field(name=f"{icon} Estado",      value=label,            inline=True)
    embed.add_field(name="📅 Fecha pedido",     value=p["created_at"],  inline=True)

    # Aprobación
    if p.get("approved_at"):
        embed.add_field(
            name="✅ Aprobado",
            value=(
                f"**Por:** {p['approved_by']}\n"
                f"**Fecha:** {p['approved_at']}"
            ),
            inline=True,
        )

    # Historial de revalidaciones (muestra la más reciente)
    if p.get("revalidaciones"):
        rev = p["revalidaciones"][-1]
        n   = len(p["revalidaciones"])
        embed.add_field(
            name=f"🔄 Revalidado ({n}x)",
            value=(
                f"**Por:** {rev['revalidado_por']}\n"
                f"**Razón:** {rev['razon']}\n"
                f"**Fecha:** {rev['fecha']}"
            ),
            inline=False,
        )

    items_str = "\n".join(f"• {i}" for i in p["items"])
    embed.add_field(
        name=f"🪑 Decoraciones solicitadas ({len(p['items'])})",
        value=items_str,
        inline=False,
    )

    if p.get("images"):
        links = "\n".join(
            f"[📷 Imagen {n + 1}]({u})" for n, u in enumerate(p["images"])
        )
        embed.add_field(name=f"🖼️ Imágenes ({len(p['images'])})", value=links, inline=False)
        embed.set_image(url=p["images"][0])

    if p.get("reason"):
        embed.add_field(name="📋 Razón de rechazo", value=p["reason"], inline=False)

    if p.get("delivery_notes"):
        embed.add_field(name="📝 Detalles de entrega", value=p["delivery_notes"], inline=False)

    if p.get("closed_at"):
        embed.add_field(name="🔒 Cerrado el",  value=p["closed_at"], inline=True)
        embed.add_field(name="🛡️ Cerrado por", value=p["closed_by"], inline=True)

    embed.set_footer(text=f"Pedido {p['id']} de {total} • Miner7days • Decoración")
    return embed


# ═════════════════════════════════════════════════════════════════════
# MODAL — Hacer pedido  (usuarios)
# ═════════════════════════════════════════════════════════════════════
class PedidoModal(discord.ui.Modal, title="🪑 Pedido de Decoración"):
    nombre_juego = discord.ui.TextInput(
        label="Tu nombre en 7 Days to Die",
        placeholder="Ej: Fran23135",
        min_length=2,
        max_length=40,
    )
    items_text = discord.ui.TextInput(
        label="Decoraciones (guión antes de cada nombre)",
        style=discord.TextStyle.paragraph,
        placeholder="-Lámpara de techo\n-Silla de madera\n-Mesa grande\n\nO en una línea: -Lámpara -Silla",
        min_length=2,
        max_length=800,
    )

    def __init__(self, cog: "DecoracionCog"):
        super().__init__()
        self._cog = cog
        self._img_label = discord.ui.Label(
            text="Imágenes de referencia (máx. 4, opcional):",
            component=discord.ui.FileUpload(
                custom_id="deco_images",
                min_values=0,
                max_values=4,
                required=False,
            ),
        )
        self.add_item(self._img_label)

    async def on_submit(self, interaction: discord.Interaction):
        # ── 1. Parsear y validar items ─────────────────────────────
        items = _parsear_items(self.items_text.value)
        if not items:
            await interaction.response.send_message(
                "❌ **Formato incorrecto en la lista de decoraciones.**\n\n"
                "Pon un guión delante de cada nombre, así:\n"
                "```\n-Lámpara de techo\n-Silla de madera\n```"
                "O en una sola línea:\n"
                "```\n-Lámpara -Silla -Mesa\n```",
                ephemeral=True,
            )
            return

        # ── 2. Validar archivos adjuntos ───────────────────────────
        raw_atts = interaction.data.get("resolved", {}).get("attachments", {})
        atts     = list(raw_atts.values())

        if len(atts) > 4:
            await interaction.response.send_message(
                "❌ Solo se permiten **4 imágenes** como máximo.", ephemeral=True
            )
            return

        bad = [
            a["filename"] for a in atts
            if os.path.splitext(a["filename"])[1].lower() not in VALID_IMG
        ]
        if bad:
            await interaction.response.send_message(
                f"❌ Estos archivos no son imágenes válidas: `{'`, `'.join(bad)}`\n"
                "Formatos aceptados: `jpg, jpeg, png, gif, webp, bmp, tiff`",
                ephemeral=True,
            )
            return

        # ── 3. Defer antes de subir ────────────────────────────────
        await interaction.response.defer(ephemeral=True, thinking=True)

        # ── 4. Subir imágenes a ImgBB ──────────────────────────────
        img_urls: list[str] = []
        for att in atts:
            url = await _upload_imgbb(
                att["url"],
                att["filename"],
                att.get("content_type", "image/png"),
            )
            if url:
                img_urls.append(url)
            else:
                await interaction.followup.send(
                    f"❌ No se pudo subir `{att['filename']}` a ImgBB. Intenta de nuevo.",
                    ephemeral=True,
                )
                return

        # ── 5. Guardar en JSON ─────────────────────────────────────
        data   = _load()
        pedido = {
            "id":             _next_id(data["pedidos"]),
            "user_id":        str(interaction.user.id),
            "user_name":      str(interaction.user),
            "ingame_name":    self.nombre_juego.value.strip(),
            "items":          items,
            "images":         img_urls,
            "status":         "en_revision",   # Espera aprobación del mod
            "revalidado":     False,
            "revalidaciones": [],
            "reason":         None,
            "approved_at":    None,
            "approved_by":    None,
            "delivery_notes": None,
            "created_at":     _now(),
            "closed_at":      None,
            "closed_by":      None,
        }
        data["pedidos"].append(pedido)
        _save(data)

        # ── 6. Notificar canal de mods ─────────────────────────────
        notify_ch = self._cog.bot.get_channel(CANALES["7days-deco"])
        if notify_ch:
            menciones = " ".join(f"<@&{rid}>" for rid in ROLES.values())
            owner = notify_ch.guild.owner
            if owner:
                menciones += f" {owner.mention}"

            notif = discord.Embed(
                title=f"🔵 Nuevo Pedido de Decoración #{pedido['id']} — Pendiente de revisión",
                color=0x5865F2,
            )
            notif.add_field(name="👤 Discord",          value=str(interaction.user), inline=True)
            notif.add_field(name="🎮 Nombre en 7 Days", value=pedido["ingame_name"],  inline=True)
            notif.add_field(
                name=f"🪑 Decoraciones ({len(items)})",
                value="\n".join(f"• {i}" for i in items),
                inline=False,
            )
            if img_urls:
                notif.add_field(
                    name="🖼️ Imágenes adjuntas",
                    value=f"{len(img_urls)} imagen(es) subida(s)",
                    inline=True,
                )
                notif.set_image(url=img_urls[0])
            notif.add_field(
                name="📋 Gestionar",
                value="Usa `!deco` para revisar y aprobar o rechazar el pedido.",
                inline=False,
            )
            notif.set_footer(text=f"📅 {pedido['created_at']} • Miner7days")
            await notify_ch.send(content=menciones, embed=notif)

        # ── 7. Confirmar al usuario (efímero) ──────────────────────
        ok = discord.Embed(
            title="✅ ¡Pedido enviado!",
            description=(
                f"Tu pedido fue registrado con el ID `#{pedido['id']}`.\n\n"
                f"🪑 **Decoraciones pedidas:** {len(items)}\n"
                f"🖼️ **Imágenes adjuntas:** {len(img_urls)}\n\n"
                "⏳ Un moderador lo **revisará y aprobará** cuando pueda.\n"
                "Te notificaremos por MD cuando sea aprobado o rechazado. **Ten paciencia.** 🙏\n\n"
                "Puedes ver el estado de tus pedidos con `!decolist` en MD."
            ),
            color=0x00CC66,
        )
        ok.set_footer(text="Miner7days • Decoración")
        await interaction.followup.send(embed=ok, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[decoracion] PedidoModal error: {error}")
        try:
            await interaction.followup.send(
                "❌ Ocurrió un error al procesar tu pedido. Intenta de nuevo.",
                ephemeral=True,
            )
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
# VIEW — Botón de pedido  (!decoracion público)
# ═════════════════════════════════════════════════════════════════════
class DecoPublicView(View):
    def __init__(self, cog: "DecoracionCog"):
        super().__init__(timeout=None)
        self._cog = cog

    @discord.ui.button(label="📦 Hacer pedido", style=discord.ButtonStyle.primary, emoji="🪑")
    async def btn_pedir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PedidoModal(self._cog))


# ═════════════════════════════════════════════════════════════════════
# MODAL — Razón de rechazo  (mods)
# ═════════════════════════════════════════════════════════════════════
class RechazoModal(discord.ui.Modal, title="❌ Razón del rechazo"):
    razon = discord.ui.TextInput(
        label="Explica por qué se rechaza el pedido",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: Los objetos solicitados no están disponibles actualmente.",
        min_length=5,
        max_length=400,
        required=True,
    )

    def __init__(self, cog: "DecoracionCog", pedido: dict):
        super().__init__()
        self._cog    = cog
        self._pedido = pedido

    async def on_submit(self, interaction: discord.Interaction):
        razon_text = self.razon.value.strip()
        ahora      = _now()

        data = _load()
        for p in data["pedidos"]:
            if p["id"] == self._pedido["id"]:
                p["status"]    = "rechazado"
                p["reason"]    = razon_text
                p["closed_at"] = ahora
                p["closed_by"] = str(interaction.user)
                self._pedido   = p
                break
        _save(data)

        # DM al usuario
        try:
            user     = await self._cog.bot.fetch_user(int(self._pedido["user_id"]))
            dm_embed = discord.Embed(
                title=f"❌ Tu pedido #{self._pedido['id']} fue rechazado",
                description=(
                    f"Hola {user.mention}, lamentablemente tu pedido de decoración no pudo ser procesado.\n\n"
                    f"🪑 **Pedido original:**\n"
                    + "\n".join(f"• {i}" for i in self._pedido["items"])
                    + f"\n\n📋 **Razón:** {razon_text}\n"
                    f"🛡️ **Rechazado por:** {interaction.user}\n"
                    f"📅 **Fecha:** {ahora}"
                ),
                color=0xFF4444,
            )
            dm_embed.set_footer(text="Miner7days • Decoración")
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"[decoracion] No se pudo enviar DM de rechazo: {e}")

        await interaction.response.send_message(
            f"❌ Pedido `#{self._pedido['id']}` marcado como **rechazado**. "
            "El usuario fue notificado por DM.",
            ephemeral=True,
        )


# ═════════════════════════════════════════════════════════════════════
# MODAL — Razón de revalidación  (mods, solo rechazados)
# ═════════════════════════════════════════════════════════════════════
class RevalidarModal(discord.ui.Modal, title="🔄 Revalidar pedido"):
    razon = discord.ui.TextInput(
        label="¿Por qué se revalida este pedido?",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: Error al rechazarlo, los objetos ahora están disponibles...",
        min_length=5,
        max_length=400,
        required=True,
    )

    def __init__(self, cog: "DecoracionCog", pedido: dict):
        super().__init__()
        self._cog    = cog
        self._pedido = pedido

    async def on_submit(self, interaction: discord.Interaction):
        razon_text = self.razon.value.strip()
        ahora      = _now()

        data = _load()
        for p in data["pedidos"]:
            if p["id"] == self._pedido["id"]:
                p["status"]     = "pendiente"
                p["revalidado"] = True
                p["reason"]     = None
                p["closed_at"]  = None
                p["closed_by"]  = None
                p.setdefault("revalidaciones", []).append({
                    "revalidado_por": str(interaction.user),
                    "razon":          razon_text,
                    "fecha":          ahora,
                })
                self._pedido = p
                break
        _save(data)

        # DM al usuario
        try:
            user     = await self._cog.bot.fetch_user(int(self._pedido["user_id"]))
            dm_embed = discord.Embed(
                title=f"🔄 Tu pedido #{self._pedido['id']} fue revalidado",
                description=(
                    f"¡Hola {user.mention}! Un moderador ha revalidado tu pedido de decoración "
                    "y vuelve a estar en espera.\n\n"
                    f"🪑 **Pedido:**\n"
                    + "\n".join(f"• {i}" for i in self._pedido["items"])
                    + f"\n\n📋 **Razón de revalidación:** {razon_text}\n"
                    f"🛡️ **Revalidado por:** {interaction.user}\n"
                    f"📅 **Fecha:** {ahora}\n\n"
                    "Los moderadores lo gestionarán de nuevo. ¡Ten paciencia! 🙏"
                ),
                color=0x5865F2,
            )
            dm_embed.set_footer(text="Miner7days • Decoración")
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"[decoracion] No se pudo enviar DM de revalidación: {e}")

        await interaction.response.send_message(
            f"🔄 Pedido `#{self._pedido['id']}` **revalidado** y vuelve a estar pendiente. "
            "El usuario fue notificado por DM.",
            ephemeral=True,
        )


# ═════════════════════════════════════════════════════════════════════
# MODAL — Detalles de entrega  (mods, opcional)
# ═════════════════════════════════════════════════════════════════════
class EntregaModal(discord.ui.Modal, title="📦 Confirmar entrega"):
    detalles = discord.ui.TextInput(
        label="Detalles de la entrega (opcional)",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: Todo colocado en la base norte, junto al cofre principal...",
        required=False,
        max_length=500,
    )

    def __init__(self, cog: "DecoracionCog", pedido: dict, mod: discord.Member):
        super().__init__()
        self._cog    = cog
        self._pedido = pedido
        self._mod    = mod

    async def on_submit(self, interaction: discord.Interaction):
        notas = self.detalles.value.strip() if self.detalles.value else None
        ahora = _now()

        data = _load()
        for p in data["pedidos"]:
            if p["id"] == self._pedido["id"]:
                p["status"]         = "finalizado"
                p["closed_at"]      = ahora
                p["closed_by"]      = str(interaction.user)
                p["delivery_notes"] = notas
                self._pedido        = p
                break
        _save(data)

        # DM al usuario
        try:
            user = await self._cog.bot.fetch_user(int(self._pedido["user_id"]))
            desc = (
                f"¡Hola {user.mention}! Tu pedido de decoración ya fue completado. 🎉\n\n"
                f"🪑 **Decoraciones entregadas:**\n"
                + "\n".join(f"• {i}" for i in self._pedido["items"])
                + f"\n\n🛡️ **Entregado por:** {interaction.user}\n"
                f"📅 **Fecha:** {ahora}"
            )
            if notas:
                desc += f"\n\n📝 **Detalles de entrega:** {notas}"

            dm_embed = discord.Embed(
                title=f"✅ ¡Tu pedido #{self._pedido['id']} fue entregado!",
                description=desc,
                color=0x00CC66,
            )
            dm_embed.set_footer(text="Miner7days • Decoración")
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"[decoracion] No se pudo enviar DM de entrega: {e}")

        await interaction.response.send_message(
            f"✅ Pedido `#{self._pedido['id']}` marcado como **entregado**. "
            "El usuario fue notificado por DM.",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[decoracion] EntregaModal error: {error}")
        try:
            await interaction.followup.send(
                "❌ Ocurrió un error al confirmar la entrega. Intenta de nuevo.",
                ephemeral=True,
            )
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
# VIEW — Botones de acción sobre un pedido  (mods)
#   • en_revision  →  Aprobar / Rechazar
#   • pendiente    →  Entregar (modal) / Rechazar
# ═════════════════════════════════════════════════════════════════════
class PedidoActionView(View):
    def __init__(self, cog: "DecoracionCog", pedido: dict):
        super().__init__(timeout=None)
        self._cog    = cog
        self._pedido = pedido

        if pedido["status"] == "en_revision":
            btn_aprobar = discord.ui.Button(
                label="✅ Aprobar pedido",
                style=discord.ButtonStyle.success,
                row=0,
            )
            btn_aprobar.callback = self._aprobar
            self.add_item(btn_aprobar)

            btn_rechazar = discord.ui.Button(
                label="❌ Rechazar",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            btn_rechazar.callback = self._rechazar
            self.add_item(btn_rechazar)

        elif pedido["status"] == "pendiente":
            btn_entregar = discord.ui.Button(
                label="📦 Marcar como entregado",
                style=discord.ButtonStyle.success,
                row=0,
            )
            btn_entregar.callback = self._entregar
            self.add_item(btn_entregar)

            btn_rechazar = discord.ui.Button(
                label="❌ Rechazar",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            btn_rechazar.callback = self._rechazar
            self.add_item(btn_rechazar)

    # ── Aprobar (en_revision → pendiente) ──────────────────────────
    async def _aprobar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()

        data   = _load()
        pedido = next((p for p in data["pedidos"] if p["id"] == self._pedido["id"]), None)
        if not pedido or pedido["status"] != "en_revision":
            return await interaction.response.send_message(
                "⚠️ Este pedido ya no está en revisión.", ephemeral=True
            )

        ahora              = _now()
        pedido["status"]      = "pendiente"
        pedido["approved_at"] = ahora
        pedido["approved_by"] = str(interaction.user)
        _save(data)
        self._pedido = pedido

        # DM al usuario
        try:
            user     = await self._cog.bot.fetch_user(int(pedido["user_id"]))
            dm_embed = discord.Embed(
                title=f"✅ ¡Tu pedido #{pedido['id']} fue aprobado!",
                description=(
                    f"¡Hola {user.mention}! Tu pedido de decoración ha sido **aprobado**. 🎉\n\n"
                    f"🪑 **Decoraciones pedidas:**\n"
                    + "\n".join(f"• {i}" for i in pedido["items"])
                    + f"\n\n📦 La entrega está **pendiente**. Un moderador lo llevará cuando pueda.\n"
                    f"🛡️ **Aprobado por:** {interaction.user}\n"
                    f"📅 **Fecha:** {ahora}\n\n"
                    "¡Ten paciencia! 🙏"
                ),
                color=0x00CC66,
            )
            dm_embed.set_footer(text="Miner7days • Decoración")
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"[decoracion] No se pudo enviar DM de aprobación: {e}")

        await interaction.response.send_message(
            f"✅ Pedido `#{pedido['id']}` **aprobado** — ahora está pendiente de entrega. "
            "El usuario fue notificado por DM.",
            ephemeral=True,
        )

    # ── Entregar (pendiente → finalizado, abre modal con notas) ────
    async def _entregar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()

        data   = _load()
        pedido = next((p for p in data["pedidos"] if p["id"] == self._pedido["id"]), None)
        if not pedido or pedido["status"] != "pendiente":
            return await interaction.response.send_message(
                "⚠️ Este pedido ya no está pendiente.", ephemeral=True
            )

        await interaction.response.send_modal(
            EntregaModal(self._cog, pedido, interaction.user)
        )

    # ── Rechazar (en_revision o pendiente → rechazado) ─────────────
    async def _rechazar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()

        data   = _load()
        pedido = next((p for p in data["pedidos"] if p["id"] == self._pedido["id"]), None)
        if not pedido or pedido["status"] not in ("en_revision", "pendiente"):
            return await interaction.response.send_message(
                "⚠️ Este pedido no puede rechazarse en su estado actual.", ephemeral=True
            )

        await interaction.response.send_modal(RechazoModal(self._cog, pedido))


# ═════════════════════════════════════════════════════════════════════
# VIEW — Botón Revalidar  (solo rechazados, desde historial)
# ═════════════════════════════════════════════════════════════════════
class RevalidarView(View):
    def __init__(self, cog: "DecoracionCog", pedido: dict):
        super().__init__(timeout=None)
        self._cog    = cog
        self._pedido = pedido

    @discord.ui.button(label="🔄 Revalidar pedido", style=discord.ButtonStyle.blurple)
    async def btn_revalidar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()

        data   = _load()
        pedido = next((p for p in data["pedidos"] if p["id"] == self._pedido["id"]), None)
        if not pedido or pedido["status"] != "rechazado":
            return await interaction.response.send_message(
                "⚠️ Este pedido ya no está rechazado.", ephemeral=True
            )

        await interaction.response.send_modal(RevalidarModal(self._cog, pedido))


# ═════════════════════════════════════════════════════════════════════
# SELECT — Pedidos activos (en_revision + pendientes), paginado
# ═════════════════════════════════════════════════════════════════════
class PedidoSelect(discord.ui.Select):
    def __init__(self, cog: "DecoracionCog", pedidos: list, total: int, page: int):
        self._cog   = cog
        self._total = total
        self._map   = {str(p["id"]): p for p in pedidos}

        options = []
        for p in pedidos:
            preview = ", ".join(p["items"][:2])
            if len(p["items"]) > 2:
                preview += f" +{len(p['items']) - 2} más"

            if p["status"] == "en_revision":
                emoji   = "🔵"
                tag     = " [Revisión]"
            elif p.get("revalidado"):
                emoji   = "🔄"
                tag     = " [Revalidado]"
            else:
                emoji   = "🟠"
                tag     = " [Pendiente]"

            options.append(discord.SelectOption(
                label=f"#{p['id']}{tag} — {p['ingame_name'][:22]}",
                description=f"🪑 {preview[:50]} • {p['created_at']}",
                value=str(p["id"]),
                emoji=emoji,
            ))

        super().__init__(
            placeholder=f"📦 Página {page + 1} — Selecciona un pedido…",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()
        pedido = self._map.get(self.values[0])
        if not pedido:
            return await interaction.response.send_message(
                "❌ Pedido no encontrado.", ephemeral=True
            )
        embed = _pedido_embed(pedido, self._total)
        view  = PedidoActionView(self._cog, pedido)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ═════════════════════════════════════════════════════════════════════
# SELECT — Historial (finalizados + rechazados)
# ═════════════════════════════════════════════════════════════════════
class HistorialSelect(discord.ui.Select):
    def __init__(self, cog: "DecoracionCog", pedidos: list, total: int):
        self._cog   = cog
        self._total = total
        self._map   = {str(p["id"]): p for p in pedidos}

        options = []
        for p in pedidos:
            preview = ", ".join(p["items"][:2])
            if len(p["items"]) > 2:
                preview += f" +{len(p['items']) - 2} más"
            emoji  = "✅" if p["status"] == "finalizado" else "❌"
            estado = "Finalizado" if p["status"] == "finalizado" else "Rechazado"
            options.append(discord.SelectOption(
                label=f"#{p['id']} [{estado}] — {p['ingame_name'][:20]}",
                description=f"🪑 {preview[:50]} • {p.get('closed_at', p['created_at'])[:10]}",
                value=str(p["id"]),
                emoji=emoji,
            ))

        super().__init__(
            placeholder="📋 Selecciona un pedido del historial…",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()
        pedido = self._map.get(self.values[0])
        if not pedido:
            return await interaction.response.send_message(
                "❌ Pedido no encontrado.", ephemeral=True
            )

        embed = _pedido_embed(pedido, self._total)
        # Solo rechazados tienen botón de revalidar
        view = RevalidarView(self._cog, pedido) if pedido["status"] == "rechazado" else None

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ═════════════════════════════════════════════════════════════════════
# VIEW — Panel historial  (ephemeral, sin timeout)
# ═════════════════════════════════════════════════════════════════════
class HistorialView(View):
    def __init__(self, cog: "DecoracionCog"):
        super().__init__(timeout=None)
        self._cog = cog

        data     = _load()
        todos    = data["pedidos"]
        total    = len(todos)
        cerrados = [p for p in todos if p["status"] in ("finalizado", "rechazado")]

        if cerrados:
            # Máximo 25 opciones (límite Discord), los más recientes primero
            recientes = sorted(
                cerrados,
                key=lambda x: x.get("closed_at") or x["created_at"],
                reverse=True,
            )[:25]
            self.add_item(HistorialSelect(cog, recientes, total))
        else:
            dummy = discord.ui.Select(
                placeholder="📋 No hay pedidos en el historial aún…",
                options=[discord.SelectOption(label="—", value="none")],
                disabled=True,
                row=0,
            )
            self.add_item(dummy)


# ═════════════════════════════════════════════════════════════════════
# VIEW — Panel admin !deco  (sin timeout, paginación en ≥15 activos)
# ═════════════════════════════════════════════════════════════════════
class DecoAdminView(View):
    def __init__(self, cog: "DecoracionCog", activos: list, total: int, page: int = 0):
        super().__init__(timeout=None)
        self._cog     = cog
        self._activos = activos   # en_revision + pendiente
        self._total   = total
        self._page    = page
        self._pages   = max(1, (len(activos) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._build()

    def _build(self):
        self.clear_items()

        # ── Row 0: Select de pedidos activos ──
        start = self._page * _PAGE_SIZE
        chunk = self._activos[start : start + _PAGE_SIZE]
        if chunk:
            self.add_item(PedidoSelect(self._cog, chunk, self._total, self._page))

        # ── Row 1: Botón fijo "📋 Ver historial" ──
        btn_hist = discord.ui.Button(
            label="📋 Ver historial",
            style=discord.ButtonStyle.secondary,
            emoji="📂",
            row=1,
        )
        btn_hist.callback = self._ver_historial
        self.add_item(btn_hist)

        # ── Row 2: Paginación (solo si ≥15 activos) ──
        if len(self._activos) >= 15:
            prev = discord.ui.Button(
                label="◀ Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=(self._page == 0),
                row=2,
            )
            prev.callback = self._prev
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self._page + 1} / {self._pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=2,
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self._page >= self._pages - 1),
                row=2,
            )
            nxt.callback = self._next
            self.add_item(nxt)

    async def _ver_historial(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()

        data        = _load()
        todos       = data["pedidos"]
        finalizados = [p for p in todos if p["status"] == "finalizado"]
        rechazados  = [p for p in todos if p["status"] == "rechazado"]

        embed = discord.Embed(title="📋 Historial de Pedidos", color=0x5865F2)
        embed.add_field(
            name="📊 Resumen",
            value=(
                f"✅ **Finalizados:** {len(finalizados)}\n"
                f"❌ **Rechazados:** {len(rechazados)}\n"
                f"📦 **Total historial:** {len(finalizados) + len(rechazados)}"
            ),
            inline=False,
        )
        embed.add_field(
            name="ℹ️ Nota",
            value=(
                "Solo los pedidos **rechazados** tienen opción de **🔄 Revalidar**.\n"
                "Se muestran los **25 más recientes**."
            ),
            inline=False,
        )
        embed.set_footer(text="Miner7days • Decoración • Historial")

        await interaction.response.send_message(
            embed=embed,
            view=HistorialView(self._cog),
            ephemeral=True,
        )

    def _make_summary_embed(self) -> discord.Embed:
        data        = _load()
        todos       = data["pedidos"]
        en_revision = [p for p in todos if p["status"] == "en_revision"]
        pendientes  = [p for p in todos if p["status"] == "pendiente"]
        finalizados = [p for p in todos if p["status"] == "finalizado"]
        rechazados  = [p for p in todos if p["status"] == "rechazado"]

        embed = discord.Embed(title="🪑 Panel de Pedidos de Decoración", color=0x8B0000)
        embed.add_field(
            name="📊 Resumen",
            value=(
                f"🔵 **En revisión:** {len(en_revision)}\n"
                f"🟠 **Pendiente entrega:** {len(pendientes)}\n"
                f"✅ **Finalizados:** {len(finalizados)}\n"
                f"❌ **Rechazados:** {len(rechazados)}\n"
                f"📦 **Total:** {len(todos)}"
            ),
            inline=False,
        )
        if self._activos:
            embed.add_field(
                name="ℹ️ Instrucciones",
                value=(
                    f"Página **{self._page + 1}** de **{self._pages}**. "
                    "🔵 = Por revisar / 🟠 = Por entregar. "
                    "Selecciona un pedido del menú para gestionarlo."
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="✅ Sin pedidos activos",
                value=(
                    "No hay pedidos pendientes de revisión ni de entrega.\n"
                    "Usa **📋 Ver historial** para ver finalizados y rechazados."
                ),
                inline=False,
            )
        embed.set_footer(text=f"Miner7days • Decoración  |  Total: {len(todos)} pedido(s)")
        return embed

    async def _prev(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()
        self._page -= 1
        self._build()
        await interaction.response.edit_message(embed=self._make_summary_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            return await interaction.response.defer()
        self._page += 1
        self._build()
        await interaction.response.edit_message(embed=self._make_summary_embed(), view=self)


# ═════════════════════════════════════════════════════════════════════
# SELECT — Lista de pedidos del usuario  (!decolist en MD)
# ═════════════════════════════════════════════════════════════════════
_DECO_STATUS_EMOJI = {
    "en_revision": "🔵",
    "pendiente":   "🟠",
    "finalizado":  "✅",
    "rechazado":   "❌",
}
_DECO_STATUS_LABEL = {
    "en_revision": "En revisión",
    "pendiente":   "Pendiente",
    "finalizado":  "Entregado",
    "rechazado":   "Rechazado",
}

class DecoListSelect(discord.ui.Select):
    def __init__(self, cog: "DecoracionCog", chunk: list, total_global: int, page: int):
        self._cog          = cog
        self._total_global = total_global
        self._map          = {str(p["id"]): p for p in chunk}

        options = []
        for p in chunk:
            emoji   = _DECO_STATUS_EMOJI.get(p["status"], "❓")
            estado  = _DECO_STATUS_LABEL.get(p["status"], p["status"])
            preview = ", ".join(p["items"][:2])
            if len(p["items"]) > 2:
                preview += f" +{len(p['items']) - 2} más"
            options.append(discord.SelectOption(
                label=f"#{p['id']} [{estado}] — {p['ingame_name'][:20]}",
                description=f"🪑 {preview[:50]} • {p['created_at']}",
                value=str(p["id"]),
                emoji=emoji,
            ))

        super().__init__(
            placeholder=f"📦 Página {page + 1} — Selecciona un pedido para ver detalles…",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        pedido = self._map.get(self.values[0])
        if not pedido:
            return await interaction.response.send_message(
                "❌ Pedido no encontrado.", ephemeral=True
            )
        embed = _pedido_embed(pedido, self._total_global)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═════════════════════════════════════════════════════════════════════
# VIEW — Panel de pedidos del usuario  (!decolist en MD)  — paginado
# ═════════════════════════════════════════════════════════════════════
class DecoListView(View):
    def __init__(self, cog: "DecoracionCog", pedidos: list, page: int = 0):
        super().__init__(timeout=None)
        self._cog    = cog
        # Ordenados más recientes primero
        self._pedidos = sorted(pedidos, key=lambda p: p["created_at"], reverse=True)
        self._total   = len(self._pedidos)
        self._page    = page
        self._pages   = max(1, (self._total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._build()

    def _build(self):
        self.clear_items()

        # ── Row 0: Select del chunk actual ──
        start = self._page * _PAGE_SIZE
        chunk = self._pedidos[start : start + _PAGE_SIZE]
        if chunk:
            self.add_item(DecoListSelect(self._cog, chunk, self._total, self._page))

        # ── Row 1: Paginación (siempre visible si hay más de una página) ──
        if self._pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=(self._page == 0),
                row=1,
            )
            prev.callback = self._prev
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self._page + 1} / {self._pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=1,
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self._page >= self._pages - 1),
                row=1,
            )
            nxt.callback = self._next
            self.add_item(nxt)

    def _make_embed(self) -> discord.Embed:
        en_revision = sum(1 for p in self._pedidos if p["status"] == "en_revision")
        pendientes  = sum(1 for p in self._pedidos if p["status"] == "pendiente")
        finalizados = sum(1 for p in self._pedidos if p["status"] == "finalizado")
        rechazados  = sum(1 for p in self._pedidos if p["status"] == "rechazado")

        inicio = self._page * _PAGE_SIZE + 1
        fin    = min(inicio + _PAGE_SIZE - 1, self._total)

        embed = discord.Embed(
            title="📦 Mis pedidos de decoración",
            color=0x5865F2,
        )
        embed.add_field(
            name="📊 Resumen",
            value=(
                f"🔵 **En revisión:** {en_revision}\n"
                f"🟠 **Pendiente de entrega:** {pendientes}\n"
                f"✅ **Entregados:** {finalizados}\n"
                f"❌ **Rechazados:** {rechazados}\n"
                f"📦 **Total:** {self._total}"
            ),
            inline=False,
        )
        embed.add_field(
            name="ℹ️ Cómo ver un pedido",
            value="Selecciona un pedido del menú de abajo para ver todos sus detalles.",
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Miner7days • Decoración  |  "
                f"Mostrando {inicio}–{fin} de {self._total}  •  "
                f"Página {self._page + 1} de {self._pages}"
            )
        )
        return embed

    async def _prev(self, interaction: discord.Interaction):
        self._page -= 1
        self._build()
        await interaction.response.edit_message(embed=self._make_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self._page += 1
        self._build()
        await interaction.response.edit_message(embed=self._make_embed(), view=self)


# ═════════════════════════════════════════════════════════════════════
# COG PRINCIPAL
# ═════════════════════════════════════════════════════════════════════
class DecoracionCog(commands.Cog, name="Decoracion"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── !decoracion ───────────────────────────────────────────────────
    @commands.command(name="decoracion")
    async def cmd_decoracion(self, ctx: commands.Context):
        """Muestra el panel público para hacer pedidos de decoración."""
        try:
            await ctx.message.delete()
        except Exception:
            pass

        embed = discord.Embed(
            title="🪑 Pedidos de Decoración",
            description=(
                "¿Quieres decorar tu base o zona?\n\n"
                "Pulsa el botón para hacer tu pedido. Necesitarás:\n\n"
                "🎮 **Tu nombre en 7 Days to Die**\n"
                "🪑 **Lista de decoraciones** — con guión antes de cada una:\n"
                "```\n-Lámpara de techo\n-Silla de madera\n```"
                "🖼️ **Imágenes de referencia** — opcional, máximo 4\n\n"
                "Un moderador lo revisará y aprobará cuando pueda. ¡Ten paciencia! 🙏\n\n"
                "📬 Usa `!decolist` en **MD** para ver el estado de tus pedidos."
            ),
            color=0x8B0000,
        )
        embed.set_footer(text="Miner7days • Decoración")
        await ctx.send(embed=embed, view=DecoPublicView(self))

    # ── !decolist  (solo en MD) ───────────────────────────────────────
    @commands.command(name="decolist")
    async def cmd_decolist(self, ctx: commands.Context):
        """Muestra tus pedidos de decoración con su estado (solo en MD)."""
        # Rechazar si no es DM
        if not isinstance(ctx.channel, discord.DMChannel):
            try:
                await ctx.message.delete()
            except Exception:
                pass
            await ctx.send(
                "❌ Este comando solo puede usarse en **MD** (mensaje directo).\n"
                "Escríbeme en privado y usa `!decolist` allí.",
                delete_after=8,
            )
            return

        data         = _load()
        mis_pedidos  = [p for p in data["pedidos"] if p["user_id"] == str(ctx.author.id)]

        if not mis_pedidos:
            embed = discord.Embed(
                title="📦 Mis pedidos de decoración",
                description=(
                    "No tienes ningún pedido registrado todavía.\n\n"
                    "Ve al servidor y usa el botón de `!decoracion` para hacer uno. 🙏"
                ),
                color=0x5865F2,
            )
            embed.set_footer(text="Miner7days • Decoración")
            return await ctx.send(embed=embed)

        view  = DecoListView(self, mis_pedidos)
        embed = view._make_embed()
        await ctx.send(embed=embed, view=view)

    # ── !deco ─────────────────────────────────────────────────────────
    @commands.command(name="deco")
    async def cmd_deco(self, ctx: commands.Context):
        """Panel de gestión de pedidos de decoración (solo mods)."""
        if not _es_mod(ctx.author):
            return

        data        = _load()
        todos       = data["pedidos"]
        en_revision = [p for p in todos if p["status"] == "en_revision"]
        pendientes  = [p for p in todos if p["status"] == "pendiente"]
        finalizados = [p for p in todos if p["status"] == "finalizado"]
        rechazados  = [p for p in todos if p["status"] == "rechazado"]

        # Pedidos activos = en_revision + pendientes (ordenados: primero en_revision, luego pendientes)
        activos = en_revision + pendientes

        embed = discord.Embed(title="🪑 Panel de Pedidos de Decoración", color=0x8B0000)
        embed.add_field(
            name="📊 Resumen",
            value=(
                f"🔵 **En revisión:** {len(en_revision)}\n"
                f"🟠 **Pendiente entrega:** {len(pendientes)}\n"
                f"✅ **Finalizados:** {len(finalizados)}\n"
                f"❌ **Rechazados:** {len(rechazados)}\n"
                f"📦 **Total:** {len(todos)}"
            ),
            inline=False,
        )
        if activos:
            embed.add_field(
                name="ℹ️ Instrucciones",
                value=(
                    f"Hay **{len(en_revision)}** pedido(s) por revisar y "
                    f"**{len(pendientes)}** pendiente(s) de entrega. "
                    "Selecciona uno del menú para gestionarlo. "
                    "Usa **📋 Ver historial** para finalizados y rechazados."
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="✅ Sin pedidos activos",
                value=(
                    "No hay pedidos pendientes de revisión ni de entrega.\n"
                    "Usa **📋 Ver historial** para ver finalizados y rechazados."
                ),
                inline=False,
            )
        embed.set_footer(text=f"Miner7days • Decoración  |  Total: {len(todos)} pedido(s)")

        view = DecoAdminView(self, activos, len(todos))
        await ctx.send(embed=embed, view=view)


# ═════════════════════════════════════════════════════════════════════
# SETUP
# ═════════════════════════════════════════════════════════════════════
async def setup(bot: commands.Bot):
    await bot.add_cog(DecoracionCog(bot))