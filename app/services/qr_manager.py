import qrcode
import json
import os
from PIL import Image
from datetime import datetime

# Folder where QR images are saved
QR_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'static', 'qrcodes')
os.makedirs(QR_FOLDER, exist_ok=True)


def generate_qr(patient_id, room, schedule_id):
    """
    Generate a QR code for a patient schedule.
    Encodes: { patient_id, room, schedule_id, generated_at }
    Saves as PNG and returns the filename.
    """
    data = json.dumps({
        "patient_id":  patient_id,
        "room":        room,
        "schedule_id": schedule_id,
        "generated_at": datetime.now().isoformat()
    })

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    filename = f"qr_patient{patient_id}_schedule{schedule_id}.png"
    filepath = os.path.join(QR_FOLDER, filename)
    img.save(filepath)

    return filename


def decode_qr(image_path):
    """
    Decode a QR code from an image file.
    Returns the parsed dict or None if not found.
    """
    try:
        import cv2
        img = cv2.imread(image_path)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[QR] Decode error: {e}")
    return None


def scan_from_camera(timeout=30):
    """
    Scan QR code from live camera feed.
    Used by the robot when it arrives at patient room.
    Returns parsed dict or None if timeout reached.
    """
    try:
        import cv2
        import time

        cap = cv2.VideoCapture(0)
        detector = cv2.QRCodeDetector()
        start = time.time()

        while time.time() - start < timeout:
            ret, frame = cap.read()
            if not ret:
                continue
            data, _, _ = detector.detectAndDecode(frame)
            if data:
                cap.release()
                try:
                    return json.loads(data)
                except Exception:
                    return None
            time.sleep(0.1)

        cap.release()
    except Exception as e:
        print(f"[QR] Camera scan error: {e}")
    return None
