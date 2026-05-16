import os
from flask import Blueprint, jsonify, send_file, request
from app import db
from app.models import Schedule, Mission, Patient

qr_bp = Blueprint("qr", __name__)

QR_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'static', 'qrcodes')


@qr_bp.route("/generate/<int:schedule_id>", methods=["POST"])
def generate_qr(schedule_id):
    """
    Generate QR code for a schedule.
    Called automatically when schedule is created.
    """
    schedule = Schedule.query.get_or_404(schedule_id)
    patient  = schedule.patient

    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    from app.services.qr_manager import generate_qr as gen
    filename = gen(
        patient_id=patient.id,
        room=patient.room,
        schedule_id=schedule_id
    )

    return jsonify({
        "message":  "QR code generated",
        "filename": filename,
        "url":      f"/api/qr/image/{filename}"
    })


@qr_bp.route("/image/<filename>", methods=["GET"])
def get_qr_image(filename):
    """Serve the QR code image file."""
    filepath = os.path.join(QR_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "QR image not found"}), 404
    return send_file(filepath, mimetype="image/png")


@qr_bp.route("/verify", methods=["POST"])
def verify_qr():
    """
    Verify a scanned QR code against the active mission.
    Called by the robot after scanning.

    Body: {
        "patient_id":  1,
        "room":        "Room 3",
        "schedule_id": 2,
        "mission_id":  5
    }
    """
    data = request.get_json()

    patient_id  = data.get("patient_id")
    room        = data.get("room")
    schedule_id = data.get("schedule_id")
    mission_id  = data.get("mission_id")

    # Load schedule
    schedule = Schedule.query.get(schedule_id)
    if not schedule or not schedule.is_active:
        return jsonify({"verified": False, "reason": "Schedule not found or inactive"}), 400

    # Check patient matches
    if schedule.patient_id != patient_id:
        return jsonify({"verified": False, "reason": "Patient mismatch"}), 400

    # Check room matches
    patient = schedule.patient
    if patient.room != room:
        return jsonify({"verified": False, "reason": "Room mismatch"}), 400

    # Check mission exists and is in scanning_qr state
    if mission_id:
        mission = Mission.query.get(mission_id)
        if not mission:
            return jsonify({"verified": False, "reason": "Mission not found"}), 400
        if mission.state != "scanning_qr":
            return jsonify({"verified": False, "reason": f"Mission in wrong state: {mission.state}"}), 400

    return jsonify({
        "verified":    True,
        "patient_id":  patient_id,
        "patient_name": patient.name,
        "room":        room,
        "schedule_id": schedule_id,
        "message":     "QR verified successfully"
    })


@qr_bp.route("/scan-camera", methods=["POST"])
def scan_camera():
    """
    Trigger live camera QR scan on the Pi.
    Body: { "mission_id": 5, "timeout": 30 }
    """
    data       = request.get_json()
    mission_id = data.get("mission_id")
    timeout    = int(data.get("timeout", 30))

    from app.services.qr_manager import scan_from_camera
    result = scan_from_camera(timeout=timeout)

    if not result:
        return jsonify({"verified": False, "reason": "No QR code detected within timeout"}), 400

    # Auto verify the scanned result
    result["mission_id"] = mission_id
    from flask import current_app
    with current_app.test_request_context(
        "/api/qr/verify",
        method="POST",
        json=result
    ):
        pass

    return jsonify({"verified": True, "scanned": result})
