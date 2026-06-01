import cv2
import requests
import time
import threading
import queue

SERVER_URL = "https://android-1-6m4p.onrender.com/upload_1"
CAM_ID = "cam1"

# ✅ Point to your video file instead of webcam (0)
VIDEO_PATH = "VID_20260601_162529.mp4"

frame_queue = queue.Queue(maxsize=1)
upload_state = {"quality": 60, "slow_count": 0}


def capture_loop():
    while True:  # Loop the video forever
        cap = cv2.VideoCapture(VIDEO_PATH)

        if not cap.isOpened():
            print("Cannot open video file")
            time.sleep(1)
            continue

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        delay = 1.0 / fps

        while True:
            ret, frame = cap.read()

            if not ret:
                # End of video — restart from beginning
                break

            try:
                frame_queue.put_nowait(frame)
            except queue.Full:
                pass

            time.sleep(delay)

        cap.release()


def upload_loop():
    session = requests.Session()

    while True:
        frame = frame_queue.get()

        quality = upload_state["quality"]
        _, img_encoded = cv2.imencode(
            '.jpg', frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        frame_bytes = img_encoded.tobytes()

        t0 = time.monotonic()
        try:
            session.post(
                SERVER_URL,
                data={"cam_id": CAM_ID},
                files={"frame": ("frame.jpg", frame_bytes, "image/jpeg")},
                timeout=2
            )
            elapsed = time.monotonic() - t0

            if elapsed < 0.08:
                upload_state["slow_count"] = 0
                upload_state["quality"] = min(60, upload_state["quality"] + 2)
            else:
                upload_state["slow_count"] += 1
                if upload_state["slow_count"] > 3:
                    upload_state["quality"] = max(20, upload_state["quality"] - 5)

        except Exception as e:
            print(f"Upload failed ({quality}q): {e}")
            upload_state["quality"] = max(20, upload_state["quality"] - 10)


threading.Thread(target=capture_loop, daemon=True).start()
threading.Thread(target=upload_loop, daemon=True).start()

while True:
    time.sleep(1)
