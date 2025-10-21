import requests, os, glob, time, mimetypes

API = "http://127.0.0.1:8000/images"
ROOT = r"C:\Users\Vulca\Downloads\PRJ-5748\PRJ-5748\Report--earthquake-infrastructure-damage-eid-assessment-dataset-for-social-media-images\data\data\images"

def is_image(path):
    return os.path.splitext(path)[1].lower() in {".png",".jpg",".jpeg",".webp",".gif"}

pattern = os.path.join(ROOT, "**", "*")
paths = [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p) and is_image(p)]

print(f"Found {len(paths)} images")
for p in paths:
    ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
    with open(p, "rb") as fh:
        files = {"file": (os.path.basename(p), fh, ctype)}
        try:
            r = requests.post(API, files=files, timeout=60)
            r.raise_for_status()
            print("OK:", p, "->", r.json().get("id"))
        except Exception as e:
            print("ERR:", p, e)
    time.sleep(0.02)
