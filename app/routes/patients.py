from flask import Blueprint, request, jsonify
from app import db
from app.models import Patient

patients_bp = Blueprint("patients", __name__)

@patients_bp.route("/", methods=["GET"])
def list_patients():
    show_all = request.args.get("all", "false").lower() == "true"
    query = Patient.query if show_all else Patient.query.filter_by(is_active=True)
    return jsonify([p.to_dict() for p in query.order_by(Patient.name).all()])

@patients_bp.route("/<int:pid>", methods=["GET"])
def get_patient(pid):
    p = Patient.query.get_or_404(pid)
    return jsonify(p.to_dict())

@patients_bp.route("/", methods=["POST"])
def create_patient():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("room"):
        return jsonify({"error": "name and room are required"}), 400
    p = Patient(
        name=data["name"].strip(),
        room=data["room"].strip(),
        bed=data.get("bed", "").strip() or None,
        notes=data.get("notes", "").strip() or None,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201

@patients_bp.route("/<int:pid>", methods=["PUT"])
def update_patient(pid):
    p = Patient.query.get_or_404(pid)
    data = request.get_json()
    if "name"  in data: p.name  = data["name"].strip()
    if "room"  in data: p.room  = data["room"].strip()
    if "bed"   in data: p.bed   = data["bed"].strip() or None
    if "notes" in data: p.notes = data["notes"].strip() or None
    db.session.commit()
    return jsonify(p.to_dict())

@patients_bp.route("/<int:pid>/discharge", methods=["POST"])
def discharge_patient(pid):
    p = Patient.query.get_or_404(pid)
    p.is_active = False
    for s in p.schedules:
        if s.is_active:
            s.is_active = False
    db.session.commit()
    return jsonify({"message": f"{p.name} discharged successfully"})
