from flask import Blueprint, request, jsonify
from app import db
from app.models import Tube, Alert
from config import Config

tubes_bp = Blueprint("tubes", __name__)

@tubes_bp.route("/", methods=["GET"])
def list_tubes():
    return jsonify([t.to_dict() for t in Tube.query.order_by(Tube.id).all()])

@tubes_bp.route("/<int:tid>", methods=["PUT"])
def update_tube(tid):
    tube = Tube.query.get_or_404(tid)
    data = request.get_json()
    if "medication" in data: tube.medication = data["medication"].strip() or None
    if "stock"      in data: tube.stock      = int(data["stock"])
    db.session.commit()
    return jsonify(tube.to_dict())

@tubes_bp.route("/<int:tid>/refill", methods=["POST"])
def refill_tube(tid):
    tube = Tube.query.get_or_404(tid)
    data = request.get_json()
    tube.stock = int(data.get("stock", 30))
    db.session.commit()
    Alert.query.filter_by(type="low_pills", is_acknowledged=False).filter(
        Alert.message.contains(f"Tube {tid}")
    ).update({"is_acknowledged": True})
    db.session.commit()
    return jsonify({"message": f"Tube {tid} refilled", "tube": tube.to_dict()})
