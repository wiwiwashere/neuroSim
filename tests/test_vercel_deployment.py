import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vercel_builds_frontend_and_routes_api() -> None:
    config = json.loads((ROOT / "frontend" / "vercel.json").read_text())

    assert config["framework"] == "nextjs"
    assert config["buildCommand"] == "npm run build"
    assert config["installCommand"] == "npm install"
    assert config["outputDirectory"] == ".next"
    assert config["rewrites"] == [{"source": "/api/:path*", "destination": "/api/index"}]


def test_vercel_python_entrypoint_reuses_fastapi_app() -> None:
    source = (ROOT / "frontend" / "api" / "index.py").read_text()

    assert 'ROOT / "backend"' in source
    assert "from neurosim.api.main import app" in source
    requirements = (ROOT / "frontend" / "requirements.txt").read_text().splitlines()
    assert "fastapi" in requirements
    assert "google-genai" in requirements
    assert "pyarrow" in requirements


def test_next_config_keeps_local_proxy_out_of_vercel() -> None:
    source = (ROOT / "frontend" / "next.config.ts").read_text()

    assert 'process.env.VERCEL === "1"' in source
    assert "return []" in source
