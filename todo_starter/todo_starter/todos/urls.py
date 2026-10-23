from django.urls import path

from . import views

app_name = "todos"
urlpatterns = [
    path("", views.app, name="app"),
    path("session/", views.session_status, name="session"),
    path("api/todos/", views.collection, name="collection"),
    path("api/todos/import/", views.import_local, name="import"),
    path("api/todos/<uuid:pk>/", views.detail, name="detail"),
]
