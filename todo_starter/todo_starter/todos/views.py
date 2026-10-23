import json
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import ImportReceipt
from .models import Todo

MAX_IMPORT = 1000
MAX_TITLE = 300
MAX_BODY = 1_000_000


def payload(request):
    if len(request.body) > MAX_BODY:
        raise ValueError("Request too large.")
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def fields(data):
    title = data.get("title")
    completed = data.get("completed", False)
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title.strip()) > MAX_TITLE
    ):
        raise ValueError("Enter a title of 1-300 characters.")
    if not isinstance(completed, bool):
        raise ValueError("Completed must be a boolean.")
    return {"title": title.strip(), "completed": completed}


def serialize(todo):
    return {"id": str(todo.id), "title": todo.title, "completed": todo.completed}


@never_cache
@ensure_csrf_cookie
def app(request):
    return render(request, "todos/app.html")


@never_cache
def session_status(request):
    return JsonResponse(
        {"user": str(request.user.pk) if request.user.is_authenticated else None}
    )


@never_cache
@require_http_methods(["GET", "POST"])
def collection(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to use cloud todos."}, status=401)
    if request.headers.get("X-Account-ID") != str(request.user.pk):
        return JsonResponse(
            {"error": "Your account changed. Reload this page."}, status=409
        )
    if request.method == "GET":
        return JsonResponse(
            {
                "todos": [
                    serialize(todo) for todo in Todo.objects.filter(user=request.user)
                ]
            }
        )
    try:
        todo = Todo.objects.create(user=request.user, **fields(payload(request)))
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(serialize(todo), status=201)


@never_cache
@require_http_methods(["PATCH", "DELETE"])
def detail(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to use cloud todos."}, status=401)
    if request.headers.get("X-Account-ID") != str(request.user.pk):
        return JsonResponse(
            {"error": "Your account changed. Reload this page."}, status=409
        )
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    if request.method == "DELETE":
        todo.delete()
        return JsonResponse({"deleted": True})
    try:
        data = payload(request)
        values = fields(
            {
                "title": data.get("title", todo.title),
                "completed": data.get("completed", todo.completed),
            }
        )
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    for key, value in values.items():
        setattr(todo, key, value)
    todo.save(update_fields=list(values))
    return JsonResponse(serialize(todo))


@never_cache
@require_http_methods(["POST"])
def import_local(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in before importing."}, status=401)
    if request.headers.get("X-Account-ID") != str(request.user.pk):
        return JsonResponse(
            {"error": "Your account changed. Reload this page."}, status=409
        )
    try:
        rows = payload(request).get("todos")
        if not isinstance(rows, list) or len(rows) > MAX_IMPORT:
            raise ValueError("Import up to 1,000 todos at a time.")
        validated = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid todo.")
            validated.append((UUID(str(row.get("id"))), fields(row)))
        if len({key for key, _ in validated}) != len(validated):
            raise ValueError("Duplicate local IDs.")
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with transaction.atomic():
        # Serialize imports per account on PostgreSQL, including concurrent devices.
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        for local_id, values in validated:
            _, created = ImportReceipt.objects.get_or_create(
                user=request.user, local_id=local_id
            )
            if created:
                Todo.objects.create(user=request.user, **values)
    return JsonResponse({"acknowledged": [str(key) for key, _ in validated]})
