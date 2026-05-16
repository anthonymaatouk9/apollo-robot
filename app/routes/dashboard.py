from flask import Blueprint, render_template
from flask_login import login_required, current_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    return render_template("dashboard/index.html")


@dashboard_bp.route("/patients")
@login_required
def patients():
    return render_template("dashboard/patients.html")


@dashboard_bp.route("/tubes")
@login_required
def tubes():
    return render_template("dashboard/tubes.html")


@dashboard_bp.route("/schedules")
@login_required
def schedules():
    return render_template("dashboard/schedules.html")


@dashboard_bp.route("/missions")
@login_required
def missions():
    return render_template("dashboard/missions.html")


@dashboard_bp.route("/manual")
@login_required
def manual():
    return render_template("dashboard/manual.html")


@dashboard_bp.route("/camera")
@login_required
def camera():
    return render_template("dashboard/camera.html")


@dashboard_bp.route("/logs")
@login_required
def logs():
    return render_template("dashboard/logs.html")


@dashboard_bp.route("/qr-scan")
@login_required
def qr_scan():
    return render_template("dashboard/qr_scan.html")


@dashboard_bp.route("/about")
def about():
    return render_template("public/index.html")
