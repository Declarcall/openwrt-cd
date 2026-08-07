#!/usr/bin/env python3
"""Monitor an openwrt-cd GitHub Actions run and pull FULL logs + artifacts when done.

Zero-LLM-token: polls the GitHub API in background OS process.

Usage:
  python3 monitor_cd_ci.py [RUN_ID]
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

REPO = "Declarcall/openwrt-cd"
WORKDIR = os.path.dirname(os.path.abspath(__file__))
POLL_SEC = 60


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


def get_headers():
    h = {"User-Agent": "CI-Monitor", "Accept": "application/vnd.github+json"}
    token = get_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_latest_run_id():
    url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=5"
    req = urllib.request.Request(url, headers=get_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        for r in data.get("workflow_runs", []):
            if r.get("status") in ["in_progress", "queued"]:
                return r.get("id")
        runs = data.get("workflow_runs", [])
        return runs[0].get("id") if runs else None


def get_run(run_id):
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}"
    req = urllib.request.Request(url, headers=get_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_full_artifacts(run_id):
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/artifacts"
    req = urllib.request.Request(url, headers=get_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error fetching artifacts list: {e}", flush=True)
        return

    artifacts = data.get("artifacts", [])
    if not artifacts:
        print("No artifacts found for this run.", flush=True)
        return

    dest_dir = os.path.join(WORKDIR, "logs", "full_logs", str(run_id))
    os.makedirs(dest_dir, exist_ok=True)

    for art in artifacts:
        art_id = art.get("id")
        name = art.get("name", f"artifact_{art_id}")
        zip_url = f"https://api.github.com/repos/{REPO}/actions/artifacts/{art_id}/zip"
        zip_path = os.path.join(dest_dir, f"{name}.zip")

        print(f"Downloading full log artifact '{name}' (ID {art_id})...", flush=True)
        try:
            token = get_token()
            auth_header = f"Authorization: Bearer {token}" if token else "User-Agent: CI-Monitor"
            res = subprocess.run(
                ["curl", "-sSL", "-H", auth_header, "-o", zip_path, zip_url],
                check=True, capture_output=True, text=True
            )
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)
            os.remove(zip_path)
            print(f"  --> Extracted '{name}' into {dest_dir}", flush=True)
        except Exception as e:
            print(f"  --> Failed downloading artifact '{name}': {e}", flush=True)


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RUN_ID")
    if not run_id:
        run_id = fetch_latest_run_id()

    if not run_id:
        print("No active workflow run found.", flush=True)
        sys.exit(1)

    print(f"Starting zero-token monitor for run {run_id}...", flush=True)

    while True:
        try:
            d = get_run(run_id)
            status = d.get("status")
            conclusion = d.get("conclusion")
            print(f"[{time.strftime('%F %T')}] run {run_id} status={status} conclusion={conclusion}", flush=True)
            if status == "completed":
                break
        except Exception as e:
            print(f"  poll error (will retry): {e}", flush=True)
        time.sleep(POLL_SEC)

    print(f"CI_WORKFLOW_COMPLETED: run {run_id} conclusion: {conclusion}", flush=True)
    subprocess.run(["git", "fetch", "origin", "main"], cwd=WORKDIR)
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=WORKDIR)

    print("Fetching FULL log artifacts...", flush=True)
    download_full_artifacts(run_id)
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
