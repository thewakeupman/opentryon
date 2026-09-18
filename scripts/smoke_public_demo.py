"""Real-inference smoke test. Sends ONLY the bundled public upstream samples to the official demo."""

import argparse
import json
import os
import time
from pathlib import Path

import httpx
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sample_paths = {
        "model": root / "tests/fixtures/public-demo-model.webp",
        "garment": root / "tests/fixtures/public-demo-garment.webp",
    }
    with httpx.Client(
        base_url=args.url, headers={"X-API-Key": os.getenv("VTON_API_KEY", "")}, timeout=90
    ) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        if health.json()["provider"]["mode"] != "public":
            raise SystemExit(
                "Set VTON_PROVIDER=space and restart the server before this explicit public-demo test."
            )
        print("Sending bundled public sample images to the official FASHN Hugging Face demo.", flush=True)
        files = {
            f"{kind}_image": (
                f"{kind}.webp",
                sample_paths[kind].read_bytes(),
                "image/webp",
            )
            for kind in ("model", "garment")
        }
        response = client.post(
            "/api/try-on",
            files=files,
            data={
                "category": "top",
                "steps": 20,
                "seed": 42,
                "garment_photo_type": "model",
                "preserve": "false",
                "allow_public_upload": "true",
            },
        )
        response.raise_for_status()
        job_id = response.json()["id"]
        print(f"Session: {job_id}", flush=True)
        deadline = time.monotonic() + 660
        previous = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job["status"] != previous:
                print(job["status"], flush=True)
                previous = job["status"]
            if job["status"] == "failed":
                raise SystemExit(job["error"])
            if job["status"] == "completed":
                response = client.get(job["result_url"])
                response.raise_for_status()
                output = root / "test-results"
                output.mkdir(exist_ok=True)
                result_path = output / "public-demo-result.png"
                result_path.write_bytes(response.content)
                (output / "public-demo-job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
                with (
                    Image.open(result_path) as result,
                    Image.open(sample_paths["model"]) as source,
                ):
                    assert result.size == source.size
                    assert result.convert("RGB").tobytes() != source.convert("RGB").tobytes()
                print(f"Real inference completed in {job['duration_seconds']}s: {result_path}", flush=True)
                return
            time.sleep(2)
        raise SystemExit("Timed out; inspect the session in the API.")


if __name__ == "__main__":
    main()
