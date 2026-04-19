import os
from dotenv import load_dotenv

load_dotenv()

OPNSENSE_HOST = os.getenv("OPNSENSE_HOST", "192.168.188.160")
OPNSENSE_API_KEY = os.getenv("OPNSENSE_API_KEY", "")
OPNSENSE_API_SECRET = os.getenv("OPNSENSE_API_SECRET", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/dashboard.db")
