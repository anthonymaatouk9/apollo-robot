from flask import Blueprint, request, jsonify
from app import db
from app.models import Tube, RobotState, DispenseLog, Alert
from app.models import now_beirut
from config import Config

manual_bp = Blueprint("manual", __name__)


def _log(action, success, detail=None, tube_id=None):
    db.session.add(DispenseLog(
        action=f"manual_{action}", success=success,
        detail=detail, tube_id=tube_id
    ))


def _send_serial(command, wait_for=None, timeout=5):
    """
    Send command to Arduino.
    If SERIAL_PORT is set and connected, use real serial.
    Otherwise use stub (for PC development).
    """
    try:
        from app.services.serial_manager import serial_manager
        if serial_manager.is_connected():
            ok, resp = serial_manager.send_command(command, timeout=timeout)
            if wait_for and ok:
                ok, resp = serial_manager.wait_for_event(wait_for, timeout=timeout)
            return ok, resp
    except Exception as e:
        print(f"[SERIAL] Error: {e}")

    # Stub for PC development — always returns success
    print(f"[SERIAL STUB] Would send: {command}")
    if wait_for:
        return True, wait_for
    return True, f"ACK:{command.split(':')[0]}"


@manual_bp.route("/dispense-pill", methods=["POST"])
def dispense_pill():
    data    = request.get_json()
    tube_id = int(data.get("tube_id", 1))
    tube    = Tube.query.get_or_404(tube_id)

    if tube.stock <= 0:
        return jsonify({"error": f"Tube {tube_id} is empty"}), 400

    # Step 1: rotate to tube
    ok, resp = _send_serial(f"ROTATE_TUBE:{tube_id}")
    if not ok:
        _log("dispense_pill", False, f"Rotate failed: {resp}", tube_id)
        db.session.commit()
        return jsonify({"error": "Failed to rotate tube", "detail": resp}), 500

    # Step 2: dispense pill, wait for IR confirmation
    ok, resp = _send_serial("DISPENSE_PILL", wait_for="PILL_CONFIRMED", timeout=6)
    if not ok or "ERR" in resp:
        _log("dispense_pill", False, resp, tube_id)
        db.session.commit()
        return jsonify({"error": "Dispense failed", "detail": resp}), 500

    # Success
    tube.stock -= 1
    _log("dispense_pill", True, "PILL_CONFIRMED", tube_id)

    if tube.stock < Config.LOW_PILL_THRESHOLD:
        if not Alert.query.filter_by(type="low_pills", is_acknowledged=False).filter(
                Alert.message.contains(f"Tube {tube_id}")).first():
            db.session.add(Alert(
                type="low_pills", severity="warning",
                message=f"Tube {tube_id} ({tube.medication}) has only {tube.stock} pills left."
            ))

    db.session.commit()
    return jsonify({"message": "Pill dispensed successfully", "tube_stock_remaining": tube.stock})


@manual_bp.route("/dispense-cup", methods=["POST"])
def dispense_cup():
    ok, resp = _send_serial("DISPENSE_CUP", wait_for="CUP_OK", timeout=5)
    success  = ok and "ERR" not in resp
    _log("dispense_cup", success, resp)
    db.session.commit()
    if not success:
        return jsonify({"error": "Cup dispense failed", "detail": resp}), 500
    return jsonify({"message": "Cup dispensed"})


@manual_bp.route("/dispense-water", methods=["POST"])
def dispense_water():
    data      = request.get_json()
    amount_ml = int(data.get("amount_ml", 150))

    # Step 1: drop cup
    ok, resp = _send_serial("DISPENSE_CUP", wait_for="CUP_OK", timeout=5)
    if not ok or "ERR" in resp:
        _log("dispense_water", False, f"Cup failed: {resp}")
        db.session.commit()
        return jsonify({"error": "Cup dispense failed", "detail": resp}), 500

    # Step 2: fill water
    ok, resp = _send_serial(f"FILL_WATER:{amount_ml}", wait_for="WATER_DONE", timeout=15)
    success  = ok and "ERR" not in resp
    _log("dispense_water", success, resp)

    if success:
        robot = RobotState.query.get(1)
        if robot:
            robot.water_pct = max(0, robot.water_pct - round(amount_ml / 20))

    db.session.commit()
    if not success:
        return jsonify({"error": "Water fill failed", "detail": resp}), 500
    return jsonify({"message": f"{amount_ml}ml dispensed successfully"})


@manual_bp.route("/reset-tube", methods=["POST"])
def reset_tube():
    ok, resp = _send_serial("RESET_TUBE", wait_for="HOME_OK", timeout=10)
    _log("reset_tube", ok, resp)
    db.session.commit()
    return jsonify({"message": "Tube reset to home", "response": resp})


@manual_bp.route("/refill-pills", methods=["POST"])
def refill_pills():
    data    = request.get_json()
    tube_id = int(data.get("tube_id", 1))
    stock   = int(data.get("stock", 30))
    tube    = Tube.query.get_or_404(tube_id)
    tube.stock = stock
    db.session.commit()
    return jsonify({"message": f"Tube {tube_id} set to {stock} pills", "tube": tube.to_dict()})


@manual_bp.route("/refill-water", methods=["POST"])
def refill_water():
    robot = RobotState.query.get(1)
    if robot:
        robot.water_pct = 100
        db.session.commit()
    Alert.query.filter_by(type="low_water", is_acknowledged=False)\
        .update({"is_acknowledged": True})
    db.session.commit()
    return jsonify({"message": "Water tank marked as full"})


@manual_bp.route("/sensor-status", methods=["GET"])
def sensor_status():
    robot = RobotState.query.get(1)
    return jsonify({
        "battery_pct": robot.battery_pct if robot else None,
        "water_pct":   robot.water_pct   if robot else None,
        "phase":       robot.phase        if robot else None,
        "last_ping":   robot.last_ping.isoformat() if robot and robot.last_ping else None,
    })


@manual_bp.route("/connect-serial", methods=["POST"])
def connect_serial():
    """Try to connect to Arduino over serial."""
    from app.services.serial_manager import serial_manager
    success = serial_manager.connect()
    return jsonify({
        "connected": success,
        "message": "Arduino connected" if success else "Could not connect — check port in .env"
    })


@manual_bp.route("/serial-status", methods=["GET"])
def serial_status():
    """Check if Arduino serial is connected."""
    from app.services.serial_manager import serial_manager
    return jsonify({
        "connected": serial_manager.is_connected(),
        "port": Config.SERIAL_PORT
    })
