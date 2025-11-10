import tkinter as tk
from tkinter import ttk
from ttkthemes import ThemedStyle
from PIL import Image, ImageTk, UnidentifiedImageError
import requests
import io
import threading
import socket

# Every pip install I need
# pip install ttkthemes
# pip install opencv-python
# pip install PySimpleGUI

# ---------- SETTINGS ----------
STREAM_URL = "http://192.168.4.1:81/stream"
HOST = "192.168.4.1"
PORT = 81
# -------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    root.title("ESP32-CAM Viewer")
    root.geometry("900x560")

    style = ThemedStyle(root)
    style.set_theme("equilux")

    class ESP32CamApp:
        def __init__(self, root):
            self.root = root
            self.root.configure(bg=style.lookup(".", "background"))

            # ========= MAIN LAYOUT =========
            # create a container with 2 halves
            main_frame = ttk.Frame(root)
            main_frame.pack(fill="both", expand=True)

            # left = video feed area
            left_frame = ttk.Frame(main_frame, padding=10)
            left_frame.pack(side="left", fill="both", expand=True)

            # right = control panel
            right_frame = ttk.Frame(main_frame, padding=10)
            right_frame.pack(side="right", fill="y")

            # ========= LEFT SIDE (VIDEO) =========
            self.label = ttk.Label(left_frame)
            self.label.pack(expand=True, fill="both")

            # ========= RIGHT SIDE (CONTROLS) =========
            ttk.Label(right_frame, text="Controls", font=("Segoe UI", 12, "bold")).pack(pady=(0,10))
            ttk.Button(right_frame, text="Start", width=15, command=self.start_stream).pack(pady=5, fill="x")
            ttk.Button(right_frame, text="Stop", width=15, command=self.stop_stream).pack(pady=5, fill="x")
            ttk.Button(right_frame, text="Exit", width=15, command=self.quit_app).pack(pady=5, fill="x")

            ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=10)

            # Example of extra buttons
            ttk.Button(right_frame, text="Deploy", width=15, command=self.deploy_action).pack(pady=5, fill="x")
            ttk.Button(right_frame, text="Drop", width=15, command=self.drop_action).pack(pady=5, fill="x")

            # Toggle
            self.auto_var = tk.BooleanVar()
            ttk.Checkbutton(
                right_frame,
                text="Arm Net",
                variable=self.auto_var,
                command=self.toggle_auto_mode    # ✅ link the function
            ).pack(anchor="w", pady=5)

            self.status = ttk.Label(right_frame, text="Status: Idle", foreground="gray")
            self.status.pack(pady=(20,0))
            # =======================================

            self.running = False
            self.thread = None

            root.attributes("-topmost", True)
            root.after(200, lambda: root.attributes("-topmost", False))

        # ---------- Utility ----------
        def test_connection(self):
            try:
                s = socket.create_connection((HOST, PORT), timeout=3)
                s.close()
                return True
            except Exception:
                return False

        # ---------- Background thread ----------
        def stream_video(self):
            try:
                with requests.get(STREAM_URL, stream=True, timeout=5) as r:
                    buffer = b""
                    for chunk in r.iter_content(chunk_size=1024):
                        if not self.running:
                            break
                        buffer += chunk
                        a = buffer.find(b'\xff\xd8')
                        b = buffer.find(b'\xff\xd9')
                        if a != -1 and b != -1:
                            jpg = buffer[a:b+2]
                            buffer = buffer[b+2:]
                            try:
                                img = Image.open(io.BytesIO(jpg))
                                img = img.resize((640, 480))
                                frame = ImageTk.PhotoImage(img)
                                self.root.after(0, self.update_image, frame)
                            except UnidentifiedImageError:
                                continue
            except requests.exceptions.ConnectTimeout:
                self.root.after(0, lambda: self.status.config(
                    text="Status: Timeout — camera not reachable", foreground="red"))
            except Exception as e:
                print("Stream error:", e)
                self.root.after(0, lambda: self.status.config(
                    text="Status: Error", foreground="red"))

        def update_image(self, frame):
            self.label.imgtk = frame
            self.label.configure(image=frame)

        # ---------- Buttons ----------
        def start_stream(self):
            if not self.running:
                if not self.test_connection():
                    self.status.config(text="Status: Can't reach camera", foreground="red")
                    return
                self.running = True
                self.status.config(text="Status: Streaming", foreground="green")
                self.thread = threading.Thread(target=self.stream_video, daemon=True)
                self.thread.start()

        def stop_stream(self):
            self.running = False
            self.status.config(text="Status: Stopped", foreground="orange")

        def quit_app(self):
            self.running = False
            self.root.destroy()

        # Example custom actions
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
        def toggle_auto_mode(self):
            try:
                if self.auto_var.get():
                    # Checkbox turned ON
                    requests.get("http://192.168.4.1/on", timeout=2)
                    self.status.config(text="Auto Mode: ON", foreground="cyan")
                else:
                    # Checkbox turned OFF
                    requests.get("http://192.168.4.1/off", timeout=2)
                    self.status.config(text="Auto Mode: OFF", foreground="orange")
            except Exception as e:
                self.status.config(text="Auto Mode: Failed", foreground="red")
                print("Auto toggle error:", e)

    app = ESP32CamApp(root)
    root.mainloop()
