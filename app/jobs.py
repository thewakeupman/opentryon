import json
import logging
import secrets
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from uuid import uuid4

from PIL import Image

from app.providers import ProviderError

logger = logging.getLogger(__name__)


class JobStore:
    def __init__(self, settings, provider):
        self.settings, self.provider = settings, provider
        self.root = settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vton")
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created REAL, status TEXT, payload TEXT)"
            )
            for row in db.execute(
                "SELECT id, payload FROM jobs WHERE status IN ('queued','running')"
            ).fetchall():
                job = json.loads(row[1])
                job.update(status="failed", error="Server restarted during generation. Please try again.")
                db.execute("UPDATE jobs SET status='failed', payload=? WHERE id=?", (json.dumps(job), row[0]))
        self.cleanup()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.root / "jobs.sqlite3", timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, job_id, **changes):
        with self.lock:
            job = self.get(job_id)
            job.update(changes)
            with self.connect() as db:
                db.execute(
                    "UPDATE jobs SET status=?, payload=? WHERE id=?", (job["status"], json.dumps(job), job_id)
                )

    def submit(self, person, garment, options):
        with self.lock:
            self.cleanup()
            with self.connect() as db:
                pending = db.execute(
                    "SELECT count(*) FROM jobs WHERE status IN ('queued','running')"
                ).fetchone()[0]
            if pending >= self.settings.max_pending:
                raise OverflowError("The generation queue is full. Please try again shortly.")
            job_id = str(uuid4())
            folder = self.root / job_id
            folder.mkdir()
            try:
                person.save(folder / "model.png")
                garment.save(folder / "garment.png")
                job = {
                    "id": job_id,
                    "status": "queued",
                    "created_at": time.time(),
                    "options": asdict(options),
                    "provider": self.provider.name,
                    "error": None,
                    "result_url": None,
                    "width": person.width,
                    "height": person.height,
                }
                with self.connect() as db:
                    db.execute(
                        "INSERT INTO jobs VALUES (?,?,?,?)",
                        (job_id, job["created_at"], job["status"], json.dumps(job)),
                    )
                self.pool.submit(self.run, job_id, options)
                return job
            except Exception:
                shutil.rmtree(folder)
                with self.connect() as db:
                    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                raise

    def run(self, job_id, options):
        self.update(job_id, status="running")
        start = time.monotonic()
        folder = self.root / job_id
        try:
            with Image.open(folder / "model.png") as source, Image.open(folder / "garment.png") as clothing:
                result = self.provider.generate(source.convert("RGB"), clothing.convert("RGB"), options)
                if result.size != source.size:
                    raise RuntimeError("Provider returned incorrect output dimensions.")
                result.convert("RGB").save(folder / "result.png")
            self.update(
                job_id,
                status="completed",
                result_url=f"/api/jobs/{job_id}/result",
                duration_seconds=round(time.monotonic() - start, 1),
            )
        except Exception as exc:
            incident = secrets.token_hex(4)
            logger.exception("Generation %s failed (incident %s)", job_id, incident)
            message = (
                "GPU memory exhausted. Use a GPU with more memory or a remote worker."
                if "out of memory" in str(exc).lower()
                else f"Generation failed. Check model setup and server logs (reference {incident})."
            )
            if isinstance(exc, ProviderError):
                message = str(exc)
            self.update(job_id, status="failed", error=message)

    def delete(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if not job:
                return False
            if job["status"] in {"queued", "running"}:
                raise ValueError("Wait for generation to finish before deleting this session.")
            folder = (self.root / job_id).resolve()
            if folder.parent != self.root:
                raise ValueError("Invalid session path.")
            if folder.exists():
                shutil.rmtree(folder)
            with self.connect() as db:
                db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            return True

    def cleanup(self):
        cutoff = time.time() - self.settings.retention_hours * 3600
        with self.lock, self.connect() as db:
            rows = db.execute(
                "SELECT id FROM jobs WHERE created < ? AND status NOT IN ('queued','running')", (cutoff,)
            ).fetchall()
            for (job_id,) in rows:
                self.delete(job_id)

    def close(self):
        self.pool.shutdown(wait=True)
