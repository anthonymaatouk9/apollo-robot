import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
    SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", 115200))
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Beirut")
    LOW_PILL_THRESHOLD = 5
    LOW_WATER_THRESHOLD = 20
    LOW_BATTERY_THRESHOLD = 30
    CRITICAL_BATTERY = 20
