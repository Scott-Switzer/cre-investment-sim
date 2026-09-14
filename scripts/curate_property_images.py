"""Curate the local property image library from Openverse (CC-licensed).

One query per type (4 total), 3 variants each, downloaded sequentially with
curl + polite pacing. Writes JSON manifest for docs generation.
"""
import json
import os
import subprocess
import time

OUT = "/Users/scottthomasswitzer/Documents/Fenrix_RE/services/game/client/public/images/properties"
os.makedirs(OUT, exist_ok=True)
UA = "FenrixRE-EducationalGame/0.1 (classroom CRE sim; contact scott@fenrix.education)"

QUERIES = {
    "Office": "modern office building glass facade exterior",
    "Industrial": "industrial warehouse",
    "Multifamily": "apartment building",
    "Retail": "shopping mall",
}

def curl_get(url):
    r = subprocess.run(
        ["curl", "-s", "-m", "40", "-A", UA, url],
        capture_output=True, text=True,
    )
    return r.stdout

def openverse(q, n=12):
    import urllib.parse
    url = (
        "https://api.openverse.org/v1/images/?q=" + urllib.parse.quote(q) +
        "&license=by,by-sa,cc0,pdm&mature=false&per_page=" + str(n) +
        "&size=large"
    )
    return curl_get(url)

def download(url, dest):
    r = subprocess.run(
        ["curl", "-s", "-L", "-m", "60", "-A", UA, "-o", dest, url],
        capture_output=True,
    )
    if r.returncode != 0 or not os.path.exists(dest):
        return False
    if os.path.getsize(dest) < 20_000:
        return False
    # Downscale to a web-friendly width (1200px, quality 78) with macOS sips.
    subprocess.run(
        ["sips", "-Z", "1200", "-s", "format", "jpeg", "-s", "formatOptions", "78", dest],
        capture_output=True,
    )
    return True

manifest = {}
for ptype, q in QUERIES.items():
    print(f"=== {ptype}: query '{q}' ===", flush=True)
    raw = openverse(q)
    try:
        data = json.loads(raw)
    except Exception:
        print("  API failed:", raw[:120], flush=True)
        time.sleep(10)
        raw = openverse(q)
        try:
            data = json.loads(raw)
        except Exception:
            print("  API failed again — skipping type", flush=True)
            continue

    results = data.get("results", [])
    print(f"  {len(results)} candidates", flush=True)

    picked = []
    for item in results:
        url = item.get("url", "")
        lic = (item.get("license") or "").lower()
        if not url or not lic:
            continue
        if lic not in ("cc0", "pdm", "by", "by-sa"):
            continue
        picked.append(item)
        if len(picked) >= 3:
            break

    manifest[ptype] = []
    for i, item in enumerate(picked, start=1):
        fname = f"{ptype.lower()}-{i}.jpg"
        path = os.path.join(OUT, fname)
        ok = download(item["url"], path)
        if not ok:
            print(f"  {fname} download failed, trying next", flush=True)
            continue
        entry = {
            "file": fname,
            "license": item.get("license"),
            "license_version": item.get("license_version"),
            "title": item.get("title", ""),
            "creator": item.get("creator", ""),
            "source": item.get("foreign_landing_url", ""),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        manifest[ptype].append(entry)
        print(f"  {fname}: {entry['license']} | {entry['title'][:50]} | {os.path.getsize(path)//1024}KB", flush=True)
        time.sleep(2)
    time.sleep(6)

with open(os.path.join(OUT, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
print("DONE", flush=True)
