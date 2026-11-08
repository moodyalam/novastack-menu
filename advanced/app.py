"""NovaStack orders counter: the menu service with a database behind it."""

import os

import psycopg
from flask import Flask, jsonify

app = Flask(__name__)


def database_url() -> str:
    # Settings come from the environment, never from the code.
    return os.environ["DATABASE_URL"]


@app.get("/")
def home():
    return "NovaStack orders service\n"


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/orders/count")
def orders_count():
    with psycopg.connect(database_url()) as conn:
        (count,) = conn.execute("SELECT count(*) FROM orders").fetchone()
    return jsonify(count=count)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
