"""
events.py — Sistema de eventos para 7 Days to Die.

Público:
  !events    — ver eventos activos e interactuar (inscribirse / subir prueba)
  !enviar    — cerrar sesión de prueba y enviarla

Mods:
  !addevent  — crear nuevo evento (título, descripción, categorías, imágenes)
  !eventlist — gestionar todos los eventos (activos y finalizados) y sus participantes
"""

import discord
import asyncio
from discord.ext import commands
from discord.ui import View, Button
from discord.ui.label import Label
from discord.ui.file_upload import FileUpload
from datetime import datetime
import json, os, uuid, aiohttp, random, string, io, zipfile
from config import CANALES as _CFG_CANALES
from ticket import ALLOWED_ROLE_IDS
from pin import IMGBB_API
import pin

# ─────────────────────────────────────────────────────────────────────
# RUTAS Y CONSTANTES
# ─────────────────────────────────────────────────────────────────────
BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
EVENTS_PATH = os.path.join(BASE_DIR, "Cache", "events.json")
ANNOUNCE_CHANNEL_ID: int = _CFG_CANALES["eventos_anuncio"]
NETLIFY_MANIFEST = os.path.join(BASE_DIR, "Cache", "netlify_manifest.json")
VALID_IMG  = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_PAGE_SIZE = 10

# ─────────────────────────────────────────────────────────────────────
# JSON HELPERS — toda la info del evento viene del events.json
# ─────────────────────────────────────────────────────────────────────
def _load() -> dict:
    if not os.path.exists(EVENTS_PATH):
        return {}
    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data: dict):
    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def _next_part_id(participantes: list) -> int:
    return max((p["id"] for p in participantes), default=0) + 1

# ─────────────────────────────────────────────────────────────────────
# PERMISOS
# ─────────────────────────────────────────────────────────────────────
def _es_mod(member: discord.Member) -> bool:
    ids = {r.id for r in member.roles}
    return bool(ids & set(ALLOWED_ROLE_IDS.values()))

# ─────────────────────────────────────────────────────────────────────
# IMGBB
# ─────────────────────────────────────────────────────────────────────
async def _upload_imgbb(attachment: discord.Attachment) -> str | None:
    nombre = "ev_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    try:
        if isinstance(attachment, discord.Attachment):
            img_bytes = await attachment.read()
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment) as resp:
                    img_bytes = await resp.read()    
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("key",   IMGBB_API)
            data.add_field("name",  nombre)
            data.add_field("image", img_bytes,
                           filename=attachment.filename,
                           content_type=attachment.content_type or "image/png")
            async with session.post("https://api.imgbb.com/1/upload", data=data) as r:
                resp = await r.json()
                if resp.get("success"):
                    return resp["data"]["url"]
    except Exception as e:
        print(f"[events] imgbb error: {e}")
    return None

def _es_imagen(att: discord.Attachment) -> bool:
    return os.path.splitext(att.filename)[1].lower() in VALID_IMG

# ─────────────────────────────────────────────────────────────────────
# SESIONES DE CREACIÓN DE EVENTO  { user_id: datos_parciales }
# ─────────────────────────────────────────────────────────────────────
def _evento_embed(ev: dict) -> discord.Embed:
    embed = discord.Embed(
        title=ev["titulo"],
        description=ev.get("desc_larga") or ev.get("desc_corta", ""),
        color=0xFFD700 if ev.get("activo") else 0x555555,
    )
    if ev.get("categorias"):
        embed.add_field(name="📂 Categorías", value=f"{len(ev['categorias'])} proyectos", inline=True)
    if ev.get("recompensas"):
        embed.add_field(name="🏆 Recompensas", value=ev["recompensas"], inline=True)
    embed.add_field(name="👥 Inscritos", value=str(len(ev.get("participantes", []))), inline=True)
    embed.add_field(name="📌 Estado", value="🟢 Activo" if ev.get("activo") else "🔴 Finalizado", inline=True)
    embed.add_field(
        name="📋 Inscripción",
        value="✅ Obligatoria" if ev.get("requiere_inscripcion") else "❌ No requerida",
        inline=True,
    )
    embed.set_footer(text="Miner7days • Eventos")
    return embed


def _participante_embed(p: dict, ev_titulo: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"👤 Participante #{p['id']} — {p['nombre']}",
        color=0x8B0000,
    )
    if p.get("categoria"):
        embed.add_field(name="📂 Categoría",    value=p["categoria"],             inline=False)
    if p.get("descripcion"):
        embed.add_field(name="📝 Descripción",  value=p["descripcion"],           inline=False)
    embed.add_field(name="👥 Equipo",           value=p.get("equipo") or "Solo",  inline=True)
    embed.add_field(name="🏷️ Discord",         value=p["discord_tag"],           inline=True)
    embed.add_field(name="📅 Fecha",            value=p["fecha"],                 inline=True)
    embed.set_footer(text=ev_titulo)
    return embed


def _list_embed(partics: list, ev_titulo: str, page: int) -> tuple[discord.Embed, int]:
    total = len(partics)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    chunk = partics[page * _PAGE_SIZE:(page + 1) * _PAGE_SIZE]
    lines = "\n".join(
        f"`#{p['id']}` **{p['nombre']}**" +
        (f" — {p['categoria']}" if p.get("categoria") else "")
        for p in chunk
    ) or "*(Sin participantes)*"
    embed = discord.Embed(
        title=f"📋 Participantes — {ev_titulo}",
        description=lines,
        color=0x8B0000,
    )
    embed.set_footer(text=f"Página {page + 1}/{pages} • {total} inscritos")
    return embed, pages


# ═════════════════════════════════════════════════════════════════════
# MODAL DE INSCRIPCIÓN (dinámico: con o sin categorías)
# ═════════════════════════════════════════════════════════════════════
class InscripcionModal(discord.ui.Modal, title="Inscripción al Evento"):
    nombre = discord.ui.TextInput(
        label="Tu nombre en el servidor",
        placeholder="Ej: Fran23135",
        min_length=2, max_length=40,
    )
    descripcion = discord.ui.TextInput(
        label="Descripción breve de tu participación",
        placeholder="Cuéntanos un poco cómo lo imaginas...",
        style=discord.TextStyle.paragraph,
        min_length=5, max_length=200,
    )
    equipo = discord.ui.TextInput(
        label="Equipo (opcional)",
        placeholder="Déjalo vacío si vas solo",
        required=False,
        max_length=40,
    )

    def __init__(self, ev_id: str, categorias: list):
        super().__init__()
        self._ev_id     = ev_id
        self._cats      = categorias
        self._cat_field = None
        if categorias:
            self._cat_field = discord.ui.TextInput(
                label=f"Número de categoría (1-{len(categorias)})",
                placeholder=f"Escribe un número del 1 al {len(categorias)}",
                min_length=1, max_length=2,
            )
            self.add_item(self._cat_field)

    async def on_submit(self, interaction: discord.Interaction):
        data = _load()
        ev   = data.get(self._ev_id)
        if not ev:
            await interaction.response.send_message("❌ Evento no encontrado.", ephemeral=True)
            return

        cat_nombre = None
        if self._cats and self._cat_field:
            try:
                idx = int(self._cat_field.value.strip()) - 1
                if not (0 <= idx < len(self._cats)):
                    raise ValueError
                cat_nombre = self._cats[idx]["nombre"]
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Categoría inválida. Elige un número del 1 al {len(self._cats)}.",
                    ephemeral=True,
                )
                return
 
        partics = ev.setdefault("participantes", [])
         # ── Verificar inscripción duplicada ──────────────────────────
        partics_actuales = ev.get("participantes", [])
        for p in partics_actuales:
            if p["discord_id"] == interaction.user.id:
                if not self._cats:
                    # Sin categorías → una sola inscripción permitida
                    await interaction.response.send_message(
                        "⚠️ Ya estás inscrito en este evento.", ephemeral=True
                    )
                    return
                # Con categorías → no puede repetir la misma categoría
                if p.get("categoria") == cat_nombre:
                    await interaction.response.send_message(
                        f"⚠️ Ya estás inscrito en la categoría **{cat_nombre}**.\n"
                        "Puedes inscribirte en otras categorías distintas.",
                        ephemeral=True,
                    )
                    return
        # ─────────────────────────────────────────────────────────────
        nueva = {
            "id":          _next_part_id(partics),
            "discord_id":  interaction.user.id,
            "discord_tag": str(interaction.user),
            "nombre":      self.nombre.value.strip(),
            "categoria":   cat_nombre,
            "descripcion": self.descripcion.value.strip(),
            "equipo":      self.equipo.value.strip() or None,
            "fecha":       _now(),
        }
        partics.append(nueva)
        _save(data)

        embed = discord.Embed(title="✅ ¡Inscripción confirmada!", color=0x00FF88)
        embed.add_field(name="👤 Nombre", value=nueva["nombre"],      inline=True)
        embed.add_field(name="🆔 ID",     value=f"`#{nueva['id']}`",  inline=True)
        if cat_nombre:
            embed.add_field(name="📂 Categoría",   value=cat_nombre,          inline=False)
        embed.add_field(name="📝 Descripción",     value=nueva["descripcion"], inline=False)
        if nueva["equipo"]:
            embed.add_field(name="👥 Equipo",      value=nueva["equipo"],     inline=True)
        embed.set_footer(text=f"{ev['titulo']} • {nueva['fecha']}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═════════════════════════════════════════════════════════════════════
# VISTA DE CATEGORÍAS
# ═════════════════════════════════════════════════════════════════════
class CategoriasView(View):
    def __init__(self, categorias: list):
        super().__init__(timeout=None)
        sel = discord.ui.Select(
            placeholder="🔍 Elige una categoría para ver sus detalles...",
            options=[
                discord.SelectOption(
                    label=c["nombre"][:100],
                    value=str(i),
                    description=c.get("resumen", "")[:100],
                )
                for i, c in enumerate(categorias)
            ],
        )
        sel.callback = self._cb
        self._cats = categorias
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        cat   = self._cats[int(interaction.data["values"][0])]
        embed = discord.Embed(
            title=cat["nombre"],
            description=cat.get("detalles") or cat.get("resumen", "Sin descripción."),
            color=0xFFD700,
        )
        embed.set_footer(text="Miner7days • Categorías")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def _upload_imgbb_from_url(url: str) -> str | None:
    """Sube una imagen desde una URL directa a ImgBB."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                img_bytes = await resp.read()
                # Ahora usa la misma lógica de _upload_imgbb pero con bytes
                data = aiohttp.FormData()
                data.add_field("key", IMGBB_API)
                data.add_field("image", img_bytes)
                async with session.post("https://api.imgbb.com/1/upload", data=data) as r:
                    result = await r.json()
                    if result.get("success"):
                        return result["data"]["url"]
    except Exception as e:
        print(f"[events] Error subiendo URL a ImgBB: {e}")
    return None

# ═════════════════════════════════════════════════════════════════════
# MODAL DE SUBIDA DE PRUEBA (igual que AddeventImagenesModal)
# ═════════════════════════════════════════════════════════════════════
class PruebaImagenesModal(discord.ui.Modal, title="Subir prueba del evento"):
    def __init__(self, ev_id: str, guild):
        super().__init__()
        self._ev_id = ev_id
        self._guild = guild
        self.label_item = discord.ui.Label(
            text="Selecciona hasta 5 imágenes como prueba:",
            component=discord.ui.FileUpload(
                custom_id="prueba_images",
                min_values=1,
                max_values=5,
                required=True,
            )
        )
        self.add_item(self.label_item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        attachments_data = interaction.data.get("resolved", {}).get("attachments", {})
        if not attachments_data:
            await interaction.followup.send("❌ No se detectaron archivos.", ephemeral=True)
            return

        urls = [info["url"] for info in attachments_data.values()]
        uploaded_urls = []
        for url in urls:
            img_url = await _upload_imgbb_from_url(url)
            if img_url:
                uploaded_urls.append(img_url)

        if not uploaded_urls:
            await interaction.followup.send("❌ No se pudo subir ninguna imagen.", ephemeral=True)
            return

        data = _load()
        ev   = data.get(self._ev_id)
        if not ev:
            await interaction.followup.send("❌ Evento no encontrado.", ephemeral=True)
            return

        prueba = {
            "id":           str(uuid.uuid4())[:8],
            "discord_id":   interaction.user.id,
            "discord_tag":  str(interaction.user),
            "autor_nombre": interaction.user.display_name,
            "imagenes":     uploaded_urls,
            "estado":       "pendiente",
            "fecha":        _now(),
        }
        ev.setdefault("pruebas", []).append(prueba)
        _save(data)

        # Anuncio público
        canal = self._guild.get_channel(ANNOUNCE_CHANNEL_ID) if self._guild else None
        if canal:
            anuncio = discord.Embed(
                title="📸 ¡Nueva prueba enviada!",
                description=(
                    f"**{interaction.user.display_name}** ha enviado "
                    f"{len(uploaded_urls)} imagen(es) como prueba para "
                    f"**{ev['titulo']}**.\n\n"
                    "⏳ En espera de validación por los moderadores."
                ),
                color=0xFFA500,
            )
            anuncio.set_image(url=uploaded_urls[0])
            anuncio.set_footer(text=_now())
            await canal.send(embed=anuncio)

        await interaction.followup.send(
            f"✅ {len(uploaded_urls)} imagen(es) enviada(s) correctamente como prueba.",
            ephemeral=True,
        )


# ═════════════════════════════════════════════════════════════════════
# VISTA PRINCIPAL DE UN EVENTO
# ═════════════════════════════════════════════════════════════════════
class EventoView(View):
    def __init__(self, ev_id: str, ev: dict):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._ev    = ev

        # Inscribirse solo si el evento lo requiere
        if ev.get("requiere_inscripcion"):
            btn_insc = Button(label="📝 Inscribirme", style=discord.ButtonStyle.success, emoji="🏗️", row=0)
            btn_insc.callback = self._inscribirse
            self.add_item(btn_insc)

        btn_prueba = Button(label="📸 Subir prueba", style=discord.ButtonStyle.primary, emoji="📷", row=0)
        btn_prueba.callback = self._subir_prueba
        self.add_item(btn_prueba)

        if ev.get("categorias"):
            btn_cats = Button(label="📋 Ver categorías", style=discord.ButtonStyle.secondary, row=0)
            btn_cats.callback = self._ver_cats
            self.add_item(btn_cats)

    async def _inscribirse(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            InscripcionModal(self._ev_id, self._ev.get("categorias", [])))

    async def _subir_prueba(self, interaction: discord.Interaction):
        # Si requiere inscripción, verificar que el usuario esté inscrito
        if self._ev.get("requiere_inscripcion"):
            inscritos = [p["discord_id"] for p in self._ev.get("participantes", [])]
            if interaction.user.id not in inscritos:
                await interaction.response.send_message(
                    "❌ Este evento requiere estar inscrito antes de subir pruebas.\n"
                    "Pulsa **📝 Inscribirme** para registrarte primero.",
                    ephemeral=True,
                )
                return
        await interaction.response.send_modal(
            PruebaImagenesModal(self._ev_id, interaction.guild))

    async def _ver_cats(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Selecciona una categoría para ver sus detalles:",
            view=CategoriasView(self._ev["categorias"]),
            ephemeral=True,
        )


# ═════════════════════════════════════════════════════════════════════
# VISTA SELECT DE EVENTOS ACTIVOS  (cuando hay más de uno)
# ═════════════════════════════════════════════════════════════════════
class EventosActivosView(View):
    def __init__(self, activos: dict):
        super().__init__(timeout=None)
        self._activos = activos
        sel = discord.ui.Select(
            placeholder="🎮 Selecciona un evento...",
            options=[
                discord.SelectOption(
                    label=ev["titulo"][:100],
                    value=eid,
                    description=ev.get("desc_corta", "")[:100],
                )
                for eid, ev in list(activos.items())[:25]
            ],
        )
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        ev_id = interaction.data["values"][0]
        ev    = self._activos.get(ev_id)
        if not ev:
            await interaction.response.send_message("❌ Evento no encontrado.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_evento_embed(ev),
            view=EventoView(ev_id, ev),
            ephemeral=True,
        )


# ═════════════════════════════════════════════════════════════════════
# VISTA DE PARTICIPANTES CON GESTIÓN  (para !eventlist)
# ═════════════════════════════════════════════════════════════════════
class ParticipantesView(View):
    def __init__(self, ev_id: str, ev: dict, page: int = 0):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._ev    = ev
        self.page   = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        partics = self._ev.get("participantes", [])
        total   = len(partics)
        pages   = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        chunk   = partics[self.page * _PAGE_SIZE:(self.page + 1) * _PAGE_SIZE]

        if chunk:
            sel_ver = discord.ui.Select(
                placeholder="👤 Ver detalles de participante...",
                options=[
                    discord.SelectOption(
                        label=f"#{p['id']} {p['nombre']}"[:100],
                        value=str(p["id"]),
                        description=(p.get("categoria") or "Sin categoría")[:100],
                    )
                    for p in chunk
                ],
                row=0,
            )
            sel_ver.callback = self._ver_cb
            self.add_item(sel_ver)

            sel_del = discord.ui.Select(
                placeholder="🗑️ Eliminar participante...",
                options=[
                    discord.SelectOption(
                        label=f"#{p['id']} {p['nombre']}"[:100],
                        value=str(p["id"]),
                        description="Eliminar inscripción",
                    )
                    for p in chunk
                ],
                row=1,
            )
            sel_del.callback = self._del_cb
            self.add_item(sel_del)

        if pages > 1:
            prev = Button(label="◀ Anterior", style=discord.ButtonStyle.secondary,
                          disabled=self.page == 0, row=2)
            prev.callback = self._prev
            self.add_item(prev)

            self.add_item(Button(
                label=f"{self.page + 1} / {pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True, row=2,
            ))

            nxt = Button(label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                         disabled=self.page >= pages - 1, row=2)
            nxt.callback = self._next
            self.add_item(nxt)

        # Botón cerrar evento (solo si está activo)
        if self._ev.get("activo"):
            btn_cerrar = Button(
                label="🔒 Cerrar Evento",
                style=discord.ButtonStyle.danger,
                row=3,
            )
            btn_cerrar.callback = self._cerrar_evento
            self.add_item(btn_cerrar)

        # Botón ver pruebas (siempre)
        btn_pruebas = Button(
            label="📸 Ver Pruebas",
            style=discord.ButtonStyle.secondary,
            row=3,
        )
        btn_pruebas.callback = self._ver_pruebas
        self.add_item(btn_pruebas)

    async def _ver_cb(self, interaction: discord.Interaction):
        pid    = int(interaction.data["values"][0])
        partic = next((p for p in self._ev["participantes"] if p["id"] == pid), None)
        if not partic:
            await interaction.response.send_message("❌ No encontrado.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_participante_embed(partic, self._ev["titulo"]), ephemeral=True)

    async def _del_cb(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        pid  = int(interaction.data["values"][0])
        data = _load()
        ev   = data.get(self._ev_id)
        if not ev:
            await interaction.response.send_message("❌ Evento no encontrado.", ephemeral=True)
            return
        nombre_eliminado = next((p["nombre"] for p in ev["participantes"] if p["id"] == pid), "—")
        ev["participantes"] = [p for p in ev["participantes"] if p["id"] != pid]
        _save(data)
        self._ev  = ev
        self.page = max(0, min(self.page,
                               max(0, (len(ev["participantes"]) - 1) // _PAGE_SIZE)))
        self._rebuild()
        embed, _ = _list_embed(ev["participantes"], ev["titulo"], self.page)
        await interaction.response.edit_message(
            content=f"🗑️ **{nombre_eliminado}** eliminado.",
            embed=embed, view=self,
        )

    async def _prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        embed, _ = _list_embed(self._ev["participantes"], self._ev["titulo"], self.page)
        await interaction.response.edit_message(embed=embed, view=self, content=None)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        embed, _ = _list_embed(self._ev["participantes"], self._ev["titulo"], self.page)
        await interaction.response.edit_message(embed=embed, view=self, content=None)

    async def _ver_pruebas(self, interaction: discord.Interaction):
        pruebas = self._ev.get("pruebas", [])
        if not pruebas:
            await interaction.response.send_message(
                "📭 No hay pruebas registradas para este evento.", ephemeral=True)
            return
        embed, _ = _pruebas_embed(pruebas, self._ev["titulo"], 0)
        await interaction.response.send_message(
            embed=embed, view=PruebasView(self._ev_id, self._ev, 0), ephemeral=True)

    async def _cerrar_evento(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        data = _load()
        ev   = data.get(self._ev_id)
        if not ev or not ev.get("activo"):
            await interaction.response.send_message("⚠️ Este evento ya está cerrado.", ephemeral=True)
            return
        # Confirmación efímera
        conf_embed = discord.Embed(
            title="⚠️ ¿Cerrar el evento?",
            description=(
                f"Vas a cerrar **{ev['titulo']}**.\n\n"
                "Se anunciará en el canal público y ya no se podrán subir pruebas ni inscribirse.\n"
                "¿Confirmas?"
            ),
            color=0xFF4444,
        )
        await interaction.response.send_message(
            embed=conf_embed,
            view=_ConfirmCerrarView(self._ev_id, self),
            ephemeral=True,
        )


# ═════════════════════════════════════════════════════════════════════
# VISTA CONFIRMACIÓN CIERRE DE EVENTO
# ═════════════════════════════════════════════════════════════════════
class _ConfirmCerrarView(View):
    def __init__(self, ev_id: str, parent):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._parent = parent

    @discord.ui.button(label="✅ Confirmar cierre", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, btn: Button):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        data = _load()
        ev   = data.get(self._ev_id)
        if not ev:
            await interaction.response.edit_message(content="❌ Evento no encontrado.", embed=None, view=None)
            return
        ev["activo"]         = False
        ev["finalizado_at"]  = _now()
        ev["finalizado_por"] = str(interaction.user)
        _save(data)

        # Actualizar vista padre
        self._parent._ev = ev
        self._parent._rebuild()
        embed, _ = _list_embed(ev.get("participantes", []), ev["titulo"], self._parent.page)
        await interaction.response.edit_message(content="🔒 Evento cerrado.", embed=None, view=None)

        # Anuncio público
        canal = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID) if interaction.guild else None
        if canal:
            anuncio = discord.Embed(
                title=f"🔒 {ev['titulo']} — Evento Cerrado",
                description=(
                    "**El período de participación ha finalizado.**\n\n"
                    "¡Gracias a todos por su participar!"
                ),
                color=0x8B0000,
            )
            anuncio.add_field(name="👥 Participantes", value=str(len(ev.get("participantes", []))), inline=True)
            anuncio.add_field(name="📅 Cerrado", value=_now(), inline=True)
            anuncio.add_field(name="👤 Por", value=interaction.user.display_name, inline=True)
            anuncio.set_footer(text="Miner7days • Eventos")
            await canal.send("@here", embed=anuncio,
                             allowed_mentions=discord.AllowedMentions(everyone=True))

    @discord.ui.button(label="✖️ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, btn: Button):
        await interaction.response.edit_message(content="↩️ Cierre cancelado.", embed=None, view=None)


# ═════════════════════════════════════════════════════════════════════
# VISTA DE PRUEBAS (para !eventlist → Ver Pruebas)
# ═════════════════════════════════════════════════════════════════════
def _pruebas_embed(pruebas: list, ev_titulo: str, page: int) -> tuple[discord.Embed, int]:
    total = len(pruebas)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    chunk = pruebas[page * _PAGE_SIZE:(page + 1) * _PAGE_SIZE]
    _EL = {"validada": "✅ Validada", "rechazada": "❌ Rechazada", "pendiente": "⏳ Pendiente"}
    lines = "\n".join(
        f"`#{p['id']}` **{p['autor_nombre']}** — {p['fecha']} — "
        f"{_EL.get(p.get('estado', 'pendiente'), '⏳ Pendiente')} — "
        f"{len(p.get('imagenes', []))} img"
        for p in chunk
    ) or "*(Sin pruebas)*"
    embed = discord.Embed(
        title=f"📸 Pruebas — {ev_titulo}",
        description=lines,
        color=0xFFA500,
    )
    embed.set_footer(text=f"Página {page + 1}/{pages} • {total} pruebas")
    return embed, pages


class PruebasView(View):
    """Lista de pruebas paginada. Selecciona una para gestionar."""
    def __init__(self, ev_id: str, ev: dict, page: int = 0):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._ev    = ev
        self.page   = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        pruebas = self._ev.get("pruebas", [])
        pages   = max(1, (len(pruebas) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        chunk   = pruebas[self.page * _PAGE_SIZE:(self.page + 1) * _PAGE_SIZE]

        if chunk:
            _ESTADO = {"validada": "✅", "rechazada": "❌", "pendiente": "⏳"}
            sel = discord.ui.Select(
                placeholder="📸 Selecciona prueba para gestionar...",
                options=[
                    discord.SelectOption(
                        label=f"{p['autor_nombre']}"[:100],
                        value=p["id"],
                        emoji=_ESTADO.get(p.get("estado", "pendiente"), "⏳"),
                        description=f"{p['fecha']} • {len(p.get('imagenes',[]))} img — {p.get('estado','pendiente')}"[:100],
                    )
                    for p in chunk
                ],
                row=0,
            )
            sel.callback = self._sel_cb
            self.add_item(sel)

        if pages > 1:
            prev = Button(label="◀", style=discord.ButtonStyle.secondary,
                          disabled=self.page == 0, row=1)
            prev.callback = self._prev
            self.add_item(prev)
            self.add_item(Button(label=f"{self.page+1}/{pages}",
                                 style=discord.ButtonStyle.secondary, disabled=True, row=1))
            nxt = Button(label="▶", style=discord.ButtonStyle.secondary,
                         disabled=self.page >= pages - 1, row=1)
            nxt.callback = self._next
            self.add_item(nxt)

    async def _sel_cb(self, interaction: discord.Interaction):
        pid    = interaction.data["values"][0]
        prueba = next((p for p in self._ev["pruebas"] if p["id"] == pid), None)
        if not prueba:
            await interaction.response.send_message("❌ No encontrada.", ephemeral=True)
            return
        estado    = prueba.get("estado", "pendiente")
        color_map = {"validada": 0x00FF88, "rechazada": 0xFF4444, "pendiente": 0xFFA500}
        imagenes  = prueba.get("imagenes", [])
        emb = discord.Embed(
            title=f"📸 Prueba de {prueba['autor_nombre']}",
            color=color_map.get(estado, 0xFFA500),
        )
        emb.add_field(name="🏷️ Discord", value=prueba["discord_tag"], inline=True)
        emb.add_field(name="📅 Fecha",   value=prueba["fecha"],       inline=True)
        emb.add_field(name="📌 Estado",
                      value={"validada":"✅ Validada","rechazada":"❌ Rechazada"}.get(estado,"⏳ Pendiente"),
                      inline=True)
        if prueba.get("razon_rechazo"):
            emb.add_field(name="📋 Motivo rechazo", value=prueba["razon_rechazo"], inline=False)
        # Asociar a inscripción si el evento lo requiere
        if self._ev.get("requiere_inscripcion"):
            partic = next(
                (p for p in self._ev.get("participantes", [])
                 if p["discord_id"] == prueba["discord_id"]),
                None,
            )
            if partic:
                cat_txt = f" — {partic['categoria']}" if partic.get("categoria") else ""
                emb.add_field(
                    name="📝 Inscripción asociada",
                    value=f"**{partic['nombre']}**{cat_txt} (`#{partic['id']}`)",
                    inline=False,
                )
            else:
                emb.add_field(name="⚠️ Inscripción", value="Sin inscripción registrada", inline=False)
        emb.add_field(name="🖼️ Imágenes", value=str(len(imagenes)), inline=True)
        if imagenes:
            emb.set_image(url=imagenes[0])
            if len(imagenes) > 1:
                links = "  ".join(f"[Imagen {i+1}]({u})" for i, u in enumerate(imagenes[1:], 1))
                emb.add_field(name=f"🔗 Más ({len(imagenes)-1})", value=links, inline=False)
        emb.set_footer(text=f"{self._ev['titulo']} • ID: {prueba['id']}")
        await interaction.response.send_message(
            embed=emb,
            view=_PruebaAccionesView(self._ev_id, pid, self),
            ephemeral=True,
        )

    async def _prev(self, interaction: discord.Interaction):
        self.page -= 1; self._rebuild()
        embed, _ = _pruebas_embed(self._ev["pruebas"], self._ev["titulo"], self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1; self._rebuild()
        embed, _ = _pruebas_embed(self._ev["pruebas"], self._ev["titulo"], self.page)
        await interaction.response.edit_message(embed=embed, view=self)


# ═════════════════════════════════════════════════════════════════════
# VISTA DE ACCIONES SOBRE UNA PRUEBA CONCRETA
# ═════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════
# VISTA DE ACCIONES SOBRE UNA PRUEBA CONCRETA
# ═════════════════════════════════════════════════════════════════════
class _PruebaAccionesView(View):
    def __init__(self, ev_id: str, prueba_id: str, parent: "PruebasView"):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._pid   = prueba_id
        self._parent = parent
        self._rebuild_btns()

    def _rebuild_btns(self):
        self.clear_items()
        data   = _load()
        ev     = data.get(self._ev_id, {})
        prueba = next((p for p in ev.get("pruebas", []) if p["id"] == self._pid), None)
        estado = prueba.get("estado", "pendiente") if prueba else "pendiente"

        if estado == "pendiente":
            btn_val = Button(label="✅ Validar", style=discord.ButtonStyle.success, row=0)
            btn_val.callback = self._validar
            self.add_item(btn_val)

            btn_rec = Button(label="❌ Rechazar", style=discord.ButtonStyle.danger, row=0)
            btn_rec.callback = self._rechazar
            self.add_item(btn_rec)

        elif estado == "validada":
            # Revalidar abre un submenú para elegir nuevo estado
            btn_rev = Button(label="🔄 Revalidar", style=discord.ButtonStyle.secondary, row=0)
            btn_rev.callback = self._revalidar_menu
            self.add_item(btn_rev)

        elif estado == "rechazada":
            btn_val = Button(label="✅ Validar", style=discord.ButtonStyle.success, row=0)
            btn_val.callback = self._validar
            self.add_item(btn_val)

            btn_rev = Button(label="🔄 Revalidar", style=discord.ButtonStyle.secondary, row=0)
            btn_rev.callback = self._revalidar_menu
            self.add_item(btn_rev)

    async def _revalidar_menu(self, interaction: discord.Interaction, btn: Button = None):
        """Abre el menú de revalidación (Validar o Rechazar) sin modificar aún el estado."""
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return

        view = _RevalidarOpcionesView(self._ev_id, self._pid, self._parent)
        await interaction.response.send_message(
            "🔄 **Revalidación** — elige el nuevo estado de la prueba:",
            view=view,
            ephemeral=True,
        )

    async def _validar(self, interaction, btn=None):
        await self._cambiar_estado(interaction, "validada")

    async def _rechazar(self, interaction, btn=None):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(_ModalRechazarPrueba(self._ev_id, self._pid, self._parent))

    async def _cambiar_estado(self, interaction: discord.Interaction, nuevo: str, razon: str | None = None):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return

        data   = _load()
        ev     = data.get(self._ev_id)
        prueba = next((p for p in ev.get("pruebas", []) if p["id"] == self._pid), None) if ev else None
        if not ev or not prueba:
            await interaction.response.edit_message(content="❌ No encontrado.", embed=None, view=None)
            return

        prueba["estado"] = nuevo
        if razon:
            prueba["razon_rechazo"] = razon
        elif "razon_rechazo" in prueba and nuevo != "rechazada":
            del prueba["razon_rechazo"]
        _save(data)

        # Actualizar la vista padre (PruebasView)
        self._parent._ev = ev
        self._parent._rebuild()

        icono = {"validada":"✅","rechazada":"❌","pendiente":"🔄"}.get(nuevo,"🔄")
        await interaction.response.edit_message(
            content=f"{icono} Estado actualizado a **{nuevo}**.", embed=None, view=None
        )

        # Anuncio público
        canal = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID) if interaction.guild else None
        if canal:
            if nuevo == "validada":
                titulo = "✅ Prueba validada"
                desc   = f"<@{prueba['discord_id']}> tu prueba para **{ev['titulo']}** ha sido **validada** ✅"
                color  = 0x00FF88
            elif nuevo == "rechazada":
                titulo = "❌ Prueba rechazada"
                desc   = f"<@{prueba['discord_id']}> tu prueba para **{ev['titulo']}** ha sido **rechazada** ❌"
                if razon:
                    desc += f"\n\n📋 **Motivo:** {razon}"
                color  = 0xFF4444
            else:  # pendiente (no debería anunciarse directamente desde aquí)
                return

            anuncio = discord.Embed(title=titulo, description=desc, color=color)
            anuncio.add_field(name="👤 Usuario", value=prueba["discord_tag"], inline=True)
            anuncio.add_field(name="🎮 Evento",  value=ev["titulo"],          inline=True)
            if prueba.get("imagenes"):
                anuncio.set_thumbnail(url=prueba["imagenes"][0])
            anuncio.set_footer(text=f"Por {interaction.user.display_name} • {_now()}")
            await canal.send(embed=anuncio)


# ═════════════════════════════════════════════════════════════════════
# VISTA DE OPCIONES DE REVALIDACIÓN (Validar / Rechazar)
# ═════════════════════════════════════════════════════════════════════
class _RevalidarOpcionesView(View):
    def __init__(self, ev_id: str, prueba_id: str, parent: "PruebasView"):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._pid   = prueba_id
        self._parent = parent

    @discord.ui.button(label="✅ Validar", style=discord.ButtonStyle.success)
    async def validar_btn(self, interaction: discord.Interaction, btn: Button):
        # Cambiar estado a validada
        view = _PruebaAccionesView(self._ev_id, self._pid, self._parent)
        await view._cambiar_estado(interaction, "validada")

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger)
    async def rechazar_btn(self, interaction: discord.Interaction, btn: Button):
        # Mostrar modal para motivo de rechazo
        await interaction.response.send_modal(_ModalRechazarPrueba(self._ev_id, self._pid, self._parent))

# ═════════════════════════════════════════════════════════════════════
# MODAL PARA MOTIVO DE RECHAZO
# ═════════════════════════════════════════════════════════════════════
class _ModalRechazarPrueba(discord.ui.Modal, title="Rechazar Prueba"):
    motivo = discord.ui.TextInput(
        label="Motivo del rechazo",
        placeholder="Explica por qué se rechaza...",
        style=discord.TextStyle.paragraph,
        min_length=5, max_length=300,
    )

    def __init__(self, ev_id: str, prueba_id: str, parent: "PruebasView"):
        super().__init__()
        self._ev_id  = ev_id
        self._pid    = prueba_id
        self._parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        # Creamos una vista temporal para usar su método _cambiar_estado
        view = _PruebaAccionesView(self._ev_id, self._pid, self._parent)
        await view._cambiar_estado(interaction, "rechazada", razon=self.motivo.value.strip())
class _ModalRechazarPrueba(discord.ui.Modal, title="Rechazar Prueba"):
    motivo = discord.ui.TextInput(
        label="Motivo del rechazo",
        placeholder="Explica por qué se rechaza...",
        style=discord.TextStyle.paragraph,
        min_length=5, max_length=300,
    )

    def __init__(self, ev_id: str, prueba_id: str, parent: PruebasView):
        super().__init__()
        self._ev_id  = ev_id
        self._pid    = prueba_id
        self._parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        view = _PruebaAccionesView(self._ev_id, self._pid, self._parent)
        await view._cambiar_estado(interaction, "rechazada", razon=self.motivo.value.strip())

# ═════════════════════════════════════════════════════════════════════
# VISTA CONFIRMACIÓN CIERRE DE EVENTO
# ═════════════════════════════════════════════════════════════════════
class _ConfirmCerrarView(View):
    def __init__(self, ev_id: str, parent):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._parent = parent

    @discord.ui.button(label="✅ Confirmar cierre", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, btn: Button):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        data = _load()
        ev   = data.get(self._ev_id)
        if not ev:
            await interaction.response.edit_message(content="❌ Evento no encontrado.", embed=None, view=None)
            return
        ev["activo"]         = False
        ev["finalizado_at"]  = _now()
        ev["finalizado_por"] = str(interaction.user)
        _save(data)

        # Actualizar vista padre
        self._parent._ev = ev
        if hasattr(self._parent, "_build"):
            self._parent._build()
        elif hasattr(self._parent, "_rebuild"):
            self._parent._rebuild()
        await interaction.response.edit_message(content="🔒 Evento cerrado.", embed=None, view=None)

        # Anuncio público
        canal = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID) if interaction.guild else None
        if canal:
            anuncio = discord.Embed(
                title=f"🔒 {ev['titulo']} — Evento Cerrado",
                description=(
                    "**El período de participación ha finalizado.**\n\n"
                    "¡Gracias a todos por particiapar!"
                ),
                color=0x8B0000,
            )
            anuncio.add_field(name="👥 Participantes", value=str(len(ev.get("participantes", []))), inline=True)
            anuncio.add_field(name="📅 Cerrado", value=_now(), inline=True)
            anuncio.add_field(name="👤 Por", value=interaction.user.display_name, inline=True)
            anuncio.set_footer(text="7 Days to Die • Esperad los resultados")
            await canal.send("@here", embed=anuncio,
                             allowed_mentions=discord.AllowedMentions(everyone=True))

    @discord.ui.button(label="✖️ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, btn: Button):
        await interaction.response.edit_message(content="↩️ Cierre cancelado.", embed=None, view=None)


# ═════════════════════════════════════════════════════════════════════
# VISTA DE PRUEBAS (para !eventlist → Ver Pruebas)
# ═════════════════════════════════════════════════════════════════════
def _pruebas_embed(pruebas: list, ev_titulo: str, page: int) -> tuple[discord.Embed, int]:
    total = len(pruebas)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page  = max(0, min(page, pages - 1))
    chunk = pruebas[page * _PAGE_SIZE:(page + 1) * _PAGE_SIZE]
    _EL = {"validada": "✅ Validada", "rechazada": "❌ Rechazada", "pendiente": "⏳ Pendiente"}
    lines = "\n".join(
        f"`#{p['id']}` **{p['autor_nombre']}** — {p['fecha']} — "
        f"{_EL.get(p.get('estado', 'pendiente'), '⏳ Pendiente')} — "
        f"{len(p.get('imagenes', []))} img"
        for p in chunk
    ) or "*(Sin pruebas)*"
    embed = discord.Embed(
        title=f"📸 Pruebas — {ev_titulo}",
        description=lines,
        color=0xFFA500,
    )
    embed.set_footer(text=f"Página {page + 1}/{pages} • {total} pruebas")
    return embed, pages


class PruebasView(View):
    """Lista de pruebas paginada. Selecciona una para gestionar."""
    def __init__(self, ev_id: str, ev: dict, page: int = 0):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._ev    = ev
        self.page   = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        pruebas = self._ev.get("pruebas", [])
        pages   = max(1, (len(pruebas) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        chunk   = pruebas[self.page * _PAGE_SIZE:(self.page + 1) * _PAGE_SIZE]

        if chunk:
            sel = discord.ui.Select(
                placeholder="📸 Selecciona una prueba para ver detalles...",
                options=[
                    discord.SelectOption(
                        label=f"#{p['id']} {p['autor_nombre']}"[:100],
                        value=p["id"],
                        description=(
                            f"{'✅' if p.get('estado') == 'validada' else '⏳'} "
                            f"{p['fecha']} • {len(p.get('imagenes', []))} imagen(es)"
                        )[:100],
                    )
                    for p in chunk
                ],
                row=0,
            )
            sel.callback = self._sel_cb
            self.add_item(sel)

        if pages > 1:
            prev = Button(label="◀ Anterior", style=discord.ButtonStyle.secondary,
                          disabled=self.page == 0, row=1)
            prev.callback = self._prev
            self.add_item(prev)
            self.add_item(Button(label=f"{self.page + 1} / {pages}",
                                 style=discord.ButtonStyle.secondary, disabled=True, row=1))
            nxt = Button(label="Siguiente ▶", style=discord.ButtonStyle.secondary,
                         disabled=self.page >= pages - 1, row=1)
            nxt.callback = self._next
            self.add_item(nxt)

    async def _sel_cb(self, interaction: discord.Interaction):
        pid    = interaction.data["values"][0]
        prueba = next((p for p in self._ev["pruebas"] if p["id"] == pid), None)
        if not prueba:
            await interaction.response.send_message("❌ No encontrada.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"📸 Prueba #{prueba['id']} — {prueba['autor_nombre']}",
            color=0x00FF88 if prueba.get("estado") == "validada" else 0xFFA500,
        )
        embed.add_field(name="🏷️ Discord",  value=prueba["discord_tag"], inline=True)
        embed.add_field(name="📅 Fecha",     value=prueba["fecha"],       inline=True)
        embed.add_field(name="📌 Estado",
                        value="✅ Validada" if prueba.get("estado") == "validada" else "⏳ Pendiente",
                        inline=True)
        embed.add_field(name="🖼️ Imágenes", value=str(len(prueba.get("imagenes", []))), inline=True)
        if prueba.get("imagenes"):
            embed.set_image(url=prueba["imagenes"][0])
        embed.set_footer(text=self._ev["titulo"])
        await interaction.response.send_message(
            embed=embed,
            view=_PruebaAccionesView(self._ev_id, pid, self),
            ephemeral=True,
        )

    async def _prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        embed, _ = _pruebas_embed(self._ev["pruebas"], self._ev["titulo"], self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        embed, _ = _pruebas_embed(self._ev["pruebas"], self._ev["titulo"], self.page)
        await interaction.response.edit_message(embed=embed, view=self)
# ═════════════════════════════════════════════════════════════════════
# VISTA SELECT DE TODOS LOS EVENTOS  (para !eventlist)
# ═════════════════════════════════════════════════════════════════════
class TodosEventosView(View):
    def __init__(self, todos: dict):
        super().__init__(timeout=None)
        self._todos = todos
        sel = discord.ui.Select(
            placeholder="🎮 Selecciona un evento...",
            options=[
                discord.SelectOption(
                    label=ev["titulo"][:100],
                    value=eid,
                    emoji="🟢" if ev.get("activo") else "🔴",
                    description=(
                        "Activo" if ev.get("activo")
                        else f"Finalizado: {ev.get('finalizado_at', '—')}"
                    )[:100],
                )
                for eid, ev in list(todos.items())[:25]
            ],
        )
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        ev_id = interaction.data["values"][0]
        ev    = self._todos.get(ev_id)
        if not ev:
            await interaction.response.send_message("❌ Evento no encontrado.", ephemeral=True)
            return
        emb = _gestion_embed(ev, ev_id)
        await interaction.response.send_message(
            embed=emb,
            view=EventoGestionView(ev_id, ev, self._todos),
            ephemeral=True,
        )



# ═════════════════════════════════════════════════════════════════════
# PANEL DE GESTIÓN — embed + botones condicionales
# ═════════════════════════════════════════════════════════════════════
def _gestion_embed(ev: dict, ev_id: str) -> discord.Embed:
    activo   = ev.get("activo", False)
    partics  = ev.get("participantes", [])
    pruebas  = ev.get("pruebas", [])
    pendientes = [p for p in pruebas if p.get("estado") == "pendiente"]
    validadas  = [p for p in pruebas if p.get("estado") == "validada"]
    rechazadas = [p for p in pruebas if p.get("estado") == "rechazada"]

    emb = discord.Embed(
        title=f"{'🟢' if activo else '🔴'} {ev['titulo']}",
        description=ev.get("desc_corta") or ev.get("desc_larga", ""),
        color=0x00CC44 if activo else 0x555555,
    )
    emb.add_field(name="📌 Estado",        value="Activo" if activo else "Finalizado", inline=True)
    emb.add_field(name="👥 Participantes", value=str(len(partics)), inline=True)
    emb.add_field(name="📸 Pruebas",
                  value=f"⏳ {len(pendientes)} pend. • ✅ {len(validadas)} val. • ❌ {len(rechazadas)} rech.",
                  inline=False)
    if not activo:
        emb.add_field(name="📅 Cerrado",  value=ev.get("finalizado_at","—"), inline=True)
        emb.add_field(name="👤 Por",      value=ev.get("finalizado_por","—"), inline=True)
    if ev.get("requiere_inscripcion"):
        emb.add_field(name="📋 Inscripción", value="✅ Obligatoria", inline=True)
    emb.set_footer(text=f"ID: {ev_id} • 7 Days to Die")
    return emb


class EventoGestionView(View):
    """Vista de gestión completa de un evento para moderadores."""
    def __init__(self, ev_id: str, ev: dict, todos: dict):
        super().__init__(timeout=None)
        self._ev_id = ev_id
        self._ev    = ev
        self._todos = todos
        self._build()

    def _build(self):
        self.clear_items()
        activo  = self._ev.get("activo", False)
        partics = self._ev.get("participantes", [])
        pruebas = self._ev.get("pruebas", [])

        # Anunciar evento — siempre disponible
        btn_anunciar = Button(label="📢 Anunciar Evento", style=discord.ButtonStyle.primary, row=0)
        btn_anunciar.callback = self._anunciar
        self.add_item(btn_anunciar)

        # Ver participantes — solo si hay
        if partics:
            btn_parts = Button(label=f"👥 Ver Participantes ({len(partics)})",
                               style=discord.ButtonStyle.secondary, row=0)
            btn_parts.callback = self._ver_participantes
            self.add_item(btn_parts)

        # Ver pruebas — solo si hay
        if pruebas:
            btn_pruebas = Button(label=f"📸 Ver Pruebas ({len(pruebas)})",
                                 style=discord.ButtonStyle.secondary, row=1)
            btn_pruebas.callback = self._ver_pruebas
            self.add_item(btn_pruebas)

        # Cerrar / Reabrir
        if activo:
            btn_cerrar = Button(label="🔒 Cerrar Evento", style=discord.ButtonStyle.danger, row=1)
            btn_cerrar.callback = self._cerrar
            self.add_item(btn_cerrar)
        else:
            btn_reabrir = Button(label="🔓 Reabrir Evento", style=discord.ButtonStyle.success, row=1)
            btn_reabrir.callback = self._reabrir
            self.add_item(btn_reabrir)

    async def _anunciar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        canal = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID) if interaction.guild else None
        if not canal:
            await interaction.response.send_message("❌ Canal de anuncios no encontrado.", ephemeral=True)
            return
        ev = self._ev
        anuncio = discord.Embed(
            title=f"🎮 {ev['titulo']}",
            description=ev.get("desc_larga") or ev.get("desc_corta",""),
            color=0xFFD700,
        )
        if ev.get("recompensas"):
            anuncio.add_field(name="🏆 Recompensas", value=ev["recompensas"], inline=False)
        if ev.get("categorias"):
            anuncio.add_field(name="📂 Categorías", value=str(len(ev["categorias"])), inline=True)
        if ev.get("imagenes"):
            anuncio.set_image(url=ev["imagenes"][0])
        anuncio.set_footer(text="7 Days to Die • ¡Participa ahora!")
        await canal.send("@here", embed=anuncio,
                         allowed_mentions=discord.AllowedMentions(everyone=True))
        await interaction.response.send_message("✅ Evento anunciado en el canal.", ephemeral=True)

    async def _ver_participantes(self, interaction: discord.Interaction):
        embed, _ = _list_embed(self._ev["participantes"], self._ev["titulo"], 0)
        await interaction.response.send_message(
            embed=embed, view=ParticipantesView(self._ev_id, self._ev, 0), ephemeral=True)

    async def _ver_pruebas(self, interaction: discord.Interaction):
        embed, _ = _pruebas_embed(self._ev["pruebas"], self._ev["titulo"], 0)
        await interaction.response.send_message(
            embed=embed, view=PruebasView(self._ev_id, self._ev, 0), ephemeral=True)

    async def _cerrar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        conf = discord.Embed(
            title="⚠️ ¿Cerrar el evento?",
            description=f"Vas a cerrar **{self._ev['titulo']}**. ¿Confirmas?",
            color=0xFF4444,
        )
        await interaction.response.send_message(
            embed=conf,
            view=_ConfirmCerrarView(self._ev_id, self),
            ephemeral=True,
        )

    async def _reabrir(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        data = _load()
        ev   = data.get(self._ev_id)
        if not ev:
            await interaction.response.send_message("❌ Evento no encontrado.", ephemeral=True)
            return
        ev["activo"] = True
        ev.pop("finalizado_at", None)
        ev.pop("finalizado_por", None)
        _save(data)
        self._ev = ev
        self._todos[self._ev_id] = ev
        self._build()
        await interaction.response.edit_message(embed=_gestion_embed(ev, self._ev_id), view=self)

        canal = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID) if interaction.guild else None
        if canal:
         anuncio = discord.Embed(
            title=f"🔓 {ev['titulo']} — ¡Abierto!",
            description="El evento ha sido reabierto por los moderadores. ¡Podéis volver a participar!\n\n"
                        "📢 Usa `!events` para ver los eventos activos e inscribirte.",
            color=0x00FF88,
         )
         anuncio.set_footer(text=f"Reabierto por {interaction.user.display_name} • {_now()}")
         await canal.send(embed=anuncio)   # Sin view

# ═════════════════════════════════════════════════════════════════════
# COG
# ═════════════════════════════════════════════════════════════════════
class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        '''if not os.path.exists(EVENTS_PATH):
            raise FileNotFoundError(
                f"[events] No se encontró {EVENTS_PATH}. "
                "Coloca el events.json en el directorio del bot antes de arrancar."
            )'''

    # ── !events — público ────────────────────────────────────────────
    @commands.command(name="events")
    async def cmd_events(self, ctx: commands.Context):
        """Muestra los eventos activos."""
        data    = _load()
        activos = {eid: ev for eid, ev in data.items() if ev.get("activo")}

        if not activos:
            await ctx.send("📭 No hay eventos activos en este momento.")
            return

        embed = discord.Embed(
            title="🎮 Eventos Activos",
            description=(
                f"Hay **{len(activos)}** evento(s) activo(s).\n"
                "Selecciona uno del menú para ver los detalles, inscribirte o subir una prueba."
            ),
            color=0xFFD700,
        )
        embed.set_footer(text="7 Days to Die • Selecciona del menú ↓")
        await ctx.send(embed=embed, view=EventosActivosView(activos))

    # ── !eventlist — solo mods ───────────────────────────────────────
    @commands.command(name="eventlist")
    @commands.guild_only()
    async def cmd_eventlist(self, ctx: commands.Context):
        """Lista todos los eventos y gestiona participantes. Solo mods."""
        if not _es_mod(ctx.author):
            await ctx.message.delete()
            return

        data = _load()
        if not data:
            await ctx.send("📭 No hay eventos registrados.")
            return

        activos     = sum(1 for ev in data.values() if ev.get("activo"))
        finalizados = len(data) - activos

        embed = discord.Embed(
            title="📋 Gestión de Eventos",
            description=(
                f"🟢 **Activos:** {activos}\n"
                f"🔴 **Finalizados:** {finalizados}\n\n"
                "Selecciona un evento para gestionar sus participantes."
            ),
            color=0x8B0000,
        )
        embed.set_footer(text="Solo moderadores y admins")
        await ctx.send(embed=embed, view=TodosEventosView(data))
    
    # ── !addevent — solo mods ───────────────────────────────────────
    @commands.command(name="addevent")
    @commands.guild_only()
    async def cmd_addevent(self, ctx: commands.Context):
        """Lanza el panel de creación de eventos. Solo mods."""
        if not _es_mod(ctx.author):
            await ctx.message.delete()
            return

        embed = discord.Embed(
            title="🎮 Event Creator",
            description=(
                "Pulsa **🌐 Generar Enlace** para obtener un enlace temporal al\n"
                "formulario de creación de eventos.\n\n"
                "**Pasos:**\n"
                "1️⃣ Pulsa el botón y espera unos segundos\n"
                "2️⃣ Abre el enlace y rellena todos los campos\n"
                "3️⃣ Descarga el `.json` con el botón de la web\n"
                "4️⃣ Pulsa **📂 Cargar JSON** y sube el archivo\n\n"
                "⏱️ El enlace expira en **24 horas**."
            ),
            color=0x8B0000,
        )
        embed.set_footer(text=f"Solicitado por {ctx.author.display_name} • Solo mods")
        await ctx.send(embed=embed, view=AddeventView(ctx.guild))


# ═════════════════════════════════════════════════════════════════════
# URL TEMPORAL — litterbox.catbox.moe (expira en 24h)
# ═════════════════════════════════════════════════════════════════════
async def _upload_event_creator() -> str:
    """Sube event_creator.html a litterbox (24h). Si falla, usa Netlify como respaldo."""
    html_path = os.path.join(BASE_DIR, "html", "event_creator.html")
    if not os.path.exists(html_path):
        raise FileNotFoundError(
            "No se encontró event_creator.html en el directorio del bot."
        )
    with open(html_path, "rb") as f:
        html_bytes = f.read()

    async def try_litterbox(session):
        try:
            form = aiohttp.FormData()
            form.add_field("reqtype", "fileupload")
            form.add_field("time",    "24h")
            form.add_field(
                "fileToUpload",
                html_bytes,
                filename="event_creator.html",
                content_type="text/html; charset=utf-8",
            )
            async with session.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                print(f"🔄 litterbox → {resp.status}")
                text = (await resp.text()).strip()
                if resp.status == 200 and text.startswith("http"):
                    return text
        except Exception as e:
            print(f"⚠️ litterbox: {e}")
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
            filename  = f"event_creator_{file_hash}.html"

            # Leer manifest compartido (el mismo que usa ticket.py)
            manifest = {}
            if os.path.exists(NETLIFY_MANIFEST):
                with open(NETLIFY_MANIFEST, "r", encoding="utf-8") as f:
                    manifest = json.load(f)

            manifest[file_hash] = {
                "filename":   filename,
                "created_at": datetime.now().isoformat(),
                "url":        f"{base_url.rstrip('/')}/{filename}",
                "html":       html_bytes.decode("utf-8"),
            }
            with open(NETLIFY_MANIFEST, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            # Construir zip con todos los archivos del manifest
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
                    "Content-Type":  "application/zip",
                },
                data=zip_buffer.read(),
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                print(f"🔄 Netlify deploy → {r.status}")
                if r.status in (200, 201):
                    deploy_data = await r.json()
                    deploy_id   = deploy_data.get("id")
                    target_url  = manifest[file_hash]["url"]

                    if deploy_id:
                        
                        for _ in range(30):  # máx ~90s
                            await asyncio.sleep(3)
                            async with session.get(
                                f"https://api.netlify.com/api/v1/deploys/{deploy_id}",
                                headers={"Authorization": f"Bearer {token}"},
                                timeout=aiohttp.ClientTimeout(total=15),
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
                    return target_url
        except Exception as e:
            print(f"⚠️ Netlify: {e}")
        return None

    async with aiohttp.ClientSession() as session:
        for nombre, intento in [
            ("litterbox", try_litterbox),
            ("netlify",   try_netlify),
        ]:
            print(f"🔄 Intentando {nombre}...")
            url = await intento(session)
            if url:
                print(f"✅ event_creator subido en {nombre}: {url}")
                return url

    raise RuntimeError("Todos los servicios fallaron. Intenta más tarde.")
# ═════════════════════════════════════════════════════════════════════
# MODAL DE CARGA DE JSON
# ═════════════════════════════════════════════════════════════════════
_REQUIRED_KEYS = {"titulo", "desc_corta", "desc_larga", "activo"}


def _validate_event_json(obj: dict) -> str | None:
    """Valida un nodo de evento. Devuelve mensaje de error o None si es válido."""
    if not isinstance(obj, dict):
        return "El JSON debe ser un objeto."
    missing = _REQUIRED_KEYS - obj.keys()
    if missing:
        return f"Faltan campos obligatorios: {', '.join(missing)}"
    if not isinstance(obj.get("titulo"), str) or not obj["titulo"].strip():
        return "El campo 'titulo' debe ser un texto no vacío."
    if not isinstance(obj.get("desc_corta"), str) or not obj["desc_corta"].strip():
        return "El campo 'desc_corta' debe ser un texto no vacío."
    if not isinstance(obj.get("desc_larga"), str) or not obj["desc_larga"].strip():
        return "El campo 'desc_larga' debe ser un texto no vacío."
    if not isinstance(obj.get("activo"), bool):
        return "El campo 'activo' debe ser true o false."
    if "categorias" in obj and not isinstance(obj["categorias"], list):
        return "El campo 'categorias' debe ser una lista."
    return None


class CargarEventoModal(discord.ui.Modal, title="Cargar Evento desde JSON"):
    def __init__(self, guild):
        super().__init__()
        self._guild = guild
        self.label_item = discord.ui.Label(
            text="Archivo .json del Event Creator:",
            component=discord.ui.FileUpload(
                custom_id="event_json",
                min_values=1,
                max_values=1,
                required=True,
            )
        )
        self.add_item(self.label_item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        attachments = interaction.data.get("resolved", {}).get("attachments", {})
        if not attachments:
            await interaction.followup.send("❌ No se detectó ningún archivo.", ephemeral=True)
            return

        att_info = next(iter(attachments.values()))
        filename  = att_info.get("filename", "")

        if not filename.lower().endswith(".json"):
            await interaction.followup.send(
                "❌ Solo se aceptan archivos `.json`.", ephemeral=True)
            return

        # Descargar el contenido del JSON
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(att_info["url"]) as resp:
                    raw = await resp.text(encoding="utf-8")
        except Exception as e:
            await interaction.followup.send(f"❌ No se pudo leer el archivo: {e}", ephemeral=True)
            return

        # Parsear
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            await interaction.followup.send(
                f"❌ El archivo no es JSON válido: {e}", ephemeral=True)
            return

        # Puede ser { ev_id: {...} } (formato del creator) o directamente {...}
        if not isinstance(payload, dict):
            await interaction.followup.send(
                "❌ El JSON debe ser un objeto.", ephemeral=True)
            return

        # Detectar si es un envoltorio { id: evento } o un evento directo
        events_to_add: dict[str, dict] = {}

        first_val = next(iter(payload.values()), None)
        if isinstance(first_val, dict) and "titulo" in first_val:
            # Formato envoltorio
            for eid, ev in payload.items():
                err = _validate_event_json(ev)
                if err:
                    await interaction.followup.send(
                        f"❌ Error en evento `{eid}`: {err}", ephemeral=True)
                    return
                events_to_add[eid] = ev
        else:
            # Evento directo, generar ID
            err = _validate_event_json(payload)
            if err:
                await interaction.followup.send(f"❌ JSON inválido: {err}", ephemeral=True)
                return
            events_to_add[str(uuid.uuid4())[:8]] = payload

        # Asegurar campos mínimos y limpiar
        now_str = _now()
        for eid, ev in events_to_add.items():
            ev.setdefault("categorias",           [])
            ev.setdefault("recompensas",           None)
            ev.setdefault("requiere_inscripcion",  False)
            ev.setdefault("participantes",         [])
            ev.setdefault("pruebas",               [])
            ev.setdefault("creado_at",             now_str)
            ev["creado_por"] = str(interaction.user)

        # Integrar en events.json
        data = _load()
        data.update(events_to_add)
        _save(data)

        n = len(events_to_add)
        titulos = "\n".join(f"• **{ev['titulo']}**" for ev in events_to_add.values())

        embed = discord.Embed(
            title=f"✅ {n} evento(s) cargado(s)",
            description=titulos,
            color=0x00FF88
            
        )
        embed.set_footer(text=f"Integrado por {interaction.user.display_name} • {now_str}")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ═════════════════════════════════════════════════════════════════════
# VISTA DE !addevent
# ═════════════════════════════════════════════════════════════════════
class AddeventView(View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self._guild = guild

        btn_gen = Button(label="🌐 Generar Enlace", style=discord.ButtonStyle.primary, emoji="📋")
        btn_gen.callback = self._generar
        self.add_item(btn_gen)

        btn_json = Button(label="📂 Cargar JSON", style=discord.ButtonStyle.success, emoji="📂")
        btn_json.callback = self._cargar
        self.add_item(btn_json)

    async def _generar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        # Diferir para que no expire mientras sube el archivo
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            url = await _upload_event_creator()
        except FileNotFoundError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return
        except RuntimeError as e:
            await interaction.followup.send(f"❌ Error al subir el archivo: {e}", ephemeral=True)
            return

        # Mandar el link como botón en un mensaje efímero
        link_view = View(timeout=None)
        link_view.add_item(discord.ui.Button(
            label="🌐 Abrir Event Creator",
            style=discord.ButtonStyle.link,
            url=url,
        ))
        await interaction.followup.send(
            "✅ Enlace generado (expira en **24h**):",
            view=link_view,
            ephemeral=True,
        )

    async def _cargar(self, interaction: discord.Interaction):
        if not _es_mod(interaction.user):
            await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
            return
        await interaction.response.send_modal(CargarEventoModal(self._guild))


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))