import csv
import datetime
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(__file__).parent
key = os.environ.get("IA_ACCESS_KEY")
secret = os.environ.get("IA_SECRET_KEY")
if not key or not secret:
    raise SystemExit("Configure IA_ACCESS_KEY and IA_SECRET_KEY in GitHub Actions secrets.")

base = "https://web.archive.org/save"
headers = {"Authorization": f"LOW {key}:{secret}", "Accept": "application/json", "User-Agent": "LITHOSPHERE-monthly-archive/1.0"}

def request(url, data=None):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)

jobs = []
failed = False
with (root / "archive-log.csv").open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["utc", "url", "status", "snapshot", "job_id", "detail"])
    def log(url, status, snapshot="", job="", detail=""):
        writer.writerow([datetime.datetime.now(datetime.timezone.utc).isoformat(), url, status, snapshot, job, detail])
        f.flush()

    for url in (root / "urls.txt").read_text().splitlines():
        if not url.strip():
            continue
        try:
            result = request(base, urllib.parse.urlencode({"url": url, "capture_all": "1"}).encode())
            job = result["job_id"]
            jobs.append((url, job))
            log(url, "submitted", job=job)
        except Exception as exc:
            failed = True
            log(url, "submission_error", detail=str(exc))
        time.sleep(30)

    deadline = time.monotonic() + 3600
    while jobs and time.monotonic() < deadline:
        pending = []
        for url, job in jobs:
            try:
                result = request(base + "/status/" + urllib.parse.quote(job, safe=""))
                status = result.get("status", "pending")
                if status == "success" and result.get("timestamp"):
                    snapshot = "https://web.archive.org/web/" + result["timestamp"] + "/" + result.get("original_url", url)
                    log(url, "success", snapshot, job)
                elif status == "error":
                    failed = True
                    log(url, "error", job=job, detail=result.get("message", ""))
                else:
                    pending.append((url, job))
            except Exception as exc:
                pending.append((url, job))
                log(url, "poll_error", job=job, detail=str(exc))
            time.sleep(2)
        jobs = pending
        if jobs:
            time.sleep(60)
    for url, job in jobs:
        failed = True
        log(url, "unconfirmed", job=job)
if failed:
    raise SystemExit("Some captures failed or remain unconfirmed; see CSV.")
