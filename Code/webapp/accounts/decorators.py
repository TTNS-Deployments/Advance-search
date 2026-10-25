from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


def permission_required(permission: str):
    """Page views: 403 page when the signed-in role lacks ``permission``."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.can(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def api_permission_required(permission: str):
    """API views: JSON 403 when the signed-in role lacks ``permission``."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.can(permission):
                return JsonResponse({"error": "Your role cannot do this."}, status=403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
