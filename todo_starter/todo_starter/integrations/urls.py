from django.urls import path

from . import views

app_name = "integrations"
urlpatterns = [
    path("", views.index, name="index"),
    path("google/connect/", views.connect, name="connect"),
    path("google/callback/", views.callback, name="callback"),
    path("google/disconnect/", views.disconnect, name="disconnect"),
]
