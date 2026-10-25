from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from .roles import AnonymousUser, User

PUBLIC_PREFIXES = ("/auth/", "/static/", "/healthz", "/favicon.ico", "/robots")


class AuthenticationMiddleware:
    """Puts ``request.user`` on every request and sends anonymous users to sign in.

    API requests (``/api/``) get a JSON 401 instead of a redirect; htmx requests get an ``HX-Redirect``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = User.from_session(request.session.get("user")) or AnonymousUser()
        if request.user.is_authenticated or request.path.startswith(PUBLIC_PREFIXES):
            return self.get_response(request)
        if request.path.startswith("/api/"):
            return JsonResponse({"error": "Sign in first."}, status=401)
        login = f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}"
        if request.headers.get("HX-Request"):
            response = JsonResponse({"error": "Sign in first."}, status=401)
            response["HX-Redirect"] = login
            return response
        return redirect(login)
