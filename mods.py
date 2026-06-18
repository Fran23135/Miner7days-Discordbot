# ══════════════════════════════════════════════════════════════════════
#  mods.py  — Cog de gestión e información de Mods del servidor
#  Comandos:
#    !mods   → Público. Embed con dropdown paginado + botón de descarga.
#    !modsG  → Solo Owner/Mods. Panel completo de gestión (CRUD).
#  Fuente de datos: Cache/Gmods.json
# ══════════════════════════════════════════════════════════════════════

import discord
from discord.ext import commands
import json
import os
from config import ROLES
# ─────────────────────────────────────────────────────────────────────
#  Rutas y constantes
# ─────────────────────────────────────────────────────────────────────
# __file__ apunta al propio mods.py; con abspath + dirname obtenemos
# siempre el directorio real del proyecto, funcione en Linux o Windows.
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(BASE_DIR, "Cache")
GMODS_PATH = os.path.join(CACHE_DIR, "Gmods.json")
PAGE_SIZE  = 15   # máximo de mods por página del dropdown

_EMPTY: dict = {"mods": [], "links_descarga": []}


# ══════════════════════════════════════════════════════════════════════
#  Helpers JSON
# ══════════════════════════════════════════════════════════════════════

def _ensure_file() -> None:
    """Crea Cache/Gmods.json con estructura vacía si todavía no existe."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.isfile(GMODS_PATH):
        with open(GMODS_PATH, "w", encoding="utf-8") as f:
            json.dump(_EMPTY, f, ensure_ascii=False, indent=2)
        print(f"[mods] Gmods.json creado en {GMODS_PATH}")


def _load() -> dict:
    """
    Lee Gmods.json y devuelve su contenido.
    Si el archivo no existe lo crea primero (solo cuando se usa un comando).
    Si el JSON está corrupto lo reinicia y avisa por consola.
    """
    _ensure_file()
    try:
        with open(GMODS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Garantizar que ambas claves existen aunque el JSON sea antiguo
        data.setdefault("mods", [])
        data.setdefault("links_descarga", [])
        return data
    except json.JSONDecodeError:
        print(f"[mods] ⚠️ Gmods.json corrupto, reiniciando con estructura vacía.")
        _save(dict(_EMPTY))
        return dict(_EMPTY)


def _save(data: dict) -> None:
    """
    Escribe data en Cache/Gmods.json.
    Crea la carpeta Cache si no existiera (por si se borra manualmente).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(GMODS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _es_staff(member: discord.Member) -> bool:
    """True si el miembro es owner del servidor o tiene rol de Mod/Admin."""
    if member.guild and member.id == member.guild.owner_id:
        return True
    ids = {r.id for r in member.roles}
    return bool(ids & set(ROLES.values()))


async def _check_staff(interaction: discord.Interaction) -> bool:
    """
    Verifica en cada interacción de gestión si el usuario sigue siendo staff.
    Responde con mensaje efímero de error si no lo es.
    Retorna True si puede continuar, False si debe detenerse.
    """
    if not _es_staff(interaction.user):
        await interaction.response.send_message(
            "🚫 No tienes permisos para usar este panel. Solo Moderadores y Admins.",
            ephemeral=True,
        )
        return False
    return True


# ══════════════════════════════════════════════════════════════════════
#  ── EMBEDS BASE ──────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def _embed_mods_publico(page: int = 0) -> discord.Embed:
    data   = _load()
    mods   = data.get("mods", [])
    total  = len(mods)
    pages  = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page   = max(0, min(page, pages - 1))

    embed = discord.Embed(
        title="🧱 Mods del Servidor",
        description=(
            "Bienvenido a la sección de **Mods del servidor** de 7 Days to Die.\n\n"
            "🔽 Selecciona un mod en la lista para ver su descripción y página oficial.\n"
            "📥 Pulsa **Descargar Mods** para obtener los links de descarga directos."
        ),
        color=0x8B0000,
    )
    if total == 0:
        embed.add_field(
            name="ℹ️ Sin mods registrados",
            value="Aún no hay mods en la lista. ¡Vuelve pronto!",
            inline=False,
        )
    else:
        embed.set_footer(text=f"Página {page + 1}/{pages} • {total} mod(s) registrado(s)")
    return embed


def _embed_modsg(page: int = 0) -> discord.Embed:
    data  = _load()
    total = len(data.get("mods", []))
    links = len(data.get("links_descarga", []))
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page  = max(0, min(page, pages - 1))

    embed = discord.Embed(
        title="🧱 Gestión de Mods",
        description=(
            "Panel de administración del sistema de mods del servidor.\n\n"
            "➕ **Añadir Mod** — Registra un nuevo mod en la lista.\n"
            "🔗 **Links de Descarga** — Añade, edita o elimina links de descarga.\n"
            "📋 **Lista de Mods** — Selecciona un mod para editar o eliminar."
        ),
        color=0x8B0000,
    )
    embed.add_field(name="📦 Mods registrados",   value=f"**{total}**", inline=True)
    embed.add_field(name="🔗 Links de descarga",  value=f"**{links}**", inline=True)
    if total > 0:
        embed.set_footer(text=f"Página {page + 1}/{pages} • {total} mod(s)")
    return embed


# ══════════════════════════════════════════════════════════════════════
#  ── MODALS ───────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

class ModalAddMod(discord.ui.Modal, title="🧱 Añadir Mod"):
    nombre = discord.ui.TextInput(
        label="Nombre del Mod",
        placeholder="Ej: BdubsVehicles",
        max_length=80,
    )
    descripcion = discord.ui.TextInput(
        label="Descripción corta",
        placeholder="Ej: Más diseños de vehículos para el servidor.",
        max_length=200,
        style=discord.TextStyle.paragraph,
    )
    link = discord.ui.TextInput(
        label="Link oficial del mod",
        placeholder="https://...",
        max_length=250,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        data = _load()
        data["mods"].append({
            "nombre":      self.nombre.value.strip(),
            "descripcion": self.descripcion.value.strip(),
            "link":        self.link.value.strip(),
        })
        _save(data)
        await interaction.response.send_message(
            f"✅ Mod **🧱 {self.nombre.value.strip()}** añadido correctamente a la lista.",
            ephemeral=True,
        )


class ModalEditMod(discord.ui.Modal):
    def __init__(self, index: int):
        data = _load()
        m    = data["mods"][index]
        super().__init__(title=f"🧱 Editar Mod")
        self._index = index

        self.nombre = discord.ui.TextInput(
            label="Nombre del Mod",
            default=m["nombre"],
            max_length=80,
        )
        self.descripcion = discord.ui.TextInput(
            label="Descripción corta",
            default=m["descripcion"],
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.link = discord.ui.TextInput(
            label="Link oficial del mod",
            default=m["link"],
            max_length=250,
        )
        self.add_item(self.nombre)
        self.add_item(self.descripcion)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["mods"]):
            await interaction.response.send_message("❌ Mod no encontrado.", ephemeral=True)
            return
        data["mods"][self._index] = {
            "nombre":      self.nombre.value.strip(),
            "descripcion": self.descripcion.value.strip(),
            "link":        self.link.value.strip(),
        }
        _save(data)
        await interaction.response.send_message(
            f"✅ Mod **🧱 {self.nombre.value.strip()}** actualizado correctamente.",
            ephemeral=True,
        )


class ModalAddLink(discord.ui.Modal, title="🧱 Añadir Link de Descarga"):
    descripcion = discord.ui.TextInput(
        label="Descripción del link",
        placeholder="Ej: Pack completo de mods del servidor",
        max_length=100,
    )
    url = discord.ui.TextInput(
        label="URL de descarga",
        placeholder="https://...",
        max_length=250,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        data = _load()
        data["links_descarga"].append({
            "descripcion": self.descripcion.value.strip(),
            "url":         self.url.value.strip(),
        })
        _save(data)
        await interaction.response.send_message(
            f"✅ Link **🧱 {self.descripcion.value.strip()}** añadido correctamente.",
            ephemeral=True,
        )


class ModalEditLink(discord.ui.Modal):
    def __init__(self, index: int):
        data = _load()
        lnk  = data["links_descarga"][index]
        super().__init__(title=f"🧱 Editar Link")
        self._index = index

        self.descripcion = discord.ui.TextInput(
            label="Descripción del link",
            default=lnk["descripcion"],
            max_length=100,
        )
        self.url = discord.ui.TextInput(
            label="URL de descarga",
            default=lnk["url"],
            max_length=250,
        )
        self.add_item(self.descripcion)
        self.add_item(self.url)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["links_descarga"]):
            await interaction.response.send_message("❌ Link no encontrado.", ephemeral=True)
            return
        data["links_descarga"][self._index] = {
            "descripcion": self.descripcion.value.strip(),
            "url":         self.url.value.strip(),
        }
        _save(data)
        await interaction.response.send_message(
            "✅ Link actualizado correctamente.", ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════
#  ── VIEWS DE CONFIRMACIÓN DE BORRADO ─────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

class ConfirmDeleteMod(discord.ui.View):
    def __init__(self, index: int, nombre: str):
        super().__init__(timeout=None)   # sin timeout
        self._index  = index
        self._nombre = nombre

    @discord.ui.button(label="Sí, eliminar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["mods"]):
            await interaction.response.edit_message(
                content="⚠️ El mod ya no existe en la lista.", embed=None, view=None)
            return
        data["mods"].pop(self._index)
        _save(data)
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Mod **🧱 {self._nombre}** eliminado correctamente.",
            embed=None, view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        self.stop()
        await interaction.response.edit_message(
            content="↩️ Eliminación cancelada.", embed=None, view=None)


class ConfirmDeleteLink(discord.ui.View):
    def __init__(self, index: int, desc: str):
        super().__init__(timeout=None)   # sin timeout
        self._index = index
        self._desc  = desc

    @discord.ui.button(label="Sí, eliminar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["links_descarga"]):
            await interaction.response.edit_message(
                content="⚠️ El link ya no existe.", embed=None, view=None)
            return
        data["links_descarga"].pop(self._index)
        _save(data)
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Link **🧱 {self._desc}** eliminado correctamente.",
            embed=None, view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        self.stop()
        await interaction.response.edit_message(
            content="↩️ Eliminación cancelada.", embed=None, view=None)


# ══════════════════════════════════════════════════════════════════════
#  ── VIEWS DE GESTIÓN (ephemeral) ─────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

class ManageModView(discord.ui.View):
    """Embed efímero con botones Editar / Eliminar para un mod concreto."""

    def __init__(self, index: int):
        super().__init__(timeout=None)   # sin timeout
        self._index = index

    @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary)
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["mods"]):
            await interaction.response.send_message("❌ Mod no encontrado.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalEditMod(self._index))

    @discord.ui.button(label="🗑️ Eliminar", style=discord.ButtonStyle.danger)
    async def eliminar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["mods"]):
            await interaction.response.send_message("❌ Mod no encontrado.", ephemeral=True)
            return
        nombre = data["mods"][self._index]["nombre"]
        embed  = discord.Embed(
            title="⚠️ Confirmar eliminación",
            description=f"¿Estás seguro de que quieres eliminar el mod **🧱 {nombre}**?\n\nEsta acción no se puede deshacer.",
            color=0xFF4444,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmDeleteMod(self._index, nombre),
            ephemeral=True,
        )


class ManageLinkView(discord.ui.View):
    """Embed efímero con botones Editar / Eliminar para un link de descarga."""

    def __init__(self, index: int):
        super().__init__(timeout=None)   # sin timeout
        self._index = index

    @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary)
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["links_descarga"]):
            await interaction.response.send_message("❌ Link no encontrado.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalEditLink(self._index))

    @discord.ui.button(label="🗑️ Eliminar", style=discord.ButtonStyle.danger)
    async def eliminar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _check_staff(interaction):
            return
        data = _load()
        if self._index >= len(data["links_descarga"]):
            await interaction.response.send_message("❌ Link no encontrado.", ephemeral=True)
            return
        desc  = data["links_descarga"][self._index]["descripcion"]
        embed = discord.Embed(
            title="⚠️ Confirmar eliminación",
            description=f"¿Estás seguro de que quieres eliminar el link **🧱 {desc}**?\n\nEsta acción no se puede deshacer.",
            color=0xFF4444,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmDeleteLink(self._index, desc),
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════
#  ── VISTA GESTIÓN DE LINKS (ephemeral desde !modsG) ──────────────────
# ══════════════════════════════════════════════════════════════════════

class LinksGestView(discord.ui.View):
    """
    Embed efímero con:
      • Botón ➕ Añadir Link
      • Dropdown con todos los links registrados → ManageLinkView
    """

    def __init__(self):
        super().__init__(timeout=None)   # sin timeout
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        data  = _load()
        links = data.get("links_descarga", [])

        # ── Botón añadir ──────────────────────────────────────────
        btn_add = discord.ui.Button(
            label="➕ Añadir Link",
            style=discord.ButtonStyle.success,
            emoji="🔗",
            row=0,
        )
        btn_add.callback = self._add_cb
        self.add_item(btn_add)

        if not links:
            return

        # ── Dropdown con los links (máx 25 en un Select) ──────────
        options = [
            discord.SelectOption(
                label=f"🧱 {lnk['descripcion']}"[:100],
                value=str(i),
                description=lnk["url"][:100],
            )
            for i, lnk in enumerate(links[:25])
        ]
        sel = discord.ui.Select(
            placeholder="🔍 Selecciona un link para gestionar...",
            options=options,
            row=1,
        )
        sel.callback = self._select_cb
        self.add_item(sel)

    async def _add_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        await interaction.response.send_modal(ModalAddLink())

    async def _select_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        index = int(interaction.data["values"][0])
        data  = _load()
        links = data.get("links_descarga", [])
        if index >= len(links):
            await interaction.response.send_message("❌ Link no encontrado.", ephemeral=True)
            return
        lnk   = links[index]
        embed = discord.Embed(
            title=f"🧱 {lnk['descripcion']}",
            color=0x8B0000,
        )
        embed.add_field(name="🔗 URL de descarga", value=lnk["url"], inline=False)
        embed.set_footer(text="Gestión de Links • Usa los botones para editar o eliminar")
        await interaction.response.send_message(
            embed=embed,
            view=ManageLinkView(index),
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════════
#  ── VISTA PRINCIPAL  !mods  (PÚBLICO) ───────────────────────────────
# ══════════════════════════════════════════════════════════════════════

class ModsPublicView(discord.ui.View):
    """
    Vista del comando !mods:
      Row 0 → Dropdown paginado de mods (máx PAGE_SIZE por página)
      Row 1 → Botón 📥 Descargar Mods
      Row 2 → Botones de paginación (si hay > 1 página)
    No requiere verificación de permisos — es pública.
    """

    def __init__(self, page: int = 0):
        super().__init__(timeout=None)   # sin timeout
        self.page = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        data  = _load()
        mods  = data.get("mods", [])
        total = len(mods)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(self.page, pages - 1))
        start = self.page * PAGE_SIZE
        chunk = mods[start:start + PAGE_SIZE]

        # ── Row 0: Dropdown de mods ───────────────────────────────
        if chunk:
            options = [
                discord.SelectOption(
                    label=f"🧱 {m['nombre']}"[:100],
                    value=str(start + i),
                    description=m["descripcion"][:100],
                )
                for i, m in enumerate(chunk)
            ]
            sel = discord.ui.Select(
                placeholder="🔍 Selecciona un mod para ver más info...",
                options=options,
                row=0,
            )
            sel.callback = self._select_cb
            self.add_item(sel)

        # ── Row 1: Botón de descarga ───────────────────────────────
        btn_dl = discord.ui.Button(
            label="📥 Descargar Mods",
            style=discord.ButtonStyle.success,
            emoji="📦",
            row=1,
        )
        btn_dl.callback = self._descargar_cb
        self.add_item(btn_dl)

        # ── Row 2: Paginación ──────────────────────────────────────
        if pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0),
                row=2,
            )
            prev.callback = self._prev_cb
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=2,
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page >= pages - 1),
                row=2,
            )
            nxt.callback = self._next_cb
            self.add_item(nxt)

    # ── Callbacks (público, sin check de permisos) ────────────────────

    async def _select_cb(self, interaction: discord.Interaction):
        index = int(interaction.data["values"][0])
        data  = _load()
        mods  = data.get("mods", [])
        if index >= len(mods):
            await interaction.response.send_message("❌ Mod no encontrado.", ephemeral=True)
            return
        m     = mods[index]
        embed = discord.Embed(
            title=f"🧱 {m['nombre']}",
            color=0x8B0000,
        )
        embed.add_field(name="📖 Descripción",    value=m["descripcion"],            inline=False)
        embed.add_field(name="🔗 Página oficial", value=f"[Ver mod]({m['link']})",   inline=False)
        embed.set_footer(text="7 Days to Die • Usa el botón de descarga para obtenerlos")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _descargar_cb(self, interaction: discord.Interaction):
        data  = _load()
        links = data.get("links_descarga", [])
        if not links:
            await interaction.response.send_message(
                "❌ Aún no hay links de descarga disponibles. Contacta con un moderador.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="🧱 Links de Descarga de Mods",
            description="Aquí tienes los links disponibles para descargar los mods del servidor:",
            color=0x8B0000,
        )
        for lnk in links:
            embed.add_field(
                name=f"🧱 {lnk['descripcion']}",
                value=f"[📥 Descargar]({lnk['url']})",
                inline=False,
            )
        embed.set_footer(text="7 Days to Die • Instala los mods siguiendo la guía oficial")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _prev_cb(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        await interaction.response.edit_message(
            embed=_embed_mods_publico(self.page), view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        await interaction.response.edit_message(
            embed=_embed_mods_publico(self.page), view=self)


# ══════════════════════════════════════════════════════════════════════
#  ── VISTA PRINCIPAL  !modsG  (SOLO STAFF) ───────────────────────────
# ══════════════════════════════════════════════════════════════════════

class ModsGestView(discord.ui.View):
    """
    Vista del comando !modsG (solo Owner/Mods):
      Row 0 → Botón ➕ Añadir Mod  |  Botón 🔗 Links de Descarga
      Row 1 → Dropdown paginado de mods registrados
      Row 2 → Paginación (si hay > 1 página)
    Todos los callbacks verifican permisos en tiempo real con _check_staff.
    """

    def __init__(self, page: int = 0):
        super().__init__(timeout=None)   # sin timeout
        self.page = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        data  = _load()
        mods  = data.get("mods", [])
        total = len(mods)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(self.page, pages - 1))
        start = self.page * PAGE_SIZE
        chunk = mods[start:start + PAGE_SIZE]

        # ── Row 0: Botones de acción ──────────────────────────────
        btn_add = discord.ui.Button(
            label="➕ Añadir Mod",
            style=discord.ButtonStyle.success,
            emoji="🧱",
            row=0,
        )
        btn_add.callback = self._add_mod_cb
        self.add_item(btn_add)

        btn_links = discord.ui.Button(
            label="🔗 Links de Descarga",
            style=discord.ButtonStyle.primary,
            row=0,
        )
        btn_links.callback = self._links_cb
        self.add_item(btn_links)

        # ── Row 1: Dropdown de mods ───────────────────────────────
        if chunk:
            options = [
                discord.SelectOption(
                    label=f"🧱 {m['nombre']}"[:100],
                    value=str(start + i),
                    description=m["descripcion"][:100],
                )
                for i, m in enumerate(chunk)
            ]
            sel = discord.ui.Select(
                placeholder="🔍 Selecciona un mod para gestionar...",
                options=options,
                row=1,
            )
            sel.callback = self._select_mod_cb
            self.add_item(sel)

        # ── Row 2: Paginación ──────────────────────────────────────
        if pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0),
                row=2,
            )
            prev.callback = self._prev_cb
            self.add_item(prev)

            counter = discord.ui.Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=2,
            )
            self.add_item(counter)

            nxt = discord.ui.Button(
                label="Siguiente ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page >= pages - 1),
                row=2,
            )
            nxt.callback = self._next_cb
            self.add_item(nxt)

    # ── Callbacks ─────────────────────────────────────────────────────

    async def _add_mod_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        await interaction.response.send_modal(ModalAddMod())

    async def _links_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        data  = _load()
        links = data.get("links_descarga", [])
        embed = discord.Embed(
            title="🧱 Gestión de Links de Descarga",
            description=(
                f"Links de descarga registrados actualmente: **{len(links)}**\n\n"
                "Selecciona un link de la lista para editarlo o eliminarlo.\n"
                "Usa **➕ Añadir Link** para registrar un nuevo link de descarga."
            ),
            color=0x8B0000,
        )
        await interaction.response.send_message(
            embed=embed, view=LinksGestView(), ephemeral=True)

    async def _select_mod_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        index = int(interaction.data["values"][0])
        data  = _load()
        mods  = data.get("mods", [])
        if index >= len(mods):
            await interaction.response.send_message("❌ Mod no encontrado.", ephemeral=True)
            return
        m     = mods[index]
        embed = discord.Embed(
            title=f"🧱 {m['nombre']}",
            color=0x8B0000,
        )
        embed.add_field(name="📖 Descripción",  value=m["descripcion"],  inline=False)
        embed.add_field(name="🔗 Link oficial", value=m["link"],         inline=False)
        embed.set_footer(text="Gestión de Mods • Usa los botones para editar o eliminar")
        await interaction.response.send_message(
            embed=embed, view=ManageModView(index), ephemeral=True)

    async def _prev_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        self.page -= 1
        self._rebuild()
        await interaction.response.edit_message(
            embed=_embed_modsg(self.page), view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        if not await _check_staff(interaction):
            return
        self.page += 1
        self._rebuild()
        await interaction.response.edit_message(
            embed=_embed_modsg(self.page), view=self)


# ══════════════════════════════════════════════════════════════════════
#  ── COG ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

class ModsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Gmods.json se crea automáticamente la primera vez que se usa
        # !mods o !modsG, dentro de _load() → _ensure_file().
        # No se crea en el arranque para no desperdiciar recursos.

    # ── !mods  (Público) ──────────────────────────────────────────────
    @commands.command(name="mods")
    async def mods_cmd(self, ctx: commands.Context):
        """Muestra los mods del servidor con lista interactiva."""
        await ctx.send(embed=_embed_mods_publico(0), view=ModsPublicView(0))

    # ── !modsG  (Solo Owner / Mods) ───────────────────────────────────
    @commands.command(name="modsG")
    async def modsg_cmd(self, ctx: commands.Context):
        """Panel de gestión de mods. Solo Owner y Moderadores."""
        if not _es_staff(ctx.author):
            return   # silencio total si no tiene permisos
        await ctx.send(embed=_embed_modsg(0), view=ModsGestView(0))


async def setup(bot: commands.Bot):
    await bot.add_cog(ModsCog(bot))