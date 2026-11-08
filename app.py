"""NovaStack menu service: a tiny web page and a JSON menu."""

import json
import os
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)

TITLE = os.environ.get("MENU_TITLE", "NovaStack menu")
MENU = json.loads(Path(__file__).with_name("menu.json").read_text(encoding="utf-8"))


@app.get("/")
def home():
    return f"{TITLE} is open\n"


@app.get("/menu")
def menu():
    return jsonify(MENU)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    # 0.0.0.0 means "listen on every network door", not just the box's own.
    app.run(host="0.0.0.0", port=8000)
