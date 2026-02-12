import socket
import requests
 
IP = "85.52.134.93"
PUERTO = 26900
URL_STATS = "https://api.kasiriserver.space/stats"
URL_RANKING = "https://api.kasiriserver.space/ranking"
A2S_INFO = b"\xFF\xFF\xFF\xFFTSource Engine Query\x00"
def get_stats():
    try:
        r = requests.get(URL_STATS, timeout=13)
        r.raise_for_status()
        print(r.json())  # Imprime el JSON recibido para verificar su estructura
        return r.json()   # ← AQUÍ ya tienes el JSON como dict
    except requests.RequestException:
        print(None)
        return None
def get_ranking():
    try:
        r = requests.get(URL_RANKING, timeout=2)
        r.raise_for_status()
        print(r.json())  # Imprime el JSON recibido para verificar su estructura
        return r.json()   # ← AQUÍ ya tienes el JSON como dict
    except requests.RequestException:
        print(None)
        return None    
    
def check_status():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)

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
