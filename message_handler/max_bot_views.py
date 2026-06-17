#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging

from asgiref.sync import async_to_sync
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from max_bot_service import MaxBotConfigError, MaxBotSecretError, MaxBotService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def max_bot_webhook(request):
    """Webhook endpoint for MAX Bot API."""
    service = MaxBotService()

    if request.method == "GET":
        return JsonResponse(
            {
                "status": "ok",
                "channel": "MAX",
                "token_configured": bool(service.token),
                "secret_configured": bool(service.webhook_secret),
            }
        )

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "error": "Invalid JSON"}, status=400)

    request_secret = request.headers.get("X-Max-Bot-Api-Secret")
    try:
        result = async_to_sync(service.process_update)(
            payload,
            request_secret=request_secret,
            send_reply=True,
            validate_webhook_secret=True,
        )
    except MaxBotSecretError:
        return JsonResponse({"status": "error", "error": "Invalid secret"}, status=403)
    except MaxBotConfigError as exc:
        logger.error("MAX webhook config error: %s", exc)
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)
    except Exception as exc:
        logger.error("MAX webhook processing failed: %s", exc, exc_info=True)
        return JsonResponse({"status": "error", "error": "Internal error"}, status=500)

    return JsonResponse(
        {
            "status": result.get("status", "success"),
            "session_id": result.get("session_id"),
            "command_only": result.get("command_only", False),
        }
    )
