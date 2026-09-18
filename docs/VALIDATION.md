# V1 validation record

Date: 2026-09-17. Development host: Windows, Python 3.12, RTX 3050 (4 GB), 16 GB system RAM.

## Verified

- 28 automated tests: four categories; valid and corrupt uploads; EXIF normalization; size and pixel limits; auth; bounded queue; pending-result and active-delete rejection; failure redaction; restart recovery; retention; protected compositing; remote-worker transfer; public-demo SSE parsing, same-origin download, quota errors and mandatory upload consent.
- Browser flow: access key, invalid file, sample inputs, category change, submit, polling, result view, compare slider, PNG download, session reopen, reset, deletion, 390px mobile layout. Test generation uses an explicit test-only image provider, not AI.
- Public-mode browser check: consent starts unchecked, generating is disabled before consent, changing an image clears consent, unsupported extra preservation is disabled, real completed session opens by URL and compares correctly.
- Real inference through **OpenTryOn's own API and SpaceProvider**: official FASHN Hugging Face Space, bundled public upstream person + garment images, category `top`, garment photo type `model`, 20 steps, seed 42, `preserve=false`, `allow_public_upload=true`.
- Actual result returned in **30.0 seconds**, saved as PNG at **832×1248** (original input dimensions). Manual inspection confirmed the white T-shirt was replaced by the target black graphic T-shirt while the seated pose, hat and scene remained broadly consistent. Fine identity details and background pixels are not exact in this public-mode result; it uses native model conditioning without OpenTryOn's extra compositor.
- Real output: `test-results/public-demo-result.png`; run metadata: `test-results/public-demo-job.json`; studio comparison screenshot: `test-results/real-tryon-studio.png`. These local artifacts are ignored by Git.
- Python wheel builds and includes static assets, original license and third-party notices. `pip check` and Ruff checks pass. Compose YAML parses correctly.

## Not yet verified

- Local FASHN model execution, GPU-memory minimum and visual quality of the local parser-based compositor. Its array compositing behavior is unit-tested, but real segmentation outputs still need GPU validation.
- Real generation for bottom, dress and outerwear. Category mapping and API contracts are tested; only a top was visually evaluated.
- Docker image build/start and GPU container operation: Docker is not installed on the development host. CI includes a lightweight image build; it has not been run on GitHub from this local repository.
- Sustained concurrent/multi-user load. This V1 explicitly uses one process, a bounded serial queue and one shared access key.

## Reproduce

```bash
pytest -q
ruff check app tests scripts
python scripts/browser_check.py
python scripts/browser_check.py --public
```

For real public-model verification, run the server with `VTON_PROVIDER=space`, then explicitly run `python scripts/smoke_public_demo.py`. This consumes public GPU quota and sends the bundled public samples to the service. Local removal cannot delete remote copies. Public service uptime/quotas are outside this toolkit's control.
