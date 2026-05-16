from flask import Blueprint, request, jsonify, redirect, url_for, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from app.models import now_beirut

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    from flask import render_template
    if request.method == "GET":
        return render_template("auth/login.html")

    data     = request.get_json() if request.is_json else request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        if request.is_json:
            return jsonify({"error": "Username and password required"}), 400
        return render_template("auth/login.html", error="Username and password required")

    user = User.query.filter_by(username=username, is_active=True).first()

    if not user or not user.check_password(password):
        if request.is_json:
            return jsonify({"error": "Invalid username or password"}), 401
        return render_template("auth/login.html", error="Invalid username or password")

    login_user(user, remember=True)
    user.last_login = now_beirut()
    db.session.commit()

    if request.is_json:
        return jsonify({"message": "Login successful", "role": user.role, "redirect": "/"})

    return redirect(url_for("dashboard.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify(current_user.to_dict())
