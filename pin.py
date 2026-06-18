
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

TOKEN = os.getenv("TOKEN")  # Cambia a TOKEN 
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
IMGBB_API = os.getenv("IMGBB_API")
NETLIFY_TOKEN = os.getenv("NETLIFY_TOKEN")
NETLIFY_SITE_ID = os.getenv("NETLIFY_SITE_ID")
NETLIFY_BASE_URL = os.getenv("NETLIFY_BASE_URL")
NGROK_TOKEN  = os.getenv("_NGROK_TOKEN")