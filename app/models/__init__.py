from datetime import datetime
import pytz
from app import db

def now_beirut():
    tz = pytz.timezone("Asia/Beirut")
    return datetime.now(tz).replace(tzinfo=None)


class Patient(db.Model):
    __tablename__ = "patients"
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    room       = db.Column(db.String(20),  nullable=False)
    bed        = db.Column(db.String(20),  nullable=True)
    notes      = db.Column(db.Text,        nullable=True)
    is_active  = db.Column(db.Boolean,     default=True)
    created_at = db.Column(db.DateTime,    default=now_beirut)
    schedules  = db.relationship("Schedule", backref="patient", lazy=True)
    logs       = db.relationship("DispenseLog", backref="patient", lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "room": self.room,
            "bed": self.bed, "notes": self.notes, "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Tube(db.Model):
    __tablename__ = "tubes"
    id         = db.Column(db.Integer, primary_key=True)
    medication = db.Column(db.String(120), nullable=True)
    stock      = db.Column(db.Integer,     default=0)
    updated_at = db.Column(db.DateTime,    default=now_beirut, onupdate=now_beirut)
    schedules  = db.relationship("Schedule", backref="tube", lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "medication": self.medication,
            "stock": self.stock,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Schedule(db.Model):
    __tablename__ = "schedules"
    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    tube_id      = db.Column(db.Integer, db.ForeignKey("tubes.id"),    nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    notes        = db.Column(db.Text, nullable=True)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=now_beirut)
    missions     = db.relationship("Mission", backref="schedule", lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "tube_id": self.tube_id,
            "medication": self.tube.medication if self.tube else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "notes": self.notes, "is_active": self.is_active,
        }


class Mission(db.Model):
    __tablename__ = "missions"
    id           = db.Column(db.Integer, primary_key=True)
    schedule_id  = db.Column(db.Integer, db.ForeignKey("schedules.id"), nullable=False)
    state        = db.Column(db.String(30), default="queued")
    fail_reason  = db.Column(db.String(255), nullable=True)
    created_at   = db.Column(db.DateTime, default=now_beirut)
    started_at   = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    logs         = db.relationship("DispenseLog", backref="mission", lazy=True)

    def advance(self, new_state, fail_reason=None):
        valid = {
            "queued":      ["navigating", "cancelled"],
            "navigating":  ["arrived",    "failed"],
            "arrived":     ["scanning_qr","failed"],
            "scanning_qr": ["verified",   "failed"],
            "verified":    ["dispensing", "failed"],
            "dispensing":  ["verifying",  "failed"],
            "verifying":   ["returning",  "failed"],
            "returning":   ["completed",  "failed"],
        }
        allowed = valid.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(f"Cannot move from '{self.state}' to '{new_state}'")
        self.state = new_state
        if new_state == "navigating":
            self.started_at = now_beirut()
        if new_state in ("completed", "failed", "cancelled"):
            self.completed_at = now_beirut()
        if fail_reason:
            self.fail_reason = fail_reason

    def to_dict(self):
        return {
            "id": self.id, "schedule_id": self.schedule_id,
            "patient_name": self.schedule.patient.name if self.schedule and self.schedule.patient else None,
            "room": self.schedule.patient.room if self.schedule and self.schedule.patient else None,
            "medication": self.schedule.tube.medication if self.schedule and self.schedule.tube else None,
            "state": self.state, "fail_reason": self.fail_reason,
            "created_at":   self.created_at.isoformat()   if self.created_at   else None,
            "started_at":   self.started_at.isoformat()   if self.started_at   else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class RobotState(db.Model):
    __tablename__ = "robot_state"
    id           = db.Column(db.Integer, primary_key=True, default=1)
    battery_pct  = db.Column(db.Integer, default=100)
    water_pct    = db.Column(db.Integer, default=100)
    current_room = db.Column(db.String(50), default="Station")
    phase        = db.Column(db.String(30), default="idle")
    mission_id   = db.Column(db.Integer, nullable=True)
    last_ping    = db.Column(db.DateTime, default=now_beirut)

    def to_dict(self):
        return {
            "battery_pct": self.battery_pct, "water_pct": self.water_pct,
            "current_room": self.current_room, "phase": self.phase,
            "mission_id": self.mission_id,
            "last_ping": self.last_ping.isoformat() if self.last_ping else None,
        }


class DispenseLog(db.Model):
    __tablename__ = "dispense_logs"
    id         = db.Column(db.Integer, primary_key=True)
    mission_id = db.Column(db.Integer, db.ForeignKey("missions.id"), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)
    tube_id    = db.Column(db.Integer, nullable=True)
    action     = db.Column(db.String(50))
    success    = db.Column(db.Boolean)
    detail     = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=now_beirut)

    def to_dict(self):
        return {
            "id": self.id, "mission_id": self.mission_id,
            "patient_id": self.patient_id, "tube_id": self.tube_id,
            "action": self.action, "success": self.success,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Alert(db.Model):
    __tablename__ = "alerts"
    id              = db.Column(db.Integer, primary_key=True)
    type            = db.Column(db.String(50))
    severity        = db.Column(db.String(10), default="warning")
    message         = db.Column(db.String(255))
    is_acknowledged = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=now_beirut)
    acknowledged_at = db.Column(db.DateTime, nullable=True)

    def acknowledge(self):
        self.is_acknowledged = True
        self.acknowledged_at = now_beirut()

    def to_dict(self):
        return {
            "id": self.id, "type": self.type, "severity": self.severity,
            "message": self.message, "is_acknowledged": self.is_acknowledged,
            "created_at":      self.created_at.isoformat()      if self.created_at      else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


class Waypoint(db.Model):
    __tablename__ = "waypoints"
    id    = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(50), nullable=False)
    type  = db.Column(db.String(20), nullable=False)
    x     = db.Column(db.Float, nullable=False)
    y     = db.Column(db.Float, nullable=False)
    room  = db.Column(db.String(20), nullable=True)

    def to_dict(self):
        return {
            "id": self.id, "label": self.label, "type": self.type,
            "x": self.x, "y": self.y, "room": self.room,
        }


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(120), nullable=False)
    subject    = db.Column(db.String(200), nullable=False)
    message    = db.Column(db.Text, nullable=False)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_beirut)

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "email":      self.email,
            "subject":    self.subject,
            "message":    self.message,
            "is_read":    self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
