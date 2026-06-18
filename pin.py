
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

TOKEN = os.environ.get("TOKEN")  # Cambia a TOKEN 
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")
IMGBB_API = os.environ.get("IMGBB_API")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID")
NETLIFY_BASE_URL = os.environ.get("NETLIFY_BASE_URL")
NGROK_TOKEN  = os.environ.get("_NGROK_TOKEN")
