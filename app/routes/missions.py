from flask import Blueprint, request, jsonify
from app import db
from app.models import Mission, RobotState
from app.models import now_beirut

missions_bp = Blueprint("missions", __name__)

@missions_bp.route("/", methods=["GET"])
def list_missions():
    state  = request.args.get("state")
    active = request.args.get("active", "false").lower() == "true"
    query  = Mission.query
    if state:  query = query.filter_by(state=state)
    if active: query = query.filter(Mission.state.notin_(["completed","failed","cancelled"]))
    return jsonify([m.to_dict() for m in query.order_by(Mission.created_at.desc()).all()])

@missions_bp.route("/<int:mid>", methods=["GET"])
def get_mission(mid):
    return jsonify(Mission.query.get_or_404(mid).to_dict())

@missions_bp.route("/<int:mid>/advance", methods=["POST"])
def advance_mission(mid):
    m    = Mission.query.get_or_404(mid)
    data = request.get_json()
    new_state = data.get("state")
    if not new_state:
        return jsonify({"error": "state is required"}), 400
    try:
        m.advance(new_state, fail_reason=data.get("fail_reason"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    robot = RobotState.query.get(1)
    if robot:
        robot.last_ping = now_beirut()
        if new_state in ("completed", "failed", "cancelled"):
            robot.phase = "idle"; robot.mission_id = None
        else:
            robot.phase = "on_mission"; robot.mission_id = m.id
    db.session.commit()
    return jsonify(m.to_dict())

@missions_bp.route("/<int:mid>/cancel", methods=["POST"])
def cancel_mission(mid):
    m = Mission.query.get_or_404(mid)
    if m.state in ("completed","failed","cancelled"):
        return jsonify({"error": "Mission already terminal"}), 400
    m.advance("cancelled")
    db.session.commit()
    return jsonify({"message": "Mission cancelled", "mission": m.to_dict()})


@missions_bp.route("/<int:mid>/execute", methods=["POST"])
def execute_mission(mid):
    """
    Manually trigger execution of a queued mission immediately.
    Useful for testing without waiting for scheduled time.
    """
    from flask import current_app
    m = Mission.query.get_or_404(mid)
    if m.state != "queued":
        return jsonify({"error": f"Mission is {m.state} — only queued missions can be executed"}), 400

    from app.services.mission_runner import mission_runner
    import threading
    app = current_app._get_current_object()

    def run_with_context():
        with app.app_context():
            mission_runner._execute_mission(mid)

    t = threading.Thread(target=run_with_context, daemon=True)
    t.start()

    return jsonify({"message": f"Mission #{mid} execution started", "mission": m.to_dict()})


@missions_bp.route("/run-now", methods=["POST"])
def run_now():
    """
    Force the mission runner to check and dispatch immediately.
    Without waiting for the 10-second polling interval.
    """
    from app.services.mission_runner import mission_runner
    import threading
    t = threading.Thread(
        target=lambda: mission_runner._app and mission_runner._check_and_dispatch(),
        daemon=True
    )
    t.start()
    return jsonify({"message": "Mission check triggered"})


@missions_bp.route("/emergency-reset", methods=["POST"])
def emergency_reset():
    """
    Cancel ALL active missions and stop camera.
    Use when system gets stuck.
    """
    from app.models import RobotState
    from app.models import now_beirut

    # Cancel all non-terminal missions
    active = Mission.query.filter(
        Mission.state.notin_(["completed", "failed", "cancelled"])
    ).all()

    count = 0
    for m in active:
        m.state        = "cancelled"
        m.fail_reason  = "Emergency reset by nurse"
        m.completed_at = now_beirut()
        count += 1

    # Reset robot state
    robot = RobotState.query.get(1)
    if robot:
        robot.phase      = "idle"
        robot.mission_id = None
        robot.current_room = "Station"

    db.session.commit()

    # Stop camera
    try:
        from app.services.camera_stream import camera_stream
        camera_stream.stop_qr_mode()
        camera_stream.stop_recording()
        camera_stream.stop()
    except Exception:
        pass

    return jsonify({
        "message": f"Emergency reset complete — {count} mission(s) cancelled",
        "cancelled": count
    })


@missions_bp.route("/auto-cleanup", methods=["POST"])
def auto_cleanup():
    """
    Auto-cancel missions stuck in same state for too long.
    Called periodically by dashboard.
    Thresholds:
      navigating/returning: 3 minutes
      scanning_qr:          45 seconds
      verifying:            90 seconds
      other active:         5 minutes
    """
    from datetime import datetime
    from app.models import now_beirut

    now     = now_beirut()
    cleaned = 0

    active = Mission.query.filter(
        Mission.state.notin_(["completed", "failed", "cancelled", "queued"])
    ).all()

    for m in active:
        if not m.started_at:
            continue

        elapsed = (now - m.started_at).total_seconds()

        limits = {
            "navigating":  180,
            "arrived":     60,
            "scanning_qr": 45,
            "verified":    30,
            "dispensing":  60,
            "verifying":   90,
            "returning":   180,
        }

        limit = limits.get(m.state, 300)

        if elapsed > limit:
            m.state        = "failed"
            m.fail_reason  = f"Auto-cancelled: stuck in {m.state} for {int(elapsed)}s"
            m.completed_at = now_beirut()
            cleaned += 1

            # Stop camera if stuck in QR or verifying
            if m.state in ("scanning_qr", "verifying"):
                try:
                    from app.services.camera_stream import camera_stream
                    camera_stream.stop_qr_mode()
                    camera_stream.stop_recording()
                    camera_stream.stop()
                except Exception:
                    pass

    if cleaned > 0:
        robot = RobotState.query.get(1)
        if robot:
            robot.phase      = "idle"
            robot.mission_id = None
        db.session.commit()

    return jsonify({"cleaned": cleaned})
