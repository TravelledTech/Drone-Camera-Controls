import torch
import torch_directml
from ultralytics import YOLO
import yaml
import os

DATA_YAML_PATH = "drone_dataset\data.yaml"
MODEL_PATH = "yolov5su.pt"

with open(DATA_YAML_PATH, 'r') as f:
    data_config = yaml.safe_load(f)

device = torch_directml.device()

model = YOLO(MODEL_PATH)
model.to(device)

model.train(
    data=DATA_YAML_PATH,
    epochs=100,
    imgsz=480,
    device=device
)