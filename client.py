import cv2
import requests
import time
import threading
import queue
 
SERVER_URL = "https://middleware-server-10.onrender.com/upload_1"
 
# Queue holds at most 1 frame — always the freshest one
frame_queue = queue.Queue(maxsize=1)
 
# Shared state for adaptive quality
upload_state = {"quality": 60, "slow_count": 0}
 
def capture_loop():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
 
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
 
        quality = upload_state["quality"]
        _, img_encoded = cv2.imencode(
            '.jpg', frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
 
        try:
            # Drop stale frame if uploader hasn't consumed it yet
            frame_queue.put_nowait(img_encoded.tobytes())
        except queue.Full:
            pass  # Skip — uploader is busy, don't queue stale frames
 
        time.sleep(0.005)  # ~30 FPS cap
 
    cap.release()
 
 
def upload_loop():
    session = requests.Session()  # Reuse TCP connection (keep-alive)
 
    while True:
        frame_bytes = frame_queue.get()  # Block until a frame is ready
 
        t0 = time.monotonic()
        try:
            session.post(
                SERVER_URL,
                files={"frame": frame_bytes},
                timeout=2
            )
            elapsed = time.monotonic() - t0
 
            # Adaptive quality: recover if fast, drop if slow
            if elapsed < 0.08:
                upload_state["slow_count"] = 0
                upload_state["quality"] = min(60, upload_state["quality"] + 2)
            else:
                upload_state["slow_count"] += 1
                if upload_state["slow_count"] > 3:
                    upload_state["quality"] = max(20, upload_state["quality"] - 5)
 
        except Exception as e:
            print(f"Upload failed ({upload_state['quality']}q): {e}")
            upload_state["quality"] = max(20, upload_state["quality"] - 10)
 
 
# Start both threads
threading.Thread(target=capture_loop, daemon=True).start()
threading.Thread(target=upload_loop, daemon=True).start()
 
# Keep main thread alive
while True:
    time.sleep(1)
 