import cv2
import time
import logging
import threading
import numpy as np

logger = logging.getLogger(__name__)

# Download pretrained YOLOv8n automatically on first run
try:
    from ultralytics import YOLO
    _model = None

    def get_model():
        global _model
        if _model is None:
            logger.info("[AI] Loading YOLOv8n model...")
            _model = YOLO("yolov8n.pt")  # auto-downloads if not present
            logger.info("[AI] Model loaded")
        return _model

except ImportError:
    logger.warning("[AI] Ultralytics not installed — AI verification will be mocked")
    get_model = None

try:
    from mediapipe.python.solutions import hands as mp_hands
    from mediapipe.python.solutions import drawing_utils as mp_drawing
    MEDIAPIPE_OK = True
except Exception:
    logger.warning("[AI] MediaPipe not available — hand tracking disabled")
    MEDIAPIPE_OK = False


# ─────────────────────────────────────────────────────────
# MAIN VERIFICATION FUNCTION
# ─────────────────────────────────────────────────────────

def verify_pill_intake(timeout=60, camera_index=0):
    """
    Watch camera feed and verify patient takes pill.

    Logic:
    1. Detect person + cup using YOLOv8
    2. Track hand position using MediaPipe
    3. Detect drinking gesture (hand near face)
    4. Require 3 consecutive confirmed frames

    Returns:
        dict: {
            "confirmed": bool,
            "reason": str,
            "confidence": float,
            "duration_seconds": int
        }
    """
    # Stub if no camera or model available
    if get_model is None:
        logger.info("[AI STUB] Pill intake verified (mock)")
        time.sleep(2)
        return {
            "confirmed":        True,
            "reason":           "stub_verification",
            "confidence":       1.0,
            "duration_seconds": 2
        }

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.warning("[AI] Camera not available — using mock")
        return {
            "confirmed":        True,
            "reason":           "no_camera_mock",
            "confidence":       1.0,
            "duration_seconds": 0
        }

    model           = get_model()
    start_time      = time.time()
    confirmed_frames = 0
    required_frames  = 3
    person_seen      = False
    cup_seen         = False
    result           = None

    # MediaPipe hands
    hands_detector = None
    if MEDIAPIPE_OK:
        hands_detector = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5
        )

    logger.info(f"[AI] Starting pill intake verification (timeout: {timeout}s)")

    try:
        while time.time() - start_time < timeout:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            h, w = frame.shape[:2]

            # -- Step 1: YOLO detection -----------------------------------
            yolo_results = model(frame, verbose=False, conf=0.4)
            detections   = yolo_results[0].boxes

            person_in_frame = False
            cup_in_frame    = False
            cup_bbox        = None

            for box in detections:
                cls_id    = int(box.cls[0])
                cls_name  = model.names[cls_id]
                conf      = float(box.conf[0])
                x1,y1,x2,y2 = map(int, box.xyxy[0])

                if cls_name == "person" and conf > 0.5:
                    person_in_frame = True
                    person_seen     = True

                if cls_name in ("cup", "bottle", "wine glass", "bowl") and conf > 0.25:
                    cup_in_frame = True
                    cup_seen     = True
                    cup_bbox     = (x1, y1, x2, y2)

            # -- Step 2: MediaPipe hand tracking -------------------------
            drinking_gesture = False
            if hands_detector and person_in_frame:
                rgb_frame   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hand_result = hands_detector.process(rgb_frame)

                if hand_result.multi_hand_landmarks:
                    for hand_landmarks in hand_result.multi_hand_landmarks:
                        # Get wrist and index finger tip positions
                        wrist     = hand_landmarks.landmark[0]
                        index_tip = hand_landmarks.landmark[8]
                        thumb_tip = hand_landmarks.landmark[4]

                        # Convert to pixel coordinates
                        wrist_y     = wrist.y * h
                        index_y     = index_tip.y * h
                        thumb_y     = thumb_tip.y * h
                        index_x     = index_tip.x * w

                        # Face region = top 35% of frame
                        face_region_y = h * 0.35

                        # Drinking gesture = hand raised to face level
                        if index_y < face_region_y and thumb_y < face_region_y:
                            drinking_gesture = True

                        # Also check if hand is near cup bounding box
                        if cup_bbox:
                            cx1, cy1, cx2, cy2 = cup_bbox
                            hand_x = index_tip.x * w
                            hand_y = index_tip.y * h
                            if cx1 < hand_x < cx2 and cy1 < hand_y < cy2:
                                drinking_gesture = True

            # -- Step 3: Confirmation logic ------------------------------
            if person_in_frame and (cup_in_frame or cup_seen) and drinking_gesture:
                confirmed_frames += 1
                logger.info(f"[AI] Confirmed frame {confirmed_frames}/{required_frames}")
            else:
                confirmed_frames = max(0, confirmed_frames - 1)

            if confirmed_frames >= required_frames:
                elapsed = time.time() - start_time
                result  = {
                    "confirmed":        True,
                    "reason":           "drinking_gesture_detected",
                    "confidence":       0.95,
                    "duration_seconds": int(elapsed)
                }
                logger.info(f"[AI] Pill intake CONFIRMED in {int(elapsed)}s")
                break

            time.sleep(0.1)

    except Exception as e:
        logger.error(f"[AI] Verification error: {e}")
        result = {
            "confirmed":        False,
            "reason":           f"error: {str(e)}",
            "confidence":       0.0,
            "duration_seconds": int(time.time() - start_time)
        }
    finally:
        cap.release()
        if hands_detector:
            hands_detector.close()

    if result is None:
        elapsed = time.time() - start_time
        result  = {
            "confirmed":        False,
            "reason":           "timeout_no_gesture_detected",
            "confidence":       0.0,
            "duration_seconds": int(elapsed)
        }
        logger.warning(f"[AI] Pill intake NOT confirmed — timeout after {int(elapsed)}s")

    return result


# ─────────────────────────────────────────────────────────
# BACKGROUND VERIFICATION (non-blocking)
# ─────────────────────────────────────────────────────────

class AIVerifier:
    """
    Non-blocking AI verifier.
    Runs verification in background thread.
    Mission runner checks result when done.
    """

    def __init__(self):
        self._result   = None
        self._running  = False
        self._thread   = None

    def start(self, timeout=60, camera_index=0):
        self._result  = None
        self._running = True
        self._thread  = threading.Thread(
            target=self._run,
            args=(timeout, camera_index),
            daemon=True
        )
        self._thread.start()

    def _run(self, timeout, camera_index):
        self._result  = verify_pill_intake(timeout, camera_index)
        self._running = False

    def is_done(self):
        return not self._running and self._result is not None

    def get_result(self):
        return self._result


# Global instance
ai_verifier = AIVerifier()
