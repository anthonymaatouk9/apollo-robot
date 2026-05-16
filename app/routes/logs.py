from flask import Blueprint, jsonify
from app.models import DispenseLog

logs_bp = Blueprint("logs", __name__)

@logs_bp.route("/", methods=["GET"])
def list_logs():
    logs = DispenseLog.query.order_by(DispenseLog.created_at.desc()).limit(100).all()
    return jsonify([l.to_dict() for l in logs])
