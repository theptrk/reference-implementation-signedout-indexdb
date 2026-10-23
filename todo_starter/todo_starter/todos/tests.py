import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import IntegrityError
from django.test import Client

from .models import ImportReceipt
from .models import Todo

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(client, user):
    client.force_login(user)
    client.defaults["HTTP_X_ACCOUNT_ID"] = str(user.pk)
    return client


def item(**kwargs):
    return {"id": str(uuid4()), "title": "A small step", "completed": False, **kwargs}


def test_anonymous_has_no_cloud_access(client):
    assert client.get("/app/").status_code == 200
    for method, url in [
        ("get", "/app/api/todos/"),
        ("post", "/app/api/todos/"),
        ("post", "/app/api/todos/import/"),
    ]:
        assert (
            getattr(client, method)(
                url, {}, content_type="application/json"
            ).status_code
            == 401
        )
    assert not Todo.objects.exists()


def test_owner_scoped_crud(api, user):
    created = api.post(
        "/app/api/todos/", {"title": "Write docs"}, content_type="application/json"
    )
    assert created.status_code == 201
    pk = created.json()["id"]
    other = type(user).objects.create_user(email="other@example.com")
    private = Todo.objects.create(user=other, title="Private")
    assert len(api.get("/app/api/todos/").json()["todos"]) == 1
    assert (
        api.patch(
            f"/app/api/todos/{private.pk}/",
            {"completed": True},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert api.delete(f"/app/api/todos/{private.pk}/").status_code == 404
    assert api.patch(
        f"/app/api/todos/{pk}/", {"completed": True}, content_type="application/json"
    ).json()["completed"]
    assert api.delete(f"/app/api/todos/{pk}/").status_code == 200
    assert Todo.objects.filter(user=other).exists()


def test_import_retries_and_deleted_todos_do_not_resurrect(api, user):
    rows = [item(), item(completed=True)]
    for _ in range(2):
        result = api.post(
            "/app/api/todos/import/", {"todos": rows}, content_type="application/json"
        )
        assert result.status_code == 200
        assert result.json()["acknowledged"] == [row["id"] for row in rows]
    assert Todo.objects.filter(user=user).count() == 2
    assert Todo.objects.filter(completed=True).count() == 1
    Todo.objects.filter(user=user).delete()
    api.post("/app/api/todos/import/", {"todos": rows}, content_type="application/json")
    assert not Todo.objects.exists()
    assert ImportReceipt.objects.count() == 2


def test_import_validates_whole_batch_before_saving(api):
    response = api.post(
        "/app/api/todos/import/",
        {"todos": [item(), item(title="")]},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert not Todo.objects.exists()
    assert not ImportReceipt.objects.exists()


def test_import_rolls_back_on_database_failure(api):
    api.raise_request_exception = False
    with patch.object(
        Todo.objects, "create", side_effect=IntegrityError("Simulated database failure")
    ):
        assert (
            api.post(
                "/app/api/todos/import/",
                {"todos": [item()]},
                content_type="application/json",
            ).status_code
            == 500
        )
    assert not ImportReceipt.objects.exists()


@pytest.mark.parametrize(
    "data",
    [
        {"title": " "},
        {"title": "x" * 301},
        {"title": "ok", "completed": "yes"},
        [],
        None,
    ],
)
def test_invalid_payload(api, data):

    assert (
        api.post(
            "/app/api/todos/", json.dumps(data), content_type="application/json"
        ).status_code
        == 400
    )


def test_stale_account_tab_cannot_import(api):
    api.defaults["HTTP_X_ACCOUNT_ID"] = "a-different-account"
    assert (
        api.post(
            "/app/api/todos/import/",
            {"todos": [item()]},
            content_type="application/json",
        ).status_code
        == 409
    )
    assert not Todo.objects.exists()


def test_csrf_required(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert (
        client.post(
            "/app/api/todos/import/",
            {"todos": [item()]},
            content_type="application/json",
        ).status_code
        == 403
    )


def test_account_pages_render_without_google(client):
    for url in ["/", "/accounts/login/", "/accounts/signup/"]:
        assert client.get(url).status_code == 200
