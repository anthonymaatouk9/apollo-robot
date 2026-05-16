import logging
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_login import LoginManager
from config import Config

db            = SQLAlchemy()
migrate       = Migrate()
login_manager = LoginManager()

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # User loader
    from app.models.user import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Import all models
    from app.models import (
        Patient, Tube, Schedule, Mission,
        RobotState, DispenseLog, Alert, Waypoint
    )

    # Register blueprints
    from app.routes.patients  import patients_bp
    from app.routes.tubes     import tubes_bp
    from app.routes.schedules import schedules_bp
    from app.routes.missions  import missions_bp
    from app.routes.robot     import robot_bp
    from app.routes.alerts    import alerts_bp
    from app.routes.manual    import manual_bp
    from app.routes.logs      import logs_bp
    from app.routes.qr        import qr_bp
    from app.routes.ai        import ai_bp
    from app.routes.camera    import camera_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.auth      import auth_bp
    from app.routes.admin     import admin_bp
    from app.routes.chatbot   import chatbot_bp
    from app.routes.contact   import contact_bp

    app.register_blueprint(patients_bp,  url_prefix="/api/patients")
    app.register_blueprint(tubes_bp,     url_prefix="/api/tubes")
    app.register_blueprint(schedules_bp, url_prefix="/api/schedules")
    app.register_blueprint(missions_bp,  url_prefix="/api/missions")
    app.register_blueprint(robot_bp,     url_prefix="/api/robot")
    app.register_blueprint(alerts_bp,    url_prefix="/api/alerts")
    app.register_blueprint(manual_bp,    url_prefix="/api/manual")
    app.register_blueprint(logs_bp,      url_prefix="/api/logs")
    app.register_blueprint(qr_bp,        url_prefix="/api/qr")
    app.register_blueprint(ai_bp,        url_prefix="/api/ai")
    app.register_blueprint(camera_bp,    url_prefix="/api/camera")
    app.register_blueprint(dashboard_bp, url_prefix="/")
    app.register_blueprint(auth_bp,      url_prefix="/")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(chatbot_bp,   url_prefix="/api/chatbot")
    app.register_blueprint(contact_bp,   url_prefix="/api/contact")

    with app.app_context():
        db.create_all()
        _seed_initial_data()

    # Start mission runner
    from app.services.mission_runner import mission_runner
    mission_runner.start(app)

    return app


def _seed_initial_data():
    from app.models import RobotState, Tube
    from app.models.user import User

    if not RobotState.query.get(1):
        db.session.add(RobotState(id=1))
        db.session.commit()

    for tube_id in [1, 2, 3, 4]:
        if not Tube.query.get(tube_id):
            db.session.add(Tube(id=tube_id, medication=None, stock=0))

    # Create default admin account if none exists
    if not User.query.filter_by(role="admin").first():
        admin = User(
            username="admin",
            full_name="Administrator",
            role="admin"
        )
        admin.set_password("apollo2024")
        db.session.add(admin)
        logger.info("Default admin account created — username: admin, password: apollo2024")

    db.session.commit()
