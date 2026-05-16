import cv2
import time
import threading
import logging
import os
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

# Folder to save recordings
RECORDINGS_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'static', 'recordings')
os.makedirs(RECORDINGS_FOLDER, exist_ok=True)


class CameraStream:
    """
    Manages live camera feed with YOLOv8 + MediaPipe overlay.
    Streams frames to dashboard via MJPEG.
    Records video per mission.
    """

    def __init__(self):
        self.cap            = None
        self.running        = False
        self.current_frame  = None
        self.lock           = threading.Lock()
        self._thread        = None
        self.recording      = False
        self.video_writer   = None
        self.mission_id     = None
        self.status         = "idle"       # idle / watching / confirmed / failed
        self.confirmed      = False
        self.confirmed_frames = 0
        self.required_frames  = 3
        self._model           = None
        self._hands           = None
        self._frame_count     = 0
        self._last_boxes      = []  # keep last detection boxes to prevent flicker
        # QR scanning state
        self.qr_mode          = False
        self.qr_detected      = False
        self.qr_data          = None
        self.qr_expected      = {}

    def start(self, camera_index=0):
        """Start camera capture thread."""
        if self.running and self.cap and self.cap.isOpened():
            return True
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            logger.error("[CAM] Cannot open camera")
            return False
        self.running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("[CAM] Camera stream started")
        return True

    def stop(self):
        """Stop camera capture."""
        self.running = False
        self.stop_recording()
        if self.cap:
            self.cap.release()
        logger.info("[CAM] Camera stream stopped")

    def start_recording(self, mission_id):
        """Start recording video for a mission."""
        self.mission_id = mission_id
        timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename        = f"mission_{mission_id}_{timestamp}.mp4"
        filepath        = os.path.join(RECORDINGS_FOLDER, filename)
        fourcc          = cv2.VideoWriter_fourcc(*'mp4v')
        filepath        = filepath.replace('.avi', '.mp4')
        self.video_writer = cv2.VideoWriter(filepath, fourcc, 10.0, (640, 480))
        self.recording    = True
        self.confirmed    = False
        self.confirmed_frames = 0
        self.status       = "watching"
        logger.info(f"[CAM] Recording started: {filename}")
        return filename

    def stop_recording(self):
        """Stop recording and save file."""
        self.recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        self.status = "idle"
        logger.info("[CAM] Recording stopped")

    def start_qr_mode(self, expected_patient_id, expected_room, expected_schedule_id):
        """Switch camera to QR scanning mode."""
        self.qr_mode     = True
        self.qr_detected = False
        self.qr_data     = None
        self.status      = "scanning_qr"
        self.qr_expected = {
            "patient_id":  expected_patient_id,
            "room":        expected_room,
            "schedule_id": expected_schedule_id
        }
        logger.info(f"[CAM] QR mode started — expecting patient {expected_patient_id}")

    def stop_qr_mode(self):
        """Stop QR scanning mode."""
        self.qr_mode = False
        self.status  = "idle"
        logger.info("[CAM] QR mode stopped")

    def wait_for_qr(self, timeout=30):
        """
        Block until QR code is detected and verified or timeout.
        Returns (verified, data)
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.qr_detected:
                return True, self.qr_data
            time.sleep(0.5)
        return False, None

    def get_result(self):
        """Get current verification result."""
        return {
            "confirmed":       self.confirmed,
            "status":          self.status,
            "confirmed_frames": self.confirmed_frames,
            "required_frames":  self.required_frames
        }

    def _get_model(self):
        if self._model is None:
            try:
                from ultralytics import YOLO
                self._model = YOLO("yolov8n.pt")
            except Exception as e:
                logger.error(f"[CAM] YOLO load error: {e}")
        return self._model

    def _get_hands(self):
        if self._hands is None:
            try:
                from mediapipe.python.solutions import hands as mp_hands
                self._hands = mp_hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.6,
                    min_tracking_confidence=0.5
                )
            except Exception as e:
                logger.error(f"[CAM] MediaPipe load error: {e}")
        return self._hands

    def _capture_loop(self):
        """Main capture loop — runs in background thread."""
        model = self._get_model()
        hands = self._get_hands()

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            frame = cv2.resize(frame, (640, 480))
            h, w  = frame.shape[:2]
            self._frame_count += 1

            person_detected  = False
            cup_detected     = False
            drinking_gesture = False

            # -- YOLOv8 detection — run every 3rd frame, keep last result --
            if model and self._frame_count % 3 == 0:
                try:
                    results   = model(frame, verbose=False, conf=0.4)
                    new_boxes = []
                    for box in results[0].boxes:
                        cls_id   = int(box.cls[0])
                        cls_name = model.names[cls_id]
                        conf     = float(box.conf[0])
                        x1,y1,x2,y2 = map(int, box.xyxy[0])
                        if cls_name == "person" and conf > 0.5:
                            new_boxes.append(("person", conf, x1,y1,x2,y2))
                        if cls_name in ("cup","bottle","wine glass","bowl") and conf > 0.25:
                            new_boxes.append((cls_name, conf, x1,y1,x2,y2))
                    if new_boxes:
                        self._last_boxes = new_boxes
                except Exception as e:
                    logger.error(f"[CAM] YOLO error: {e}")

            # Always draw last known boxes (no flicker)
            for (cls_name, conf, x1,y1,x2,y2) in self._last_boxes:
                if cls_name == "person":
                    person_detected = True
                    cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
                    cv2.putText(frame, f"Person {conf:.0%}", (x1,y1-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
                else:
                    cup_detected = True
                    cv2.rectangle(frame, (x1,y1), (x2,y2), (255,165,0), 2)
                    cv2.putText(frame, f"{cls_name} {conf:.0%}", (x1,y1-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,165,0), 2)

            # -- MediaPipe hand tracking ---------------------------------
            if hands:
                try:
                    from mediapipe.python.solutions import hands as mp_hands
                    from mediapipe.python.solutions import drawing_utils as mp_drawing
                    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    hres  = hands.process(rgb)
                    if hres.multi_hand_landmarks:
                        for hlm in hres.multi_hand_landmarks:
                            mp_drawing.draw_landmarks(
                                frame, hlm, mp_hands.HAND_CONNECTIONS,
                                mp_drawing.DrawingSpec(color=(0,0,255), thickness=2),
                                mp_drawing.DrawingSpec(color=(0,255,255), thickness=2)
                            )
                            # Check drinking gesture — hand in upper 60% of frame
                            index_y  = hlm.landmark[8].y * h
                            thumb_y  = hlm.landmark[4].y * h
                            wrist_y  = hlm.landmark[0].y * h
                            index_x  = hlm.landmark[8].x * w
                            middle_y = hlm.landmark[12].y * h

                            # Gesture 1: hand raised above waist level
                            hand_raised = wrist_y < h * 0.65

                            # Gesture 2: fingers pointing toward face (upper half)
                            fingers_up = index_y < h * 0.55 and middle_y < h * 0.55

                            # Gesture 3: hand in center of frame (near mouth area)
                            hand_centered = w * 0.15 < index_x < w * 0.85

                            if hand_raised and fingers_up and hand_centered:
                                drinking_gesture = True
                except Exception as e:
                    logger.error(f"[CAM] MediaPipe error: {e}")

            # -- Verification logic --------------------------------------
            if self.recording and self.status == "watching":
                # Confirm if person + cup both visible in frame
                # Hand tracking is shown visually but not required for confirmation
                if person_detected and cup_detected:
                    self.confirmed_frames += 1
                    logger.info(f"[CAM] Verification frame {self.confirmed_frames}/{self.required_frames}")
                elif person_detected and drinking_gesture:
                    # Fallback: person + hand gesture (no cup needed)
                    self.confirmed_frames += 1
                    logger.info(f"[CAM] Gesture frame {self.confirmed_frames}/{self.required_frames}")
                else:
                    self.confirmed_frames = max(0, self.confirmed_frames - 1)

                if self.confirmed_frames >= self.required_frames:
                    self.confirmed = True
                    self.status    = "confirmed"

            # -- QR scanning overlay -------------------------------------
            if self.qr_mode:
                qr_found = False
                data     = None

                # Method 1: pyzbar (better for screen QR codes)
                try:
                    from pyzbar import pyzbar
                    gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    decoded = pyzbar.decode(gray)
                    if decoded:
                        data = decoded[0].data.decode("utf-8")
                        # Draw bounding box
                        rect = decoded[0].rect
                        cv2.rectangle(frame,
                            (rect.left, rect.top),
                            (rect.left + rect.width, rect.top + rect.height),
                            (0,255,0), 3)
                        qr_found = True
                except Exception:
                    pass

                # Method 2: OpenCV fallback
                if not qr_found:
                    try:
                        detector = cv2.QRCodeDetector()
                        d, points, _ = detector.detectAndDecode(frame)
                        if d:
                            data = d
                            qr_found = True
                            if points is not None:
                                pts = points[0].astype(int)
                                cv2.polylines(frame, [pts], True, (0,255,0), 3)
                    except Exception:
                        pass

                if data:
                    try:
                        import json
                        payload = json.loads(data)
                        exp     = self.qr_expected

                        patient_ok  = payload.get("patient_id")  == exp.get("patient_id")
                        room_ok     = str(payload.get("room"))    == str(exp.get("room"))
                        schedule_ok = payload.get("schedule_id") == exp.get("schedule_id")

                        if patient_ok and room_ok and schedule_ok:
                            self.qr_detected = True
                            self.qr_data     = payload
                            cv2.putText(frame, "QR VERIFIED", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,255,0), 3)
                        else:
                            cv2.putText(frame, "WRONG QR!", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,255), 3)
                            cv2.putText(frame, f"Expected patient {exp.get('patient_id')}", (10, 95),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)
                    except Exception:
                        cv2.putText(frame, "INVALID QR DATA", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                else:
                    # Scanning animation
                    scan_y = int((time.time() * 100) % h)
                    cv2.line(frame, (0, scan_y), (w, scan_y), (0,255,0), 2)
                    cv2.putText(frame, "Scanning for QR code...", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,165,0), 2)

            # -- Status overlay ------------------------------------------
            status_colors = {
                "idle":      (128, 128, 128),
                "watching":  (255, 165,   0),
                "confirmed": (0,   200,   0),
                "failed":    (0,     0, 255),
            }
            color = status_colors.get(self.status, (128,128,128))

            # Status bar at top
            cv2.rectangle(frame, (0,0), (w,36), (0,0,0), -1)
            if self.qr_mode:
                status_text = f"Apollo QR Scanner — {self.status.upper()}"
            elif self.recording:
                status_text = f"Apollo AI Verification — {self.status.upper()}"
            else:
                status_text = "Apollo Camera — Ready"
            cv2.putText(frame, status_text,
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # Confirmation progress bar
            if self.recording:
                bar_w = int((self.confirmed_frames / self.required_frames) * w)
                cv2.rectangle(frame, (0, h-8), (w, h), (40,40,40), -1)
                cv2.rectangle(frame, (0, h-8), (bar_w, h), color, -1)
                cv2.putText(frame, f"Confirmed: {self.confirmed_frames}/{self.required_frames}",
                    (10, h-12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

            # Recording indicator
            if self.recording:
                cv2.circle(frame, (w-20, 20), 8, (0,0,255), -1)
                cv2.putText(frame, "REC", (w-50, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)

            # Save frame to recording
            if self.recording and self.video_writer:
                self.video_writer.write(frame)

            # Store current frame for streaming
            with self.lock:
                self.current_frame = frame.copy()

            time.sleep(0.033)  # ~30fps

    def get_jpeg_frame(self):
        """Get current frame as JPEG bytes for MJPEG stream."""
        with self.lock:
            if self.current_frame is None:
                return None
            _, jpeg = cv2.imencode('.jpg', self.current_frame,
                                   [cv2.IMWRITE_JPEG_QUALITY, 70])
            return jpeg.tobytes()


# Global instance
camera_stream = CameraStream()
