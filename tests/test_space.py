import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.images import decode_image
from app.main import create_app
from app.providers import Options, ProviderError, SpaceProvider
from tests.test_api import files, png


def test_space_requires_consent_before_any_network(monkeypatch):
    provider = SpaceProvider()
    monkeypatch.setattr(provider, "_client", lambda: pytest.fail("No network before consent"))
    with pytest.raises(ProviderError, match="explicitly"):
        provider.generate(None, None, Options("top", preserve=False))
    with pytest.raises(ProviderError, match="preserve=false"):
        provider.generate(None, None, Options("top", allow_public_upload=True))


def test_space_api_consent_enforced(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    with TestClient(create_app(settings, SpaceProvider())) as client:
        response = client.post("/api/try-on", files=files(), data={"category": "top", "preserve": "false"})
        assert response.status_code == 422
        assert "consent" in response.json()["detail"]
        response = client.post(
            "/api/try-on", files=files(), data={"category": "top", "allow_public_upload": "true"}
        )
        assert response.status_code == 422
        assert "preserve=false" in response.json()["detail"]


def test_space_stream_round_trip(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/gradio_api/upload":
            assert b"model.png" in request.content and b"garment.png" in request.content
            return httpx.Response(200, json=["/tmp/model.png", "/tmp/garment.png"])
        if request.method == "POST":
            data = json.loads(request.content)["data"]
            assert data[2:] == ["one-pieces", "flat-lay", 20, 1.5, 123, True]
            return httpx.Response(200, json={"event_id": "abc123"})
        if request.url.path.endswith("/abc123"):
            result = [{"path": "/tmp/result.webp", "url": "http://malicious.example/private"}]
            return httpx.Response(
                200,
                text="event: heartbeat\ndata: null\n\nevent: complete\ndata: " + json.dumps(result) + "\n\n",
            )
        assert request.url.host == "fashn-ai-fashn-vton-1-5.hf.space"
        assert request.url.path == "/gradio_api/file=/tmp/result.webp"
        return httpx.Response(200, content=png(size=(192, 256), color="red"))

    provider = SpaceProvider()
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.Client(base_url=provider.base_url, transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(
        decode_image(png()),
        decode_image(png()),
        Options("dress", steps=20, seed=123, preserve=False, allow_public_upload=True),
    )
    assert result.size == (256, 384)
    assert result.getpixel((0, 0)) == (255, 0, 0)
    assert len(seen) == 4


def test_space_quota_error_is_actionable(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/upload"):
            return httpx.Response(200, json=["/tmp/a", "/tmp/b"])
        if request.method == "POST":
            return httpx.Response(200, json={"event_id": "abc123"})
        return httpx.Response(200, text='event: error\ndata: "private details"\n\n')

    provider = SpaceProvider()
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.Client(base_url=provider.base_url, transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError, match="quota"):
        provider.generate(
            decode_image(png()), decode_image(png()), Options("top", preserve=False, allow_public_upload=True)
        )
