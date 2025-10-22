from bs4 import BeautifulSoup
import time
import cv2
import numpy as np
import pytesseract
import re
import threading
from queue import Queue
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException

# ============================================================
#  Insurance Lookup (Async, Cached)
# ============================================================

def lookup_plate_tjekbil(plate, result_queue=None):
    """
    Scrape tjekbil.dk to check if a vehicle is self-insured.
    Runs in a background thread to avoid blocking the main loop.
    """
    driver = None
    info = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(options=chrome_options)
        url = f"https://www.tjekbil.dk/nummerplade/{plate.upper().replace(' ', '')}/overblik"

        driver.get(url)
        time.sleep(2)  # allow basic content load

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        text = soup.get_text(" ").lower()

        if "ikke fundet" in text or "not found" in text or len(text) < 100:
            info = None
        else:
            self_insured = any(
                kw in text
                for kw in [
                    "selvforsikret",
                    "egenforsikring",
                    "selvforsikring",
                    "selv forsikret",
                    "egen forsikring",
                ]
            )
            has_insurance_company = any(
                kw in text
                for kw in [
                    "tryg",
                    "topdanmark",
                    "if",
                    "alm brand",
                    "codan",
                    "sydbank forsikring",
                ]
            )

            info = {
                "plate": plate,
                "is_self_insured": self_insured,
                "has_insurance_company": has_insurance_company,
            }

    except (WebDriverException, TimeoutException):
        info = None
    finally:
        if driver:
            driver.quit()

    if result_queue:
        result_queue.put((plate, info))
    return info


# ============================================================
#  OCR Preprocessing
# ============================================================

def preprocess_for_ocr(roi):
    roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(denoised)
    _, thresh = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    return morph


# ============================================================
#  Plate Detection
# ============================================================

def detect_license_plates(frame, debug=False):
    small_frame = cv2.resize(frame, (640, 360))
    gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    plates = []
    debug_frame = small_frame.copy() if debug else None

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / h
        if 1.5 < aspect < 7.0 and w > 60 and h > 20:
            roi = small_frame[y : y + h, x : x + w]
            processed = preprocess_for_ocr(roi)
            configs = [
                r"--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                r"--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            ]
            best_text, best_conf = "", 0
            for cfg in configs:
                data = pytesseract.image_to_data(
                    processed, config=cfg, output_type=pytesseract.Output.DICT
                )
                texts, confs = [], []
                for j, conf in enumerate(data["conf"]):
                    if conf > 0:
                        texts.append(data["text"][j])
                        confs.append(conf)
                if confs:
                    text = re.sub(r"[^A-Z0-9]", "", "".join(texts).upper())
                    avg_conf = sum(confs) / len(confs)
                    if avg_conf > best_conf:
                        best_text, best_conf = text, avg_conf
            valid = any(
                re.match(p, best_text)
                for p in [r"^[A-Z]{2}[0-9]{4,5}$", r"^[A-Z]{3}[0-9]{3}$"]
            )
            if valid and best_conf > 40:
                scale_x = frame.shape[1] / 640
                scale_y = frame.shape[0] / 360
                X, Y, W, H = int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y)
                plates.append((best_text, (X, Y, W, H), best_conf))
                if debug:
                    cv2.rectangle(debug_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(debug_frame, best_text, (x, y - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    if debug:
        return plates, cv2.resize(debug_frame, frame.shape[1::-1])
    return plates


# ============================================================
#  Main Camera Loop
# ============================================================

def run_camera_detection(debug_mode=True):
    print("🎥 Starting smooth camera detection...\nPress Q to quit.")

    cap = cv2.VideoCapture(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("❌ Could not open camera.")
        return

    tracked_vehicles = {}
    lookup_results = Queue()
    last_ocr_time = {}
    frame_count = 0
    paused = False

    def lookup_worker():
        while True:
            plate, info = lookup_results.get()
            if plate in tracked_vehicles and info:
                tracked_vehicles[plate]["is_self_insured"] = info["is_self_insured"]
                tracked_vehicles[plate]["checked"] = True
            lookup_results.task_done()

    threading.Thread(target=lookup_worker, daemon=True).start()

    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_count % 5 == 0:
                    detected_plates, dbg_frame = detect_license_plates(frame, debug=debug_mode)
                else:
                    detected_plates = detect_license_plates(frame, debug=False)
                    dbg_frame = frame

                now = time.time()
                for plate_text, bbox, conf in detected_plates:
                    if plate_text not in tracked_vehicles:
                        print(f"🔍 New plate: {plate_text} ({conf:.0f}%)")
                        tracked_vehicles[plate_text] = {
                            "bbox": bbox,
                            "last_seen": now,
                            "checked": False,
                            "is_self_insured": False,
                        }
                        threading.Thread(
                            target=lookup_plate_tjekbil, args=(plate_text, lookup_results), daemon=True
                        ).start()
                    else:
                        tracked_vehicles[plate_text]["bbox"] = bbox
                        tracked_vehicles[plate_text]["last_seen"] = now

                # Draw tracked vehicles
                for plate, info in tracked_vehicles.items():
                    if now - info["last_seen"] < 5.0:
                        x, y, w, h = info["bbox"]
                        color = (0, 0, 255) if info["is_self_insured"] else (0, 255, 0)
                        label = f"{plate} - {'SELF' if info['is_self_insured'] else 'INSURED'}"
                        cv2.rectangle(dbg_frame, (x, y), (x + w, y + h), color, 2)
                        cv2.putText(dbg_frame, label, (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                cv2.putText(dbg_frame, f"Tracked: {len(tracked_vehicles)}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                cv2.imshow("Danish Vehicle Insurance Checker (Smooth)", dbg_frame)
                frame_count += 1

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):
                paused = not paused
                print("⏸️ Paused" if paused else "▶️ Resumed")
            elif key == ord("d"):
                debug_mode = not debug_mode
                print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")

    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


# ============================================================
#  Entry Point
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "camera":
        run_camera_detection(debug_mode=True)
    else:
        print("Usage: python3 main.py camera")
