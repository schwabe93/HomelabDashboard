import os
from dotenv import load_dotenv

load_dotenv()

OPNSENSE_HOST = os.getenv("OPNSENSE_HOST", "192.168.188.160")
OPNSENSE_API_KEY = os.getenv("OPNSENSE_API_KEY", "")
OPNSENSE_API_SECRET = os.getenv("OPNSENSE_API_SECRET", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/dashboard.db")
IPDHCP_HISTORY_FILE = os.getenv("IPDHCP_HISTORY_FILE", "data/ipdhcp-history.json")
IPDHCP_SUBNET_PREFIX = os.getenv("IPDHCP_SUBNET_PREFIX", "192.168.188.")

UNRAID_HOST = os.getenv("UNRAID_HOST", "192.168.188.160")
UNRAID_USER = os.getenv("UNRAID_USER", "root")
UNRAID_PASSWORD = os.getenv("UNRAID_PASSWORD", "")
UNRAID_HOSTKEY = os.getenv("UNRAID_HOSTKEY", "")
UNRAID_SSH_MODE = os.getenv("UNRAID_SSH_MODE", "auto").lower()
PLINK_EXE = os.getenv("PLINK_EXE", "plink.exe")
