from django.conf import settings
from django.urls import reverse

import advancesearch

NAV = [
    ("search", "Search", "portal:search", "search"),
    ("documents", "Documents", "portal:documents", "manage_documents"),
    ("settings", "Settings", "portal:settings", "edit_settings"),
]


def portal(request):
    user = getattr(request, "user", None)
    items = []
    if user is not None and user.is_authenticated:
        items = [{"key": key, "label": label, "href": reverse(name)} for key, label, name, perm in NAV if user.can(perm)]
    match = getattr(request, "resolver_match", None)
    active = (match.url_name or "") if match else ""
    active = {"results": "search", "documents_table": "documents"}.get(active, active)
    return {
        "user": user,
        "nav_items": items, "active_nav": active, "app_version": advancesearch.__version__,
        "environment_name": settings.ENVIRONMENT_NAME, "auth_mode": settings.AUTH_MODE,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
    }
