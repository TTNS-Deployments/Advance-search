from django.urls import path

from . import api

app_name = "api"

urlpatterns = [
    path("search", api.search, name="search"),
    path("documents", api.documents, name="documents"),
    path("status", api.status, name="status"),
]
