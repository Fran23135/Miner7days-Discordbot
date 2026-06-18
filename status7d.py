import socket
import requests
import random
import os
import json
import time
import aiohttp
from pathlib import Path
from pin import TWITCH_CLIENT_SECRET, TWITCH_CLIENT_ID
import random
import base64 
from pathlib import Path
IP = "85.52.134.93"
PUERTO = 26900
URL_STATS = "https://api.kasiriserver.space/stats"
URL_RANKING = "https://api.kasiriserver.space/ranking"
A2S_INFO = b"\xFF\xFF\xFF\xFFTSource Engine Query\x00"
TWITCH_CHANNEL = "Kasiri"
GAME_NAME = "7 Days to Die"
CLIP_CURSORS = []
CURSORS_READY = False
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FOLDER = os.path.join(BASE_DIR, "stats_cache")
# Crear carpeta si no existe
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)

CACHE_STATS = os.path.join(CACHE_FOLDER, "stats_cache.json")
CACHE_RANKING = os.path.join(CACHE_FOLDER, "ranking_cache.json")
GIF_CORRUPTED = {
    "7f7e932a-3329-4c1e-b274-13d1a21e0037",
    "e9298145-35c9-4f70-b710-750dd4997119",
    "6dabd39f-0312-4bea-a3dc-060af4be1eae"
}

def gif_corrupto(url: str) -> bool:
    filename = url.split("/")[-1].replace(".gif", "")
    return filename in GIF_CORRUPTED
def save_cache(path, data):
    cache_data = {
        "data": data,
        "cached_at": time.time()
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    print(f"[CACHE] actualizado → {os.path.basename(path)}")

def load_cache(path):
    """Carga los datos y el timestamp. Si es formato antiguo, devuelve solo datos y timestamp None."""
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        cache_data = json.load(f)
        # Verificar si es formato nuevo (con 'data' y 'cached_at')
        if isinstance(cache_data, dict) and "data" in cache_data and "cached_at" in cache_data:
            return cache_data["data"], cache_data["cached_at"]
        else:
            # Formato antiguo (solo datos)
            return cache_data, None
def get_stats():
    try:
        r = requests.get(URL_STATS, timeout=15)
        r.raise_for_status()
        data = r.json()
        save_cache(CACHE_STATS, data)
        # Añadir metadatos de datos actuales
        data["_cached"] = False
        data["_cached_at"] = time.time()
        return data
    except requests.RequestException as e:
        print(f"❌ Error al obtener las stats: {str(e)}")
        data, cached_at = load_cache(CACHE_STATS)
        if data is None:
            return None
        data["_cached"] = True
        data["_cached_at"] = cached_at if cached_at else time.time()
        return data
    
def get_ranking():
    try:
        r = requests.get(URL_RANKING, timeout=2)
        r.raise_for_status()
        data = r.json()
        save_cache(CACHE_RANKING, data)
        data["_cached"] = False
        data["_cached_at"] = time.time()
        return data
    except requests.RequestException as e:
        print(f"❌ Error al obtener el ranking: {str(e)}")
        data, cached_at = load_cache(CACHE_RANKING)
        if data is None:
            return None
        data["_cached"] = True
        data["_cached_at"] = cached_at if cached_at else time.time()
        return data
    
def check_status():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(8)

    try:
        sock.sendto(A2S_INFO, (IP, PUERTO))
        data, _ = sock.recvfrom(4096)

        # Challenge A2S
        if data.startswith(b"\xFF\xFF\xFF\xFFA"):
            challenge = data[5:9]
            sock.sendto(A2S_INFO + challenge, (IP, PUERTO))
            data, _ = sock.recvfrom(4096)
        if data.startswith(b"\xFF\xFF\xFF\xFFI"):
            return True
        else:
            return False

    except socket.timeout:
        return False

    finally:
        sock.close()

def get_twitch_token():
    url = "https://id.twitch.tv/oauth2/token"

    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    r = requests.post(url, params=params)
    return r.json()["access_token"]


def get_game_id(token):
    url = "https://api.twitch.tv/helix/games"

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    params = {"name": GAME_NAME}

    r = requests.get(url, headers=headers, params=params)
    return r.json()["data"][0]["id"]


def get_user_id(token):
    url = "https://api.twitch.tv/helix/users"

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    params = {"login": TWITCH_CHANNEL}

    r = requests.get(url, headers=headers, params=params)
    return r.json()["data"][0]["id"]

def scan_clip_pages():
    global CLIP_CURSORS, CURSORS_READY

    token = get_twitch_token()
    user_id = get_user_id(token)

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    url = "https://api.twitch.tv/helix/clips"

    CLIP_CURSORS = [None]  # página 1
    cursor = None

    while True:
        params = {
            "broadcaster_id": user_id,
            "first": 100
        }

        if cursor:
            params["after"] = cursor

        r = requests.get(url, headers=headers, params=params)
        data = r.json()

        cursor = data.get("pagination", {}).get("cursor")

        if not cursor:
            break

        CLIP_CURSORS.append(cursor)

    CURSORS_READY = True
def get_random_clip():
    token = get_twitch_token()
    game_id = get_game_id(token)

    # Si los cursores aún se están cargando en segundo plano,
    # usar [None] como fallback (equivale a pedir desde la página 1).
    cursors = CLIP_CURSORS if CURSORS_READY else [None]
    random_cursor = random.choice(cursors)

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    params = {
        "broadcaster_id": get_user_id(token),
        "first": 100
    }

    if random_cursor:
        params["after"] = random_cursor

    r = requests.get(
        "https://api.twitch.tv/helix/clips",
        headers=headers,
        params=params
    )

    data = r.json()["data"]

    clips_7d = [c for c in data if c["game_id"] == game_id]

    if not clips_7d:
        return None

    return random.choice(clips_7d)["url"]
# ==================== NEKOS.BEST INTEGRATION ====================


class NekosBestCache:
    """Caché que SOLO se usa si la API falla, con rotación sin repetir."""
    def __init__(self, cache_dir="cache_nekos", max_cache_size=100):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_cache_size = max_cache_size
        self._seen = {}          # categoria -> set de URLs ya usadas
        self._all_urls = {}      # categoria -> list de todas las URLs conocidas (para reiniciar)

    def _get_cache_file(self, categoria):
        return self.cache_dir / f"{categoria}.json"

    def _cargar_cache(self, categoria):
        archivo = self._get_cache_file(categoria)
        if not archivo.exists():
            return []
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def _guardar_cache(self, categoria, lista_gifs):
        if len(lista_gifs) > self.max_cache_size:
            lista_gifs = lista_gifs[-self.max_cache_size:]
        with open(self._get_cache_file(categoria), 'w', encoding='utf-8') as f:
            json.dump(lista_gifs, f, indent=2, ensure_ascii=False)

    def _actualizar_lista_urls(self, categoria, lista_gifs):
        urls = [gif['url'] for gif in lista_gifs if 'url' in gif]
        self._all_urls[categoria] = urls

    # Mapeo de categorías nekos.best -> otakugifs.xyz
     

    def obtener_gif(self, categoria):
     import requests as _req
     url_api = f"https://nekos.best/api/v2/{categoria}"

     # ── Llamar a la API para enriquecer el pool local ────────────
     try:
        r = _req.get(url_api, timeout=5)
        r.raise_for_status()
        datos = r.json()
        if 'results' in datos and datos['results']:
            api_gif = datos['results'][0]
            if 'url' in api_gif and not gif_corrupto(api_gif['url']):
                # Descargar y guardar b64 en el mismo momento
                try:
                    gr = _req.get(api_gif['url'], timeout=10)
                    if gr.status_code == 200:
                        api_gif['b64'] = base64.b64encode(gr.content).decode('utf-8')
                except Exception:
                    pass  # sin b64, no pasa nada, la URL sigue funcionando

                cache = self._cargar_cache(categoria)
                if not any(g.get('url') == api_gif['url'] for g in cache):
                    cache.append(api_gif)
                    self._guardar_cache(categoria, cache)
     except Exception:
        pass

    # ── Cargar caché y rellenar b64 faltantes ────────────────────
     cache = self._cargar_cache(categoria)
     if not cache:
        return None

    # Entradas antiguas sin b64: descargarlas ahora
     updated = False
     for g in cache:
        if 'url' in g and 'b64' not in g and not gif_corrupto(g['url']):
            try:
                import requests as _req2
                gr = _req2.get(g['url'], timeout=10)
                if gr.status_code == 200:
                    g['b64'] = base64.b64encode(gr.content).decode('utf-8')
                    updated = True
            except Exception:
                pass
     if updated:
        self._guardar_cache(categoria, cache)

    # ── Seleccionar con rotación sin repetir ─────────────────────
     self._actualizar_lista_urls(categoria, cache)

     if categoria not in self._seen:
        self._seen[categoria] = set()

     no_vistos = [
        g for g in cache
        if g['url'] not in self._seen[categoria] and not gif_corrupto(g['url'])
     ]

     if not no_vistos:
        self._seen[categoria] = set()
        no_vistos = [g for g in cache if not gif_corrupto(g['url'])]

     if not no_vistos:
        return None

     gif_info = random.choice(no_vistos)
     self._seen[categoria].add(gif_info['url'])
     return gif_info
# ==================== TWITCH STREAM MONITOR ====================
NEKOS_CACHE_DIR = os.path.join(BASE_DIR, "cache_nekos")
nekos_cache = NekosBestCache(cache_dir=NEKOS_CACHE_DIR)
class TwitchMonitor:
    """
    Monitor asíncrono de streams de Twitch.
    - Detecta cuando un streamer pasa a En Directo / Offline.
    - Cachea el token OAuth (válido ~60 días) para no pedirlo cada vez.
    - Precauciones: avisa UNA sola vez por sesión de stream.
    """

    def __init__(self):
        self._token: str | None        = None
        self._token_expires: float     = 0.0          # epoch
        self._live_ids: dict[str, str] = {}          # login → aviso ya enviado
        self._offline_count: dict[str, int] = {}       # login → checks consecutivos offline
        self.OFFLINE_THRESHOLD = 3     # checks offline seguidos para confirmar que cerró

    # ── Token ────────────────────────────────────────────────────────
    async def _get_token(self, session: aiohttp.ClientSession) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token

        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id":     TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type":    "client_credentials",
            }
        ) as r:
            data = await r.json()
            self._token         = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 3600 * 24 * 30) - 60
            return self._token

    def _headers(self, token: str) -> dict:
        return {
            "Client-ID":     TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }

    # ── Stream info ──────────────────────────────────────────────────
    async def get_stream(self, session: aiohttp.ClientSession, login: str) -> dict | None:
     token = await self._get_token(session)
     async with session.get(
        "https://api.twitch.tv/helix/streams",
        headers=self._headers(token),
        params={"user_login": login},
     ) as r:
        if r.status == 401:
            # Token revocado antes de expirar → forzar renovación el próximo tick
            print(f"[TwitchMonitor] Token inválido (401). Forzando renovación.")
            self._token = None
            self._token_expires = 0
            return None
        if r.status != 200:
            print(f"[TwitchMonitor] Error Twitch API: {r.status} para {login}")
            return None
        data = await r.json()
        streams = data.get("data", [])
        return streams[0] if streams else None

    async def get_user(self, session: aiohttp.ClientSession, login: str) -> dict | None:
     token = await self._get_token(session)
     async with session.get(
        "https://api.twitch.tv/helix/users",
        headers=self._headers(token),
        params={"login": login},
     ) as r:
        if r.status == 401:
            print(f"[TwitchMonitor] Token inválido (401) en get_user. Forzando renovación.")
            self._token = None
            self._token_expires = 0
            return None
        if r.status != 200:
            print(f"[TwitchMonitor] Error Twitch API en get_user: {r.status} para {login}")
            return None
        data = await r.json()
        users = data.get("data", [])
        return users[0] if users else None

    # ── Check completo ───────────────────────────────────────────────
    async def check(self, login: str) -> dict | None:
        """
        Comprueba si 'login' ha pasado a En Directo.
        Devuelve dict con stream+user si hay que notificar, None si no.
        Gestiona el estado interno (evita doble aviso y confirma offline).
        """
        async with aiohttp.ClientSession() as session:
            stream = await self.get_stream(session, login)

            if stream:
                self._offline_count[login] = 0
                stream_id = stream.get("id", "")
                if self._live_ids.get(login) == stream_id:
                    return None          # mismo stream, ya se avisó
                # stream_id nuevo = directo nuevo (o reinicio)
                self._live_ids[login] = stream_id
                user = await self.get_user(session, login)
                return {"stream": stream, "user": user}

            else:
                # Está offline
                count = self._offline_count.get(login, 0) + 1
                self._offline_count[login] = count
                if count >= self.OFFLINE_THRESHOLD and login in self._live_ids:

                    del self._live_ids[login]
                    print(f"[TwitchMonitor] {login} confirmado offline — reset de aviso.")
                return None


# Instancia global
twitch_monitor = TwitchMonitor()