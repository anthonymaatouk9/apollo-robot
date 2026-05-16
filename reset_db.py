from app import create_app, db
from app.models import Patient, Tube, Schedule, Mission, DispenseLog, Alert, RobotState, Waypoint

app = create_app()

with app.app_context():
    DispenseLog.query.delete()
    Alert.query.delete()
    Mission.query.delete()
    Schedule.query.delete()
    Patient.query.delete()
    Tube.query.delete()
    RobotState.query.delete()
    Waypoint.query.delete()
    db.session.commit()

    db.session.add(RobotState(id=1, battery_pct=100, water_pct=100, current_room="Station", phase="idle"))
    for i in [1, 2, 3, 4]:
        db.session.add(Tube(id=i, medication=None, stock=0))
    db.session.commit()

    print("OK - All data cleared")
    print("OK - RobotState reset to 100% battery / 100% water / idle")
    print("OK - Tubes 1-4 reset to empty")
