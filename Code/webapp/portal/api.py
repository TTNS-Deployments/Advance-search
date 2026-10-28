"""JSON API (same session sign-in and roles as the pages)."""

import logging

from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from accounts.decorators import api_permission_required
from advancesearch.index import IndexMismatch

from . import data

log = logging.getLogger(__name__)


@require_GET
@api_permission_required("search")
def search(request):
    query = request.GET.get("q", "")
    if not query.strip():
        return JsonResponse({"error": "Add a query: /api/search?q=..."}, status=400)
    try:
        response = data.run_search(query)
    except IndexMismatch as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except Exception:  # noqa: BLE001
        log.exception("API search failed")
        return JsonResponse({"error": "Search is temporarily unavailable."}, status=503)
    body = response.to_dict()
    for item in body["results"]:
        item["openUrl"] = request.build_absolute_uri(reverse("portal:open", args=[item["docId"], item["fileName"]]))
        for image in item["images"]:
            image["url"] = request.build_absolute_uri(reverse("portal:image", args=[image["docId"], image["imageId"]]))
            image["fileName"] = item["fileName"]
    return JsonResponse(body)


@require_GET
@api_permission_required("manage_documents")
def documents(request):
    docs = data.service().list()
    return JsonResponse({"count": len(docs), "documents": [{
        "docId": d.doc_id, "fileName": d.name, "fileType": d.file_type, "size": d.size, "status": d.status,
        "error": d.error, "chunks": d.chunks, "images": d.images, "uploadedBy": d.uploaded_by,
        "uploadedAt": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "indexedAt": d.indexed_at.isoformat() if d.indexed_at else None,
    } for d in docs]})


@require_GET
@api_permission_required("manage_documents")
def status(request):
    docs = data.service().list()
    counts = {}
    for d in docs:
        counts[d.status] = counts.get(d.status, 0) + 1
    return JsonResponse({"documents": counts, "queue": data.worker().backlog, "system": data.system_info(),
                         "warning": data.index_warning()})
