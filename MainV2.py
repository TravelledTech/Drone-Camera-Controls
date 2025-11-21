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
YOLO_SKIP = 5          # Number of frames skipped until YOLO runs
CamToggle = True       # False = ESP32, True = webcam
MODEL_PATH = "best2.pt"  # Model used
# ------------------------------------------


# ---- ESP32 STREAM CHECK ----
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

        # Initial Variables
        self.hasToggle = True        # one-shot trigger
        self.isArmed = False         # remote arming state
        self.confidence = 0.60       # trigger threshold MAKE SURE ITS DECIMAL
        self.running = False
        self.frame_count = 0
        self.cap = None
        self.last_boxes = None
        self.last_labels = None
        self.has_shown_streaming = False

        self.root = root

        # Load YOLO
        self.model = YOLO(MODEL_PATH)

        # GUI Layout
        root.title("Detection Cam")
        root.geometry("900x560")

        style = ThemedStyle(root)
        style.set_theme("equilux")
        root.configure(bg=style.lookup(".", "background"))

        main_frame = ttk.Frame(root)
        main_frame.pack(fill="both", expand=True)

        # 2 frames within the frame (one for camera feed and other for controls)
        left_frame = ttk.Frame(main_frame, padding=5)
        left_frame.pack(side="left", fill="both", expand=True)

        right_frame = ttk.Frame(main_frame, padding=5)
        right_frame.pack(side="right", fill="y")

        # Video feed
        self.video_label = ttk.Label(left_frame)
        self.video_label.pack(expand=True, fill="both")

        ttk.Label(right_frame, text="Control Panel",
                  foreground="white",
                  font=("Segoe UI", 16, "bold")).pack(pady=5)

        # Buttons
        ttk.Button(right_frame, text="Start", width=15, command=self.start_stream).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Stop", width=15, command=self.stop_stream).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Exit", width=15, command=self.quit_app).pack(pady=5, fill="x")

        ttk.Separator(right_frame).pack(fill="x", pady=10)

        # YOLO toggle
        self.yolo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(right_frame, text="Enable YOLO",
                        variable=self.yolo_var,
                        command=self.toggle_yolo_mode).pack(anchor="center", pady=5)

        ttk.Separator(right_frame).pack(fill="x", pady=10)

        # ESP32-only UI
        if not CamToggle:
            ttk.Button(right_frame, text="Deploy", width=15, command=self.deploy_action).pack(pady=5, fill="x")
            ttk.Button(right_frame, text="Drop", width=15, command=self.drop_action).pack(pady=5, fill="x")

            ttk.Separator(right_frame).pack(fill="x", pady=10)

            self.arm_var = tk.BooleanVar()
            ttk.Checkbutton(right_frame, text="Arm Net",
                            variable=self.arm_var,
                            command=self.toggle_arm_mode).pack(anchor="center", pady=5)

            ttk.Separator(right_frame).pack(fill="x", pady=10)

        ttk.Label(right_frame, text="Latest Status",
                  foreground="lightgray",
                  font=("Segoe UI", 10, "bold")).pack()

        # Display the latest status
        self.status = ttk.Label(right_frame, text="Status: Idle",
                                foreground="gray",
                                wraplength=100,
                                justify="center")
        self.status.pack(pady=5)

        ttk.Separator(right_frame).pack(fill="x", pady=5)

        # Logo (why not)
        try:
            img = Image.open("logo.png").resize((120, 58))
            self.gui_img = ImageTk.PhotoImage(img)
            ttk.Label(right_frame, image=self.gui_img).pack(pady=12)
        except:
            pass


    # ---------- STREAM THREAD ----------
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

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # YOLO run scheduling
            self.frame_count += 1
            run_yolo = self.yolo_var.get() and (self.frame_count % YOLO_SKIP == 0)

            if run_yolo:
                results = self.model(frame_rgb, verbose=False)
                self.last_boxes = results[0].boxes
                self.last_labels = results[0].names

            annotated = frame_rgb.copy()

            # Draw YOLO boxes (So bounding box stays shown in between YOLO frames)
            if self.yolo_var.get() and self.last_boxes is not None:

                for box in self.last_boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = f"{self.last_labels[cls]} {conf:.2f}"

                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(annotated, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (0, 255, 0), 2)

                    #--------- CAMERA TRIGGER ---------
                    
                    #print("---- TRIGGER CHECK ----")
                    print("conf =", conf*100)
                    #print("threshold =", self.confidence)
                    #print("isArmed =", self.isArmed)
                    #print("hasToggle =", self.hasToggle)
                    #print("------------------------")
                    
                    # Checks:
                    # If confidence is high enough
                    # If trigger has been armed
                    # If it has been triggered before (only 1 trigger before reset)
                    if conf > self.confidence and self.isArmed and self.hasToggle:
                        try:
                            requests.get("http://192.168.4.1/deploy", timeout=2)
                            self.status.config(text="Deploy signal sent", foreground="cyan")
                        except Exception as e:
                            self.status.config(text="Deploy failed", foreground="red")
                            print(e)

                        self.hasToggle = False     # one-shot works properly now

            # Convert to Tkinter image
            img = Image.fromarray(annotated).resize((640, 480))
            tk_img = ImageTk.PhotoImage(img)
            self.root.after(0, self.update_frame, tk_img)

        if self.cap:
            self.cap.release()


    def update_frame(self, tk_img):
        self.video_label.imgtk = tk_img
        self.video_label.configure(image=tk_img)



    # ---------- BUTTON HANDLERS ----------
    # Start stream button
    def start_stream(self):
        self.hasToggle = True    # reset one-shot

        if self.running:
            return

        self.status.config(text="Checking camera...", foreground="orange")
        self.root.update_idletasks()

        if not CamToggle and not is_stream_available(STREAM_URL):
            self.status.config(text="ESP32 offline", foreground="red")
            return

        # Open camera
        if CamToggle:
            self.cap = cv2.VideoCapture(0)
        else:
            self.cap = cv2.VideoCapture(STREAM_URL)

        if not self.cap.isOpened():
            self.status.config(text="Failed to open stream", foreground="red")
            return

        self.running = True
        threading.Thread(target=self.stream_thread, daemon=True).start()


    def stop_stream(self):
        self.running = False
        self.hasToggle = True
        self.status.config(text="Stopped", foreground="orange")


    def quit_app(self):
        self.running = False
        self.root.destroy()

    # Enable and disable YOLO for better performance
    def toggle_yolo_mode(self):
        if self.yolo_var.get():
            self.status.config(text="YOLO Enabled", foreground="lime")
        else:
            self.last_boxes = None
            self.status.config(text="YOLO Disabled", foreground="orange")



    # ---------- ESP32 COMMANDS ----------
    #Command to deploy net
    def deploy_action(self):
        try:
            requests.get("http://192.168.4.1/deploy", timeout=2)
            self.status.config(text="Deploy signal sent", foreground="cyan")
        except Exception as e:
            self.status.config(text="Deploy failed", foreground="red")
            print(e)

    # Command to drop the net (after deploy)
    def drop_action(self):
        try:
            requests.get("http://192.168.4.1/release", timeout=2)
            self.status.config(text="Drop signal sent", foreground="cyan")
        except Exception as e:
            self.status.config(text="Drop failed", foreground="red")
            print(e)

    # Arm net (really only for automatic stuff, doesnt effect manual deploy)
    def toggle_arm_mode(self):
        try:
            if self.arm_var.get():
                self.isArmed = True
                requests.get("http://192.168.4.1/on", timeout=2)
                self.status.config(text="Net Armed", foreground="cyan")
            else:
                self.isArmed = False
                requests.get("http://192.168.4.1/off", timeout=2)
                self.status.config(text="Net unArmed", foreground="orange")
        except Exception as e:
            self.status.config(text="Net Arming Failed", foreground="red")
            print(e)



# ---------------- RUN ----------------
root = tk.Tk()
app = YOLOViewer(root)
root.mainloop()
