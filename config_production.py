import os

class ProductionConfig:
    SECRET_KEY         = os.getenv("SECRET_KEY", "apollo-production-key")
    SQLALCHEMY_DATABASE_URI     = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERIAL_PORT        = None
    SERIAL_BAUD        = 115200
    TIMEZONE           = "Asia/Beirut"
    LOW_PILL_THRESHOLD  = 5
    LOW_WATER_THRESHOLD = 20
    LOW_BATTERY_THRESHOLD = 30
    CRITICAL_BATTERY    = 20
    IS_PRODUCTION       = True
