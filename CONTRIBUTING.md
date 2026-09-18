# Contributing to OpenTryOn

Thank you for improving the toolkit. Bug reports, documentation fixes and model-provider adapters are welcome.

## Development setup

```bash
python -m venv .venv
pip install -e ".[dev]"
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows, use `Copy-Item .env.example .env` and `\.venv\Scripts\python`.

Before opening a pull request, run:

```bash
ruff check app tests scripts
pytest -q
python scripts/browser_check.py
python scripts/browser_check.py --public
```

Do not include model weights, generated user images, `.env` files or credentials. New inference providers must implement the provider interface in `app/providers.py`, report capabilities through `status()`, and document their license and data handling in `THIRD_PARTY_NOTICES.md` and the README.

By contributing, you agree that your contribution is licensed under this repository's MIT license. Third-party code and assets must retain their original notices.
