from flask import Blueprint, request, jsonify
from app import db
from app.models import Alert

alerts_bp = Blueprint("alerts", __name__)

@alerts_bp.route("/", methods=["GET"])
def list_alerts():
    show_all = request.args.get("all", "false").lower() == "true"
    query = Alert.query if show_all else Alert.query.filter_by(is_acknowledged=False)
    return jsonify([a.to_dict() for a in query.order_by(Alert.created_at.desc()).all()])

@alerts_bp.route("/<int:aid>/acknowledge", methods=["POST"])
def acknowledge_alert(aid):
    alert = Alert.query.get_or_404(aid)
    alert.acknowledge()
    db.session.commit()
    return jsonify({"message": "Alert acknowledged", "alert": alert.to_dict()})

@alerts_bp.route("/acknowledge-all", methods=["POST"])
def acknowledge_all():
    Alert.query.filter_by(is_acknowledged=False).update({"is_acknowledged": True})
    db.session.commit()
    return jsonify({"message": "All alerts acknowledged"})
