import logging
logging.basicConfig(level=logging.INFO)

from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_login import LoginManager
import os

class ProductionConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "apollo-secret")
    _db_url = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_DATABASE_URI = _db_url.replace("postgres://", "postgresql://") if _db_url else None
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERIAL_PORT = None
    SERIAL_BAUD = 115200
    TIMEZONE = "Asia/Beirut"
    LOW_PILL_THRESHOLD = 5
    LOW_WATER_THRESHOLD = 20
    LOW_BATTERY_THRESHOLD = 30
    CRITICAL_BATTERY = 20

db            = SQLAlchemy()
migrate       = Migrate()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(ProductionConfig)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.models.user import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.models import (
        Patient, Tube, Schedule, Mission,
        RobotState, DispenseLog, Alert, Waypoint
    )
    from app.models import ContactMessage

    # Public routes only
    from app.routes.contact   import contact_bp
    from app.routes.auth      import auth_bp
    from app.routes.admin     import admin_bp

    # Public website
    from flask import render_template
    @app.route("/")
    @app.route("/about")
    def public():
        return render_template("public/index.html")

    app.register_blueprint(contact_bp, url_prefix="/api/contact")
    app.register_blueprint(auth_bp,    url_prefix="/")
    app.register_blueprint(admin_bp,   url_prefix="/admin")

    _seed(app)

    return app


def _seed(app):
    from app.models import RobotState, Tube
    from app.models.user import User

    with app.app_context():
        # Create all tables first
        db.create_all()

        # Small delay to ensure tables are ready
        import time
        time.sleep(1)

        try:
            if not db.session.get(RobotState, 1):
                db.session.add(RobotState(id=1))
                db.session.commit()

            for tube_id in [1, 2, 3, 4]:
                if not db.session.get(Tube, tube_id):
                    db.session.add(Tube(id=tube_id))

            if not User.query.filter_by(role="admin").first():
                admin = User(
                    username="admin",
                    full_name="Administrator",
                    role="admin"
                )
                admin.set_password("apollo2024")
                db.session.add(admin)

            db.session.commit()
        except Exception as e:
            print(f"Seed error (non-fatal): {e}")
            db.session.rollback()


app = create_app()
