import io
import base64
import random
import discord
from discord.ui import Button, View
from discord.ext import commands
from status7d import nekos_cache

# ------------------------------------------------------------
# LISTAS DE RESPUESTAS (mensajes de texto que aparecen ARRIBA del primer embed)
# ------------------------------------------------------------
SALUDOS_BOT_TEXTO = [
    "¡Hola! 👋 Encantado de saludarte.",
    "¡Hey! Qué bueno verte por aquí. 😊",
    "¡Saludos, humano! ✨",
    "¡Wena wena! 👋",
    "¡Holi! ¿Cómo andas? :D"
]

GOLPES_BOT_TEXTO = [
    "¡Auch! Eso dolió... 😵",
    "¡Oye! ¿Por qué me pegas? 😭",
    "¡No soy saco de boxeo! 👊😠",
    "¡Devuelvo el golpe con un abrazo virtual! 🤗",
    "¡Agresión detectada! Voy a llamar a Kasiri. 🚨"
]

COLORES = [
    0xFF69B4, 0xFF6B6B, 0xFFA07A, 0xFFD700,
    0x98FB98, 0x87CEEB, 0xDDA0DD, 0xF0E68C,
    0xFF8C00, 0x00CED1, 0x9370DB, 0x3CB371
]
# Mapeo de tag -> (nombre_comando, frase_con_target, frase_pasado, label_boton, emoji, respuesta_bot, frase_sin_target)
INTERACCIONES = {
    # ── Ejemplo de cómo se usan los campos ───────────────────────────────────
    # frase_con_target : "{autor} {frase_con_target} {target}."   → "Fran está saludando a User."
    # frase_pasado     : "{user} {frase_pasado} a {autor}."       → "User devolvió el saludo a Fran."
    # frase_sin_target : "{autor} {frase_sin_target}."            → "Fran saluda a todos con entusiasmo."
    # ─────────────────────────────────────────────────────────────────────────
    "wave":      ("saludar",        "está saludando a",                    "devolvió el saludo a",                  "Devolver saludo",         "👋",  random.choice(SALUDOS_BOT_TEXTO),          "saluda a todos con entusiasmo"),
    "angry":     ("enfadar",        "está muy enfadado con",               "también se enfadó con",                 "¡Enfadarse de vuelta!",   "😠",  "¡Grrr! Hay que respirar hondo... 😤",      "echa humo de puro coraje sin razón aparente"),
    "baka":      ("baka",           "le llama baka a",                     "le devolvió el baka a",                 "¡Baka tú también!",       "🙄",  "¡Baka! Eso sí que ha dolido >_<",          "les grita baka a todos sin distinción"),
    "bite":      ("morder",         "le da un mordisco a",                 "le devolvió el mordisco a",             "¡Morder de vuelta!",      "🦷",  "¡Ay! ¿Eso fue un mordisco? 😣",            "muerde el aire con toda su alma"),
    "bleh":      ("bleh",           "le saca la lengua a",                 "le devolvió el gesto a",                "¡Bleh de vuelta!",        "😝",  "¡Bleh! Dos pueden jugar a eso. 😜",        "saca la lengua a quien quiera verlo"),
    "blowkiss":  ("lanzarbeso",     "le lanza un besito a",                "atrapó el besito de",                   "¡Lanzar beso!",           "😘",  "¡Oh! Un beso volador inesperado... 😳",    "lanza un beso al aire esperando que alguien lo atrape"),
    "blush":     ("sonrojar",       "se pone coloradísimo por",            "también se sonrojó por",                "¡Sonrojarse juntos!",     "😊",  "¡Ay, qué vergüenza! >///<",                "se pone rojo como un tomate"),
    "bonk":      ("bonk",           "le da un bonk en la cabeza a",        "le devolvió el bonk a",                 "¡Bonk de vuelta!",        "🏏",  "¡BONK! Eso te lo tenías merecido. 🏏",     "se bonkea a sí mismo por accidente"),
    "carry":     ("cargar",         "carga en brazos a",                   "se dejó cargar por",                    "¡Dejarse cargar!",        "🤝",  "¡Oh! Me estás cargando. Qué amable. 😄",   "intenta cargarse a sí mismo con resultados muy cuestionables"),
    "clap":      ("aplaudir",       "aplaude a",                           "aplaudió de vuelta a",                  "¡Aplaudir!",              "👏",  "¡Gracias! Aplausos recibidos. 👏",         "aplaude al vacío con todo el entusiasmo del mundo"),
    "confused":  ("confundir",      "está confundidísimo por culpa de",    "Quedo tambien confundido por",          "¡Confundir",              "🤔",  "Mmm... yo tampoco entiendo nada. 🤯",      "no entiende absolutamente nada de nada"),
    "cry":       ("llorar",         "llora en el hombro de",               "consoló con cariño a",                  "¡Consolar!",              "😢",  "No llores... estoy aquí contigo. 🥹",      "llora a mares sin saber muy bien por qué"),
    "cuddle":    ("acurrucar",      "se acurruca con",                     "se acurrucó de vuelta con",             "¡Acurrucarse!",           "🤗",  "¡Acurruquémonos juntos! 🥰",               "busca desesperadamente a alguien con quien acurrucarse"),
    "dance":     ("bailar",         "rompe a bailar con",                  "bailó junto a",                         "¡Bailar juntos!",         "💃",  "¡A bailar se ha dicho! 🎶",                "rompe a bailar de repente sin música ni razón"),
    "facepalm":  ("facepalm",       "se da un facepalm por culpa de",      "le dedicó otro facepalm a",             "¡Facepalm de vuelta!",    "🤦",  "Ay, la humanidad... 🤦",                   "se lleva la mano a la cara con una fuerza inquietante"),
    "feed":      ("alimentar",      "le da de comer a",                    "pidió más comida a",                    "¡Comer!",                 "🍔",  "¡Ñam ñam! Delicioso. 😋",                  "reparte comida a todo el que pasa por aquí"),
    "handhold":  ("tomarmano",      "toma de la mano a",                   "tomó la mano de vuelta de",             "¡Tomar de la mano!",      "🤝",  "Qué gesto tan bonito... 🥹",               "extiende la mano en el vacío buscando a alguien"),
    "handshake": ("saludomano",     "le da un apretón de manos a",         "le devolvió el apretón a",              "¡Apretón de manos!",      "🤝",  "¡Un placer conocerte! 🤝",                 "estrecha manos con absolutamente todo el servidor"),
    
    "highfive":  ("chocar",         "choca los cinco con",                 "chocó los cinco de vuelta con",         "¡Chocar los cinco!",      "🖐️",  "¡YEAH! Bien hecho. 🖐️",                   "deja la mano en el aire esperando a alguien que la choque"),
    "hug":       ("abrazar",        "le da un abrazo enorme a",            "devolvió el abrazo a",                  "¡Devolver abrazo!",       "🤗",  "¡Aww! Abrazo recibido con mucho amor. 🥰", "abre los brazos buscando a quien abrazar"),
    "kabedon":   ("kabedon",        "le hace un kabedon a",                "le hizo kabedon de vuelta a",           "¡Kabedon de vuelta!",     "🚪",  "¡Kyaa! >///<",                             "practica el kabedon contra la pared con total dedicación"),
    "kick":      ("patear",         "le pega una patada a",                "le devolvió la patada a",               "¡Patear de vuelta!",      "🦵",  "¡Ouch! ¿Por qué me pateas? 😭",            "patea el aire con toda la frustración del mundo"),
    "kiss":      ("besar",          "le planta un beso a",                 "devolvió el beso a",                    "¡Devolver beso!",         "💋",  "¡Oh! Un beso inesperado... 😳",             "besa el vacío con un sentimiento enorme"),
    "lappillow": ("almohada",       "usa las rodillas de",                 "ofreció las rodillas de vuelta a",      "¡Ofrecer rodillas!",      "😴",  "Zzz... qué cómodo. 💤",                    "busca unas rodillas cómodas en las que descansar"),
    "laugh":     ("reir",           "se ríe a carcajadas de",              "se rio también junto a",                "¡Reírse juntos!",         "😂",  "¡Jajaja! Eso tiene mucha gracia. 😆",      "suelta una carcajada sin ningún motivo aparente"),
    "lurk":      ("acechar",        "acecha sigilosamente a",              "notó que lo acechaban y volvió a acechar a", "¡Acechar de vuelta!", "👀", "Te estoy viendo... 👀",                   "acecha desde las sombras sin que nadie lo sepa"),
    "nod":       ("asentir",        "asiente ante",                        "asintió también ante",                  "¡Asentir!",               "🙂",  "Entendido. Así es. 🙂",                    "asiente lentamente en silencio sin decir nada más"),
    "nope":      ("nope",           "le dice que nope a",                  "también le dijo nope a",                "¡Nope de vuelta!",        "🙅",  "Nope. Nope. Nope. 🙅",                     "niega con la cabeza sin dar más explicaciones"),
    "nya":       ("nya",            "le dice nya a",                       "le contestó nya a",                     "¡Nyaa de vuelta!",        "😺",  "¡Nyaa~! ฅ^•ﻌ•^ฅ",                         "maúlla al servidor entero sin vergüenza alguna"),
    "pat":       ("acariciar",      "le acaricia la cabeza a",             "ronroneó y acarició de vuelta a",       "¡Ronronear!",             "👋",  "Qué suave... ☺️ Sigo aquí.",               "acaricia el aire buscando a alguien con quien compartirlo"),
    "peck":      ("picotear",       "le da un piquito a",                  "devolvió el piquito a",                 "¡Piquito de vuelta!",     "🐦",  "Un piquito... qué tierno. 🥹",             "reparte piquitos a diestra y siniestra"),
    "poke":      ("tocar",          "le hace boop a",                      "le hizo boop de vuelta a",              "¡Boop de vuelta!",        "👉",  "Boop recibido. 👉",                        "hace boop a todo lo que se le pone por delante"),
    "pout":      ("puchero",        "le hace puchero a",                   "no pudo resistir el puchero de",        "¡Rendirse al puchero!",   "😕",  "No te enfades conmigo... 🥺",              "pone cara de puchero sin dirigirse a nadie en concreto"),
    "punch":     ("golpear",        "le da un puñetazo a",                 "golpeó de vuelta a",                    "¡Golpear de vuelta!",     "👊",  random.choice(GOLPES_BOT_TEXTO),            "golpea el aire como si le debiera dinero"),
    "run":       ("correr",         "sale corriendo de ",                  "salio corriendo detras de",                "¡Perseguir!",         "🏃",  "¡Corre! ¡Que te alcanzo! 💨",              "sale disparado a toda velocidad sin mirar atrás"),
    "salute":    ("saludomilitar", "le hace el saludo militar a",         "devolvió el saludo militar a",          "¡Saludo militar!",        "🫡",  "¡A sus órdenes, sargento! 🫡",             "saluda militarmente al servidor entero"),
    "shake":     ("agitar",         "agita frenéticamente a",              "aguantó el mareo y agitó de vuelta a",  "¡Agitar de vuelta!",      "🤝",  "¡Me mareas! 😵‍💫",                         "se agita solo como si lo hubiera agarrado un terremoto"),
    "shoot":     ("disparar",       "le dispara a",                        "esquivó la bala y disparó de vuelta a", "¡Disparar de vuelta!",    "🔫",  "¡Bang! Por suerte soy digital. 😅",         "dispara al aire sin apuntar a absolutamente nadie"),
    "shocked":   ("sorprender",     "deja con la boca abierta a",          "también se quedó sin palabras por",     "¡Sorprenderse!",          "😲",  "¡Increíble! No me lo esperaba. 😱",         "se queda en shock de repente sin razón aparente"),
    "shrug":     ("encogerse",      "se encoge de hombros ante",           "también se encogió de hombros con",     "¡Encogerse juntos!",      "🤷",  "No sé qué decirte... 🤷",                  "no sabe, no contesta y se encoge de hombros"),
    "slap":      ("abofetear",      "le da una bofetada a",                "devolvió la bofetada a",                "¡Bofetada de vuelta!",    "🖐️",  "¡AU! Eso ha dolido de verdad. 😵",          "abofetea el aire con toda la energía que tiene"),
    "sleep":     ("dormir",         "se queda dormido encima de",          "arropó dulcemente a",                   "¡Arropar!",               "😴",  "Shhh... que duerme. 💤",                   "se queda frito en el sitio sin previo aviso"),
    "smile":     ("sonreir",        "le dedica una sonrisa a",             "le sonrió de vuelta a",                 "¡Sonreír de vuelta!",     "😊",  "Qué sonrisa más bonita. 😊",               "sonríe a todo el mundo sin ningún motivo concreto"),
    "smug":      ("presumir",       "mira con superioridad a",             "le devolvió la mirada a",               "¡Devolver la mirada!",    "😏",  "Hmph. Qué gracioso. 😒",                   "sonríe con suficiencia sin dirigirse a nadie en concreto"),
    "stare":     ("mirar",          "mira fijamente a",                    "le sostuvo la mirada a",                "¡Mirar de vuelta!",       "👀",  "¿Qué? ¿Tengo algo en la cara? 👀",         "mira fijamente al vacío como si viera algo que nadie más ve"),
    "tableflip": ("voltearmesa",    "voltea la mesa por culpa de",         "también volteó la mesa junto a",        "¡Voltear Mesa!",        "💢",  "(╯°□°）╯︵ ┻━┻  ¡Toma ya! 😤",            "voltea la mesa de pura desesperación existencial"),
    "tee   hee":    ("teehee",         "ríe disimuladamente mirando a",       "también rió disimuladamente con",       "¡Teehee de vuelta!",      "😊",  "Teehee~ 🤭",                               "suelta una risita disimulada que no engaña a nadie"),
    "thumbsup":  ("pulgararriba",   "le da el visto bueno a",              "devolvió el pulgar arriba a",           "¡Pulgar arriba!",         "👍",  "¡Aprobado! 👍",                            "le da el visto bueno a todo el servidor sin excepción"),
    "tickle":    ("cosquillas",     "le hace cosquillas a",                "se vengó haciéndole cosquillas a",      "¡Cosquillas de vuelta!",  "😆",  "¡Ja, ja, para, para! 😂",                  "tiene cosquillas de solo pensarlo"),
    "wink":      ("guiñar",         "le guiña un ojo a",                   "le devolvió el guiño a",                "¡Guiñar de vuelta!",      "😉",  "😉 Entendido.",                             "guiña el ojo al servidor entero con mucho descaro"),
    "yeet":      ("lanzar",         "lanza por los aires a",               "voló de vuelta hacia",                  "¡Volar de vuelta!",       "🚀",  "¡YEET! Al infinito y más allá. 🚀",        "se lanza a sí mismo al vacío sin pensarlo dos veces"),
    
    "bored":     ("aburrido",       "está aburrido de",                    "ignoró el aburrimiento de",             "Yo tambien",              "🥱",  "Sí... esto es muy aburrido. 😐",            "también se aburrió junto con", "también se aburrió junto con"),
    "happy":     ("feliz",          "está radiante de felicidad junto a",  "se contagió de la felicidad de",        "Estoy feliz tambien",     "😄",  "¡Tu felicidad me alegra mucho! 😊",         "irradia felicidad sin poder contenerse"),
    "think":     ("pensar",         "piensa profundamente en",             "se puso a filosofar junto con",         "Pensar juntos",           "🤔",  "Hmm... buena pregunta. 🤔",                 "entra en modo filósofo y se pierde en sus pensamientos"),
    "wag":       ("menear",         "menea la cola de felicidad al ver a", "meneó la cola junto con",               "¡Menear también!",        "🐕",  "¡Meneo de alegría! 🐾",                     "menea la cola de felicidad sin poder contenerse"),
    "yawn":      ("bostezar",       "se contagia del bostezo de",          "se contagió el bostezo de",             "Bostezar Tambien",        "🥱",  "¡Ahhh! Me contagiaste el bostezo. 😴",      "bosteza y contagia de sueño a absolutamente todos"),
}

# Acciones en solitario: (nombre_comando, frase, emoji, label_boton)
INTERACCIONES_SOLO = {
    "sip":    ("sorber",    "sorbe su bebida mirando pensativamente al vacío",         "☕", "Sorber juntos",   "sorbió junto con"),
    "spin":   ("girar",     "gira sobre sí mismo sin parar hasta que alguien lo pare", "🌀", "¡Girar juntos!",  "giró sin parar junto con"),
    "nom":    ("comer",     "Esta comiendo",                                           "🍴",  "Comer tambien",  "Come junto con")
    }

def color_random():
    return random.choice(COLORES)

# ─────────────────────────────────────────────────────────────
#  HELPERS DE GIF — construye embed + archivo desde gif_info
# ─────────────────────────────────────────────────────────────
def make_embed(titulo: str, gif_info: dict) -> tuple[discord.Embed, discord.File | None]:
    """Devuelve (embed, gif_file).
    Si gif_info tiene 'b64', el GIF se adjunta desde memoria (BytesIO).
    Si no, se usa la URL directamente.
    gif_file es None cuando se usa URL."""
    embed = discord.Embed(description=f"**{titulo}**", color=color_random())
    embed.set_footer(text=f"Anime: {gif_info.get('anime_name', 'Desconocido')}")

    gif_file = None
    if gif_info.get("b64"):
        try:
            bio = io.BytesIO(base64.b64decode(gif_info["b64"]))
            bio.seek(0)
            gif_file = discord.File(fp=bio, filename="accion.gif")
            embed.set_image(url="attachment://accion.gif")
        except Exception:
            # b64 corrupto, caer a URL
            embed.set_image(url=gif_info["url"])
    else:
        embed.set_image(url=gif_info["url"])

    return embed, gif_file


async def _send_gif(fn, embed: discord.Embed, gif_file: discord.File | None, **kwargs):
    """Llama fn(embed=embed, ...) añadiendo file= si hay gif_file."""
    if gif_file:
        await fn(embed=embed, file=gif_file, **kwargs)
    else:
        await fn(embed=embed, **kwargs)


# ------------------------------------------------------------
# GENERADOR DE COMANDOS DE INTERACCIÓN
# ------------------------------------------------------------
def crear_comando_interaccion(tag, nombre_comando, frase_con_target, frase_pasado, label_boton, emoji, respuesta_bot, frase_sin_target, frase_pasado_solo=None):
    async def comando(ctx, miembro: discord.Member = None):
        target = None
        if ctx.message.reference and ctx.message.reference.resolved:
            referenced_msg = ctx.message.reference.resolved
            if isinstance(referenced_msg, discord.Message):
                if referenced_msg.author != ctx.author:
                    target = referenced_msg.author
        if target is None and miembro:
            target = miembro

        # Caso: el bot es el objetivo
        if target and target == ctx.bot.user:
            gif_info = nekos_cache.obtener_gif(tag)
            if not gif_info:
                await ctx.send("❌ No hay GIF")
                return
            titulo = f"{ctx.author.display_name} {frase_con_target} {ctx.bot.user.display_name}."
            embed, gif_file = make_embed(titulo, gif_info)
            view = AccionView(ctx.author, ctx.bot.user, frase_con_target, frase_pasado, label_boton, tag, emoji)
            await _send_gif(ctx.send, embed, gif_file, view=view)
            await ctx.reply(respuesta_bot)
            gif_info2 = nekos_cache.obtener_gif(tag)
            if gif_info2:
                embed2, gif_file2 = make_embed(f"{ctx.bot.user.display_name} {frase_pasado} {ctx.author.display_name}.", gif_info2)
                await _send_gif(ctx.reply, embed2, gif_file2)
            return

        # Caso: a sí mismo
        if target and target == ctx.author:
            await ctx.send(f"🤔 {ctx.author.mention} ¿Hacer eso contigo mismo? Raro...")
            return

        # Caso: otro bot
        if target and target.bot:
            await ctx.send(f"🤖 {ctx.author.mention} Los bots no entienden estas cosas.")
            return

        # Normal
        if target:
            titulo = f"{ctx.author.display_name} {frase_con_target} {target.display_name}."
        else:
            titulo = f"{ctx.author.display_name} {frase_sin_target}."

        gif_info = nekos_cache.obtener_gif(tag)
        if not gif_info:
            await ctx.send("❌ No hay GIF")
            return
        embed, gif_file = make_embed(titulo, gif_info)
        view = AccionView(ctx.author, target, frase_con_target, frase_pasado, label_boton, tag, emoji, frase_pasado_solo)
        await _send_gif(ctx.send, embed, gif_file, view=view)

    return comando


# ------------------------------------------------------------
# VISTA GENÉRICA PARA ACCIONES (BOTÓN INTERACTIVO)
# Solo se usa cuando el destinatario NO es el bot
# ------------------------------------------------------------
class AccionView(View):
    def __init__(self, autor, target, accion_verbo, accion_pasado, boton_label, gif_tipo, emoji="👋", accion_pasado_solo=None):
        super().__init__(timeout=None)
        self.autor = autor
        self.target = target
        self.accion_verbo = accion_verbo
        self.accion_pasado = accion_pasado
        self.boton_label = boton_label
        self.gif_tipo = gif_tipo
        self.emoji = emoji
        self.usuarios_que_presionaron = set()
        self.devolver_button = Button(style=discord.ButtonStyle.secondary, label=boton_label, emoji=emoji)
        self.devolver_button.callback = self.devolver_button_callback
        self.add_item(self.devolver_button)
        self.accion_pasado_solo = accion_pasado_solo or accion_pasado

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.target is not None:
            if interaction.user.id != self.target.id:
                await interaction.response.defer()
                return False
        return True

    async def devolver_button_callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if interaction.user.id == self.autor.id:
            await interaction.response.defer()
            return
        if user_id in self.usuarios_que_presionaron:
            await interaction.response.defer()
            return

        self.usuarios_que_presionaron.add(user_id)

        if self.target:
            titulo = f"{interaction.user.display_name} {self.accion_pasado} a {self.autor.display_name}."
        else:
            titulo = f"{interaction.user.display_name} {self.accion_pasado_solo} {self.autor.display_name}."

        gif_info = nekos_cache.obtener_gif(self.gif_tipo)
        if not gif_info:
            await interaction.response.defer()
            return

        embed, gif_file = make_embed(titulo, gif_info)
        await _send_gif(interaction.message.reply, embed, gif_file)
        await interaction.response.defer()


# ------------------------------------------------------------
# FUNCIÓN PARA ENVIAR UN EMBED DE ACCIÓN (sin botón)
# ------------------------------------------------------------
async def enviar_embed_accion(destino, autor, target, accion_verbo, gif_tipo):
    gif_info = nekos_cache.obtener_gif(gif_tipo)
    if not gif_info:
        return False

    if target:
        titulo = f"{autor.display_name} {accion_verbo} a {target.display_name}."
    else:
        titulo = f"{autor.display_name} {accion_verbo}."

    embed, gif_file = make_embed(titulo, gif_info)
    await _send_gif(destino.send, embed, gif_file)
    return True


class SoloView(View):
    def __init__(self, tag, autor, frase, frase_pasado, emoji, label_boton):
        super().__init__(timeout=None)
        self.tag = tag
        self.autor = autor
        self.frase = frase
        self.frase_pasado = frase_pasado
        self.usuarios_que_presionaron = set()
        boton = Button(style=discord.ButtonStyle.secondary, label=label_boton, emoji=emoji)
        boton.callback = self.boton_callback
        self.add_item(boton)

    async def boton_callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in self.usuarios_que_presionaron:
            await interaction.response.defer()
            return
        self.usuarios_que_presionaron.add(user_id)
        gif_info = nekos_cache.obtener_gif(self.tag)
        if not gif_info:
            await interaction.response.defer()
            return
        titulo = f"{interaction.user.display_name} {self.frase_pasado} {self.autor.display_name}."
        embed, gif_file = make_embed(titulo, gif_info)
        await _send_gif(interaction.message.reply, embed, gif_file)
        await interaction.response.defer()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.autor.id:
            await interaction.response.defer()
            return False
        return True


def crear_comando_solo(tag, nombre_comando, frase, emoji, label_boton, frase_pasado):
    async def comando(ctx):
        gif_info = nekos_cache.obtener_gif(tag)
        if not gif_info:
            await ctx.send("❌ No hay GIF")
            return
        titulo = f"{ctx.author.display_name} {frase}."
        embed, gif_file = make_embed(titulo, gif_info)
        view = SoloView(tag, ctx.author, frase, frase_pasado, emoji, label_boton)
        await _send_gif(ctx.send, embed, gif_file, view=view)
    return comando


# ------------------------------------------------------------
# FUNCIÓN PRINCIPAL PARA ENVIAR ACCIÓN INTERACTIVA
# ------------------------------------------------------------
async def enviar_accion_interactiva(ctx, autor, target, accion_verbo, accion_pasado, boton_label, gif_tipo, emoji, mensaje_texto=None):
    gif_info = nekos_cache.obtener_gif(gif_tipo)
    if not gif_info:
        await ctx.send("❌ No tengo un GIF para eso ahora.")
        return False

    if target:
        if accion_verbo == "saluda":
            titulo1 = f"{autor.display_name} saluda a {target.display_name}."
        else:
            titulo1 = f"{autor.display_name} golpea a {target.display_name}."
    else:
        if accion_verbo == "saluda":
            titulo1 = f"{autor.display_name} dice hola!"
        else:
            titulo1 = f"{autor.display_name} golpea el aire!"

    embed1, gif_file1 = make_embed(titulo1, gif_info)
    view = AccionView(autor, target, accion_verbo, accion_pasado, boton_label, gif_tipo, emoji)

    if mensaje_texto:
        await ctx.send(mensaje_texto)

    await _send_gif(ctx.send, embed1, gif_file1, view=view)
    return True


# ------------------------------------------------------------
# COMANDO !saludar
# ------------------------------------------------------------
async def saludar_command(ctx, miembro: discord.Member = None):
    target = None
    if ctx.message.reference and ctx.message.reference.resolved:
        referenced_msg = ctx.message.reference.resolved
        if isinstance(referenced_msg, discord.Message):
            if referenced_msg.author != ctx.author and not referenced_msg.author.bot:
                target = referenced_msg.author
    if target is None and miembro:
        target = miembro

    # Caso: saludar al bot
    if target and target == ctx.bot.user:
        gif_info = nekos_cache.obtener_gif("wave")
        if not gif_info:
            await ctx.send("❌ No hay GIF")
            return
        embed1, gif_file1 = make_embed(f"{ctx.author.display_name} saluda a {ctx.bot.user.display_name}.", gif_info)
        view = AccionView(ctx.author, ctx.bot.user, "saluda", "devolvió el saludo", "Devolver saludo", "wave", "👋")
        await _send_gif(ctx.send, embed1, gif_file1, view=view)

        texto_respuesta = random.choice(SALUDOS_BOT_TEXTO)
        await ctx.reply(texto_respuesta)

        gif_info2 = nekos_cache.obtener_gif("wave")
        if gif_info2:
            embed2, gif_file2 = make_embed(f"{ctx.bot.user.display_name} devolvió el saludo a {ctx.author.display_name}.", gif_info2)
            await _send_gif(ctx.reply, embed2, gif_file2)
        return

    # Caso: saludarse a sí mismo
    if target and target == ctx.author:
        await ctx.send(f"🤔 {ctx.author.mention} ¿Saludarte a ti mismo?")
        return
    # Caso: saludar a otro bot
    if target and target.bot:
        await ctx.send(f"🤖 {ctx.author.mention} Los bots no necesitan saludos.")
        return

    if target:
        titulo = f"{ctx.author.display_name} saluda a {target.display_name}."
    else:
        titulo = f"{ctx.author.display_name} dice hola."

    gif_info = nekos_cache.obtener_gif("wave")
    if not gif_info:
        await ctx.send("❌ No hay GIF")
        return
    embed, gif_file = make_embed(titulo, gif_info)
    view = AccionView(ctx.author, target, "saluda", "devolvió el saludo", "Saludar", "wave", "👋")
    await _send_gif(ctx.send, embed, gif_file, view=view)


# ------------------------------------------------------------
# COMANDO !golpear
# ------------------------------------------------------------
async def golpear_command(ctx, miembro: discord.Member = None):
    target = None
    if ctx.message.reference and ctx.message.reference.resolved:
        referenced_msg = ctx.message.reference.resolved
        if isinstance(referenced_msg, discord.Message):
            if isinstance(referenced_msg, discord.Message):
                if referenced_msg.author != ctx.author:
                    target = referenced_msg.author
    if target is None and miembro:
        target = miembro

    # Caso: golpear al bot
    if target and target == ctx.bot.user:
        gif_info = nekos_cache.obtener_gif("punch")
        if not gif_info:
            await ctx.send("❌ No hay GIF")
            return
        embed1, gif_file1 = make_embed(f"{ctx.author.display_name} golpea a {ctx.bot.user.display_name}.", gif_info)
        view = AccionView(ctx.author, ctx.bot.user, "golpea", "golpeó de vuelta", "Golpear devuelta", "punch", "👊")
        await _send_gif(ctx.send, embed1, gif_file1, view=view)

        texto_respuesta = random.choice(GOLPES_BOT_TEXTO)
        await ctx.reply(texto_respuesta)

        gif_info2 = nekos_cache.obtener_gif("punch")
        if gif_info2:
            embed2, gif_file2 = make_embed(f"{ctx.bot.user.display_name} golpeó de vuelta a {ctx.author.display_name}.", gif_info2)
            await _send_gif(ctx.reply, embed2, gif_file2)
        return

    # Caso: golpearse a sí mismo
    if target and target == ctx.author:
        await ctx.send(f"😵 {ctx.author.mention} ¿Golpearte a ti mismo?")
        return
    if target and target.bot:
        await ctx.send(f"🤖 {ctx.author.mention} Los bots no sienten golpes.")
        return

    if target:
        titulo = f"{ctx.author.display_name} golpea a {target.display_name}."
    else:
        titulo = f"{ctx.author.display_name} golpea el aire."

    gif_info = nekos_cache.obtener_gif("punch")
    if not gif_info:
        await ctx.send("❌ No hay GIF")
        return
    embed, gif_file = make_embed(titulo, gif_info)
    view = AccionView(ctx.author, target, "golpea", "golpeó de vuelta", "Golpear", "punch", "👊")
    await _send_gif(ctx.send, embed, gif_file, view=view)


# ------------------------------------------------------------
# MANEJADOR DE MENCIONES AL BOT (sin comando)
# ------------------------------------------------------------
async def manejar_menciones(message, bot):
    if message.author == bot.user:
        return
    if bot.user in message.mentions and not message.content.startswith('!'):
        mensaje_aleatorio = random.choice(SALUDOS_BOT_TEXTO)
        class FakeCtx:
            def __init__(self, msg, bot):
                self.author = msg.author
                self.bot = bot
                self.send = msg.channel.send
                self.message = msg
        fake_ctx = FakeCtx(message, bot)
        await enviar_accion_interactiva(
            fake_ctx, message.author, bot.user,
            "saluda", "devolvió el saludo", "Devolver saludo", "wave", "👋",
            mensaje_texto=mensaje_aleatorio
        )