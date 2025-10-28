import os
import io
import requests
import torch
import torch.nn as nn
from torchvision import transforms, models
from google.cloud import storage
from google.oauth2 import service_account
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image

dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path)

BUCKET_NAME = "eid_swin_model"
BLOB_NAME = "eid_swin.pth"
LOCAL_MODEL_PATH = Path("eid_swin.pth")
GCS_KEY_FILE = os.getenv("GCS_KEY_FILE")

def get_gcs_client():
    """Create an authenticated GCS client using credentials from env."""
    if not GCS_KEY_FILE or not Path(GCS_KEY_FILE).exists():
        raise ValueError("Missing GCS_CREDENTIALS_JSON environment variable.")
    return storage.Client.from_service_account_json(GCS_KEY_FILE)

def download_model():
    """Download model file from GCS if not already cached locally."""
    if not LOCAL_MODEL_PATH.exists():
        client = get_gcs_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(BLOB_NAME)
        blob.download_to_filename(LOCAL_MODEL_PATH)

def load_model():
    """Load model architecture and weights."""
    model = models.swin_v2_s(weights=None) 
    num_classes = 4
    model.head = nn.Linear(model.head.in_features, num_classes)
    checkpoint = torch.load(LOCAL_MODEL_PATH, map_location="cpu")
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model

def make_inference(model, img_url: str):
    """Perform inference using the loaded model.
    Methodology from https://journals.sagepub.com/doi/10.1177/87552930251335649"""
    transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.CenterCrop(256),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    response = requests.get(img_url)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    img_tensor = transform(image).unsqueeze(0)
    model.eval()
    with torch.no_grad():
        outputs = model(img_tensor)
        pred_class = torch.argmax(outputs, dim=1).item()
    # 0: Irrelevant or non-informative to infrastructure damage assessment
    # 1: No Damage
    # 2: Mild Damage
    # 3: Severe Damage
    pred_map = {0: 1, 1: 2, 2: 3, 3: 0}
    return pred_map[pred_class]