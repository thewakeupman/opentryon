import io
import threading
import time
from dataclasses import asdict
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.images import decode_image, preserve_regions
from app.jobs import JobStore
from app.main import create_app
from app.providers import CATEGORY_MAP, FashnProvider, Options, RemoteProvider
from tests.fakes import TestProvider


def png(size=(256, 384), color="white", mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")
    return buffer.getvalue()


def files():
    return {
        "model_image": ("../../person.png", png(), "image/png"),
        "garment_image": ("garment.png", png(), "image/png"),
    }


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / "data", weights_dir=tmp_path / "weights")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, TestProvider())) as browser:
        yield browser


def wait(client, job_id):
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.01)
    pytest.fail("Job did not finish")


@pytest.mark.parametrize("category", ["top", "bottom", "dress", "outerwear"])
def test_end_to_end(client, category):
    response = client.post("/api/try-on", files=files(), data={"category": category, "seed": 99})
    assert response.status_code == 202
    job = wait(client, response.json()["id"])
    assert job["status"] == "completed"
    assert job["options"]["seed"] == 99
    result = client.get(job["result_url"])
    assert result.headers["content-type"] == "image/png"
    assert result.headers["cache-control"] == "no-store"
    assert "opentryon-result-" in result.headers["content-disposition"]
    assert Image.open(io.BytesIO(result.content)).size == (256, 384)
    assert client.get(f"/api/jobs/{job['id']}/model").status_code == 200
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(job["result_url"]).status_code == 404
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_branding_is_exposed_to_the_web_client(settings):
    settings.app_name = "My Wardrobe"
    settings.app_tagline = "私人 AI 试衣间"
    settings.repository_url = "https://github.com/example/my-wardrobe"
    with TestClient(create_app(settings, TestProvider())) as client:
        health = client.get("/api/health").json()
        assert health["app"] == {
            "name": "My Wardrobe",
            "tagline": "私人 AI 试衣间",
            "repository_url": "https://github.com/example/my-wardrobe",
        }


def test_invalid_upload(client):
    upload = files()
    upload["model_image"] = ("fake.png", b"not an image", "image/png")
    response = client.post("/api/try-on", files=upload, data={"category": "top"})
    assert response.status_code == 422
    assert "image" in response.json()["detail"]


@pytest.mark.parametrize(
    "data",
    [
        {"category": "shoes"},
        {"category": "top", "steps": 100},
        {"category": "top", "seed": -1},
        {"category": "top", "garment_photo_type": "unknown"},
    ],
)
def test_invalid_options(client, data):
    assert client.post("/api/try-on", files=files(), data=data).status_code == 422


def test_authentication(settings):
    settings.api_key = "private-secret"
    with TestClient(create_app(settings, TestProvider())) as client:
        assert client.get("/").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/health").status_code == 401
        assert client.post("/api/try-on", files=files(), data={"category": "top"}).status_code == 401
        assert client.get(f"/api/jobs/{uuid4()}/result").status_code == 401
        assert client.get("/api/health", headers={"X-API-Key": "private-secret"}).status_code == 200


def test_missing_model_is_honest(settings):
    with TestClient(create_app(settings, FashnProvider(settings))) as client:
        assert client.get("/api/health").json()["provider"]["ready"] is False
        assert client.post("/api/try-on", files=files(), data={"category": "top"}).status_code == 503


def test_queue_capacity_and_busy_delete(settings):
    release = threading.Event()

    class Slow(TestProvider):
        def generate(self, person, garment, options):
            release.wait(5)
            return person

    settings.max_pending = 1
    with TestClient(create_app(settings, Slow())) as client:
        try:
            response = client.post("/api/try-on", files=files(), data={"category": "top"})
            job_id = response.json()["id"]
            assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
            assert client.delete(f"/api/jobs/{job_id}").status_code == 409
            full = client.post("/api/try-on", files=files(), data={"category": "top"})
            assert full.status_code == 429
            assert full.headers["retry-after"] == "10"
        finally:
            release.set()


def test_failure_does_not_leak_credentials(settings):
    class Broken(TestProvider):
        def generate(self, *args):
            raise RuntimeError("api_key=secret-value internal/path")

    with TestClient(create_app(settings, Broken())) as client:
        job_id = client.post("/api/try-on", files=files(), data={"category": "dress"}).json()["id"]
        job = wait(client, job_id)
        assert job["status"] == "failed"
        assert "secret-value" not in job["error"]
        assert "reference" in job["error"]


def test_retention_and_restart_recovery(settings):
    store = JobStore(settings, TestProvider())
    image = decode_image(png())
    job = store.submit(image, image, Options("top"))
    store.close()
    job_id = job["id"]
    with store.connect() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
    recovered = JobStore(settings, TestProvider())
    assert recovered.get(job_id)["status"] == "failed"
    with recovered.connect() as db:
        db.execute("UPDATE jobs SET created=0 WHERE id=?", (job_id,))
    recovered.cleanup()
    assert recovered.get(job_id) is None
    assert not (recovered.root / job_id).exists()
    recovered.close()


def test_body_limit(client):
    response = client.post(
        "/api/try-on", content=b"x" * (31 * 1024 * 1024), headers={"content-type": "application/octet-stream"}
    )
    assert response.status_code == 413


def test_bad_ids_and_path_traversal(client):
    assert client.get("/api/jobs/not-a-uuid").status_code == 422
    assert client.get(f"/api/jobs/{uuid4()}").status_code == 404
    assert client.get("/data/jobs.sqlite3").status_code == 404
    assert client.get("/../.env").status_code == 404


def test_normalization_and_limits():
    result = decode_image(png(color=(255, 0, 0, 0), mode="RGBA"))
    assert result.mode == "RGB"
    assert result.getpixel((0, 0)) == (255, 255, 255)
    assert result.info == {}
    with pytest.raises(ValueError, match="at least"):
        decode_image(png(size=(32, 32)))
    with pytest.raises(ValueError, match="15 MB"):
        decode_image(b"x" * (16 * 1024 * 1024))


def test_exif_orientation():
    source = Image.new("RGB", (200, 300))
    exif = source.getexif()
    exif[274] = 6
    buffer = io.BytesIO()
    source.save(buffer, "JPEG", exif=exif)
    result = decode_image(buffer.getvalue())
    assert result.size == (300, 200)
    assert not result.getexif()


def test_protection_locks_face_hair_background_and_allows_new_silhouette():
    original = Image.new("RGB", (256, 384), "white")
    generated = Image.new("RGB", (256, 384), "red")
    labels = np.zeros((384, 256), dtype=np.uint8)
    labels[130:300, 80:160] = 3
    labels[100:150, 100:140] = 1  # face overlaps garment envelope
    labels[90:140, 90:100] = 2  # hair
    new = labels.copy()
    new[160:250, 160:195] = 3  # wider garment may expand into background
    result = preserve_regions(original, generated, labels, new, [3], [1, 2])
    assert result.getpixel((110, 135)) == (255, 255, 255)
    assert result.getpixel((95, 125)) == (255, 255, 255)
    assert result.getpixel((5, 5)) == (255, 255, 255)
    assert result.getpixel((120, 200)) == (255, 0, 0)
    assert result.getpixel((180, 200)) == (255, 0, 0)


def test_no_garment_region_fails_instead_of_returning_original():
    image = Image.new("RGB", (256, 384))
    labels = np.zeros((384, 256), dtype=np.uint8)
    with pytest.raises(ValueError, match="No editable"):
        preserve_regions(image, image, labels, labels, [3], [1, 2])


def test_category_contract():
    assert CATEGORY_MAP == {"top": "tops", "outerwear": "tops", "bottom": "bottoms", "dress": "one-pieces"}
    assert asdict(Options("top"))["preserve"] is True


def test_remote_invalid_config(settings):
    settings.remote_url = "file:///etc/passwd"
    assert not RemoteProvider(settings).status()["ready"]


def test_remote_round_trip(settings, monkeypatch):
    import httpx

    job_id = str(uuid4())
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        assert request.headers["x-api-key"] == "worker-secret"
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"provider": {"mode": "local", "ready": True}})
        if request.method == "POST":
            assert b'name="category"' in request.content
            assert b"outerwear" in request.content
            return httpx.Response(202, json={"id": job_id})
        if request.url.path.endswith("/result"):
            return httpx.Response(200, content=png(), headers={"content-type": "image/png"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"status": "completed"})

    provider = RemoteProvider(settings)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.Client(
            base_url="https://worker/",
            headers={"X-API-Key": "worker-secret"},
            transport=httpx.MockTransport(handler),
        ),
    )
    result = provider.generate(decode_image(png()), decode_image(png()), Options("outerwear"))
    assert result.size == (256, 384)
    assert seen[-1] == ("DELETE", f"/api/jobs/{job_id}")


def test_remote_rejects_forwarding_loop(settings, monkeypatch):
    import httpx

    provider = RemoteProvider(settings)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.Client(
            base_url="https://worker/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"provider": {"mode": "remote", "ready": True}})
            ),
        ),
    )
    with pytest.raises(RuntimeError, match="local model"):
        provider.generate(decode_image(png()), decode_image(png()), Options("top"))
