"""Fetch replacement candidates for three weak slots and build a contact sheet."""
import json
import os
import subprocess
import urllib.parse

UA = "FenrixRE-EducationalGame/0.1 (classroom CRE sim; contact scott@fenrix.education)"
TMP = "/tmp/candidates"
os.makedirs(TMP, exist_ok=True)

SLOTS = {
    "multifamily-1": "apartment building street view residential",
    "office-3": "modern glass office tower exterior",
    "retail-1": "shopping center exterior storefronts",
}

def curl_get(url):
    r = subprocess.run(["curl", "-s", "-m", "40", "-A", UA, url], capture_output=True, text=True)
    return r.stdout

manifest = {}
for slot, q in SLOTS.items():
    url = ("https://api.openverse.org/v1/images/?q=" + urllib.parse.quote(q) +
           "&license=by,by-sa,cc0,pdm&mature=false&per_page=8&size=large")
    data = json.loads(curl_get(url))
    picked = [r for r in data.get("results", []) if (r.get("license") or "").lower() in ("cc0", "pdm", "by", "by-sa")][:3]
    manifest[slot] = []
    for i, item in enumerate(picked):
        dest = os.path.join(TMP, f"{slot}-{i+1}.jpg")
        subprocess.run(["curl", "-s", "-L", "-m", "60", "-A", UA, "-o", dest, item["url"]], capture_output=True)
        if os.path.getsize(dest) < 20_000:
            continue
        subprocess.run(["sips", "-Z", "1200", "-s", "format", "jpeg", "-s", "formatOptions", "78", dest], capture_output=True)
        manifest[slot].append({"file": f"{slot}-{i+1}.jpg", "license": item.get("license"),
                               "title": item.get("title", ""), "creator": item.get("creator", ""),
                               "source": item.get("foreign_landing_url", "")})
        print(f"{slot}-{i+1}: {item.get('license')} | {item.get('title','')[:60]}", flush=True)

with open(os.path.join(TMP, "candidates.json"), "w") as f:
    json.dump(manifest, f, indent=2)

# Contact sheet: 3 cols x 3 rows
from PIL import Image
files = sorted(f for f in os.listdir(TMP) if f.endswith(".jpg"))
W, H = 380, 240
sheet = Image.new("RGB", (W * 3, H * 3), "white")
for i, f in enumerate(files):
    img = Image.open(os.path.join(TMP, f))
    img.thumbnail((360, 220))
    sheet.paste(img, ((i % 3) * W + 10, (i // 3) * H + 10))
sheet.save("/Users/scottthomasswitzer/Documents/Fenrix_RE/artifacts/candidates_sheet.png")
print("SHEET DONE", flush=True)
