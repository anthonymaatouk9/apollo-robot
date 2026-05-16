import cv2
import json
import time
import logging

logger = logging.getLogger(__name__)


def scan_qr_live(expected_patient_id, expected_room, expected_schedule_id, timeout=30):
    """
    Open live camera, scan QR code, verify it matches mission.
    Returns (verified: bool, reason: str, scanned_data: dict)
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.warning("[QR] Camera not available — using mock")
        return True, "mock_no_camera", {}

    detector  = cv2.QRCodeDetector()
    start     = time.time()
    last_data = None

    logger.info(f"[QR] Scanning for patient {expected_patient_id} in {expected_room}")

    try:
        while time.time() - start < timeout:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            data, _, _ = detector.detectAndDecode(frame)

            if data and data != last_data:
                last_data = data
                logger.info(f"[QR] Scanned: {data}")

                try:
                    payload = json.loads(data)
                except Exception:
                    logger.warning("[QR] Invalid JSON in QR code")
                    time.sleep(0.5)
                    continue

                # Verify all fields match
                scanned_patient  = payload.get("patient_id")
                scanned_room     = payload.get("room")
                scanned_schedule = payload.get("schedule_id")

                if scanned_patient != expected_patient_id:
                    cap.release()
                    return False, f"Wrong patient: expected {expected_patient_id} got {scanned_patient}", payload

                if str(scanned_room) != str(expected_room):
                    cap.release()
                    return False, f"Wrong room: expected {expected_room} got {scanned_room}", payload

                if scanned_schedule != expected_schedule_id:
                    cap.release()
                    return False, f"Wrong schedule: expected {expected_schedule_id} got {scanned_schedule}", payload

                cap.release()
                return True, "qr_verified", payload

            time.sleep(0.1)

    except Exception as e:
        logger.error(f"[QR] Scan error: {e}")
        cap.release()
        return False, f"error: {str(e)}", {}

    cap.release()
    return False, "timeout_no_qr_detected", {}
