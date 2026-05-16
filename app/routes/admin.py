from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models.user import User

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """Decorator — only admin users can access this route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/")
@login_required
@admin_required
def admin_panel():
    return render_template("admin/panel.html")


@admin_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users])


@admin_bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    """
    Admin creates a new nurse account.
    Body: { "username": "nurse1", "password": "pass123", "full_name": "Sarah Khoury", "role": "nurse" }
    """
    data      = request.get_json()
    username  = data.get("username", "").strip()
    password  = data.get("password", "")
    full_name = data.get("full_name", "").strip()
    role      = data.get("role", "nurse")

    if not username or not password or not full_name:
        return jsonify({"error": "username, password and full_name are required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    if role not in ("admin", "nurse"):
        return jsonify({"error": "Role must be admin or nurse"}), 400

    user = User(username=username, full_name=full_name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": f"Account created for {full_name}", "user": user.to_dict()}), 201


@admin_bp.route("/users/<int:uid>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(uid):
    user = User.query.get_or_404(uid)
    if user.role == "admin" and User.query.filter_by(role="admin").count() == 1:
        return jsonify({"error": "Cannot delete the last admin account"}), 400
    user.is_active = False
    db.session.commit()
    return jsonify({"message": f"{user.full_name} deactivated"})


@admin_bp.route("/users/<int:uid>/reset-password", methods=["POST"])
@login_required
@admin_required
def reset_password(uid):
    user     = User.query.get_or_404(uid)
    data     = request.get_json()
    password = data.get("password", "")
    if not password or len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    user.set_password(password)
    db.session.commit()
    return jsonify({"message": f"Password reset for {user.full_name}"})
