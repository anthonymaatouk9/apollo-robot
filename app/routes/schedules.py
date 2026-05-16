from flask import Blueprint, request, jsonify
from datetime import datetime
from app import db
from app.models import Schedule, Patient, Tube, Mission

schedules_bp = Blueprint("schedules", __name__)

@schedules_bp.route("/", methods=["GET"])
def list_schedules():
    patient_id = request.args.get("patient_id", type=int)
    query = Schedule.query.filter_by(is_active=True)
    if patient_id:
        query = query.filter_by(patient_id=patient_id)
    return jsonify([s.to_dict() for s in query.order_by(Schedule.scheduled_at).all()])

@schedules_bp.route("/", methods=["POST"])
def create_schedule():
    data = request.get_json()
    for field in ["patient_id", "tube_id", "scheduled_at"]:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400
    patient = Patient.query.get(data["patient_id"])
    if not patient or not patient.is_active:
        return jsonify({"error": "Patient not found or discharged"}), 404
    tube = Tube.query.get(data["tube_id"])
    if not tube:
        return jsonify({"error": "Tube not found"}), 404
    try:
        scheduled_at = datetime.fromisoformat(data["scheduled_at"])
    except Exception:
        return jsonify({"error": "Invalid datetime format. Use: 2025-01-15T14:30:00"}), 400
    schedule = Schedule(
        patient_id=data["patient_id"], tube_id=data["tube_id"],
        scheduled_at=scheduled_at, notes=data.get("notes", "").strip() or None,
    )
    db.session.add(schedule)
    db.session.flush()
    mission = Mission(schedule_id=schedule.id, state="queued")
    db.session.add(mission)
    db.session.commit()

    # Auto-generate QR code for this schedule
    qr_filename = None
    try:
        from app.services.qr_manager import generate_qr
        qr_filename = generate_qr(
            patient_id=patient.id,
            room=patient.room,
            schedule_id=schedule.id
        )
    except Exception as e:
        print(f"[QR] Generation failed: {e}")

    return jsonify({
        "schedule":    schedule.to_dict(),
        "mission":     mission.to_dict(),
        "qr_filename": qr_filename,
        "qr_url":      f"/api/qr/image/{qr_filename}" if qr_filename else None,
        "message":     "Schedule created, mission queued, QR generated"
    }), 201

@schedules_bp.route("/<int:sid>", methods=["DELETE"])
def cancel_schedule(sid):
    schedule = Schedule.query.get_or_404(sid)
    schedule.is_active = False
    for mission in schedule.missions:
        if mission.state == "queued":
            mission.state = "cancelled"
    db.session.commit()
    return jsonify({"message": "Schedule cancelled"})
