import cv2
import requests
import time
import threading
import queue

SERVER_URL = "https://android-1-6m4p.onrender.com/upload_1"
CAM_ID = "cam1"

frame_queue = queue.Queue(maxsize=3)
upload_state = {"quality": 60, "slow_count": 0}

def capture_loop():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():                          # ✅ Check camera opened
        print("ERROR: Cannot open camera!")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("WARNING: Frame read failed, retrying...")
            time.sleep(0.1)
            continue

        quality = upload_state["quality"]
        _, img_encoded = cv2.imencode(
            '.jpg', frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )

        try:
            frame_queue.put_nowait(img_encoded.tobytes())
        except queue.Full:
            try:
                frame_queue.get_nowait()            # Drop oldest
                frame_queue.put_nowait(img_encoded.tobytes())
            except:
                pass

        time.sleep(1 / 30)

    cap.release()


def upload_loop():
    session = requests.Session()

    while True:
        try:
            frame_bytes = frame_queue.get(timeout=5)  # ✅ Timeout so thread doesn't hang forever
        except queue.Empty:
            print("WARNING: No frames received for 5 seconds")
            continue

        t0 = time.monotonic()
        try:
            resp = session.post(
                SERVER_URL,
                data={"cam_id": CAM_ID},
                files={"frame": ("frame.jpg", frame_bytes, "image/jpeg")},
                timeout=3
            )
            elapsed = time.monotonic() - t0

            if resp.status_code == 200:             # ✅ Check server accepted the frame
                if elapsed < 0.1:
                    upload_state["slow_count"] = 0
                    upload_state["quality"] = min(70, upload_state["quality"] + 2)
                else:
                    upload_state["slow_count"] += 1
                    if upload_state["slow_count"] > 3:
                        upload_state["quality"] = max(20, upload_state["quality"] - 5)
            else:
                print(f"Server rejected frame: {resp.status_code}")

        except requests.exceptions.Timeout:
            print(f"Timeout ({upload_state['quality']}q) — reducing quality")
            upload_state["quality"] = max(20, upload_state["quality"] - 10)

        except requests.exceptions.ConnectionError:
            print("Connection lost — retrying in 2s...")
            upload_state["quality"] = max(20, upload_state["quality"] - 10)
            time.sleep(2)                           # ✅ Wait before retry on connection error

        except Exception as e:
            print(f"Upload failed ({upload_state['quality']}q): {e}")
            upload_state["quality"] = max(20, upload_state["quality"] - 10)


# ✅ Print startup info
print(f"Starting camera client...")
print(f"Server : {SERVER_URL}")
print(f"Cam ID : {CAM_ID}")
print(f"View at: https://android-1-6m4p.onrender.com/video_feed/{CAM_ID}")

threading.Thread(target=capture_loop, daemon=True).start()
threading.Thread(target=upload_loop, daemon=True).start()

while True:
    time.sleep(1)
