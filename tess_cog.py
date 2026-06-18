"""
tess_cog.py — Cog de Tesseract para el bot Discord
====================================================
Ejecuta e interpreta código Tesseract directamente desde un DM.

Comandos expuestos:
  !exec    → Abre sesión (24 h), pide archivo .tss o txt y muestra opciones
  !cancel  → Detiene la ejecución activa / cierra la sesión

Estructura esperada en disco (junto a main.py):
  Tess/
    <nombre_del_exe>    ← ejecutable generado por build.py (el usuario lo nombra)
    _internal/          ← carpeta de PyInstaller (ignorada al buscar el exe)

Targets:
  interp  → ejecutar directo                         (default, sin flags extra)
  native  → compilar binario                         (--target native --win32|--linux -o <nombre>)
  web     → transpilar a JS + empaquetar en HTML     (--target web -o <nombre>)

El modo web genera un .js con el código transpilado.
El BOT toma ese .js y lo envuelve en un HTML propio que:
  • Redirige console.log / console.error al div de output visible en pantalla.
  • Usa prompt() nativo del browser para las entradas de consola (el lenguaje
    ya sustituye stdin por prompt() en el target web, el HTML solo lo muestra).
  • Sube el .html resultante para que el usuario lo abra directamente.

Extensiones de salida:
  win32 → <nombre>.exe
  linux → <nombre>         (sin extensión)
  web   → <nombre>.html    (el .js se embebe dentro, no se sube por separado)

Stdin interactivo (modo interp):
  • IO_TIMEOUT segundos sin output → el bot asume que el proceso pide input.
  • !cancel  durante ejecución → mata el proceso y cierra sesión.
  • \\!cancel durante ejecución → envía "!cancel" literal al stdin del proceso.
"""

import asyncio
import hashlib
import os
import shutil
import tempfile
import textwrap
import time

import discord
from discord.ext import commands, tasks

# ─────────────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TESS_DIR    = os.path.join(BASE_DIR, "Tess")

SESSION_TTL = 86_400   # 24 h en segundos (para GC de sesiones expiradas)
DISCORD_MAX = 1_900    # caracteres por mensaje (margen bajo el límite de 2 000)
IO_TIMEOUT  = 1.0      # segundos sin output para asumir que el proceso pide input


# ─────────────────────────────────────────────────────────────────────────────
# Template HTML para el target web
# ─────────────────────────────────────────────────────────────────────────────
# El JS generado por Tesseract se embebe dentro de este HTML.
# console.log / console.error / console.warn se redirigen al div #output.
# prompt() ya es nativo del browser → el lenguaje lo usa como stdin.

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tesseract \u2b21 {title}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');

    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #13111a;
      --surface:   #1c1929;
      --border:    #2e2a40;
      --accent:    #7c6af7;
      --accent-dim:#3d3580;
      --green:     #a8ff78;
      --red:       #ff6b6b;
      --yellow:    #ffd166;
      --muted:     #6b6585;
      --text:      #e2dff5;
    }}

    html, body {{
      height: 100%;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'JetBrains Mono', 'Courier New', monospace;
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      padding: 0;
    }}

    /* ── Topbar ── */
    .topbar {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-shrink: 0;
    }}

    .topbar-logo {{
      font-size: 1rem;
      font-weight: 600;
      color: var(--accent);
      letter-spacing: -0.02em;
    }}

    .topbar-sep {{
      color: var(--border);
      font-size: 1.1rem;
    }}

    .topbar-title {{
      font-size: 0.82rem;
      color: var(--muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .topbar-badge {{
      margin-left: auto;
      font-size: 0.7rem;
      background: var(--accent-dim);
      color: var(--accent);
      border-radius: 4px;
      padding: 2px 8px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}

    /* ── Terminal container ── */
    .terminal-wrap {{
      flex: 1;
      padding: 20px 24px 24px;
      display: flex;
      flex-direction: column;
      gap: 0;
    }}

    .terminal {{
      background: #0e0c14;
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      flex: 1;
      display: flex;
      flex-direction: column;
      box-shadow: 0 4px 32px rgba(0,0,0,0.5);
    }}

    .terminal-header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 9px 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .dot {{
      width: 11px;
      height: 11px;
      border-radius: 50%;
    }}
    .dot-r {{ background: #ff5f56; }}
    .dot-y {{ background: #ffbd2e; }}
    .dot-g {{ background: #27c93f; }}

    .terminal-label {{
      margin-left: 6px;
      font-size: 0.72rem;
      color: var(--muted);
    }}

    #output {{
      flex: 1;
      padding: 18px 20px;
      overflow-y: auto;
      font-size: 0.88rem;
      line-height: 1.75;
      white-space: pre-wrap;
      word-break: break-word;
      min-height: 300px;
    }}

    /* Líneas de output */
    .out-line {{ color: var(--green); }}
    .out-err  {{ color: var(--red);    }}
    .out-warn {{ color: var(--yellow); }}

    /* Scrollbar */
    #output::-webkit-scrollbar       {{ width: 6px; }}
    #output::-webkit-scrollbar-track {{ background: transparent; }}
    #output::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}

    /* ── Input inline ── */
    .tess-input-line {{
      display: flex;
      align-items: center;
      padding: 0 20px 6px;
      flex-shrink: 0;
    }}
    .tess-input-prompt {{
      color: var(--accent);
      font-size: 0.88rem;
      margin-right: 6px;
      font-family: inherit;
      flex-shrink: 0;
    }}
    .tess-input-field {{
      flex: 1;
      background: transparent;
      border: none;
      border-bottom: 1px solid var(--accent-dim);
      outline: none;
      color: var(--text);
      font-family: inherit;
      font-size: 0.88rem;
      padding: 2px 0;
      caret-color: var(--accent);
    }}
    .tess-input-field:focus {{ border-bottom-color: var(--accent); }}
    .tess-sent-input {{
      display: flex;
      align-items: center;
      padding: 0 20px 2px;
    }}
    .tess-sent-prompt {{ color: var(--accent); font-size: 0.88rem; margin-right: 6px; }}
    .tess-sent-value  {{ color: var(--text);   font-size: 0.88rem; }}

    /* ── Footer ── */
    footer {{
      padding: 10px 24px;
      font-size: 0.7rem;
      color: var(--muted);
      border-top: 1px solid var(--border);
      display: flex;
      gap: 16px;
      flex-shrink: 0;
    }}

    footer span {{ color: var(--accent); }}
  </style>
</head>
<body>

  <div class="topbar">
    <div class="topbar-logo">\u2b21 Tesseract</div>
    <div class="topbar-sep">/</div>
    <div class="topbar-title">{title}</div>
    <div class="topbar-badge">web</div>
  </div>

  <div class="terminal-wrap">
    <div class="terminal">

      <div class="terminal-header">
        <div class="dot dot-r"></div>
        <div class="dot dot-y"></div>
        <div class="dot dot-g"></div>
        <span class="terminal-label">{title}</span>
      </div>

      <div id="output"></div>
      <div id="__tess_input_area"></div>

    </div>
  </div>

  <footer>
    <span>\u2b21 Tesseract</span>
    <span style="color:var(--muted)">\u00b7 {title}</span>
  </footer>

  <!-- Interceptor de consola \u2014 debe ir ANTES del script del programa -->
  <script>
    (function () {{
      const out = document.getElementById('output');

      function writeLine(text, cls) {{
        const el = document.createElement('div');
        el.className = cls;
        el.textContent = String(text ?? '');
        out.appendChild(el);
        out.scrollTop = out.scrollHeight;
      }}

      const _log   = console.log.bind(console);
      const _error = console.error.bind(console);
      const _warn  = console.warn.bind(console);

      console.log   = (...a) => {{ _log(...a);   writeLine(a.join(' '), 'out-line'); }};
      console.error = (...a) => {{ _error(...a); writeLine(a.join(' '), 'out-err');  }};
      console.warn  = (...a) => {{ _warn(...a);  writeLine(a.join(' '), 'out-warn'); }};

      window.addEventListener('error', function (e) {{
        writeLine('Error: ' + e.message, 'out-err');
      }});
    }})();
  </script>

  <!-- C\u00f3digo Tesseract transpilado a JS -->
  <script>
{js_code}
  </script>

</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _find_exe() -> str | None:
    """Primer ejecutable en Tess/ (ignora _internal)."""
    if not os.path.isdir(TESS_DIR):
        return None
    for entry in os.scandir(TESS_DIR):
        if entry.is_file() and entry.name != "_internal" and os.access(entry.path, os.X_OK):
            return entry.path
    return None


def _auto_name(user_id: int) -> str:
    h = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8]
    return f"codigo_{h}"


def _sanitize(raw: str) -> str:
    safe = "".join(c for c in raw if c.isalnum() or c in "_-")
    return safe or "output"


def _split_msg(text: str) -> list[str]:
    """Parte texto en trozos de \u2264 DISCORD_MAX caracteres."""
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i : i + DISCORD_MAX])
        i += DISCORD_MAX
    return chunks or [""]


_TESS_READ_IMPL = """\
function __tessRead(promptText) {
  return new Promise(function(resolve) {
    var area = document.getElementById('__tess_input_area');
    var out  = document.getElementById('output');
    var wrapper = document.createElement('div');
    wrapper.className = 'tess-input-line';
    var prefix = document.createElement('span');
    prefix.className = 'tess-input-prompt';
    prefix.textContent = '\u203a';
    var field = document.createElement('input');
    field.type = 'text';
    field.className = 'tess-input-field';
    field.autocomplete = 'off';
    field.spellcheck = false;
    wrapper.appendChild(prefix);
    wrapper.appendChild(field);
    if (area) { area.innerHTML = ''; area.appendChild(wrapper); }
    if (out) out.scrollTop = out.scrollHeight;
    setTimeout(function() { field.focus(); }, 0);
    field.addEventListener('keydown', function(e) {
      if (e.key !== 'Enter') return;
      var value = field.value;
      var sent = document.createElement('div');
      sent.className = 'tess-sent-input';
      var sp = document.createElement('span');
      sp.className = 'tess-sent-prompt';
      sp.textContent = '\u203a';
      var sv = document.createElement('span');
      sv.className = 'tess-sent-value';
      sv.textContent = value;
      sent.appendChild(sp);
      sent.appendChild(sv);
      if (out) { out.appendChild(sent); out.scrollTop = out.scrollHeight; }
      if (area) area.innerHTML = '';
      resolve(value);
    });
  });
}"""


def _patch_tess_js(js: str) -> str:
    """Post-procesa el JS transpilado: async __tessRead, await en llamadas, async IIFE."""
    import re

    # 1. Reemplazar CUALQUIER __tessRead existente por la implementación estilizada
    start_marker = "function __tessRead("
    if start_marker in js:
        start = js.index(start_marker)
        brace_pos = js.index("{", start)
        depth, end = 0, brace_pos
        for i, ch in enumerate(js[brace_pos:], brace_pos):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        js = js[:start] + _TESS_READ_IMPL + js[end + 1:]
    else:
        # Si no había __tessRead (sin READs en el programa), igual la inyectamos
        # por si acaso; no hace daño si no se llama.
        js = _TESS_READ_IMPL + "\n\n" + js

    # 2. Añadir await a todas las llamadas __tessRead() que no lo tengan ya
    # Lookbehind doble: excluir "await " (ya tiene) y "function " (declaración)
    js = re.sub(r"(?<!await )(?<!function )(__tessRead\()", r"await \1", js)

    # 3. Envolver el cuerpo principal en async IIFE si no está ya
    programa_marker = "// -- Programa --"
    if programa_marker in js and "(async function" not in js:
        idx = js.index(programa_marker) + len(programa_marker)
        before = js[:idx]
        after  = js[idx:].rstrip()
        js = before + "\n(async function () {" + after + "\n})();"

    return js


def _wrap_html(js_content: str, title: str) -> str:
    """Embebe el JS generado por Tesseract dentro del template HTML."""
    js_content = _patch_tess_js(js_content)
    indented = textwrap.indent(js_content, "    ")
    return _HTML_TEMPLATE.format(title=title, js_code=indented)


# ─────────────────────────────────────────────────────────────────────────────
# Modal
# ─────────────────────────────────────────────────────────────────────────────

class NombreModal(discord.ui.Modal, title="Nombre del archivo de salida"):
    nombre = discord.ui.TextInput(
        label="Nombre (sin extensión)",
        placeholder="mi_programa",
        required=True,
        min_length=1,
        max_length=50,
    )

    def __init__(self, session: "TessSession", platform: str):
        super().__init__()
        self.session  = session
        self.platform = platform

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.session.build(self.platform, _sanitize(self.nombre.value.strip()))


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class AccionView(discord.ui.View):
    """Botones principales: Ejecutar ahora | Crear ejecutable."""

    def __init__(self, session: "TessSession"):
        super().__init__(timeout=None)
        self.session = session

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.session.user.id

    def _lock(self):
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

    @discord.ui.button(label="▶ Ejecutar ahora", style=discord.ButtonStyle.success)
    async def btn_ejecutar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._lock()
        await interaction.response.edit_message(view=self)
        self.stop()
        asyncio.create_task(self.session.ejecutar())

    @discord.ui.button(label="📦 Crear ejecutable", style=discord.ButtonStyle.primary)
    async def btn_compilar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._lock()
        await interaction.response.edit_message(view=self)
        self.stop()
        await interaction.followup.send(
            embed=discord.Embed(title="🖥️ ¿Para qué plataforma?", color=0x8B0000),
            view=PlataformaView(self.session),
            ephemeral=True,
        )


class PlataformaView(discord.ui.View):
    """Selección de plataforma destino para la compilación."""

    def __init__(self, session: "TessSession"):
        super().__init__(timeout=None)
        self.session = session

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.session.user.id

    async def _pedir_nombre(self, interaction: discord.Interaction, platform: str):
        self.stop()
        await interaction.response.send_message(
            embed=discord.Embed(title="📝 ¿Quieres ponerle nombre?", color=0x8B0000),
            view=NombreOpcionView(self.session, platform),
            ephemeral=True,
        )

    @discord.ui.button(label="🪟 Windows (.exe)", style=discord.ButtonStyle.primary)
    async def btn_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._pedir_nombre(interaction, "win32")

    @discord.ui.button(label="🐧 Linux", style=discord.ButtonStyle.secondary)
    async def btn_linux(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._pedir_nombre(interaction, "linux")

    @discord.ui.button(label="🌐 Web (.html)", style=discord.ButtonStyle.success)
    async def btn_web(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._pedir_nombre(interaction, "web")


class NombreOpcionView(discord.ui.View):
    """¿Nombre manual (modal) o automático?"""

    def __init__(self, session: "TessSession", platform: str):
        super().__init__(timeout=None)
        self.session  = session
        self.platform = platform

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.session.user.id

    @discord.ui.button(label="📝 Elegir nombre", style=discord.ButtonStyle.secondary)
    async def btn_elegir(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_modal(NombreModal(self.session, self.platform))

    @discord.ui.button(label="🎲 Nombre automático", style=discord.ButtonStyle.secondary)
    async def btn_auto(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        nombre = _auto_name(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        await self.session.build(self.platform, nombre)


# ─────────────────────────────────────────────────────────────────────────────
# Sesión
# ─────────────────────────────────────────────────────────────────────────────

class TessSession:
    """
    Una sesión por usuario, máximo SESSION_TTL segundos de vida.
    Gestiona tanto la ejecución interactiva (interp) como la compilación (native/web).
    """

    def __init__(
        self,
        user: discord.User,
        channel: discord.DMChannel,
        tess_file: str,
        tess_exe: str,
        sessions: "dict[int, TessSession]",
    ):
        self.user      = user
        self.channel   = channel
        self.tess_file = tess_file          # ruta al .tss o txt descargado
        self.tess_exe  = tess_exe           # ruta al ejecutable en Tess/
        self._sessions = sessions           # ref al dict del cog para auto-limpieza

        self.created_at = time.time()
        self._workdir   = os.path.dirname(tess_file)

        # Estado de ejecución interactiva
        self.proc: asyncio.subprocess.Process | None = None
        self.running           = False
        self.cancelled         = False
        self.waiting_for_input = False
        self.input_queue: asyncio.Queue[str] = asyncio.Queue()

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        return time.time() - self.created_at > SESSION_TTL

    def cleanup(self):
        shutil.rmtree(self._workdir, ignore_errors=True)

    def _finalize(self):
        """Saca la sesión del dict del cog y borra el directorio temporal."""
        self._sessions.pop(self.user.id, None)
        self.cleanup()

    # ── Cancelar proceso activo ───────────────────────────────────────────────

    async def cancel_proc(self):
        self.cancelled = True
        self.running   = False
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass
        await self.input_queue.put("")   # desbloquea cualquier wait en input_queue

    # ─────────────────────────────────────────────────────────────────────────
    # EJECUCIÓN INTERACTIVA  (target: interp)
    # ─────────────────────────────────────────────────────────────────────────

    async def ejecutar(self):
        """
        Lanza el intérprete Tesseract sobre el archivo .tss o .txt.

        Flujo de I/O:
          - El output del proceso va al DM en bloques de código.
          - Cuando el proceso lleva IO_TIMEOUT s sin escribir nada, el bot
            asume que está esperando input y se lo pide al usuario por chat.
          - stdin llega desde el listener on_message del cog.
          - !cancel  mata el proceso; \\!cancel manda "!cancel" literal al stdin.
        """
        await self.channel.send(embed=discord.Embed(
            title="▶ Ejecutando código Tesseract",
            description=(
                "Escribe `!cancelC` para detener en cualquier momento.\n"
                "Si el programa pide una entrada, escríbela directamente aquí.\n"
                "Para enviar `!cancelC` **literal** al programa: `\\!cancelC`"
            ),
            color=0x2ecc71,
        ))

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.running = True

        self.proc = await asyncio.create_subprocess_exec(
            self.tess_exe,
            self.tess_file,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self._workdir,
            env=env,
        )

        buf: list[str] = []

        async def flush():
            if not buf:
                return
            text = "\n".join(buf)
            buf.clear()
            for chunk in _split_msg(text):
                if chunk.strip():
                    await self.channel.send(f"```\n{chunk}\n```")

        # ── Bucle principal de lectura ─────────────────────────────────────────
        while not self.cancelled:
            try:
                line = await asyncio.wait_for(
                    self.proc.stdout.readline(),
                    timeout=IO_TIMEOUT,
                )
            except asyncio.TimeoutError:
                # Sin output durante IO_TIMEOUT 
                if self.proc.returncode is not None:
                    break   # proceso terminó, salir del bucle

                # Probablemente espera input → preguntar al usuario
                await flush()
                self.waiting_for_input = True

                await self.channel.send(embed=discord.Embed(
                    description="✏️ **El programa espera una entrada:**",
                    color=0x5865F2,
                ))

                data = await self.input_queue.get()

                self.waiting_for_input = False

                if self.cancelled:
                    break

                self.proc.stdin.write((data + "\n").encode("utf-8"))
                await self.proc.stdin.drain()
                continue

            if not line:    # EOF → proceso terminó
                break

            decoded = line.decode("utf-8", errors="replace").rstrip()
            buf.append(decoded)

            # Flush anticipado si el buffer se acerca al límite de Discord
            if sum(len(l) for l in buf) >= DISCORD_MAX:
                await flush()

        # ── Post-bucle ────────────────────────────────────────────────────────
        await flush()
        self.running = False
        rc = await self.proc.wait()

        if self.cancelled:
            color, title = 0xff4444, "⛔ Ejecución cancelada"
        elif rc == 0:
            color, title = 0x2ecc71, "✅ Ejecución completada"
        else:
            color, title = 0xff4444, f"❌ El proceso terminó con código {rc}"

        await self.channel.send(embed=discord.Embed(title=title, color=color))
        self._finalize()

    # ─────────────────────────────────────────────────────────────────────────
    # COMPILACIÓN / TRANSPILACIÓN  (target: native | web)
    # ─────────────────────────────────────────────────────────────────────────

    async def build(self, platform: str, output_name: str):
        """
        Compila o transpila el .tss o .txt y sube el resultado al DM.

        platform    : "win32" | "linux" | "web"
        output_name : nombre base sin extensión

        Para el target web:
          1. Corre el exe con --target web -o <output_name>
             → el compilador genera <output_name>.js
          2. El bot lee ese .js y lo embebe en un HTML (_wrap_html)
             que redirige console.log al div #output y usa prompt() para entradas
          3. Se sube el .html (el .js intermedio no se incluye)

        Para native:
          Se sube el binario directamente (.exe en win32, sin extensión en linux).
        """
        LABELS     = {"win32": "Windows",  "linux": "Linux", "web": "Web"}
        UPLOAD_EXT = {"win32": ".exe",     "linux": "",      "web": ".html"}

        label           = LABELS.get(platform, platform)
        upload_ext      = UPLOAD_EXT.get(platform, "")
        upload_filename = output_name + upload_ext

        status_msg = await self.channel.send(embed=discord.Embed(
            title="⚙️ Compilando…",
            description=f"Plataforma: **{label}** → `{upload_filename}`",
            color=0xffaa00,
        ))

        # ── Comando para el compilador Tesseract ──────────────────────────────
        if platform == "web":
            # El compilador genera <output_name>.js en el cwd
            cmd = [
                self.tess_exe,
                "--target", "web",
                "-o", output_name,
                "-html",
                self.tess_file,
            ]
        else:
            cmd = [
                self.tess_exe,
                "--target", "native",
                f"--{platform}",          # --win32 o --linux
                "-o", output_name,
                self.tess_file,
            ]

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        with tempfile.TemporaryDirectory(prefix="tess_build_") as build_dir:

            # ── Ejecutar el compilador ─────────────────────────────────────────
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=build_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            stdout, _ = await proc.communicate()
            out_text  = stdout.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                await status_msg.edit(embed=discord.Embed(
                    title="❌ Error de compilación",
                    description=f"```\n{out_text[:1800]}\n```",
                    color=0xff4444,
                ))
                self._finalize()
                return

            # ── Procesar salida según plataforma ──────────────────────────────

            if platform == "web":
                # Buscar el .js generado por el compilador
                js_path = os.path.join(build_dir, output_name + ".js")

                if not os.path.exists(js_path):
                    # Fallback: cualquier .js en el directorio
                    candidates = [
                        e.path for e in os.scandir(build_dir)
                        if e.is_file() and e.name.endswith(".js")
                    ]
                    if not candidates:
                        await status_msg.edit(embed=discord.Embed(
                            title="❌ No se generó el archivo JS",
                            description="El compilador no produjo ningún `.js` en el directorio de build.",
                            color=0xff4444,
                        ))
                        self._finalize()
                        return
                    js_path = candidates[0]

                # Leer el JS y envolverlo en el HTML
                with open(js_path, "r", encoding="utf-8", errors="replace") as f:
                    js_content = f.read()

                html_content = _wrap_html(js_content, upload_filename)

                html_path = os.path.join(build_dir, upload_filename)
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)

                generated = html_path

            else:
                # native: buscar el binario por nombre exacto o cualquier candidato
                expected = os.path.join(build_dir, upload_filename)
                if os.path.exists(expected):
                    generated = expected
                else:
                    candidates = [
                        e.path for e in os.scandir(build_dir)
                        if e.is_file()
                        and not e.name.endswith((".c", ".o", ".ll", ".webir.json"))
                        and e.name != os.path.basename(self.tess_file)
                    ]
                    if not candidates:
                        await status_msg.edit(embed=discord.Embed(
                            title="❌ No se generó ningún binario",
                            description="El compilador no produjo ningún archivo ejecutable.",
                            color=0xff4444,
                        ))
                        self._finalize()
                        return
                    generated = candidates[0]

            gen_name  = os.path.basename(generated)
            file_size = os.path.getsize(generated)

            # ── Límite de tamaño Discord ──────────────────────────────────────
            LIMIT_BYTES = 8 * 1024 * 1024   # 8 MB servidores normales
            if file_size > LIMIT_BYTES:
                await status_msg.edit(embed=discord.Embed(
                    title="⚠️ Archivo demasiado grande para Discord",
                    description=(
                        f"`{gen_name}` pesa `{file_size / 1024 ** 2:.1f} MB`.\n"
                        f"El límite es **8 MB** (25 MB con Nitro)."
                    ),
                    color=0xff9900,
                ))
                self._finalize()
                return

            # ── Éxito: editar status y subir archivo ──────────────────────────
            await status_msg.edit(embed=discord.Embed(
                title="✅ Compilación exitosa",
                description=f"Plataforma: **{label}** • `{gen_name}`",
                color=0x2ecc71,
            ))
            await self.channel.send(
                file=discord.File(generated, filename=gen_name)
            )

        self._finalize()


# ─────────────────────────────────────────────────────────────────────────────
# Cog principal
# ─────────────────────────────────────────────────────────────────────────────

class TessCog(commands.Cog, name="Tesseract"):
    """Cog para ejecutar/compilar código Tesseract desde Discord (solo DMs)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: dict[int, TessSession] = {}
        self._gc_loop.start()

    def cog_unload(self):
        self._gc_loop.cancel()

    # ── Garbage collector: limpia sesiones expiradas cada 30 min ─────────────

    @tasks.loop(minutes=30)
    async def _gc_loop(self):
        expired = [uid for uid, s in list(self.sessions.items()) if s.is_expired()]
        for uid in expired:
            session = self.sessions.pop(uid, None)
            if session:
                if session.running:
                    await session.cancel_proc()
                session.cleanup()

    # ── Listener: stdin interactivo ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Intercepta mensajes del DM durante una ejecución activa.
        Solo actúa cuando el proceso está esperando input explícitamente.
          - Mensajes que empiezan con '!' → se dejan para el sistema de comandos.
          - '\\!...' → se manda como '!...' literal al stdin del proceso.
          - Cualquier otro texto → va directo al stdin.
        """
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        session = self.sessions.get(message.author.id)
        if not (session and session.running and session.waiting_for_input):
            return

        content = message.content.strip()

        # Comandos del bot (empiezan con !) → dejar que los procese el bot
        if content.startswith("!"):
            return

        # \\!cancel → !cancel literal al stdin
        if content.startswith("\\!"):
            content = content[1:]

        await session.input_queue.put(content)

    # ── !exec ─────────────────────────────────────────────────────────────────

    @commands.command(name="exec")
    async def cmd_exec(self, ctx: commands.Context):
        """Abre una sesión Tesseract en el DM (24 h de vida)."""

        # Solo DMs
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.send(embed=discord.Embed(
                title="⚠️ Solo en mensajes directos",
                description="Envíame este comando por DM para abrir una sesión.",
                color=0xff9900,
            ))
            return

        # ── Sesión ya existente ────────────────────────────────────────────────
        existing = self.sessions.get(ctx.author.id)
        if existing:
            if not existing.is_expired():
                await ctx.send(embed=discord.Embed(
                    title="⚠️ Ya tienes una sesión activa",
                    description="Usa `!cancel` para cerrarla antes de abrir otra.",
                    color=0xff9900,
                ))
                return
            # Expirada → limpiar sin ruido
            self.sessions.pop(ctx.author.id, None)
            existing.cleanup()

        # ── Verificar que el intérprete existe ────────────────────────────────
        tess_exe = _find_exe()
        if not tess_exe:
            await ctx.send(embed=discord.Embed(
                title="❌ Intérprete no encontrado",
                description="No hay ningún ejecutable en `Tess/`. Contacta al administrador.",
                color=0xff4444,
            ))
            return

        # ── Pedir el archivo .tess ────────────────────────────────────────────
        await ctx.send(embed=discord.Embed(
            title="🔷 Tesseract — Nueva sesión",
            description=(
                "Sube tu archivo `.tss` o `.txt` para continuar.\n"
                "⏳ La sesión expira en **24 horas**."
            ),
            color=0x8B0000,
        ))

        def _check_file(m: discord.Message) -> bool:
            return (
                m.author.id == ctx.author.id
                and isinstance(m.channel, discord.DMChannel)
                and bool(m.attachments)
                and m.attachments[0].filename.endswith((".tss", ".txt"))
            )

        try:
            file_msg = await self.bot.wait_for("message", check=_check_file, timeout=None)
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Tiempo agotado esperando el archivo. Usa `!exec` de nuevo.")
            return

        # ── Descargar archivo ─────────────────────────────────────────────────
        attachment = file_msg.attachments[0]
        tmp_dir    = tempfile.mkdtemp(prefix="tess_")
        tess_path  = os.path.join(tmp_dir, attachment.filename)

        try:
            await attachment.save(tess_path)
        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            await ctx.send(embed=discord.Embed(
                title="❌ No se pudo descargar el archivo",
                description=str(e),
                color=0xff4444,
            ))
            return

        # ── Crear sesión y mostrar opciones ───────────────────────────────────
        dm_channel = ctx.author.dm_channel or await ctx.author.create_dm()
        session    = TessSession(ctx.author, dm_channel, tess_path, tess_exe, self.sessions)
        self.sessions[ctx.author.id] = session

        await ctx.send(
            embed=discord.Embed(
                title=f"📄 `{attachment.filename}` listo",
                description="¿Qué quieres hacer con este código?",
                color=0x8B0000,
            ),
            view=AccionView(session),
        )

    # ── !cancel ───────────────────────────────────────────────────────────────

    @commands.command(name="cancelC")
    async def cmd_cancel(self, ctx: commands.Context):
        """Cancela la ejecución activa y cierra la sesión."""
        session = self.sessions.pop(ctx.author.id, None)
        if not session:
            return

        await session.cancel_proc()
        session.cleanup()

        await ctx.send(embed=discord.Embed(
            title="⛔ Sesión cancelada",
            color=0xff4444,
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(TessCog(bot))