import importlib.util
import io
import json
import time
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import quote, urlparse
from uuid import UUID

import httpx
import numpy as np
from PIL import Image

from app.config import Settings
from app.images import decode_image, preserve_regions

Category = Literal["top", "bottom", "dress", "outerwear"]
CATEGORY_MAP = {"top": "tops", "bottom": "bottoms", "dress": "one-pieces", "outerwear": "tops"}


@dataclass(frozen=True)
class Options:
    category: Category
    steps: int = 30
    seed: int = 42
    garment_photo_type: str = "flat-lay"
    preserve: bool = True
    allow_public_upload: bool = False


class ProviderError(RuntimeError):
    """A provider failure with an intentionally safe, user-facing message."""


class Provider(Protocol):
    name: str

    def status(self) -> dict: ...
    def generate(self, person: Image.Image, garment: Image.Image, options: Options) -> Image.Image: ...


class FashnProvider:
    name = "FASHN VTON 1.5"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pipeline = None

    def status(self):
        installed = importlib.util.find_spec("fashn_vton") is not None
        required = ["model.safetensors", "dwpose/yolox_l.onnx", "dwpose/dw-ll_ucoco_384.onnx"]
        missing = [name for name in required if not (self.settings.weights_dir / name).is_file()]
        ready = installed and not missing
        return {
            "name": self.name,
            "ready": ready,
            "mode": "local",
            "message": "Model installed · loads on first generation"
            if ready
            else "Install the inference extra and download model weights. See Setup.",
            "missing_weights": missing,
        }

    def generate(self, person, garment, options):
        from fashn_human_parser import (
            BODY_COVERAGE_TO_LABELS,
            CATEGORY_TO_BODY_COVERAGE,
            IDENTITY_LABELS,
            LABELS_TO_IDS,
        )
        from fashn_vton import TryOnPipeline

        if self.pipeline is None:
            self.pipeline = TryOnPipeline(
                weights_dir=str(self.settings.weights_dir),
                device=None if self.settings.device == "auto" else self.settings.device,
            )
        category = CATEGORY_MAP[options.category]
        result = self.pipeline(
            person_image=person,
            garment_image=garment,
            category=category,
            garment_photo_type=options.garment_photo_type,
            num_timesteps=options.steps,
            seed=options.seed,
            num_samples=1,
            segmentation_free=True,
        ).images[0]
        result = result.convert("RGB").resize(person.size, Image.Resampling.LANCZOS)
        if options.preserve:
            # Run parsing at bounded resolution, then nearest-neighbor map labels to the source.
            source_small = person.copy()
            target_small = result.copy()
            source_small.thumbnail((864, 864))
            target_small.thumbnail((864, 864))
            source_labels = self.pipeline.hp_model.predict(np.array(source_small))
            target_labels = self.pipeline.hp_model.predict(np.array(target_small))
            editable = BODY_COVERAGE_TO_LABELS[CATEGORY_TO_BODY_COVERAGE[category]]
            editable_ids = [LABELS_TO_IDS[label] for label in editable]
            identity_ids = [LABELS_TO_IDS[label] for label in IDENTITY_LABELS]
            if not identity_ids:
                raise RuntimeError("Human parser label schema is incompatible with identity protection.")
            result = preserve_regions(
                person, result, source_labels, target_labels, editable_ids, identity_ids
            )
        return result


class RemoteProvider:
    """Connect to a GPU-hosted instance of this same API; no browser-side credentials."""

    name = "Remote GPU worker"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _client(self):
        return httpx.Client(
            base_url=self.settings.remote_url.rstrip("/") + "/",
            timeout=30,
            headers={"X-API-Key": self.settings.remote_api_key},
            follow_redirects=False,
        )

    def status(self):
        url = urlparse(self.settings.remote_url)
        ready = url.scheme in {"http", "https"} and bool(url.netloc)
        return {
            "name": self.name,
            "ready": ready,
            "mode": "remote",
            "message": "Remote worker configured; connection checked on generation"
            if ready
            else "Set VTON_REMOTE_URL to your GPU worker URL.",
        }

    def generate(self, person, garment, options):
        def png(image):
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            return buffer.getvalue()

        job_id = None
        with self._client() as client:
            health = client.get("api/health")
            health.raise_for_status()
            worker = health.json()["provider"]
            if worker["mode"] != "local" or not worker["ready"]:
                raise RuntimeError("The GPU worker must use a ready local model provider.")
            response = client.post(
                "api/try-on",
                files={
                    "model_image": ("model.png", png(person), "image/png"),
                    "garment_image": ("garment.png", png(garment), "image/png"),
                },
                data={
                    "category": options.category,
                    "steps": options.steps,
                    "seed": options.seed,
                    "garment_photo_type": options.garment_photo_type,
                    "preserve": str(options.preserve).lower(),
                },
            )
            response.raise_for_status()
            job_id = str(UUID(response.json()["id"]))
            try:
                deadline = time.monotonic() + 1800
                while time.monotonic() < deadline:
                    response = client.get(f"api/jobs/{job_id}")
                    response.raise_for_status()
                    job = response.json()
                    if job["status"] == "failed":
                        raise RuntimeError("Remote inference failed. Check GPU worker logs.")
                    if job["status"] == "completed":
                        with client.stream("GET", f"api/jobs/{job_id}/result") as download:
                            download.raise_for_status()
                            content = bytearray()
                            for chunk in download.iter_bytes():
                                content.extend(chunk)
                                if len(content) > 100 * 1024 * 1024:
                                    raise RuntimeError("Remote output exceeds the 100 MB limit.")
                        with Image.open(io.BytesIO(content)) as output:
                            output.load()
                            return output.convert("RGB")
                    time.sleep(2)
                raise TimeoutError("GPU worker timed out after 30 minutes.")
            finally:
                # Completed/failed remote jobs are removed after transfer. Busy jobs retain worker TTL.
                try:
                    client.delete(f"api/jobs/{job_id}")
                except httpx.HTTPError:
                    pass


class SpaceProvider:
    """Opt-in official public Gradio demo. No local model packages or secret credentials needed.

    The public demo exposes native model preservation, not our pixel-lock compositor.
    Remote copies follow the Space operator's retention policy and cannot be deleted here.
    """

    name = "FASHN · official online demo"
    base_url = "https://fashn-ai-fashn-vton-1-5.hf.space/"

    def status(self):
        return {
            "name": self.name,
            "ready": True,
            "mode": "public",
            "supports_preservation": False,
            "message": "Official Hugging Face demo. Images leave your device after explicit consent. "
            "Public quotas and availability apply; extra pixel-lock protection is unavailable.",
        }

    def _client(self):
        return httpx.Client(
            base_url=self.base_url, timeout=httpx.Timeout(90, connect=15), follow_redirects=False
        )

    def generate(self, person, garment, options):
        if not options.allow_public_upload:
            raise ProviderError("Please explicitly allow sending these images to the public demo.")
        if options.preserve:
            raise ProviderError(
                "The public demo supports model-guided preservation only. Set preserve=false."
            )
        try:
            with self._client() as client:
                uploads = []
                for name, image in (("model.png", person), ("garment.png", garment)):
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    uploads.append(("files", (name, buffer.getvalue(), "image/png")))
                response = client.post("gradio_api/upload", files=uploads)
                response.raise_for_status()
                paths = response.json()
                if len(paths) != 2 or not all(isinstance(path, str) for path in paths):
                    raise ProviderError("Public demo returned an incompatible upload response.")
                inputs = [{"path": path, "meta": {"_type": "gradio.FileData"}} for path in paths]
                response = client.post(
                    "gradio_api/call/try_on",
                    json={
                        "data": [
                            *inputs,
                            CATEGORY_MAP[options.category],
                            options.garment_photo_type,
                            options.steps,
                            1.5,
                            options.seed,
                            True,
                        ]
                    },
                )
                response.raise_for_status()
                event_id = response.json()["event_id"]
                if not isinstance(event_id, str) or not event_id.isalnum():
                    raise ProviderError("Public demo returned an invalid job identifier.")
                deadline = time.monotonic() + 600
                output_path = None
                event = ""
                with client.stream("GET", f"gradio_api/call/try_on/{event_id}") as stream:
                    stream.raise_for_status()
                    for line in stream.iter_lines():
                        if time.monotonic() > deadline:
                            raise ProviderError("The public demo timed out. Please try again later.")
                        if line.startswith("event: "):
                            event = line[7:]
                        elif line.startswith("data: "):
                            if event == "error":
                                raise ProviderError(
                                    "The public demo is unavailable or its GPU quota is exhausted. "
                                    "Try again later or use your own GPU worker."
                                )
                            if event == "complete":
                                output_path = json.loads(line[6:])[0]["path"]
                                break
                if not isinstance(output_path, str) or not output_path.startswith("/tmp/"):
                    raise ProviderError("Public demo did not return a valid image file.")
                # Construct a same-origin file URL. Never follow arbitrary URLs from a model response.
                with client.stream("GET", "gradio_api/file=" + quote(output_path, safe="/")) as download:
                    download.raise_for_status()
                    content = bytearray()
                    for chunk in download.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 15 * 1024 * 1024:
                            raise ProviderError("Public demo returned an unexpectedly large result.")
                return decode_image(bytes(content)).resize(person.size, Image.Resampling.LANCZOS)
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not reach the official public demo. Check your connection or try again later."
            ) from exc


def build_provider(settings):
    if settings.provider == "space":
        return SpaceProvider()
    return RemoteProvider(settings) if settings.provider == "remote" else FashnProvider(settings)
