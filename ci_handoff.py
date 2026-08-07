#!/usr/bin/env python3
"""Zero-LLM-token CI handoff for openwrt-cd (assistant pipeline).

Watches a GitHub Actions run (default: latest in-progress QCA-ALL on main)
until it completes, then:
  1. git fetch + git pull --rebase origin main (grabs committed failure log)
  2. downloads the kernel-diag / full failure artifacts into logs/kernel_diag/
  3. writes logs/build_status.json for the assistant to auto-handle

Separate from monitor_cd_ci.py so the original stays untouched.

Usage:
  python3 ci_handoff.py [RUN_ID]
  env GITHUB_TOKEN=<token>   # optional; falls back to the token in git remote
  env HTTPS_PROXY=...        # optional proxy, e.g. http://127.0.0.1:10808
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import zipfile

REPO = "Declarcall/openwrt-cd"
WORKDIR = os.path.dirname(os.path.abspath(__file__))
POLL_SEC = 60
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def get_token():
    t = os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=WORKDIR,
        ).stdout.strip()
        if "://" in out:
            userinfo = urllib.parse.urlparse(out).netloc.split("@")[0]
            if ":" in userinfo:
                t = userinfo.split(":", 1)[-1]
                if t:
                    return t
    except Exception:
        pass
    return None


def http_json(path, headers=None):
    url = "https://api.github.com" + path
    h = {"User-Agent": "CI-Monitor", "Accept": "application/vnd.github+json"}
    if headers:
        h.update(headers)
    token = get_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    opener = urllib.request.build_opener()
    if PROXY:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
        )
    req = urllib.request.Request(url, headers=h)
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(path, dest, headers=None):
    url = "https://api.github.com" + path
    h = {"User-Agent": "CI-Monitor", "Accept": "application/vnd.github+json"}
    if headers:
        h.update(headers)
    token = get_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    opener = urllib.request.build_opener()
    if PROXY:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
        )
    req = urllib.request.Request(url, headers=h)
    with opener.open(req, timeout=120) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def latest_run():
    try:
        d = http_json(f"/repos/{REPO}/actions/runs?per_page=10")
        for r in d.get("workflow_runs", []):
            if r.get("status") in ["in_progress", "queued", "requested"]:
                return r
        runs = d.get("workflow_runs", [])
        return runs[0] if runs else None
    except Exception as e:
        print(f"Error fetching latest run: {e}", flush=True)
        return None


def collect_artifacts(run_id, diag_dir):
    d = http_json(f"/repos/{REPO}/actions/runs/{run_id}/artifacts")
    for a in d.get("artifacts", []):
        name = a.get("name", "")
        if name.startswith("kernel-diag") or name.startswith("build-failure"):
            zip_path = os.path.join(diag_dir, name + ".zip")
            try:
                download(f"/repos/{REPO}/actions/artifacts/{a['id']}/zip", zip_path)
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(diag_dir)
                os.remove(zip_path)
                print(f"  artifact '{name}' -> {diag_dir}", flush=True)
            except Exception as e:
                print(f"  artifact '{name}' download failed: {e}", flush=True)


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not run_id:
        r = latest_run()
        if not r:
            print("No QCA-ALL run found.", flush=True)
            return
        run_id = r["id"]
        print(f"Watching latest run {run_id} ({r['status']}) head={r.get('head_sha','')[:8]}", flush=True)

    while True:
        try:
            d = http_json(f"/repos/{REPO}/actions/runs/{run_id}")
            status = d.get("status")
            concl = d.get("conclusion")
            print(f"[{time.strftime('%F %T')}] run {run_id} status={status} conclusion={concl}", flush=True)
            if status == "completed":
                break
        except Exception as e:
            print(f"  poll error (will retry): {e}", flush=True)
        time.sleep(POLL_SEC)

    print(f"CI_WORKFLOW_COMPLETED: run {run_id} conclusion: {concl}", flush=True)

    subprocess.run(["git", "fetch", "origin", "main"], cwd=WORKDIR)
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=WORKDIR)

    diag_dir = os.path.join(WORKDIR, "logs", "kernel_diag", str(run_id))
    os.makedirs(diag_dir, exist_ok=True)
    collect_artifacts(run_id, diag_dir)

    status = {
        "run_id": run_id,
        "status": status,
        "conclusion": concl,
        "head_sha": d.get("head_sha"),
        "html_url": d.get("html_url"),
        "failed": concl != "success",
        "diag_dir": os.path.relpath(diag_dir, WORKDIR),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    status_path = os.path.join(WORKDIR, "logs", "build_status.json")
    with open(status_path, "w") as f:
        json.dump(status, f, indent=2)
    print(f"Handoff written to {status_path}", flush=True)
    print(json.dumps(status, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
