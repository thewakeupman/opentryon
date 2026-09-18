import asyncio
import re
import secrets
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.images import MAX_BYTES, decode_image
from app.jobs import JobStore
from app.providers import Category, Options, build_provider


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        # Bound the entire multipart request, including chunked requests, before parsing/spooling.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 2 * MAX_BYTES + 65536:
                return await JSONResponse({"detail": "Upload too large. Maximum 15 MB per image."}, 413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def buffered():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, buffered, send)


def create_app(settings=None, provider=None):
    settings = settings or Settings()
    provider = provider or build_provider(settings)

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = JobStore(settings, provider)

        async def clean():
            while True:
                await asyncio.sleep(600)
                await asyncio.to_thread(app.state.store.cleanup)

        task = asyncio.create_task(clean())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.to_thread(app.state.store.close)

    app = FastAPI(title=f"{settings.app_name} · Virtual Try-On API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware)

    def authorize(x_api_key: Annotated[str | None, Header()] = None):
        if settings.api_key and not secrets.compare_digest(
            (x_api_key or "").encode(), settings.api_key.encode()
        ):
            raise HTTPException(401, "A valid X-API-Key header is required.")

    api = APIRouter(prefix="/api", dependencies=[Depends(authorize)])

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @api.get("/health")
    def health():
        return {
            "status": "ok",
            "app": {
                "name": settings.app_name,
                "tagline": settings.app_tagline,
                "repository_url": settings.repository_url,
            },
            "provider": provider.status(),
            "retention_hours": settings.retention_hours,
            "categories": ["top", "bottom", "dress", "outerwear"],
        }

    @api.post("/try-on", status_code=202)
    def create_job(
        model_image: Annotated[UploadFile, File()],
        garment_image: Annotated[UploadFile, File()],
        category: Annotated[Category, Form()],
        steps: Annotated[int, Form(ge=10, le=50)] = 30,
        seed: Annotated[int, Form(ge=0, le=4294967295)] = 42,
        garment_photo_type: Annotated[Literal["flat-lay", "model"], Form()] = "flat-lay",
        preserve: Annotated[bool, Form()] = True,
        allow_public_upload: Annotated[bool, Form()] = False,
    ):
        try:
            person = decode_image(model_image.file.read(MAX_BYTES + 1))
            garment = decode_image(garment_image.file.read(MAX_BYTES + 1))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            model_image.file.close()
            garment_image.file.close()
        if not provider.status()["ready"]:
            raise HTTPException(503, provider.status()["message"])
        if provider.status()["mode"] == "public":
            if not allow_public_upload:
                raise HTTPException(422, "Explicit consent is required: set allow_public_upload=true.")
            if preserve:
                raise HTTPException(
                    422, "The public demo has no extra pixel-lock protection. Set preserve=false."
                )
        try:
            return app.state.store.submit(
                person,
                garment,
                Options(category, steps, seed, garment_photo_type, preserve, allow_public_upload),
            )
        except OverflowError as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": "10"}) from exc

    @api.get("/jobs/{job_id}")
    def get_job(job_id: UUID):
        job = app.state.store.get(str(job_id))
        if not job:
            raise HTTPException(404, "Session not found or expired.")
        return job

    @api.get("/jobs/{job_id}/{kind}")
    def get_image(job_id: UUID, kind: Literal["model", "garment", "result"]):
        job = get_job(job_id)
        if kind == "result" and job["status"] != "completed":
            raise HTTPException(409, "The result is not ready yet.")
        path = app.state.store.root / str(job_id) / f"{kind}.png"
        if not path.is_file():
            raise HTTPException(404, "Image no longer available.")
        download_prefix = re.sub(r"[^a-z0-9]+", "-", settings.app_name.lower()).strip("-") or "try-on"
        return FileResponse(
            path,
            media_type="image/png",
            filename=f"{download_prefix}-{kind}-{job_id}.png",
            headers={"Cache-Control": "no-store"},
        )

    @api.delete("/jobs/{job_id}", status_code=204)
    def delete_job(job_id: UUID):
        try:
            if not app.state.store.delete(str(job_id)):
                raise HTTPException(404, "Session not found or expired.")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    app.include_router(api)
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="studio")
    return app


app = create_app()
