import logging
import mimetypes
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.decorators import permission_required
from advancesearch.extract import CONTENT_TYPES, FILE_TYPE_LABELS
from advancesearch.index import IndexMismatch
from advancesearch.ingest import STATUSES, UploadError, doc_id_for, parse_iso
from advancesearch.settings_store import SettingsError

from . import data

log = logging.getLogger(__name__)

STATUS_LABELS = {"queued": "Queued", "processing": "Processing", "indexed": "Indexed", "failed": "Failed",
                 "no_text": "No text"}


def _is_htmx(request) -> bool:
    return bool(request.headers.get("HX-Request"))


def _wants_json(request) -> bool:
    return "application/json" in request.headers.get("Accept", "")


# ---------------------------------------------------------------------------- search

def _search_context(request, query: str) -> dict:
    """Run a search and describe the outcome for the results partial."""
    ctx = {"query": query, "state": "empty"}
    if not query.strip():
        return ctx
    try:
        response = data.run_search(query)
    except IndexMismatch as exc:
        log.warning("Search refused: %s", exc)
        ctx.update(state="error", error_detail=str(exc) if request.user.is_admin else "")
        return ctx
    except Exception as exc:  # noqa: BLE001 - show a friendly error, details in the log
        log.exception("Search failed")
        ctx.update(state="error", error_detail=str(exc)[:300] if request.user.is_admin else "")
        return ctx
    results = []
    for r in response.results:
        doc = data.document(r.doc_id, r.file_name)
        results.append({
            "r": r, "type_label": FILE_TYPE_LABELS.get(r.file_type, r.file_type.upper()),
            "size": doc.size if doc else None, "uploaded": parse_iso(r.uploaded_at),
            "open_url": reverse("portal:open", args=[r.doc_id, r.file_name]),
            "source_label": "semantic ranker" if r.score_source == "semantic" else "vector similarity",
        })
    ctx.update(response=response, results=results)
    if results:
        ctx["state"] = "results"
    else:
        ctx["state"] = "no_match" if data.indexed_count() else "no_documents"
    return ctx


@require_GET
@permission_required("search")
def search_page(request):
    values = data.settings_store().effective()
    query = request.GET.get("q", "")
    ctx = {"settings_values": values, "query": query, "warning": data.index_warning() if request.user.is_admin else ""}
    if query.strip():
        ctx.update(_search_context(request, query))
    return render(request, "portal/search.html", ctx)


@require_GET
@permission_required("search")
def results(request):
    query = request.GET.get("q", "")
    if not _is_htmx(request):
        return redirect(f"{reverse('portal:search')}?q={quote(query)}")
    return render(request, "portal/partials/results.html", _search_context(request, query))


@require_GET
@permission_required("open_documents")
def open_document(request, doc_id, name):
    """Streams the original file through the app (the storage account is never exposed)."""
    if doc_id_for(name) != doc_id:
        raise Http404
    doc = data.document(doc_id, name)
    if doc is None:
        raise Http404
    content_type = CONTENT_TYPES.get(doc.file_type) or mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        stream = data.service().blobs.iter_bytes(data.service().container, name)
    except FileNotFoundError:
        raise Http404 from None
    response = StreamingHttpResponse(stream, content_type=content_type)
    response["Content-Length"] = str(doc.size)
    disposition = "inline" if doc.file_type == "pdf" else "attachment"
    filename = name.rsplit("/", 1)[-1]
    response["Content-Disposition"] = f"{disposition}; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------------------------------------------------------- documents

def _filtered_documents(request) -> tuple[list, dict]:
    docs = data.service().list()
    counts = {s: 0 for s in STATUSES}
    for d in docs:
        counts[d.status] += 1
    name = request.GET.get("q", "").strip().lower()
    status = request.GET.get("status", "")
    file_type = request.GET.get("type", "")
    shown = [d for d in docs if (not name or name in d.name.lower()) and (not status or d.status == status)
             and (not file_type or d.file_type == file_type)]
    shown.sort(key=lambda d: (d.uploaded_at is None, -(d.uploaded_at.timestamp() if d.uploaded_at else 0), d.name))
    return shown, {"counts": counts, "total": len(docs), "in_progress": any(d.in_progress for d in docs)}


def _table_context(request) -> dict:
    shown, summary = _filtered_documents(request)
    rows = [{"d": d, "type_label": FILE_TYPE_LABELS.get(d.file_type, "?"), "status_label": STATUS_LABELS[d.status],
             "open_url": reverse("portal:open", args=[d.doc_id, d.name])} for d in shown]
    return {"rows": rows, **summary, "filters": {k: request.GET.get(k, "") for k in ("q", "status", "type")},
            "backlog": data.worker().backlog}


@require_GET
@permission_required("manage_documents")
def documents(request):
    ctx = _table_context(request)
    ctx.update(status_labels=STATUS_LABELS, type_labels=FILE_TYPE_LABELS, warning=data.index_warning())
    return render(request, "portal/documents.html", ctx)


@require_GET
@permission_required("manage_documents")
def documents_table(request):
    return render(request, "portal/partials/documents_table.html", _table_context(request))


@require_POST
@permission_required("manage_documents")
def upload(request):
    """One or more files in the ``file`` field. The page's script sends one file per request (progress bars);
    without JavaScript the form posts them all at once."""
    files = request.FILES.getlist("file")
    if not files:
        if _wants_json(request):
            return JsonResponse({"ok": False, "message": "Choose a file to upload."}, status=400)
        messages.error(request, "Choose a file to upload.")
        return redirect("portal:documents")
    outcomes = []
    for f in files:
        try:
            result = data.service().upload(f.name, f, f.size, uploaded_by=request.user.role)
        except UploadError as exc:
            outcomes.append({"ok": False, "file": f.name, "message": str(exc)})
            continue
        except Exception:  # noqa: BLE001
            log.exception("Upload of %s failed", f.name)
            outcomes.append({"ok": False, "file": f.name, "message": "The upload failed. Try again."})
            continue
        data.worker().enqueue(result.name)
        note = "Replaced the earlier version; queued for indexing." if result.replaced else "Queued for indexing."
        outcomes.append({"ok": True, "file": f.name, "name": result.name, "message": note})
    if _wants_json(request):
        first = outcomes[0] if len(outcomes) == 1 else {"ok": all(o["ok"] for o in outcomes), "results": outcomes}
        return JsonResponse(first, status=200 if first["ok"] else 400)
    for o in outcomes:
        (messages.success if o["ok"] else messages.error)(request, f"{o['file']}: {o['message']}")
    return redirect("portal:documents")


def _doc_from_post(request, doc_id):
    name = request.POST.get("name", "")
    doc = data.document(doc_id, name) if name else None
    if doc is None:
        raise Http404
    return doc


def _after_action(request, message: str, ok: bool = True):
    if _is_htmx(request):
        response = render(request, "portal/partials/documents_table.html", {**_table_context(request), "flash": message,
                                                                            "flash_ok": ok})
        return response
    (messages.success if ok else messages.error)(request, message)
    return redirect("portal:documents")


@require_POST
@permission_required("manage_documents")
def reindex(request, doc_id):
    doc = _doc_from_post(request, doc_id)
    data.service().reindex(doc.name)
    data.worker().enqueue(doc.name)
    return _after_action(request, f"{doc.name} is queued for re-indexing.")


@require_POST
@permission_required("manage_documents")
def delete(request, doc_id):
    doc = _doc_from_post(request, doc_id)
    removed = data.service().delete(doc.name)
    return _after_action(request, f"Deleted {doc.name} and its {removed} passage{'s' if removed != 1 else ''}.")


@require_POST
@permission_required("manage_documents")
def sync(request):
    names = data.worker().sync(include_finished=True)
    return _after_action(request, f"Sync from storage: {len(names)} document{'s' if len(names) != 1 else ''} queued."
                         if names else "Sync from storage: every document is already indexed.")


@require_POST
@permission_required("manage_documents")
def rebuild(request):
    try:
        names = data.service().rebuild_index()
    except Exception as exc:  # noqa: BLE001
        log.exception("Index rebuild failed")
        return _after_action(request, f"The index could not be rebuilt: {str(exc)[:200]}", ok=False)
    data.reset_index_status()
    for name in names:
        data.worker().enqueue(name)
    return _after_action(request, f"The index was rebuilt; {len(names)} documents are queued for indexing.")


# ---------------------------------------------------------------------------- settings

@require_http_methods(["GET", "POST"])
@permission_required("edit_settings")
def settings_page(request):
    store = data.settings_store()
    error = ""
    if request.method == "POST":
        if request.POST.get("action") == "reset":
            store.reset()
            messages.success(request, "Settings were reset to the defaults in Config/search.yaml.")
            return redirect("portal:settings")
        try:
            store.save({k: request.POST.get(k, "") for k in ("top_n", "min_match_percent", "example_queries",
                                                              "welcome_text")})
        except SettingsError as exc:
            error = str(exc)
        else:
            messages.success(request, "Settings saved. They apply to the next search.")
            return redirect("portal:settings")
    values = store.effective()
    if request.method == "POST" and error:
        values = {**values, **{k: request.POST.get(k, "") for k in ("top_n", "min_match_percent", "welcome_text")},
                  "example_queries": request.POST.get("example_queries", "").splitlines()}
    return render(request, "portal/settings.html", {"values": values, "error": error, "system": data.system_info()},
                  status=400 if error else 200)


# ---------------------------------------------------------------------------- misc

def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


def forbidden(request, exception=None):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "Your role cannot do this."}, status=403)
    return render(request, "portal/error.html", {"code": 403, "title": "Not available for your role",
                                                 "message": "This page is for Admins. Sign in as Admin to use it."},
                  status=403)


def not_found(request, exception=None):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "Not found."}, status=404)
    return render(request, "portal/error.html", {"code": 404, "title": "Page not found",
                                                 "message": "The page or document does not exist (it may have been deleted)."},
                  status=404)


def server_error(request):
    return render(request, "portal/error.html", {"code": 500, "title": "Something went wrong",
                                                 "message": "The error was logged. Try again in a moment."}, status=500)
