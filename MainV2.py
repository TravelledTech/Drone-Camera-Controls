import tkinter as tk
from tkinter import ttk
from ttkthemes import ThemedStyle
from PIL import Image, ImageTk
from ultralytics import YOLO
import cv2
import requests
import threading
import socket
import time

# ---------------- SETTINGS ----------------
STREAM_URL = "http://192.168.4.1:81/stream"
YOLO_SKIP = 5               # YOLO every N frames
CamToggle = False          # True = webcam, False = ESP32-CAM
MODEL_PATH = "best.pt"      # YOLO model
# ------------------------------------------

isArmed = False     # Checks if net is armed (for camera detection)
confidence = 70     # Confidence Level of Cam
hasToggle = True    # Only allows 1 trigger of the drop (with cam), Resets on start button

# ---- Non-blocking ESP32 availability test ----
def is_stream_available(url):
    try:
        host = url.split("/")[2].split(":")[0]
        port = int(url.split(":")[2].split("/")[0])
        sock = socket.create_connection((host, port), timeout=0.5)
        sock.close()
        return True
    except:
        return False


# ------------------ MAIN CLASS ------------------
class YOLOViewer:
    def __init__(self, root):
        self.has_shown_streaming = False
        self.root = root
        self.running = False
        self.cap = None
        self.frame_count = 0

        # Store last YOLO results (for non-flashing boxes)
        self.last_boxes = None
        self.last_labels = None

        # Load YOLO model
        self.model = YOLO(MODEL_PATH).to("cpu")

        # GUI Setup
        root.title("Detection Cam")
        root.geometry("900x560")

        style = ThemedStyle(root)
        style.set_theme("equilux")
        root.configure(bg=style.lookup(".", "background"))

        main_frame = ttk.Frame(root)
        main_frame.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main_frame, padding=5)
        left_frame.pack(side="left", fill="both", expand=True)

        right_frame = ttk.Frame(main_frame, padding=5)
        right_frame.pack(side="right", fill="y")

        # Video Label
        self.video_label = ttk.Label(left_frame)
        self.video_label.pack(expand=True, fill="both")

        txt = ttk.Label( right_frame,
                        text="Control Panel",
                        foreground="white",
                        font=("Segoe UI", 16, "bold")
                        )
        txt.pack(pady=5)     

        # Buttons
        ttk.Button(right_frame, text="Start", width=15, command=self.start_stream).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Stop", width=15, command=self.stop_stream).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Exit", width=15, command=self.quit_app).pack(pady=5, fill="x")

        ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=10)

        # YOLO Toggle
        self.yolo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            right_frame,
            text="Enable YOLO",
            variable=self.yolo_var,
            command=self.toggle_yolo_mode,
        ).pack(anchor="center", pady=5)

        ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=10)

        # ESP32-only buttons
        if not CamToggle:
            ttk.Button(right_frame, text="Deploy", width=15, command=self.deploy_action).pack(pady=5, fill="x")
            ttk.Button(right_frame, text="Drop", width=15, command=self.drop_action).pack(pady=5, fill="x")

            ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=10)

            self.arm_var = tk.BooleanVar()
            ttk.Checkbutton(
                right_frame,
                text="Arm Net",
                variable=self.arm_var,
                command=self.toggle_arm_mode
            ).pack(anchor="center", pady=5)

            ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=10)

        txt = ttk.Label( right_frame,
                        text="Latest Status",
                        foreground="lightgray",
                        font=("Segoe UI", 10, "bold")
                        )
        txt.pack()       

        # Status label
        self.status = ttk.Label(
            right_frame,
            text="Status: Idle",
            foreground="gray",
            wraplength=100,
            justify="center"
        )
        self.status.pack(pady=(5))
        
        ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=5)
        
        img = Image.open("logo.png")       # your image file
        img = img.resize((120,58))
        self.gui_img = ImageTk.PhotoImage(img)
    
        self.img_label = ttk.Label(right_frame, image=self.gui_img)
        self.img_label.pack(pady=12)

    # ---------- Streaming Thread ----------
    def stream_thread(self):
        while self.running:
            ret, frame = self.cap.read()

            if not ret:
                self.status.config(text="No feed (camera offline)", foreground="red")
                time.sleep(0.2)
                continue

            if not self.has_shown_streaming:
                self.status.config(text="Streaming", foreground="green")
                self.has_shown_streaming = True

            # Convert BGR → RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Clear boxes when YOLO is disabled
            if not self.yolo_var.get():
                self.last_boxes = None

            self.frame_count += 1
            run_yolo = self.yolo_var.get() and (self.frame_count % YOLO_SKIP == 0)

            # Run YOLO if enabled
            if run_yolo:
                results = self.model(frame_rgb, verbose=False)
                boxes = results[0].boxes
                self.last_boxes = boxes
                self.last_labels = results[0].names

            # Draw the annotated frame
            annotated = frame_rgb.copy()

            # Draw stored YOLO boxes only if YOLO is enabled
            if self.yolo_var.get() and self.last_boxes is not None:
                for box in self.last_boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    conf = box.conf[0].item()
                    cls = int(box.cls[0])
                    label = f"{self.last_labels[cls]} {conf:.2f}"

                    # Draw bounding box
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # Draw label
                    cv2.putText(
                        annotated, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2
                    )
                    
                    # Send signal if detection is over a certain level
                    print(float(boxes.conf[0]))
                    if float(boxes.conf[0]) > confidence and isArmed and hasToggle:
                        try:
                            requests.get("http://192.168.4.1/deploy", timeout=2)
                            self.status.config(text="Deploy signal sent", foreground="cyan")
                        except Exception as e:
                            self.status.config(text="Deploy failed", foreground="red")
                            print(e)
                        hasToggle = False

            # Convert to Tkinter image
            img = Image.fromarray(annotated)
            img = img.resize((640, 480))
            tk_img = ImageTk.PhotoImage(img)

            # Update GUI
            self.root.after(0, self.update_frame, tk_img)

        if self.cap:
            self.cap.release()


    def update_frame(self, tk_img):
        self.video_label.imgtk = tk_img
        self.video_label.configure(image=tk_img)


    # ---------- Start Button ----------
    def start_stream(self):
        self.has_shown_streaming = False
        hasToggle = True
        if self.running:
            return

        self.status.config(text="Checking camera...", foreground="orange")
        self.root.update_idletasks()

        # ESP32 Mode → check first
        if not CamToggle:
            if not is_stream_available(STREAM_URL):
                self.status.config(text="ESP32 offline", foreground="red")
                return

        # Create VideoCapture
        if CamToggle:
            self.cap = cv2.VideoCapture(0)
        else:
            self.cap = cv2.VideoCapture(STREAM_URL)

        if not self.cap.isOpened():
            self.status.config(text="Failed to open stream", foreground="red")
            return

        self.running = True
        threading.Thread(target=self.stream_thread, daemon=True).start()


    # ---------- Stop Button ----------
    def stop_stream(self):
        self.running = False
        self.status.config(text="Stopped", foreground="orange")


    # ---------- Quit ----------
    def quit_app(self):
        self.running = False
        self.root.destroy()


    # ---------- YOLO Toggle ----------
    def toggle_yolo_mode(self):
        if self.yolo_var.get():
            print("YOLO Enabled")
            self.status.config(text="YOLO Enabled", foreground="lime")
        else:
            print("YOLO Disabled")
            self.last_boxes = None
            self.status.config(text="YOLO Disabled", foreground="orange")


    # ---------- ESP32 COMMANDS ----------
    def deploy_action(self):
        try:
            requests.get("http://192.168.4.1/deploy", timeout=2)
            self.status.config(text="Deploy signal sent", foreground="cyan")
        except Exception as e:
            self.status.config(text="Deploy failed", foreground="red")
            print(e)

    def drop_action(self):
        try:
            requests.get("http://192.168.4.1/drop", timeout=2)
            self.status.config(text="Drop signal sent", foreground="cyan")
        except Exception as e:
            self.status.config(text="Drop failed", foreground="red")
            print(e)

    def toggle_arm_mode(self):
        try:
            if self.arm_var.get():
                requests.get("http://192.168.4.1/on", timeout=2)
                self.status.config(text="Net Armed", foreground="cyan")
            else:
                requests.get("http://192.168.4.1/off", timeout=2)
                self.status.config(text="Net unArmed", foreground="orange")
        except Exception as e:
            self.status.config(text="Net Arming Failed", foreground="red")
            print("Auto toggle error:", e)


# ---------------- RUN APP ----------------
root = tk.Tk()
app = YOLOViewer(root)
root.mainloop()
