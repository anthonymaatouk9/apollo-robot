from flask import Blueprint, request, jsonify
from app import db
from app.models import RobotState, Alert
from app.models import now_beirut
from config import Config

robot_bp = Blueprint("robot", __name__)

@robot_bp.route("/state", methods=["GET"])
def get_state():
    return jsonify(RobotState.query.get(1).to_dict())

@robot_bp.route("/state", methods=["POST"])
def update_state():
    robot = RobotState.query.get(1)
    data  = request.get_json()
    if "battery_pct"  in data:
        robot.battery_pct = int(data["battery_pct"])
        _check_battery_alert(robot.battery_pct)
    if "water_pct"    in data:
        robot.water_pct = int(data["water_pct"])
        _check_water_alert(robot.water_pct)
    if "current_room" in data: robot.current_room = data["current_room"]
    if "phase"        in data: robot.phase        = data["phase"]
    robot.last_ping = now_beirut()
    db.session.commit()
    return jsonify(robot.to_dict())

def _check_battery_alert(pct):
    if pct <= Config.LOW_BATTERY_THRESHOLD:
        severity = "critical" if pct <= Config.CRITICAL_BATTERY else "warning"
        if not Alert.query.filter_by(type="low_battery", is_acknowledged=False).first():
            db.session.add(Alert(type="low_battery", severity=severity,
                message=f"Battery at {pct}%. {'Mission blocked.' if pct <= Config.CRITICAL_BATTERY else 'Charge soon.'}"))

def _check_water_alert(pct):
    if pct <= Config.LOW_WATER_THRESHOLD:
        if not Alert.query.filter_by(type="low_water", is_acknowledged=False).first():
            db.session.add(Alert(type="low_water", severity="warning",
                message=f"Water tank at {pct}%. Refill soon."))
