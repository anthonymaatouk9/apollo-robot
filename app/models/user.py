from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

def now_beirut():
    tz = pytz.timezone("Asia/Beirut")
    return datetime.now(tz).replace(tzinfo=None)

class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80), unique=True, nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    full_name  = db.Column(db.String(120), nullable=False)
    role       = db.Column(db.String(20), default="nurse")  # admin / nurse
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now_beirut)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def get_id(self):
        return str(self.id)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def to_dict(self):
        return {
            "id":        self.id,
            "username":  self.username,
            "full_name": self.full_name,
            "role":      self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
