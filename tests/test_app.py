import os
import tempfile

os.environ["APP_DB"] = tempfile.mktemp(suffix=".db")
os.environ["ADMIN_PASSWORD"] = "pw"
from fastapi.testclient import TestClient  # noqa: E402
from app import app  # noqa: E402

c = TestClient(app)


def test_requires_login():
    assert c.get("/", follow_redirects=False).headers["location"] == "/login"
    assert c.post("/login", data={"password": "nope"}, follow_redirects=False).headers["location"] == "/login?error=1"


def test_crud_and_export():
    c.post("/login", data={"password": "pw"})
    c.post("/items", data={"sku": "A-1", "name": "Coffee beans 1kg", "qty": 3, "reorder_at": 5})
    c.post("/items", data={"sku": "B-2", "name": "Paper cups", "qty": 400, "reorder_at": 100})
    assert "SKU+already+exists" in c.post("/items", data={"sku": "A-1", "name": "x", "qty": 1},
                                          follow_redirects=False).headers["location"]
    page = c.get("/?low=1").text
    assert "Coffee beans" in page and "Paper cups" not in page
    c.post("/items", data={"item_id": 1, "sku": "A-1", "name": "Coffee beans 1kg", "qty": 20, "reorder_at": 5})
    assert "Low stock only (0)" in c.get("/").text
    c.post("/items/2/delete")
    csv = c.get("/export.csv").text
    assert "A-1,Coffee beans 1kg,20,5" in csv and "B-2" not in csv
