"""Content-Security-Policy header and the lazy start of the ingestion worker."""

import logging

from django.conf import settings

log = logging.getLogger(__name__)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.CONTENT_SECURITY_POLICY and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = settings.CONTENT_SECURITY_POLICY
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class StartWorkerMiddleware:
    """Starts the background ingestion thread on the first request served by this process.

    Starting here (not in AppConfig.ready) keeps management commands such as collectstatic and test from
    starting it. On App Service the first request is the platform's warm-up ping, right after start-up.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.started = False

    def __call__(self, request):
        if not self.started:
            self.started = True
            try:
                from advancesearch.worker import get_worker

                get_worker().start()
            except Exception:  # noqa: BLE001 - the site must still serve pages
                log.exception("Could not start the ingestion worker")
        return self.get_response(request)
