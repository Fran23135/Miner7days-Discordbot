import discord
import random
import asyncio
import json
import os
from discord.ext import commands
from interact import make_embed, INTERACCIONES
from status7d import nekos_cache

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
PREGUNTAS_POR_JUEGO    = 6
TIEMPO_PREGUNTA        = 22          # segundos por pregunta
MINIMO_ACIERTOS_PREMIO = 3           # aciertos mínimos para recibir regalo
LETRAS                 = ["A", "B", "C", "D"]
COLORES_OPCIONES       = [
    discord.ButtonStyle.primary,    # A — azul
    discord.ButtonStyle.success,    # B — verde
    discord.ButtonStyle.danger,     # C — rojo
    discord.ButtonStyle.secondary,  # D — gris
]
PAUSA_ENTRE_PREGUNTAS  = 2           # segundos entre preguntas
COLOR_TRIVIA           = 0x8B0000    # rojo oscuro / 7DTD style

# ─────────────────────────────────────────────
#  PERSISTENCIA JSON
# ─────────────────────────────────────────────
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR   = os.path.join(_BASE_DIR, "Cache")
TRIVIA_FILE  = os.path.join(_CACHE_DIR, "trivia_preguntas.json")
_PAGE_SIZE_G = 10    # preguntas por página en el panel de gestión


def _trivia_load_raw() -> list[dict]:
    """Lee el JSON directamente (devuelve lista o [] si no existe)."""
    if not os.path.exists(TRIVIA_FILE):
        return []
    with open(TRIVIA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _trivia_save(preguntas: list[dict]) -> None:
    """Guarda y resetea el pool de rotación para evitar índices obsoletos."""
    global _usadas
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(TRIVIA_FILE, "w", encoding="utf-8") as f:
        json.dump(preguntas, f, ensure_ascii=False, indent=2)
    _usadas = set()


def _trivia_init() -> None:
    """
    Llamar en setup().
    • Si el JSON aún no existe: exporta las preguntas hardcoded.
    • Siempre carga el JSON en PREGUNTAS (in-place para que los imports sean válidos).
    """
    if not os.path.exists(TRIVIA_FILE):
        exportar = [
            {
                "pregunta": p["pregunta"],
                "opciones": list(p["opciones"]),   # tupla → lista para JSON
                "correcta": p["correcta"],
            }
            for p in _PREGUNTAS_DEFAULT
        ]
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(TRIVIA_FILE, "w", encoding="utf-8") as f:
            json.dump(exportar, f, ensure_ascii=False, indent=2)

    cargadas = _trivia_load_raw()
    PREGUNTAS.clear()
    PREGUNTAS.extend(cargadas)
    print(f"✅ [Trivia] {len(PREGUNTAS)} preguntas cargadas desde JSON.")

# ─────────────────────────────────────────────
#  BANCO DE PREGUNTAS  — DEFAULT (se exporta a JSON al primer arranque)
#  Tras el inicio, PREGUNTAS se carga siempre desde trivia_preguntas.json
# ─────────────────────────────────────────────
# correcta → índice 0-based de la tupla de opciones
_PREGUNTAS_DEFAULT: list[dict] = [
    {
        "pregunta": "¿Cada cuántos días ocurre la Luna de Sangre en configuración predeterminada?",
        "opciones": ("3 días", "5 días", "7 días", "14 días"),
        "correcta": 2,
    },
    {
        "pregunta": "¿Cuál es la moneda principal para comerciar con los mercaderes?",
        "opciones": ("Caps de botella", "Dukes Casino Token", "Lingotes de oro", "Créditos"),
        "correcta": 1,
    },
    {
        "pregunta": "¿En qué estado de EE.UU. está ambientado el mapa Navezgane?",
        "opciones": ("Nevada", "Texas", "Arizona", "California"),
        "correcta": 2,
    },
    {
        "pregunta": "¿Qué bioma presenta el mayor nivel de peligro?",
        "opciones": ("Bosque de Pino", "Bosque Quemado", "Nevada", "Tierra Baldía"),
        "correcta": 3,
    },
    {
        "pregunta": "¿Cómo se llama la marca ficticia de armas de fuego del juego?",
        "opciones": ("Iron Sights Co.", "Shotgun Messiah", "Gun Runner", "Desert Arms"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Qué material es superior al Hierro Forjado?",
        "opciones": ("Adoquin reforzado", "Acero Forjado", "Madera tratada", "Titanio"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Cuál de estos Minerales No Es de 7 days to die?",
        "opciones": ("Hierro", "Plomo", "Cobre", "Carbon"),
        "correcta": 2,
    },
    {
        "pregunta": "¿Qué atributo mejora la velocidad de movimiento y el parkour?",
        "opciones": ("Fuerza", "Agilidad", "Percepción", "Intelecto"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Qué perk incrementa el peso máximo transportable?",
        "opciones": ("Lucky Looter", "Pack Mule", "Run and Gun", "Daring Adventurer"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Cuál de estos Traders esta ubicado en Bosque Quemado?",
        "opciones": ("Rekt", "Jen", "Bob", "Hugh"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Cuántos puntos de habilidad se obtienen al subir de nivel?",
        "opciones": ("1", "2", "3", "5"),
        "correcta": 0,
    },
    {
        "pregunta": "¿Cómo se llama el mapa generado de forma procedural (no fijo)?",
        "opciones": ("Navezgane", "Mundo Aleatorio", "Modo Aventura", "Sandbox"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Qué herramienta es la más eficiente para cavar tierra y arena?",
        "opciones": ("Pico", "Hacha", "Pala", "Azadón"),
        "correcta": 2,
    },
    {
        "pregunta": "¿Con qué material básico se fabrican vendas (Bandages) al inicio?",
        "opciones": ("Trozo de Tela", "Cuero", "Algodón", "Fibra de Planta"),
        "correcta": 0,
    },
    {
        "pregunta": "¿Qué tipo de munición utiliza las Ametralladoras (Machine Guns)?",
        "opciones": ("Balas de Escopeta", "Flechas", "Balas 7.62mm", "Balas 9mm"),
        "correcta": 2,
    },
    {
        "pregunta": "¿Qué POI Encontraras Super maiz el 100% de veces?",
        "opciones": ("Pop-N-Pills Factory", "Bob's Boars & Carl's Corn", "NDC Checkpoin Three", "Grover High"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Qué debuff provoca estar mucho tiempo bajo la lluvia sin protección?",
        "opciones": ("Velocidad reducida", "Temperatura baja / riesgo de hipotermia", "Hambre acelerada", "Pérdida de stamina"),
        "correcta": 1,
    },
    {
        "pregunta": "¿Qué atributo potencia el daño con armas de dos manos como mazas?",
        "opciones": ("Fuerza", "Agilidad", "Resistencia", "Combate"),
        "correcta": 0,
    },
    {
        "pregunta": "¿Cuál de estos animales NO existe en el juego base de 7 Days to Die?",
        "opciones": ("Lobo", "Oso", "Ciervo (Deer)", "Cocodrilo"),
        "correcta": 3,
    },
    {
        "pregunta": "¿Qué acción realiza el zombie 'Spider' (Araña) que lo diferencia de los demás?",
        "opciones": ("Explota al morir", "Saltar hacia el jugador", "Lanza proyectiles", "Es invisible"),
        "correcta": 1,
    },
    {
        "pregunta": "¿En qué categoría del menú de crafteo se encuentran las trampas?",
        "opciones": ("Herramientas", "Equipamiento", "Construcción / Trampas", "Recursos"),
        "correcta": 2,
    },
    {
        "pregunta": "¿Cómo se llama el sistema de progresión principal del juego?",
        "opciones": ("Árbol de talentos", "Sistema de Habilidades y Perks", "Clases de personaje", "Sistema de experiencia lineal"),
        "correcta": 1,
    },
]

# Lista viva: se puebla desde JSON en _trivia_init() (llamado en setup)
# Los imports de otros módulos apuntan a este objeto; mútalo in-place.
PREGUNTAS: list[dict] = []

# ─────────────────────────────────────────────
#  ROTACIÓN DE PREGUNTAS
#  No se repiten hasta que pasan todas
# ─────────────────────────────────────────────
_usadas: set[int] = set()

def _elegir_preguntas() -> list[dict]:
    global _usadas
    total      = len(PREGUNTAS)
    disponibles = [i for i in range(total) if i not in _usadas]

    # Si quedan menos que las necesarias, resetear el pool
    if len(disponibles) < PREGUNTAS_POR_JUEGO:
        _usadas     = set()
        disponibles = list(range(total))

    elegidas = random.sample(disponibles, PREGUNTAS_POR_JUEGO)
    _usadas.update(elegidas)
    return [PREGUNTAS[i] for i in elegidas]

# ─────────────────────────────────────────────
#  EMBEDS
# ─────────────────────────────────────────────
def _barra_tiempo(restantes: int, total: int) -> str:
    BLOQUES = 18
    llenos  = max(0, round((restantes / total) * BLOQUES))
    vacios  = BLOQUES - llenos
    barra   = "█" * llenos + "░" * vacios
    return f"`{barra}` **{restantes}s**"

def _embed_pregunta(num: int, q: dict, restantes: int = None) -> discord.Embed:
    if restantes is None:
        restantes = TIEMPO_PREGUNTA
    opciones_txt = "\n".join(
        f"**{LETRAS[i]}.** {op}"
        for i, op in enumerate(q["opciones"])
    )
    embed = discord.Embed(
        title=f"🧟 Trivia 7 Days to Die  —  Pregunta {num}/{PREGUNTAS_POR_JUEGO}",
        description=f"**{q['pregunta']}**\n\n{opciones_txt}",
        color=COLOR_TRIVIA,
    )
    embed.add_field(
        name="⏱️ Tiempo restante",
        value=_barra_tiempo(restantes, TIEMPO_PREGUNTA),
        inline=False,
    )
    embed.set_footer(text="Pulsa tu respuesta abajo • Solo puedes responder una vez")
    return embed

def _embed_resultados(
    preguntas: list[dict],
    resp_por_pregunta: list[dict],
    aciertos: dict,
    ganadores: set[int],
    participantes_nombres: dict,
) -> discord.Embed:

    # ── Construir scoreboard ordenado ────────────────────────────────
    scoreboard = sorted(aciertos.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆  Resultados de la Trivia  🏆",
        description=(
            "─────────────────────────────────────\n"
            "Aquí van las respuestas correctas y quién las acertó."
        ),
        color=0xFFD700,
    )

    # ── Una fila por pregunta (inline=False para que ocupen todo el ancho) ──
    MEDALLAS = ["🥇", "🥈", "🥉"]

    # ── Una fila por pregunta ─────────────────────────────────────────
    lines_preguntas = []
    for i, q in enumerate(preguntas):
        correcta_idx   = q["correcta"]
        correcta_txt   = q["opciones"][correcta_idx]
        correcta_letra = LETRAS[correcta_idx]
        lines_preguntas.append(
            f"**P{i + 1}.** {q['pregunta']}\n"
            f"  ✅ {correcta_letra}. {correcta_txt}"
        )

    embed.add_field(
        name="📋 Respuestas correctas",
        value="\n".join(lines_preguntas),
        inline=False,
    )

    # ── Separador visual ─────────────────────────────────────────────
    embed.add_field(name="\u200b", value="─────────────────────────────────────", inline=False)

    # ── Scoreboard ───────────────────────────────────────────────────
    if scoreboard:
        lines = []
        for rank, (uid, total) in enumerate(scoreboard):
            medalla  = MEDALLAS[rank] if rank < 3 else "▸"
            nombre   = participantes_nombres.get(uid, f"<@{uid}>")
            estrellas = "⭐" * total + "☆" * (PREGUNTAS_POR_JUEGO - total)
            lines.append(f"{medalla} **{nombre}** — {total}/{PREGUNTAS_POR_JUEGO}  {estrellas}")
        embed.add_field(
            name="📊  Puntuaciones",
            value="\n".join(lines),
            inline=False,
        )

    # ── Ganadores ────────────────────────────────────────────────────
    if ganadores:
        ganadores_txt = "  •  ".join(
            f"🎖️ {participantes_nombres.get(uid, f'<@{uid}>')}" for uid in ganadores
        )
        embed.add_field(
            name=f"🎁  Premio  —  ≥{MINIMO_ACIERTOS_PREMIO} aciertos",
            value=f"{ganadores_txt}\n*¡Pulsa el botón para reclamar tu regalo!*",
            inline=False,
        )
    else:
        embed.add_field(
            name="🎁  Premio",
            value="*Nadie alcanzó el mínimo de aciertos esta vez. ¡A estudiar!*",
            inline=False,
        )

    embed.set_footer(text="7 Days to Die • Trivia  •  ¡Gracias por participar!")
    return embed

# ─────────────────────────────────────────────
#  VIEW — BOTONES DE RESPUESTA POR PREGUNTA
# ─────────────────────────────────────────────
class OpcionButton(discord.ui.Button):
    def __init__(self, idx: int, texto: str):
        label = f"{LETRAS[idx]}. {texto}" if len(texto) <= 60 else f"{LETRAS[idx]}. {texto[:57]}…"
        super().__init__(
            label=label,
            style=COLORES_OPCIONES[idx],
            row=idx // 2,   # A/B en fila 0, C/D en fila 1
        )
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: PreguntaView = self.view  # type: ignore

        uid      = interaction.user.id
        ya_tenia = uid in view.respuestas

        # Si el usuario pulsa exactamente la misma opción que ya tenía, avisarle
        if ya_tenia and view.respuestas[uid] == self.idx:
            return await interaction.response.send_message(
                "🎯 Ya tienes esa opción registrada.",
                ephemeral=True,
            )

        view.respuestas[uid] = self.idx
        view.nombres[uid]    = interaction.user.display_name

        msg = (
            f"🔄 Respuesta cambiada a **{LETRAS[self.idx]}**."
            if ya_tenia else
            f"🎯 Opción **{LETRAS[self.idx]}** registrada."
        )
        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.errors.NotFound:
            # Interacción expirada (pérdida de red) — la respuesta ya fue guardada
            try:
                await interaction.followup.send(
                    "⚠️ Tu respuesta fue registrada pero hubo un problema de conexión. "
                    "Si no la ves confirmada, vuelve a pulsar tu opción.",
                    ephemeral=True,
                )
            except Exception:
                pass  # nada más que hacer si el followup también falla
        except Exception:
            try:
                await interaction.followup.send(
                    "⚠️ Hubo un problema al confirmar tu respuesta. Inténtalo de nuevo.",
                    ephemeral=True,
                )
            except Exception:
                pass


class PreguntaView(discord.ui.View):
    def __init__(self, q: dict):
        super().__init__(timeout=None)   # el tick task controla el tiempo
        self.correcta_idx = q["correcta"]
        self.respuestas:  dict[int, int] = {}
        self.nombres:     dict[int, str] = {}

        for i, opcion in enumerate(q["opciones"]):
            self.add_item(OpcionButton(i, opcion))

    def resultados(self) -> dict[int, bool]:
        """Devuelve {user_id: correcto}."""
        return {
            uid: (idx == self.correcta_idx)
            for uid, idx in self.respuestas.items()
        }


# ─────────────────────────────────────────────
#  VIEW — BOTÓN DE REGALO
# ─────────────────────────────────────────────
class PremioView(discord.ui.View):
    def __init__(self, ganadores: set[int], bot_user):
        super().__init__(timeout=None)
        self.ganadores  = ganadores
        self.bot_user   = bot_user
        self.reclamados: set[int] = set()

    @discord.ui.button(label="🎁 Recibir regalo", style=discord.ButtonStyle.success)
    async def recibir(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id

        if uid in self.reclamados:
            if uid in self.ganadores:
                return await interaction.response.send_message(
                    "Ya reclamaste tu regalo. 😊", ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    "¡Ya te dije que no ganaste! 😤", ephemeral=True
                )
        # Deferir ANTES de cualquier operación lenta (Discord expira en 3s)
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            # Token expirado — el usuario tardó >3s; no se puede hacer nada
            return

        if uid in self.ganadores:
            self.reclamados.add(uid)
            tag      = random.choice(["hug", "pat"])
            gif_info = nekos_cache.obtener_gif(tag)
            data     = INTERACCIONES.get(tag)
            frase    = data[1] if data else "abraza a"
            titulo   = (
                f"{self.bot_user.display_name} {frase} "
                f"{interaction.user.display_name}. 🎁"
            )
            if gif_info:
                embed, gif_file = make_embed(titulo, gif_info)
                if gif_file:
                    await interaction.followup.send(embed=embed, file=gif_file)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(f"🎁 {titulo}")

        else:
            self.reclamados.add(uid)   # marcar para que "ya te dije" funcione la próxima vez
            # No merece premio → golpe con gif
            tag      = random.choice(["slap", "punch", "bonk"])
            gif_info = nekos_cache.obtener_gif(tag)
            data     = INTERACCIONES.get(tag)
            frase    = data[1] if data else "golpea a"
            titulo   = (
                f"¡{self.bot_user.display_name} {frase} "
                f"{interaction.user.display_name}! ¡NO RECIBES PREMIO! 🚫"
            )
            if gif_info:
                embed, gif_file = make_embed(titulo, gif_info)
                if gif_file:
                    await interaction.followup.send(embed=embed, file=gif_file)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(
                    f"👊 ¡NO RECIBES PREMIO! {interaction.user.mention}"
                )

# ─────────────────────────────────────────────
#  COG
# ─────────────────────────────────────────────
class TriviaCog(commands.Cog, name="Trivia"):
    def __init__(self, bot: commands.Bot):
        self.bot     = bot
        self._activa: set[int] = set()   # guild_ids con trivia en curso

    # ── Comando principal ─────────────────────
    @commands.command(name="trivia")
    @commands.guild_only()
    async def cmd_trivia(self, ctx: commands.Context):
        """Inicia una sesión de trivia de 7 Days to Die."""

        if ctx.guild.id in self._activa:
            return await ctx.send(
                "⚠️ Ya hay una trivia en curso en este servidor. ¡Espera a que termine!"
            )

        self._activa.add(ctx.guild.id)
        try:
            await self._ejecutar_trivia(ctx)
        finally:
            self._activa.discard(ctx.guild.id)

    # ── Comando de gestión !triviaG ───────────
    @commands.command(name="triviaG")
    @commands.guild_only()
    async def cmd_trivia_g(self, ctx: commands.Context):
        """Panel de gestión del banco de preguntas (solo mods/admins)."""
        if not _es_privilegiado(ctx.author):
            return   # silencio total para los demás

        total = len(PREGUNTAS)
        embed = discord.Embed(
            title="🧟 Gestión de Trivia — Banco de Preguntas",
            description=(
                "Panel de gestión de las preguntas de la trivia de **7 Days to Die**.\n\n"
                f"📋 **{total}** pregunta(s) registradas en el banco.\n"
                f"🎮 Se usan **{PREGUNTAS_POR_JUEGO}** por partida con rotación automática.\n"
                f"💾 Las preguntas se guardan en `Cache/trivia_preguntas.json`.\n\n"
                "Pulsa el botón para abrir el panel de gestión completo."
            ),
            color=COLOR_TRIVIA,
        )
        embed.set_footer(text="El panel es visible solo para ti (efímero) • Miner7days")
        await ctx.send(embed=embed, view=TriviaGPublicView())
        # FIN de cmd_trivia_g — NO continúa al juego

    # ── Lógica interna del juego ──────────────
    async def _ejecutar_trivia(self, ctx: commands.Context):
        preguntas = _elegir_preguntas()

        # ── Embed de inicio ───────────────────
        inicio_embed = discord.Embed(
            title="🧟 ¡Trivia de 7 Days to Die!",
            description=(
                f"Comenzamos en **3 segundos**.\n\n"
                f"📋 **{PREGUNTAS_POR_JUEGO} preguntas** de opción múltiple.\n"
                f"⏱️ **{TIEMPO_PREGUNTA} segundos** por pregunta.\n"
                f"🎁 Acierta **{MINIMO_ACIERTOS_PREMIO} o más** para recibir un regalo.\n\n"
                f"Pulsa el botón con tu respuesta. ¡Solo puedes responder una vez por pregunta!"
            ),
            color=COLOR_TRIVIA,
        )
        inicio_embed.set_footer(text="7 Days to Die • Trivia")
        inicio_msg = await ctx.send(embed=inicio_embed)
        await asyncio.sleep(3)
        try:
            await inicio_msg.delete()
        except Exception:
            pass

        # ── Tracking ──────────────────────────
        resp_por_pregunta: list[dict[int, bool]] = []
        aciertos: dict[int, int]                 = {}
        nombres:  dict[int, str]                 = {}

        # ── Rondas de preguntas ───────────────
        for i, q in enumerate(preguntas):
            view  = PreguntaView(q)
            embed = _embed_pregunta(i + 1, q)
            msg   = await ctx.send(embed=embed, view=view)

            async def _tick(msg=msg, embed=embed, view=view):
                for restantes in range(TIEMPO_PREGUNTA - 2, -1, -2):
                    await asyncio.sleep(2)
                    if view.is_finished():
                        return
                    if restantes > 0:
                        embed.set_field_at(
                            0,
                            name="⏱️ Tiempo restante",
                            value=_barra_tiempo(restantes, TIEMPO_PREGUNTA),
                            inline=False,
                        )
                        try:
                            await msg.edit(embed=embed)
                        except Exception:
                            pass
                # Tiempo agotado: parar view y borrar mensaje de inmediato
                view.stop()
                try:
                    await msg.delete()
                except Exception:
                    pass

            asyncio.create_task(_tick())

            # Espera hasta que el tick llame a view.stop()
            await view.wait()

            # Recoger resultados del view
            respuestas = view.resultados()
            resp_por_pregunta.append(respuestas)

            # Actualizar aciertos y nombres
            for uid, correcto in respuestas.items():
                aciertos[uid] = aciertos.get(uid, 0) + (1 if correcto else 0)
            nombres.update(view.nombres)

            if i < PREGUNTAS_POR_JUEGO - 1:
                await asyncio.sleep(PAUSA_ENTRE_PREGUNTAS)

        # ── Evaluación ────────────────────────
        eval_msg = await ctx.send("🔍 **Evaluando respuestas...**")
        await asyncio.sleep(2)
        try:
            await eval_msg.delete()
        except Exception:
            pass

        # ── Ganadores ─────────────────────────
        ganadores = {
            uid for uid, total in aciertos.items()
            if total >= MINIMO_ACIERTOS_PREMIO
        }

        # ── Embed de resultados ───────────────
        results_embed = _embed_resultados(
            preguntas, resp_por_pregunta, aciertos, ganadores, nombres
        )
        view = PremioView(ganadores, self.bot.user)
        await ctx.send(embed=results_embed, view=view)

# ═════════════════════════════════════════════════════════════════════
#  TRIVIAГ — HELPERS
# ═════════════════════════════════════════════════════════════════════

def _es_privilegiado(member: discord.Member) -> bool:
    """True si es admin, manage_guild o manage_roles."""
    p = member.guild_permissions
    return p.administrator or p.manage_guild or p.manage_roles


def _pregunta_detalle_embed(idx: int, q: dict) -> discord.Embed:
    """Embed que muestra la pregunta con la opción correcta resaltada."""
    embed = discord.Embed(
        title=f"📝 Pregunta #{idx + 1}",
        description=f"**{q['pregunta']}**",
        color=COLOR_TRIVIA,
    )
    lineas = []
    for i, op in enumerate(q["opciones"]):
        if i == q["correcta"]:
            lineas.append(f"**{LETRAS[i]}.** {op}  ✅")
        else:
            lineas.append(f"**{LETRAS[i]}.** {op}")
    embed.add_field(name="🗂️ Opciones", value="\n".join(lineas), inline=False)
    embed.set_footer(text=f"Índice interno {idx} • Miner7days • Trivia")
    return embed


def _panel_embed(page: int, pages: int) -> discord.Embed:
    total = len(PREGUNTAS)
    start = page * _PAGE_SIZE_G
    chunk = PREGUNTAS[start: start + _PAGE_SIZE_G]

    embed = discord.Embed(
        title="⚙️ Gestión de Trivia — Banco de Preguntas",
        color=COLOR_TRIVIA,
    )
    embed.add_field(
        name="📊 Estado",
        value=(
            f"📋 **{total}** preguntas en el banco  •  "
            f"🎮 **{PREGUNTAS_POR_JUEGO}** por partida  •  "
            f"📄 Pág. **{page + 1}/{pages}**"
        ),
        inline=False,
    )
    if chunk:
        # Dos líneas por pregunta: texto completo + opción correcta debajo
        # 10 preguntas × ~100 chars promedio = ~1000 chars → dentro de 1024
        lineas = []
        for i, q in enumerate(chunk):
            num     = start + i + 1
            texto   = q["pregunta"]
            letra   = LETRAS[q["correcta"]]
            correcta = q["opciones"][q["correcta"]]
            lineas.append(f"`#{num:>3}` {texto}\n　　✅ **{letra}.** {correcta}")
        valor = "\n".join(lineas)
        # Salvaguarda: si aun así supera 1024, partir en dos fields
        if len(valor) <= 1024:
            embed.add_field(
                name=f"📝 Preguntas — pág. {page + 1}",
                value=valor,
                inline=False,
            )
        else:
            mitad = len(lineas) // 2
            embed.add_field(
                name=f"📝 Preguntas — pág. {page + 1} (1/2)",
                value="\n".join(lineas[:mitad]),
                inline=False,
            )
            embed.add_field(
                name=f"📝 Preguntas — pág. {page + 1} (2/2)",
                value="\n".join(lineas[mitad:]),
                inline=False,
            )
    else:
        embed.add_field(
            name="❌ Sin preguntas",
            value="El banco está vacío. Pulsa **➕ Agregar pregunta** para añadir la primera.",
            inline=False,
        )
    embed.set_footer(text="Selecciona una pregunta del menú para ver sus detalles • Miner7days")
    return embed


# ═════════════════════════════════════════════════════════════════════
#  TRIVIAГ — MODALES
# ═════════════════════════════════════════════════════════════════════

class AgregarModal(discord.ui.Modal, title="➕ Nueva pregunta de Trivia"):
    pregunta = discord.ui.TextInput(
        label="Pregunta",
        placeholder="¿Cuántos días tiene la Luna de Sangre en configuración predeterminada?",
        min_length=5,
        max_length=200,
    )
    op_a = discord.ui.TextInput(label="Opción A", max_length=100)
    op_b = discord.ui.TextInput(label="Opción B", max_length=100)
    op_c = discord.ui.TextInput(label="Opción C", max_length=100)
    op_d = discord.ui.TextInput(label="Opción D", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return

        opciones = [
            self.op_a.value.strip(),
            self.op_b.value.strip(),
            self.op_c.value.strip(),
            self.op_d.value.strip(),
        ]
        pregunta_text = self.pregunta.value.strip()

        view  = CorrectaSelectView(pregunta_text, opciones, idx_edit=None)
        embed = discord.Embed(
            title="✅ ¿Cuál es la respuesta correcta?",
            description=(
                f"**{pregunta_text}**\n\n"
                + "\n".join(f"**{LETRAS[i]}.** {op}" for i, op in enumerate(opciones))
            ),
            color=COLOR_TRIVIA,
        )
        embed.set_footer(text="Elige la opción correcta para guardar la pregunta.")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class EditarPreguntaModal(discord.ui.Modal, title="✏️ Editar texto de pregunta"):
    pregunta = discord.ui.TextInput(label="Pregunta", min_length=5, max_length=200)

    def __init__(self, idx: int, q: dict):
        super().__init__()
        self._idx       = idx
        self.pregunta.default = q["pregunta"]

    async def on_submit(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return
        if self._idx >= len(PREGUNTAS):
            await interaction.response.send_message("❌ Pregunta no encontrada.", ephemeral=True)
            return

        PREGUNTAS[self._idx]["pregunta"] = self.pregunta.value.strip()
        _trivia_save(PREGUNTAS)

        embed = _pregunta_detalle_embed(self._idx, PREGUNTAS[self._idx])
        embed.color = 0x00CC66
        embed.set_footer(text="✅ Pregunta actualizada • Pulsa 🔄 Actualizar en el panel para ver el cambio")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EditarOpcionesModal(discord.ui.Modal, title="🔤 Editar opciones"):
    op_a = discord.ui.TextInput(label="Opción A", max_length=100)
    op_b = discord.ui.TextInput(label="Opción B", max_length=100)
    op_c = discord.ui.TextInput(label="Opción C", max_length=100)
    op_d = discord.ui.TextInput(label="Opción D", max_length=100)

    def __init__(self, idx: int, q: dict):
        super().__init__()
        self._idx       = idx
        self._pregunta  = q["pregunta"]
        self.op_a.default = q["opciones"][0]
        self.op_b.default = q["opciones"][1]
        self.op_c.default = q["opciones"][2]
        self.op_d.default = q["opciones"][3]

    async def on_submit(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            await interaction.response.send_message("🔒 Sin permisos.", ephemeral=True)
            return

        opciones = [
            self.op_a.value.strip(),
            self.op_b.value.strip(),
            self.op_c.value.strip(),
            self.op_d.value.strip(),
        ]
        if self._idx >= len(PREGUNTAS):
            await interaction.response.send_message("❌ Pregunta no encontrada.", ephemeral=True)
            return

        # Mantiene el índice correcto actual — para cambiarlo está "Editar opción correcta"
        correcta_actual = PREGUNTAS[self._idx]["correcta"]
        PREGUNTAS[self._idx]["opciones"] = opciones
        _trivia_save(PREGUNTAS)

        embed = _pregunta_detalle_embed(self._idx, PREGUNTAS[self._idx])
        embed.color = 0x00CC66
        embed.set_footer(text="✅ Opciones actualizadas • Pulsa 🔄 Actualizar en el panel")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═════════════════════════════════════════════════════════════════════
#  TRIVIAГ — VIEWS
# ═════════════════════════════════════════════════════════════════════

class CorrectaSelectView(discord.ui.View):
    """
    Select A/B/C/D para elegir la respuesta correcta.
    Se usa tanto al agregar (idx_edit=None) como al editar opciones (idx_edit=int).
    """

    def __init__(self, pregunta: str, opciones: list[str], idx_edit: int | None):
        super().__init__(timeout=None)
        self._pregunta  = pregunta
        self._opciones  = opciones
        self._idx_edit  = idx_edit

        sel = discord.ui.Select(
            placeholder="Elige cuál es la opción correcta…",
            options=[
                discord.SelectOption(
                    label=f"{LETRAS[i]}. {op[:90]}",
                    value=str(i),
                    description=f"Marcar como opción correcta",
                    emoji=LETRAS[i][0] if False else None,
                )
                for i, op in enumerate(opciones)
            ],
        )
        sel.callback = self._on_select
        self.add_item(sel)

    async def _on_select(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()

        correcta_idx = int(interaction.data["values"][0])

        if self._idx_edit is None:
            # ── Agregar nueva pregunta ──────────────────────────────
            nueva = {
                "pregunta": self._pregunta,
                "opciones": self._opciones,
                "correcta": correcta_idx,
            }
            PREGUNTAS.append(nueva)
            _trivia_save(PREGUNTAS)
            idx_nuevo = len(PREGUNTAS) - 1

            embed = _pregunta_detalle_embed(idx_nuevo, nueva)
            embed.color = 0x00CC66
            embed.title = f"✅ Pregunta #{idx_nuevo + 1} añadida"
            embed.set_footer(text="Guardada • Pulsa 🔄 Actualizar en el panel para verla")
        else:
            # ── Cambiar opción correcta ────────────────────────────
            if self._idx_edit >= len(PREGUNTAS):
                await interaction.response.send_message("❌ Pregunta no encontrada.", ephemeral=True)
                return
            PREGUNTAS[self._idx_edit]["correcta"] = correcta_idx
            _trivia_save(PREGUNTAS)

            letra_elegida  = LETRAS[correcta_idx]
            texto_elegido  = self._opciones[correcta_idx]
            embed = _pregunta_detalle_embed(self._idx_edit, PREGUNTAS[self._idx_edit])
            embed.color = 0x00CC66
            embed.set_footer(
                text=f"✅ Opción correcta actualizada → {letra_elegida}. {texto_elegido}"
            )

        await interaction.response.edit_message(embed=embed, view=None)


class ConfirmarEliminarTriviaView(discord.ui.View):
    def __init__(self, idx: int, q: dict):
        super().__init__(timeout=None)
        self._idx = idx
        self._q   = q

    @discord.ui.button(label="✅ Confirmar eliminación", style=discord.ButtonStyle.danger, row=0)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()

        # Verificar que el índice sigue apuntando a la misma pregunta
        if (
            self._idx >= len(PREGUNTAS)
            or PREGUNTAS[self._idx]["pregunta"] != self._q["pregunta"]
        ):
            await interaction.response.send_message(
                "❌ Pregunta no encontrada o ya eliminada.", ephemeral=True
            )
            return

        eliminada = PREGUNTAS.pop(self._idx)
        _trivia_save(PREGUNTAS)

        embed = discord.Embed(
            title="🗑️ Pregunta eliminada",
            description=(
                f"Se eliminó:\n**{eliminada['pregunta']}**\n\n"
                "Pulsa **🔄 Actualizar** en el panel para ver los cambios."
            ),
            color=0xFF6B6B,
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary, row=0)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❎ Cancelado.", embed=None, view=None)


class PreviewOpcionButton(discord.ui.Button):
    def __init__(self, idx: int, texto: str, correcta_idx: int):
        label = f"{LETRAS[idx]}. {texto}" if len(texto) <= 60 else f"{LETRAS[idx]}. {texto[:57]}…"
        super().__init__(label=label, style=COLORES_OPCIONES[idx], row=idx // 2)
        self.idx         = idx
        self.correcta_idx = correcta_idx

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"🎯 Opción **{LETRAS[self.idx]}** registrada.",
            ephemeral=True,
        )


class PreviewPreguntaView(discord.ui.View):
    """Vista de preview con botones funcionales igual que en partida real."""

    def __init__(self, q: dict):
        super().__init__(timeout=None)
        for i, opcion in enumerate(q["opciones"]):
            self.add_item(PreviewOpcionButton(i, opcion, q["correcta"]))


class DetallePreguntaView(discord.ui.View):
    """Embed efímero con una pregunta y sus botones de edición/eliminación."""

    def __init__(self, idx: int, q: dict):
        super().__init__(timeout=None)
        self._idx = idx
        self._q   = q

    @discord.ui.button(label="✏️ Editar pregunta", style=discord.ButtonStyle.primary, row=0)
    async def editar_pregunta(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        q = PREGUNTAS[self._idx] if self._idx < len(PREGUNTAS) else self._q
        await interaction.response.send_modal(EditarPreguntaModal(self._idx, q))

    @discord.ui.button(label="🔤 Editar opciones", style=discord.ButtonStyle.primary, row=0)
    async def editar_opciones(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        q = PREGUNTAS[self._idx] if self._idx < len(PREGUNTAS) else self._q
        await interaction.response.send_modal(EditarOpcionesModal(self._idx, q))

    @discord.ui.button(label="✅ Editar opción correcta", style=discord.ButtonStyle.success, row=0)
    async def editar_correcta(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        q = PREGUNTAS[self._idx] if self._idx < len(PREGUNTAS) else self._q
        correcta_actual = q["correcta"]
        opciones_txt = "\n".join(
            f"**{LETRAS[i]}.** {op}  ✅" if i == correcta_actual else f"**{LETRAS[i]}.** {op}"
            for i, op in enumerate(q["opciones"])
        )
        view  = CorrectaSelectView(q["pregunta"], list(q["opciones"]), idx_edit=self._idx)
        embed = discord.Embed(
            title="✅ Cambiar opción correcta",
            description=f"**{q['pregunta']}**\n\n{opciones_txt}",
            color=COLOR_TRIVIA,
        )
        embed.set_footer(text=f"Correcta actual: {LETRAS[correcta_actual]}. {q['opciones'][correcta_actual]}")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ Eliminar", style=discord.ButtonStyle.danger, row=0)
    async def eliminar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        q = PREGUNTAS[self._idx] if self._idx < len(PREGUNTAS) else self._q
        embed = discord.Embed(
            title="⚠️ Confirmar eliminación",
            description=(
                f"¿Eliminar esta pregunta?\n\n"
                f"**{q['pregunta']}**\n\n"
                "Esta acción **no se puede deshacer**."
            ),
            color=0xFF4444,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmarEliminarTriviaView(self._idx, q),
            ephemeral=True,
        )

    @discord.ui.button(label="🎮 Preview", style=discord.ButtonStyle.secondary, row=1)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        q = PREGUNTAS[self._idx] if self._idx < len(PREGUNTAS) else self._q
        embed = _embed_pregunta(1, q, restantes=TIEMPO_PREGUNTA)
        embed.title = "🎮 Preview — " + embed.title
        embed.set_footer(text="👁️ Vista previa — responde para probarla")
        view = PreviewPreguntaView(q)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class TriviaGPanelView(discord.ui.View):
    """
    Panel efímero principal de gestión.
    Select (15 por página) + Agregar + Actualizar + Paginación.
    Sin timeout.
    """

    def __init__(self, page: int = 0):
        super().__init__(timeout=None)
        self._page = page
        self._recalc()
        self._build()

    def _recalc(self):
        self._pages = max(1, (len(PREGUNTAS) + _PAGE_SIZE_G - 1) // _PAGE_SIZE_G)
        self._page  = min(self._page, self._pages - 1)

    def _build(self):
        self.clear_items()
        preguntas = PREGUNTAS
        start     = self._page * _PAGE_SIZE_G
        chunk     = preguntas[start: start + _PAGE_SIZE_G]

        # ── Row 0: Select de preguntas ──────────────────────────────
        if chunk:
            opciones = [
                discord.SelectOption(
                    label=f"#{start + i + 1}. {q['pregunta'][:70]}",
                    description=(
                        f"✅ {LETRAS[q['correcta']]}. "
                        f"{q['opciones'][q['correcta']][:50]}"
                    ),
                    value=str(start + i),
                    emoji="📝",
                )
                for i, q in enumerate(chunk)
            ]
            sel = discord.ui.Select(
                placeholder=f"📝 Selecciona una pregunta (pág. {self._page + 1})…",
                options=opciones,
                row=0,
            )
            sel.callback = self._on_select
            self.add_item(sel)
        else:
            dummy = discord.ui.Select(
                placeholder="📝 No hay preguntas aún…",
                options=[discord.SelectOption(label="—", value="none")],
                disabled=True,
                row=0,
            )
            self.add_item(dummy)

        # ── Row 1: Agregar + Actualizar ────────────────────────────
        agregar = discord.ui.Button(
            label="➕ Agregar pregunta",
            style=discord.ButtonStyle.success,
            row=1,
        )
        agregar.callback = self._on_agregar
        self.add_item(agregar)

        actualizar = discord.ui.Button(
            label="🔄 Actualizar",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        actualizar.callback = self._on_actualizar
        self.add_item(actualizar)

        # ── Row 2: Paginación (solo si hay más de una página) ──────
        if self._pages > 1:
            prev = discord.ui.Button(
                label="◀ Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=(self._page == 0),
                row=2,
            )
            prev.callback = self._on_prev
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
            nxt.callback = self._on_next
            self.add_item(nxt)

    # ── Callbacks ──────────────────────────────────────────────────

    async def _on_select(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()

        raw = interaction.data["values"][0]
        if raw == "none":
            return await interaction.response.defer()

        idx = int(raw)
        if idx >= len(PREGUNTAS):
            await interaction.response.send_message(
                "❌ Pregunta no encontrada. Pulsa **🔄 Actualizar**.", ephemeral=True
            )
            return

        q     = PREGUNTAS[idx]
        embed = _pregunta_detalle_embed(idx, q)
        view  = DetallePreguntaView(idx, q)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _on_agregar(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        await interaction.response.send_modal(AgregarModal())

    async def _on_actualizar(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        self._recalc()
        self._build()
        await interaction.response.edit_message(
            embed=_panel_embed(self._page, self._pages), view=self
        )

    async def _on_prev(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        self._page -= 1
        self._build()
        await interaction.response.edit_message(
            embed=_panel_embed(self._page, self._pages), view=self
        )

    async def _on_next(self, interaction: discord.Interaction):
        if not _es_privilegiado(interaction.user):
            return await interaction.response.defer()
        self._page += 1
        self._build()
        await interaction.response.edit_message(
            embed=_panel_embed(self._page, self._pages), view=self
        )


class TriviaGPublicView(discord.ui.View):
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
        panel = TriviaGPanelView()
        await interaction.response.send_message(
            embed=_panel_embed(panel._page, panel._pages),
            view=panel,
            ephemeral=True,
        )


# ─────────────────────────────────────────────
#  SETUP
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot):
    _trivia_init()          # exporta hardcoded → JSON si es la primera vez; carga siempre
    await bot.add_cog(TriviaCog(bot))