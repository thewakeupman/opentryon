# OpenTryOn — AI Virtual Try-On Toolkit

[中文快速开始](README.zh-CN.md)

**A new look. Still you.** An open-source, self-hosted fitting room with a modular model backend.

Upload a person and a garment, choose a category, generate a try-on, compare it with the original and download a full-size PNG. Includes a responsive web studio, asynchronous REST API, persistent jobs, a local FASHN VTON 1.5 adapter, a remote GPU-worker adapter, an opt-in official online-demo adapter and Docker deployment.

> **Current validation:** UI, API, queue, storage, upload validation and compositing are covered by automated tests. A real upper-body sample generation has also returned successfully through FASHN's official hosted model. Local GPU inference and the local adapter's image quality have **not** been validated on the development machine (RTX 3050, 4 GB VRAM). Docker files require verification on a Docker/NVIDIA host. There is no fake production inference backend. Use local weights, your own GPU worker, or the opt-in public demo.

## Quick start: launch the studio

Python 3.11 or 3.12 recommended. No Node build or hosted API subscription required.

```bash
git clone <your-published-repository-url>
cd <your-repository-directory>
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell activation/configuration:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000**. Interactive API documentation: **http://localhost:8000/docs**. The toolkit has not been published to GitHub automatically; replace the clone placeholder after publishing, or start from this local checkout.

## Make it your own

Branding is configured without editing application code. Set these values in `.env`:

```dotenv
VTON_APP_NAME=YourBrand
VTON_APP_TAGLINE=Your virtual fitting room
VTON_REPOSITORY_URL=https://github.com/your-name/your-repository
```

The web title, logo initial, footer, About dialog, API title, source link and downloaded filenames update automatically. Keep [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the upstream notices when redistributing the project. The validation fixtures, web sample media and inference dependencies retain their documented licenses; confirm redistribution and likeness rights for replacement media before publishing.

To publish a new GitHub repository after choosing an owner and repository name:

```bash
git add .
git commit -m "Initial open-source release"
gh repo create your-repository --public --source=. --remote=origin --push
```

Do not commit `.env`, generated images, weights, caches or local logs; they are covered by `.gitignore`. Review [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the issue templates before accepting public contributions.

The studio opens immediately without GPU packages. With the default `fashn` provider, it displays **Setup required** until a model is configured. Both uploads, sample inputs and settings work in this state; generation is disabled. The collage contains explicitly labeled sample inputs, not an AI-generated result.

## No GPU: opt-in official online demo

Set this in `.env` and restart:

```dotenv
VTON_PROVIDER=space
```

This adapter uses the [official FASHN Hugging Face Space](https://huggingface.co/spaces/fashn-ai/fashn-vton-1.5), which currently exposes a public Gradio API. No local weights or extra Python dependencies are needed. Load the sample images, explicitly agree to the public upload, then generate.

**Images are sent to a third party.** The browser requires an unchecked-by-default consent checkbox. API callers must set `allow_public_upload=true` and `preserve=false`; missing consent is rejected before any upload. The Space follows its operator's retention policy; deleting a local session does not delete copies on the Space. Do not use this mode for private photos unless this handling is acceptable.

The online demo provides the model's native pose/identity conditioning but **does not expose OpenTryOn's extra pixel-lock compositor**. The preservation switch is disabled and the UI identifies model-guided preservation. Public GPU quotas, queueing, service availability and upstream API changes apply. This is an evaluation path, not an SLA-backed production service. Polling is limited to ten minutes; stalled connections time out sooner. Use your own local or remote GPU worker for controlled deployment and extra compositing.

Explicit real-inference test using only bundled public upstream samples:

```bash
python scripts/smoke_public_demo.py
```

The script submits through this toolkit's API and saves the actual returned image and job metadata to `test-results/`. It is excluded from automated CI to avoid consuming public GPU quota.

## Enable real local inference

The first provider uses [FASHN VTON 1.5](https://github.com/fashn-AI/fashn-vton-1.5). Install a CUDA-compatible PyTorch build for your host before the inference extra. One known package pairing used in the Docker recipe is:

```bash
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[inference]"
python scripts/download_weights.py --weights-dir ./weights
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Required files:

```text
weights/
├── model.safetensors
└── dwpose/
    ├── yolox_l.onnx
    └── dw-ll_ucoco_384.onnx
```

The script also initializes the human parser to download its weights to the Hugging Face cache. Weights are downloaded from upstream, not bundled. Allow several GB of disk space. Initial downloads require internet; preserve the cache for offline operation. The VTON source is pinned; weight revisions can be selected with `--revision`. DWPose/parser use their upstream defaults.

Use a modern NVIDIA GPU with substantial memory; **8–16 GB is a planning estimate, not a verified minimum for this adapter**. Four GB is not a supported/validated target. Larger inputs also increase postprocessing memory. The native model generates at 576×864, removing aspect padding afterward; OpenTryOn resizes this output to source dimensions and restores protected source regions. It does not invent native high-resolution texture or promise pixel-perfect garment detail.

CPU mode is possible but slow:

```bash
pip uninstall -y onnxruntime-gpu
pip install onnxruntime
```

Set `VTON_DEVICE=cpu` in `.env`. A successful health check confirms packages and weight files exist, **not** that GPU memory or model execution has been validated. First inference loads the pipeline. Failed inference is reported as a failed job with a log reference.

## Remote GPU deployment

Run a local-model instance of OpenTryOn on your GPU host with `VTON_API_KEY` set. Put it behind HTTPS/authenticated access. On your laptop, configure:

```dotenv
VTON_PROVIDER=remote
VTON_REMOTE_URL=https://your-gpu-server.example
VTON_REMOTE_API_KEY=your-worker-secret
```

Restart the laptop server. The remote provider speaks **this toolkit's API**, not the commercial FASHN API. It submits multipart images, polls job state, downloads the resulting PNG and deletes completed remote sessions. Remote-to-remote chains are rejected. Network calls have 30-second timeouts; polling stops after 30 minutes. A running remote job may continue after a timeout and will be cleaned by the worker's retention policy. Secrets stay server-side; the workspace's optional browser access key is separate.

## Docker

The lightweight image serves the web app and can connect to a remote GPU worker:

```bash
docker compose up --build -d
```

With no remote configured it displays the setup screen. It does **not** contain the local model runtime.

For local GPU inference, install NVIDIA Container Toolkit on a Linux Docker host, or use a compatible Docker Desktop/WSL2 NVIDIA setup. Docker Compose must support `gpus: all`. Download weights first using the local setup instructions, then:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```

Alternatively download weights using the GPU image without a host Python environment (Linux/macOS shell):

```bash
docker build --target gpu -t opentryon:gpu .
mkdir -p weights
docker run --rm --user "$(id -u):$(id -g)" \
  -e HF_HOME=/tmp/hf-cache -v "$PWD/weights:/weights" \
  opentryon:gpu python scripts/download_weights.py --weights-dir /weights
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

In that alternative, parser cache in `/tmp` is temporary and will be downloaded once again into the persistent Compose cache on the first run. The source weights directory is mounted read-only for inference. Named volumes preserve jobs and parser cache. Containers run as non-root. The default published port is bound to `127.0.0.1`; expose it only through your chosen access layer. `/healthz` is liveness only.

## API

Submit a job (`202 Accepted`):

```bash
curl -X POST http://localhost:8000/api/try-on \
  -H "X-API-Key: YOUR_KEY_IF_CONFIGURED" \
  -F model_image=@person.jpg \
  -F garment_image=@garment.png \
  -F category=top \
  -F garment_photo_type=flat-lay \
  -F steps=30 -F seed=42 -F preserve=true
```

Windows: use `curl.exe` and replace backslash continuations with PowerShell backticks, or put the command on one line.

```json
{"id":"<uuid>","status":"queued","result_url":null,"options":{"category":"top","steps":30,"seed":42,"garment_photo_type":"flat-lay","preserve":true}}
```

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Public process liveness |
| `GET /api/health` | Provider configuration, categories, retention |
| `POST /api/try-on` | Submit multipart images and generation options |
| `GET /api/jobs/{id}` | Poll `queued → running → completed / failed` |
| `GET /api/jobs/{id}/result` | Download result PNG; 409 until completed |
| `GET /api/jobs/{id}/model` | Normalized original PNG for comparison |
| `GET /api/jobs/{id}/garment` | Normalized garment PNG |
| `DELETE /api/jobs/{id}` | Delete a finished session and its images |

Poll until `completed`, then download `result_url` with the same API key. Typical errors: `401` invalid/missing configured key; `422` invalid file/options; `429` queue full; `503` model not configured. Inference failures are represented by `status: failed` in a successfully submitted job.

Options:

| Field | Values / default |
| --- | --- |
| `category` | Required: `top`, `bottom`, `dress`, `outerwear` |
| `garment_photo_type` | `flat-lay` (default), `model` |
| `steps` | 10–50, default 30 |
| `seed` | 0–4294967295, default 42 |
| `preserve` | true by default |
| `allow_public_upload` | false by default; must be true for `space`, which also requires `preserve=false` |

Top and outerwear map to upstream `tops`; bottom to `bottoms`; dress to `one-pieces`. Outerwear is **upper-body replacement**, not a separately trained layering model.

## Preservation and image quality

FASHN uses pose conditioning and maskless generation. OpenTryOn optionally parses both original and generated images, builds an editable envelope from the union of the selected clothing regions, feathers its boundaries and composites it onto the original. Original pixels classified as face, hair and identity accessories are locked. Background beyond the editable envelope is copied exactly, and downloads retain original pixel dimensions.

This is a best-effort protection mechanism, not an identity or pose guarantee. Incorrect segmentation, crossed arms, loose or long garments, extreme poses and face occlusions can produce artifacts or incomplete clothing replacement. Tight protection may prevent necessary shape changes; turn it off to compare the raw model result. Body shape and pose inside edited regions remain model-dependent. The toolkit does not evaluate real garment fit, sizes or physics. Review outputs before use.

## Architecture and adding models

```text
Browser studio → FastAPI → SQLite + bounded single-worker queue → Provider
                                                               ├─ FashnProvider → GPU / CPU
                                                               ├─ RemoteProvider → GPU-hosted OpenTryOn
                                                               └─ SpaceProvider → official public demo (opt-in)
```

- `app/static/`: dependency-free web UI, file uploads, polling, compare slider, download and browser-local session index.
- `app/main.py`: request validation, API key check, bounded body intake, REST endpoints and lifecycle.
- `app/jobs.py`: SQLite metadata, normalized PNG storage, failure recovery and retention.
- `app/providers.py`: typed `Options` and `Provider` protocol, lazy-loaded local inference, private remote worker and public-demo adapters.
- `app/images.py`: input decoding, EXIF normalization, transparency handling and protected compositing.

Implement `name`, `status() -> dict` and `generate(person: PIL.Image, garment: PIL.Image, options: Options) -> PIL.Image` in a provider. `status` must include `ready`, `name`, `mode`, `message`; return RGB at the original dimensions. Add its selector to `Settings.provider` and `build_provider`. A local provider should report `mode: local`; the remote worker checks that to prevent forwarding loops. Keep heavy libraries lazy-imported. Validate with a contract test and a real inference smoke test. No frontend changes are needed for the four existing categories.

## Storage, operation and limits

- Intended as a private, single-owner V1 workspace. A single optional API key protects **all** API images/jobs, not individual user ownership. Set it before network deployment. Enter it via the `T` button in the studio. This is not a multi-tenant authentication system.
- Use exactly **one server process / one Uvicorn worker** per data directory. The thread queue serializes GPU access. Horizontal scaling needs a shared job broker and object storage, not multiple processes using this SQLite directory.
- Up to 8 pending jobs by default. Queue rejection happens before disk persistence. Uploads accept JPEG/PNG/WebP, 15 MB each, minimum 128×128, maximum 24 MP. The entire multipart body is bounded at roughly 30 MB even with chunked encoding. Proxy-level connection/rate limits are recommended for internet-facing hosts.
- Image bytes are re-encoded; source EXIF metadata is not retained. No uploads are sent to an external model in local mode. Remote mode sends images to your configured worker. Public-demo mode sends images to FASHN's Hugging Face Space only after explicit consent; local retention cannot remove remote copies. The UI uses system fonts and does not load external font services.
- Files live in `data/<random-uuid>/`; results and metadata persist through restart. Interrupted queued/running jobs become failed after restart; they are not resumed automatically.
- Finished sessions expire after 24 hours by default, checked every 10 minutes and at startup/submission. Active jobs are not deleted. Use Delete in Recent sessions for earlier removal. Browser history holds at most 30 job IDs, not image bytes. IDs are not shown through a global listing API.
- Native inference has no hard timeout; a stuck local model can block the queue. Restarting the single worker recovers it as failed. The remote adapter has its own timeout. There is no cancel-running-job API in V1.

Environment configuration (prefix `VTON_`, read from `.env`):

| Variable | Default |
| --- | --- |
| `PROVIDER` | `fashn` (`remote` / `space` also available) |
| `WEIGHTS_DIR` | `./weights` |
| `DATA_DIR` | `./data` |
| `DEVICE` | `auto` (`cuda` / `cpu`) |
| `API_KEY` | empty; localhost development only |
| `REMOTE_URL` / `REMOTE_API_KEY` | empty |
| `RETENTION_HOURS` | 24 (1–720) |
| `MAX_PENDING` | 8 (1–100) |

## Development and verification

```bash
pip install -e ".[dev]"
pytest -q
ruff check app tests scripts
python -m playwright install chromium
python scripts/browser_check.py
python scripts/browser_check.py --public
```

Browser verification starts an isolated server with a test-only deterministic image provider. It checks the entire upload → generation → comparison → download → history → delete flow, invalid uploads, API access and mobile layout. The `--public` variant also tests upload consent without contacting a public service. It is **not** a model-quality test. Screenshots are written to ignored `test-results/`. No test provider can be selected through production configuration. See [the validation record](docs/VALIDATION.md) for real-inference evidence and remaining verification limits.

For actual model acceptance, run sample inputs and representative user photos through the configured GPU backend for all four categories. Review face, hair, pose, anatomy, background edges, garment texture and transitions around hands; compare protection on/off. Record hardware, seed, steps and upstream weight revision. This remains required before claiming production try-on quality.

## Research and licensing

Compared on 2026-09-17:

| Project | Why considered | Decision |
| --- | --- | --- |
| [FASHN VTON 1.5](https://github.com/fashn-AI/fashn-vton-1.5) | Compact Python pipeline, maskless pose-conditioned model, three category families | First adapter; main code/model declare Apache-2.0, but the parser has separate terms |
| [CatVTON](https://github.com/Zheng-Chong/CatVTON) | Simple diffusion pipeline; upstream advertises roughly 8 GB for 1024×768 | Candidate future provider; code and checkpoints CC BY-NC-SA 4.0 |
| [IDM-VTON](https://github.com/yisol/IDM-VTON) | Established garment-detail baseline, DensePose/SCHP preprocessing | Candidate future provider; code and checkpoints CC BY-NC-SA 4.0 |

Original toolkit code is [MIT](LICENSE). Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): the default human parser inherits the [NVIDIA SegFormer license](https://github.com/NVlabs/SegFormer/blob/master/LICENSE), which has non-commercial restrictions. **Do not treat the entire default inference stack as commercially unrestricted.** No CatVTON/IDM source is copied or bundled. Validation fixtures and sample media retain their documented rights. Use and redistribute only images you have permission to process and publish.

Contributions are welcome: adapters, GPU validation reports, better mask refinement, accessibility fixes and tests. Keep new model dependencies optional, disclose their license and include setup instructions and a real-inference validation record when available.
