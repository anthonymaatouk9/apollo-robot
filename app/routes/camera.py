import os
from flask import Blueprint, Response, jsonify, request, send_from_directory

camera_bp = Blueprint("camera", __name__)

RECORDINGS_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'static', 'recordings')


def generate_frames():
    """Generator for MJPEG stream."""
    import time
    from app.services.camera_stream import camera_stream

    # Wait up to 3 seconds for first frame
    waited = 0
    while camera_stream.get_jpeg_frame() is None and waited < 30:
        time.sleep(0.1)
        waited += 1

    while True:
        frame = camera_stream.get_jpeg_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
        )
        time.sleep(0.033)


@camera_bp.route("/stream")
def stream():
    """Live MJPEG camera stream with AI overlay."""
    from app.services.camera_stream import camera_stream
    if not camera_stream.running:
        camera_stream.start()
        import time
        time.sleep(2)  # give camera time to produce first frame
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Access-Control-Allow-Origin': '*'
        }
    )


@camera_bp.route("/start", methods=["POST"])
def start_camera():
    """Start the camera stream."""
    from app.services.camera_stream import camera_stream
    success = camera_stream.start()
    return jsonify({"started": success})


@camera_bp.route("/stop", methods=["POST"])
def stop_camera():
    """Stop the camera stream."""
    from app.services.camera_stream import camera_stream
    camera_stream.stop()
    return jsonify({"stopped": True})


@camera_bp.route("/start-recording", methods=["POST"])
def start_recording():
    """
    Start recording for a mission.
    Body: { "mission_id": 5 }
    """
    data       = request.get_json()
    mission_id = data.get("mission_id")
    from app.services.camera_stream import camera_stream
    if not camera_stream.running:
        camera_stream.start()
    filename = camera_stream.start_recording(mission_id)
    return jsonify({
        "recording": True,
        "filename":  filename,
        "message":   f"Recording started for mission #{mission_id}"
    })


@camera_bp.route("/stop-recording", methods=["POST"])
def stop_recording():
    """Stop recording and save file."""
    from app.services.camera_stream import camera_stream
    camera_stream.stop_recording()
    return jsonify({"recording": False, "message": "Recording saved"})


@camera_bp.route("/status", methods=["GET"])
def camera_status():
    """Get current camera and verification status."""
    from app.services.camera_stream import camera_stream
    return jsonify({
        "running":    camera_stream.running,
        "recording":  camera_stream.recording,
        "mission_id": camera_stream.mission_id,
        "result":     camera_stream.get_result()
    })


@camera_bp.route("/recordings", methods=["GET"])
def list_recordings():
    """List all saved recordings."""
    if not os.path.exists(RECORDINGS_FOLDER):
        return jsonify([])
    files = []
    for f in sorted(os.listdir(RECORDINGS_FOLDER), reverse=True):
        if f.endswith('.avi') or f.endswith('.mp4'):
            filepath = os.path.join(RECORDINGS_FOLDER, f)
            size_mb  = round(os.path.getsize(filepath) / 1024 / 1024, 2)
            files.append({
                "filename": f,
                "size_mb":  size_mb,
                "url":      f"/api/camera/recording/{f}"
            })
    return jsonify(files)


@camera_bp.route("/recording/<filename>")
def get_recording(filename):
    """Download a specific recording."""
    return send_from_directory(RECORDINGS_FOLDER, filename)


@camera_bp.route("/recording/<filename>/delete", methods=["POST"])
def delete_recording(filename):
    """Delete a specific recording."""
    filepath = os.path.join(RECORDINGS_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    os.remove(filepath)
    return jsonify({"message": f"{filename} deleted"})
