"""NovaStack menu service: a small web page and a JSON menu."""

import json
import os
import platform
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

TITLE = os.environ.get("MENU_TITLE", "NovaStack menu")
# Docker creates /.dockerenv inside every container, so its presence means "in a box".
IN_DOCKER = Path("/.dockerenv").exists()
# A container can't see which image it came from. Pass it in to show it on the page:
#   docker run -e IMAGE_NAME=<image> ...   (optional)
IMAGE_NAME = os.environ.get("IMAGE_NAME", "")
MENU = json.loads(Path(__file__).with_name("menu.json").read_text(encoding="utf-8"))


def menu_page():
    # Fill in templates/index.html with the title, the menu and where it's running.
    return render_template(
        "index.html",
        title=TITLE,
        menu=MENU,
        system=platform.system(),  # Darwin (macOS), Windows or Linux
        machine=platform.node(),  # your laptop's name, or the container's ID
        in_docker=IN_DOCKER,
        image=IMAGE_NAME,
    )


@app.get("/")
def home():
    return menu_page()


@app.get("/menu")
def menu():
    # A browser asks for HTML, so it gets the page; curl and scripts get JSON.
    wants_page = "text/html" in request.headers.get("Accept", "")
    if wants_page and request.args.get("format") != "json":
        return menu_page()
    return jsonify(MENU)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    # A clickable link in the terminal or in `docker logs` (Ctrl/Cmd+click).
    print("Menu is ready: http://localhost:8000", flush=True)
    # 0.0.0.0 means "listen on every network door", not just the box's own.
    app.run(host="0.0.0.0", port=8000)
