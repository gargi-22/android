from flask import Flask, request, Response
import numpy as np
import threading
import cv2

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
            self.cond.notify_all()

    def read(self, last_counter):
        with self.cond:
            self.cond.wait_for(lambda: self.counter != last_counter, timeout=2)
            return self.data, self.counter

buffers = {cam: CamBuffer() for cam in CAM_IDS}

PLACEHOLDER = None

def get_placeholder():
    global PLACEHOLDER
    if PLACEHOLDER is None:
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(img, "Waiting for camera...", (140, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
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
    buffers[cam_id].write(file.read())
    return "OK", 200


@app.route("/frame/<cam_id>")
def get_frame(cam_id):
    if cam_id not in buffers:
        return "Bad cam_id", 404

    last = int(request.args.get("last", 0))
    data, counter = buffers[cam_id].read(last)

    if data is None:
        data = get_placeholder()

    return Response(
        data,
        mimetype='image/jpeg',
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Frame-Counter": str(counter)
        }
    )


def generate(cam_id):
    last = 0
    while True:
        try:
            data, last = buffers[cam_id].read(last)
            if data is None:
                data = get_placeholder()
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                data +
                b'\r\n'
            )
        except Exception:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                get_placeholder() +
                b'\r\n'
            )


@app.route("/stream/<cam_id>")
def stream(cam_id):
    if cam_id not in buffers:
        return "Bad cam_id", 404
    return Response(
        generate(cam_id),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive"
        }
    )


@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    if cam_id not in buffers:
        return "Bad cam_id", 404

    base = request.host_url.rstrip("/")

    html = """<!DOCTYPE html>
<html>
<head>
    <title>Live - """ + cam_id + """</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #111;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            font-family: Arial, sans-serif;
            color: #fff;
        }
        #feed {
            width: 100%;
            max-width: 800px;
            border-radius: 8px;
            display: block;
            background: #000;
        }
        #bar {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
            font-size: 14px;
        }
        #dot {
            width: 10px; height: 10px;
            border-radius: 50%;
            background: #f00;
        }
        #dot.live { background: #0f0; animation: pulse 1s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        #fps { color: #aaa; font-size: 12px; margin-top: 6px; }
    </style>
</head>
<body>
    <div id="bar">
        <div id="dot"></div>
        <span id="statusText">Connecting...</span>
    </div>
    <img id="feed" width="800" height="600" />
    <div id="fps">0 fps</div>

    <script>
        const CAM_ID  = \"""" + cam_id + """\";
        const BASE    = \"""" + base + """\";
        const img     = document.getElementById('feed');
        const dot     = document.getElementById('dot');
        const statusT = document.getElementById('statusText');
        const fpsDiv  = document.getElementById('fps');

        let lastCounter = 0;
        let frameCount  = 0;
        let lastFpsTime = Date.now();
        let errors      = 0;

        setInterval(() => {
            const now = Date.now();
            const elapsed = (now - lastFpsTime) / 1000;
            const fps = (frameCount / elapsed).toFixed(1);
            fpsDiv.innerText = fps + ' fps';
            frameCount = 0;
            lastFpsTime = now;
        }, 2000);

        async function fetchFrame() {
            try {
                const url = BASE + '/frame/' + CAM_ID + '?last=' + lastCounter + '&t=' + Date.now();
                const resp = await fetch(url);

                if (!resp.ok) throw new Error('HTTP ' + resp.status);

                const counter = resp.headers.get('X-Frame-Counter');
                if (counter) lastCounter = parseInt(counter);

                const blob = await resp.blob();
                const objUrl = URL.createObjectURL(blob);

                if (img._blobUrl) URL.revokeObjectURL(img._blobUrl);
                img._blobUrl = objUrl;
                img.src = objUrl;

                frameCount++;
                errors = 0;
                dot.className = 'live';
                statusT.innerText = '""" + cam_id.upper() + """ — LIVE';

            } catch (e) {
                errors++;
                dot.className = '';
                statusT.innerText = 'Reconnecting... (' + e.message + ')';
                await new Promise(r => setTimeout(r, 1000));
            }

            fetchFrame();
        }

        fetchFrame();
    </script>
</body>
</html>"""

    return html, 200, {"Content-Type": "text/html"}


@app.route("/status")
def status():
    result = {}
    for cam, buf in buffers.items():
        with buf.lock:
            result[cam] = {
                "live": buf.data is not None,
                "frames": buf.counter
            }
    return result


@app.route("/")
def home():
    base = request.host_url.rstrip("/")
    streams = {cam: base + "/video_feed/" + cam for cam in CAM_IDS}
    raw = {cam: base + "/stream/" + cam for cam in CAM_IDS}
    return {
        "status": "Live",
        "viewer_pages": streams,
        "raw_streams": raw,
        "status_check": base + "/status"
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
