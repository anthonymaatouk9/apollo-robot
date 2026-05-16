import threading
import time
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

BEIRUT = pytz.timezone("Asia/Beirut")


class MissionRunner:
    """
    Background thread that:
    1. Watches for queued missions whose scheduled time has arrived
    2. Executes each mission through all states automatically
    3. Uses mock navigation (timers) since no wheels yet
    """

    def __init__(self):
        self.running  = False
        self._thread  = None
        self._app     = None

    def start(self, app):
        """Start the mission runner with Flask app context."""
        self._app    = app
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Mission runner started")

    def stop(self):
        self.running = False
        logger.info("Mission runner stopped")

    def _loop(self):
        """Main loop — checks for ready missions every 10 seconds."""
        while self.running:
            try:
                with self._app.app_context():
                    self._check_and_dispatch()
            except Exception as e:
                logger.error(f"Mission runner error: {e}")
            time.sleep(10)

    def _check_and_dispatch(self):
        """Find queued missions that are ready to run and dispatch them."""
        from app.models import Mission, RobotState
        from app import db

        robot = RobotState.query.get(1)

        # Don't start new mission if robot is busy
        if robot and robot.phase == "on_mission":
            return

        # Don't start if battery critical
        if robot and robot.battery_pct <= 20:
            logger.warning("Battery critical — mission blocked")
            return

        now = datetime.now(BEIRUT).replace(tzinfo=None)

        # Find oldest queued mission whose schedule time has passed
        mission = Mission.query\
            .filter_by(state="queued")\
            .join(Mission.schedule)\
            .filter(Mission.schedule.has(is_active=True))\
            .order_by(Mission.created_at)\
            .first()

        if not mission:
            return

        # Check if scheduled time has arrived
        scheduled_at = mission.schedule.scheduled_at
        if scheduled_at > now:
            mins_left = int((scheduled_at - now).total_seconds() / 60)
            logger.info(f"Mission #{mission.id} not ready yet — {mins_left} min left")
            return

        logger.info(f"Dispatching mission #{mission.id}")
        self._execute_mission(mission.id)

    def _execute_mission(self, mission_id):
        """Execute a full mission through all states."""
        from app.models import Mission, RobotState, Schedule, Alert
        from app import db, create_app

        # Ensure we have app context
        from flask import current_app
        try:
            current_app._get_current_object()
        except RuntimeError:
            app = create_app()
            ctx = app.app_context()
            ctx.push()

        def advance(mission, state, fail_reason=None):
            """Advance mission state and update robot."""
            try:
                mission.advance(state, fail_reason=fail_reason)
                robot = RobotState.query.get(1)
                if robot:
                    from app.models import now_beirut
                    robot.last_ping  = now_beirut()
                    robot.mission_id = mission.id
                    if state in ("completed", "failed", "cancelled"):
                        robot.phase      = "idle"
                        robot.mission_id = None
                        robot.current_room = "Station"
                    else:
                        robot.phase = "on_mission"
                db.session.commit()
                logger.info(f"Mission #{mission.id} -> {state}")
            except Exception as e:
                logger.error(f"Advance error: {e}")
                db.session.rollback()

        def fail(mission, reason):
            """Fail the mission and create alert."""
            advance(mission, "failed", fail_reason=reason)
            db.session.add(Alert(
                type="mission_failed",
                severity="critical",
                message=f"Mission #{mission.id} failed: {reason}"
            ))
            db.session.commit()

        mission  = Mission.query.get(mission_id)
        schedule = mission.schedule
        patient  = schedule.patient
        tube     = schedule.tube

        if not patient or not patient.is_active:
            fail(mission, "Patient not found or discharged")
            return

        if tube.stock <= 0:
            fail(mission, f"Tube {tube.id} is empty")
            return

        # Safety timeout — if mission takes more than 5 minutes, fail it
        import threading
        def mission_timeout():
            time.sleep(300)
            try:
                m = Mission.query.get(mission_id)
                if m and m.state not in ("completed", "failed", "cancelled"):
                    logger.error(f"[TIMEOUT] Mission #{mission_id} timed out")
                    fail(m, "Mission timed out after 5 minutes")
                    db.session.commit()
            except Exception:
                pass
        threading.Thread(target=mission_timeout, daemon=True).start()

        # -- PHASE 1: navigating ---------------------------------------------
        advance(mission, "navigating")
        robot = RobotState.query.get(1)
        if robot:
            robot.current_room = f"En route to {patient.room}"
            db.session.commit()

        # Mock navigation delay (replace with real nav when wheels ready)
        logger.info(f"[NAV] Navigating to {patient.room}...")
        time.sleep(5)

        # -- PHASE 2: arrived ------------------------------------------------
        advance(mission, "arrived")
        if robot:
            robot.current_room = patient.room
            db.session.commit()
        time.sleep(1)

        # -- PHASE 3: scanning QR --------------------------------------------
        advance(mission, "scanning_qr")
        logger.info("[QR] Scanning QR code...")

        try:
            from app.services.camera_stream import camera_stream
            camera_stream.start()
            time.sleep(1)
            camera_stream.start_qr_mode(
                expected_patient_id  = patient.id,
                expected_room        = patient.room,
                expected_schedule_id = schedule.id
            )
            logger.info("[QR] Camera QR mode started — waiting for scan...")
            qr_verified, qr_data = camera_stream.wait_for_qr(timeout=30)
            camera_stream.stop_qr_mode()
            camera_stream.stop()
            qr_reason = "qr_verified" if qr_verified else "timeout_no_qr"
            logger.info(f"[QR] Result: {qr_verified} — {qr_reason}")
        except Exception as e:
            logger.error(f"[QR] Scanner error: {e}")
            try:
                from app.services.camera_stream import camera_stream
                camera_stream.stop_qr_mode()
                camera_stream.stop()
            except Exception:
                pass
            qr_verified = False
            qr_reason   = str(e)

        if not qr_verified:
            fail(mission, f"QR verification failed: {qr_reason}")
            return

        # -- PHASE 4: verified -----------------------------------------------
        advance(mission, "verified")
        time.sleep(1)

        # -- PHASE 5: dispensing ---------------------------------------------
        advance(mission, "dispensing")
        logger.info("[DISPENSE] Dispensing pill and water...")

        dispense_ok = _do_dispense(tube.id, mission.id, patient.id)
        if not dispense_ok:
            fail(mission, "Dispense failed — check hardware")
            return

        # Decrement tube stock
        tube.stock -= 1
        db.session.commit()

        # Low pill alert
        from config import Config
        if tube.stock < Config.LOW_PILL_THRESHOLD:
            from app import db
            existing = Alert.query.filter_by(
                type="low_pills", is_acknowledged=False
            ).filter(Alert.message.contains(f"Tube {tube.id}")).first()
            if not existing:
                db.session.add(Alert(
                    type="low_pills", severity="warning",
                    message=f"Tube {tube.id} ({tube.medication}) has only {tube.stock} pills left."
                ))
            db.session.commit()

        # -- PHASE 6: verifying (AI intake check) ----------------------------
        advance(mission, "verifying")
        logger.info("[AI] Verifying pill intake...")

        # Start camera only when needed for verification
        try:
            from app.services.camera_stream import camera_stream
            camera_stream.start()
            time.sleep(2)
            camera_stream.start_recording(mission.id)
            camera_stream.status           = "watching"
            camera_stream.confirmed        = False
            camera_stream.confirmed_frames = 0
            logger.info(f"[CAM] Recording started for mission #{mission.id}")
        except Exception as e:
            logger.error(f"[CAM] Could not start recording: {e}")

        # Wait for camera_stream to confirm — poll every second
        intake_confirmed = False
        verify_timeout   = 60
        verify_start     = time.time()

        logger.info("[AI] Waiting for pill intake confirmation from camera...")
        while time.time() - verify_start < verify_timeout:
            try:
                from app.services.camera_stream import camera_stream
                if camera_stream.confirmed:
                    intake_confirmed = True
                    logger.info("[AI] Pill intake CONFIRMED by camera")
                    break
            except Exception:
                pass
            time.sleep(1)

        if not intake_confirmed:
            logger.warning("[AI] Pill intake not confirmed within timeout")

        # Stop recording and camera
        try:
            from app.services.camera_stream import camera_stream
            camera_stream.stop_recording()
            camera_stream.stop()
            logger.info("[CAM] Camera stopped after verification")
        except Exception as e:
            logger.error(f"[CAM] Could not stop camera: {e}")
        if not intake_confirmed:
            logger.warning("[AI] Pill intake not confirmed — logging and continuing")
            db.session.add(Alert(
                type="general", severity="warning",
                message=f"Mission #{mission.id}: Patient may not have taken pill"
            ))
            db.session.commit()

        # Log AI result
        from app.models import DispenseLog
        db.session.add(DispenseLog(
            mission_id=mission.id,
            patient_id=patient.id,
            tube_id=tube.id,
            action="ai_verify",
            success=intake_confirmed,
            detail="drinking_gesture_detected" if intake_confirmed else "no_gesture_timeout"
        ))
        db.session.commit()

        # -- PHASE 7: returning ----------------------------------------------
        advance(mission, "returning")
        if robot:
            robot.current_room = "Returning to station"
            db.session.commit()
        logger.info("[NAV] Returning to station...")
        time.sleep(4)

        # -- PHASE 8: completed ----------------------------------------------
        advance(mission, "completed")
        logger.info(f"Mission #{mission_id} completed successfully")


def _do_dispense(tube_id, mission_id, patient_id):
    """
    Send dispense commands to Arduino.
    Returns True if successful.
    """
    from app.services.serial_manager import serial_manager
    from app.models import DispenseLog
    from app import db

    def log(action, success, detail):
        db.session.add(DispenseLog(
            mission_id=mission_id, patient_id=patient_id,
            tube_id=tube_id, action=action,
            success=success, detail=detail
        ))

    if serial_manager.is_connected():
        # Real hardware
        ok, resp = serial_manager.send_command(f"ROTATE_TUBE:{tube_id}")
        if not ok:
            log("dispense_pill", False, f"Rotate failed: {resp}")
            db.session.commit()
            return False

        ok, resp = serial_manager.send_command("DISPENSE_PILL", timeout=6)
        if not ok or "ERR" in resp:
            log("dispense_pill", False, resp)
            db.session.commit()
            return False

        ok, resp = serial_manager.wait_for_event("PILL_CONFIRMED", timeout=6)
        log("dispense_pill", ok, resp)

        # Dispense water
        serial_manager.send_command("DISPENSE_CUP")
        serial_manager.send_command("FILL_WATER:150")
        serial_manager.wait_for_event("WATER_DONE", timeout=15)
        log("dispense_water", True, "WATER_DONE")

        db.session.commit()
        return ok
    else:
        # Stub — mock success for PC development
        logger.info("[DISPENSE STUB] Pill and water dispensed (mock)")
        log("dispense_pill",  True, "STUB:PILL_CONFIRMED")
        log("dispense_water", True, "STUB:WATER_DONE")
        db.session.commit()
        time.sleep(2)
        return True


def _do_ai_verify(timeout=60):
    """
    Run AI pill intake verification using YOLOv8 + MediaPipe.
    Returns True if patient took pill.
    """
    try:
        from app.services.ai_verification import verify_pill_intake
        result = verify_pill_intake(timeout=timeout, camera_index=0)
        logger.info(f"[AI] Result: {result}")
        return result.get("confirmed", False)
    except Exception as e:
        logger.error(f"[AI] Verification failed: {e}")
        return False


# Global instance
mission_runner = MissionRunner()
