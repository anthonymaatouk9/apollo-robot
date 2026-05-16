from flask import Blueprint, request, jsonify
from app import db
from app.models import DispenseLog, Mission

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/verify", methods=["POST"])
def verify():
    """
    Manually trigger AI pill intake verification.
    Body: { "mission_id": 5, "timeout": 60 }
    """
    data       = request.get_json()
    mission_id = data.get("mission_id")
    timeout    = int(data.get("timeout", 60))

    try:
        from app.services.ai_verification import verify_pill_intake
        result = verify_pill_intake(timeout=timeout, camera_index=0)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Log result
    if mission_id:
        mission = Mission.query.get(mission_id)
        if mission:
            db.session.add(DispenseLog(
                mission_id=mission_id,
                patient_id=mission.schedule.patient_id if mission.schedule else None,
                action="ai_verify_manual",
                success=result.get("confirmed", False),
                detail=result.get("reason", "")
            ))
            db.session.commit()

    return jsonify(result)


@ai_bp.route("/test-camera", methods=["GET"])
def test_camera():
    """
    Test if camera is accessible.
    Returns camera info without running full verification.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return jsonify({"available": False, "message": "Camera not found"})
        ret, frame = cap.read()
        cap.release()
        if ret:
            h, w = frame.shape[:2]
            return jsonify({
                "available": True,
                "message":   "Camera working",
                "resolution": f"{w}x{h}"
            })
        return jsonify({"available": False, "message": "Camera opened but no frame"})
    except Exception as e:
        return jsonify({"available": False, "message": str(e)})


@ai_bp.route("/test-models", methods=["GET"])
def test_models():
    """
    Test if YOLOv8 and MediaPipe are loaded correctly.
    """
    results = {}

    # Test YOLOv8
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")
        results["yolov8"] = {"loaded": True, "model": "yolov8n.pt"}
    except Exception as e:
        results["yolov8"] = {"loaded": False, "error": str(e)}

    # Test MediaPipe
    try:
        import mediapipe as mp
        results["mediapipe"] = {"loaded": True}
    except Exception as e:
        results["mediapipe"] = {"loaded": False, "error": str(e)}

    # Test Camera
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        available = cap.isOpened()
        cap.release()
        results["camera"] = {"available": available}
    except Exception as e:
        results["camera"] = {"available": False, "error": str(e)}

    all_ok = all(
        v.get("loaded", v.get("available", False))
        for v in results.values()
    )

    return jsonify({
        "ready":   all_ok,
        "details": results
    })
