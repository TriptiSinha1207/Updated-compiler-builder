#!/usr/bin/env python3
"""Export the Flask templates and static assets into a static `dist/` folder.

This script reads `app_config.json` and renders `templates/index.html` and
`templates/page.html` into static HTML files. It copies the `static/` folder
and injects a `window.API_BASE` variable when the `BACKEND_URL` environment
variable is set (useful for Netlify builds).
"""
import json
import os
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
CONFIG = ROOT / "app_config.json"


class ModelWrapper:
    def __init__(self, data):
        self._data = data

    def model_dump(self, mode=None):
        return self._data


def url_for(name, filename=None):
    # Simple replacement for Flask's url_for used in templates
    if name == "static" and filename:
        return f"/static/{filename}"
    return "/"


def render():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    # copy static files
    shutil.copytree(STATIC, DIST / "static")

    # load config
    if not CONFIG.exists():
        raise SystemExit("app_config.json not found. Generate a config first.")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.globals["url_for"] = url_for

    backend = os.environ.get("BACKEND_URL", "")

    # render index
    index_t = env.get_template("index.html")
    pages = []
    for p in cfg.get("pages", []):
        pages.append({"name": p.get("name"), "path": p.get("path")})

    index_html = index_t.render(app_name=cfg.get("metadata", {}).get("app_name", "Generated App"), description=cfg.get("metadata", {}).get("description", ""), pages=pages)
    # inject API_BASE if provided
    if backend:
        index_html = index_html.replace("</head>", f"  <script>window.API_BASE = '{backend}';</script>\n</head>")
    (DIST / "index.html").write_text(index_html, encoding="utf-8")

    # render pages
    page_t = env.get_template("page.html")
    for p in cfg.get("pages", []):
        page_obj = ModelWrapper(p)
        # wrap components to provide model_dump
        comps = []
        for c in p.get("components", []):
            comps.append(ModelWrapper(c))
        page_obj._data["components"] = comps
        html = page_t.render(page=page_obj)
        if backend:
            html = html.replace("</head>", f"  <script>window.API_BASE = '{backend}';</script>\n</head>")
        # write to path (use path-based filename)
        path = p.get("path", "/").lstrip("/")
        if path == "":
            out = DIST / "app.html"
        else:
            out_dir = DIST / path
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / "index.html"
        out.write_text(html, encoding="utf-8")

    print("Exported static site to:", DIST)


if __name__ == "__main__":
    render()
