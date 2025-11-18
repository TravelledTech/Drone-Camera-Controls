import cv2
from ultralytics import YOLO

from ultralytics.utils import LOGGER    # Stops program
LOGGER.setLevel("ERROR")                # from outputting logs

model = YOLO("best.pt")
model.to('cpu')     # Sets to cpu (NO GPU AVAILABLE WHEN DOING LIVE TEST)

cap = cv2.VideoCapture(0) # Webcam (Switch to esp later)
#cap = cv2.VideoCapture("http://192.168.4.1:81/stream")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Run YOLO on frame
    results = model(frame)

    # YOLO automatically draws boxes
    annotated_frame = results[0].plot()

    cv2.imshow("Webcam + YOLO", annotated_frame)
    
    boxes = results[0].boxes
    
    if len(boxes) > 0:
        print(float(boxes.conf[0]))
    else:
        print("No detections")

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()