"""Dan's promises about the menu. Run them with:  uv run pytest"""

import pytest

from app import MENU, app


@pytest.fixture
def client():
    # Flask's built-in test client: asks the app for pages without a server.
    return app.test_client()


def test_home_page_loads(client):
    assert client.get("/").status_code == 200


def test_health_says_ok(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_menu_is_json_for_scripts(client):
    assert len(client.get("/menu").get_json()) == len(MENU)


def test_every_item_has_the_five_fields():
    fields = {"sku", "name", "category", "price", "icon"}
    for item in MENU:
        assert set(item) == fields, item


def test_skus_are_unique():
    skus = [item["sku"] for item in MENU]
    assert len(skus) == len(set(skus))
