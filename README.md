# MDH a.k.a MyDispatchHub.com

An AI powered SaaS Application for Dispatch management.

- Python 3.12+
  
## For ground zero pre-requisite instructions [click here](https://github.com/nikhilakki/mdh/blob/df7d717f091e697ce304501d40ef1a60d3daab75/How-to-Setup.md#L1)

### Setup

```bash
git clone git@github.com:nikhilakki/mdh.git && cd mdh
pip install -U uv
cd web && uv sync --frozen
cd ../ && uv run pre-commit install
# Set Python interpreter from .venv folder (VSCode)
```

### Local Development

```bash
make dev-build dev-up
make dev-migrate dev-createsuperuser # first time setup
make dev-logs-web
```

> Author - [Nikhil Akki](https://nikhilakki.in/about)

### Made in 🇮🇳 & 🇨🇦 for a better 🌎
