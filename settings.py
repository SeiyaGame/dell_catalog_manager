import os
import pathlib
from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).parent

load_dotenv(os.path.join(BASE_DIR, ".env"))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

BIOS_REPO_DIR = os.getenv("BIOS_REPO_DIR")