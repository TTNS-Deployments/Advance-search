"""Starts the web app the way App Service runs it (gunicorn, 1 worker, 4 threads) in local mode, with its own
data folder seeded from Data/sample_docs. Used by the UI tests and by qa/screenshots.py."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBAPP = REPO / "Code" / "webapp"
SAMPLES = REPO / "Data" / "sample_docs"
PASSWORD = "qa-demo-password"
NOT_SEEDED = "Supplier-Price-List-2026.xlsx"  # left out so the UI tests can upload it


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    def __init__(self, seed: bool = True, skip: tuple[str, ...] = (NOT_SEEDED,)):
        self.data_dir = Path(tempfile.mkdtemp(prefix="advsearch-qa-"))
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {
            **os.environ, "ADVSEARCH_MODE": "local", "AUTH_MODE": "password", "DEMO_PASSWORD": PASSWORD,
            "LOCAL_DATA_DIR": str(self.data_dir), "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "ENVIRONMENT_NAME": "local", "SYNC_INTERVAL_SECONDS": "10", "DJANGO_DEBUG": "false",
            "PYTHONPATH": str(REPO / "Code" / "core"),
        }
        for name in ("STORAGE_BACKEND", "SEARCH_BACKEND", "EMBEDDING_BACKEND", "INGEST_WORKER"):
            self.env.pop(name, None)
        self.seed = seed
        self.skip = skip
        self.proc: subprocess.Popen | None = None
        self.log = self.data_dir / "server.log"

    def start(self) -> "LiveServer":
        if self.seed:
            folder = self.data_dir / "seed"
            folder.mkdir()
            for f in SAMPLES.iterdir():
                if f.suffix in {".pdf", ".docx", ".xlsx"} and f.name not in self.skip:
                    shutil.copy(f, folder / f.name)
            subprocess.run([sys.executable, "-m", "advancesearch", "ingest", str(folder)], env=self.env, check=True,
                           capture_output=True, cwd=REPO)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "gunicorn", f"--bind=127.0.0.1:{self.port}", "--workers=1", "--threads=4",
             "--timeout=120", "config.wsgi"], cwd=WEBAPP, env=self.env, stdout=self.log.open("w"),
            stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self.url}/healthz", timeout=2) as r:
                    if r.status == 200:
                        return self
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise RuntimeError(f"server did not start:\n{self.log.read_text()}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if not os.environ.get("QA_KEEP_DATA"):
            shutil.rmtree(self.data_dir, ignore_errors=True)


def sign_in(page, base: str, role: str = "Admin", password: str = PASSWORD) -> None:
    page.goto(f"{base}/auth/login")
    page.check(f"input[name=role][value={role}]")
    page.fill("#password", password)
    page.click("button[type=submit]")
    page.wait_for_url(f"{base}/")
