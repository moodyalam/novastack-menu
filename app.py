"""NovaStack menu service: a small web page and a JSON menu."""

import json
import os
import platform
from pathlib import Path

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

TITLE = os.environ.get("MENU_TITLE", "NovaStack menu")
MENU = json.loads(Path(__file__).with_name("menu.json").read_text(encoding="utf-8"))
ICONS = {"main": "🌯", "side": "🍟", "snack": "🥨", "dessert": "🍰", "drink": "☕"}

# The page. {{ ... }} fills in a value; {% for %} repeats a card per item.
PAGE = """<!doctype html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #f1f5f9; }
    header { padding: 2rem 1rem; text-align: center; background: linear-gradient(135deg, #6d28d9, #be185d); }
    h1 { margin: 0 0 0.5rem; font-size: 2.2rem; }
    .box { display: inline-block; padding: 0.3rem 0.8rem; border-radius: 1rem; background: #0f172a; }
    main { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
           gap: 1rem; max-width: 60rem; margin: 1.5rem auto; padding: 0 1rem; }
    .card { background: #1e293b; border-radius: 1rem; padding: 1rem; transition: transform 0.2s; }
    .card:hover { transform: translateY(-4px) rotate(-1deg); }
    .icon { font-size: 2rem; }
    .card h2 { font-size: 1.1rem; margin: 0.4rem 0; }
    .price { color: #fbbf24; font-weight: bold; }
  </style>
</head>
<body>
  <header>
    <h1>{{ title }} is open</h1>
    <p class="box">📦 Running on {{ system }} · machine {{ machine }}</p>
  </header>
  <main>
    {% for item in menu %}
    <div class="card">
      <div class="icon">{{ icons.get(item.category, "🍽️") }}</div>
      <h2>{{ item.name }}</h2>
      <div class="price">£{{ item.price }}</div>
    </div>
    {% endfor %}
  </main>
</body>
</html>
"""


@app.get("/")
def home():
    return render_template_string(
        PAGE,
        title=TITLE,
        menu=MENU,
        icons=ICONS,
        system=platform.system(),  # Darwin (macOS), Windows or Linux
        machine=platform.node(),  # your laptop's name, or the container's ID
    )


@app.get("/menu")
def menu():
    return jsonify(MENU)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    # 0.0.0.0 means "listen on every network door", not just the box's own.
    app.run(host="0.0.0.0", port=8000)
