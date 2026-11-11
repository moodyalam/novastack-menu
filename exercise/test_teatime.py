"""Two promises about the tea-time special (Lecture 6, ORD-384).

Run them from the top folder of the repository with:
    python -m pytest exercise
"""

# pytest puts this folder first on the path, so "app" is exercise/app.py.
from app import app


def test_special_page_loads():
    assert app.test_client().get("/").status_code == 200


def test_special_names_the_price():
    assert b"3.50 pounds" in app.test_client().get("/").data
