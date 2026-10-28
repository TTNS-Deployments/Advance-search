from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.search_page, name="search"),
    path("search/results", views.results, name="results"),
    path("documents", views.documents, name="documents"),
    path("documents/table", views.documents_table, name="documents_table"),
    path("documents/upload", views.upload, name="upload"),
    path("documents/sync", views.sync, name="sync"),
    path("documents/rebuild", views.rebuild, name="rebuild"),
    path("documents/<str:doc_id>/reindex", views.reindex, name="reindex"),
    path("documents/<str:doc_id>/delete", views.delete, name="delete"),
    path("documents/<str:doc_id>/open/<path:name>", views.open_document, name="open"),
    path("documents/<str:doc_id>/images/<str:image_id>", views.document_image, name="image"),
    path("settings", views.settings_page, name="settings"),
    path("healthz", views.healthz, name="healthz"),
]
