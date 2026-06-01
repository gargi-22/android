from flask import Flask, request, Response
import numpy as np
import threading
 
app = Flask(__name__)
 
CAM_IDS = ["cam1", "cam2", "cam3", "cam4"]
 
class CamBuffer:
    def __init__(self):
        self.data    = None
        self.counter = 0
        self.lock    = threading.Lock()
        self.cond    = threading.Condition(self.lock)
 
    def write(self, jpeg_bytes):
        with self.cond:
            self.data    = jpeg_bytes
            self.counter += 1
            self.cond.notify_all()   # wake ALL waiting viewers at once
 
    def read(self, last_counter):
        with self.cond:
            # wait only if viewer already has this frame
            self.cond.wait_for(lambda: self.counter != last_counter, timeout=2)
            return self.data, self.counter
 
buffers = {cam: CamBuffer() for cam in CAM_IDS}
 
PLACEHOLDER = None
def placeholder():
    global PLACEHOLDER
    if PLACEHOLDER is None:
        import cv2
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(img, "Waiting...", (80, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
        _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 50])
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
    buffers[cam_id].write(file.read())   # store raw JPEG, no re-encode
    return "OK"
 
 
def generate(cam_id):
    last = 0
    while True:
        data, last = buffers[cam_id].read(last)
        if data is None:
            data = placeholder()
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            data +
            b'\r\n'
        )
 
 
@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    if cam_id not in buffers:
        return "Bad cam_id", 404
    return Response(
        generate(cam_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
 
 
@app.route("/")
def home():
    base = request.host_url.rstrip("/")
    return {
        "status": "Live",
        "streams": {cam: f"{base}/video_feed/{cam}" for cam in CAM_IDS}
    }
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)cle