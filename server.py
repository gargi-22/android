from flask import Flask, request, Response
import threading
import numpy as np
import cv2
 
app = Flask(__name__)
 
CAM_IDS = ["cam1", "cam2", "cam3", "cam4"]
 
 
class CamBuffer:
    def __init__(self):
        self.frame = None
        self.lock = threading.Lock()
 
    def write(self, jpeg_bytes):
        with self.lock:
            self.frame = jpeg_bytes
 
    def read(self):
        with self.lock:
            return self.frame
 
 
buffers = {cam: CamBuffer() for cam in CAM_IDS}
 
PLACEHOLDER = None
 
 
def get_placeholder():
    global PLACEHOLDER
 
    if PLACEHOLDER is None:
        img = np.zeros((240, 320, 3), dtype=np.uint8)
 
        cv2.putText(
            img,
            "Waiting...",
            (80, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
 
        _, buf = cv2.imencode(
            ".jpg",
            img,
            [cv2.IMWRITE_JPEG_QUALITY, 50]
        )
 
        PLACEHOLDER = buf.tobytes()
 
    return PLACEHOLDER
 
 
@app.route("/upload_1", methods=["POST"])
def upload():
 
    cam_id = request.form.get("cam_id", "cam1")
 
    if cam_id not in buffers:
        return "Bad cam_id", 400
 
    file = request.files.get("frame")
 
    if not file:
        return "No frame", 400
 
    buffers[cam_id].write(file.read())
 
    return "OK"
 
 
def generate(cam_id):
 
    while True:
 
        frame = buffers[cam_id].read()
 
        if frame is None:
            frame = get_placeholder()
 
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame +
            b'\r\n'
        )
 
 
@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
 
    if cam_id not in buffers:
        return "Bad cam_id", 404
 
    return Response(
        generate(cam_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
 
 
@app.route("/")
def home():
 
    base = request.host_url.rstrip("/")
 
    return {
        "status": "Live",
        "streams": {
            cam: f"{base}/video_feed/{cam}"
            for cam in CAM_IDS
        }
    }
 
 
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True,
        use_reloader=False
    )
