import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
import time
import tempfile
import urllib.parse
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from decouple import config
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from portal.models import UserProfile
from work_orders.models import WorkOrder
from work_orders.models import WorkOrderEventLog
from work_orders.models import UserCompanyMembership
from work_orders.workflow import (
    ACTION_DEFINITIONS,
    WorkflowError,
    apply_action,
    build_sla_rows,
    create_result_photo_attachment,
    get_result_photo_attachments,
)


logger = logging.getLogger(__name__)

INIT_DATA_MAX_AGE_SECONDS = 60 * 60
PHOTO_INLINE_LIMIT_BYTES = 8 * 1024 * 1024
PHOTO_UPLOAD_LIMIT_BYTES = 20 * 1024 * 1024
STT_AUDIO_LIMIT_BYTES = 1024 * 1024
STT_SOURCE_AUDIO_LIMIT_BYTES = 20 * 1024 * 1024
YANDEX_STT_ENDPOINT = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
YANDEX_STT_ALLOWED_RATES = {8000, 16000, 48000}
VOICE_SESSION_MAX_AGE_SECONDS = 15 * 60

BOSS_ROLE_CODES = {"django_admin", "direktor_uk", "chief_engineer"}
EXECUTOR_ROLE_CODES = {"executor", "contractor"}
UK_USER_ROLE_CODES = {"uk_user", "resident"}


class MaxWebAppAuthError(Exception):
    def __init__(self, message, status=401):
        self.message = message
        self.status = status
        super().__init__(message)


class MaxWebAppSpeechError(Exception):
    def __init__(self, message, status=400, code="speech_error"):
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)


def _max_webapp_bot_token():
    return (
        config("MAX_WEBAPP_BOT_TOKEN", default=None)
        or config("MAX_NOTIFIER_BOT_TOKEN", default=None)
        or config("MAX_BOT_TOKEN", default=None)
    )


def _mask_sensitive(value):
    value = str(value or "")
    if len(value) <= 16:
        return "***"
    return f"{value[:8]}...{value[-8:]}"


def _safe_max_launch_payload(params, user, init_data):
    safe_params = {}
    for key, value in params.items():
        if key == "hash":
            safe_params[key] = _mask_sensitive(value)
        elif key == "user":
            safe_params[key] = user
        else:
            safe_params[key] = value
    return {
        "source": "signed_init_data",
        "rawLength": len(init_data or ""),
        "paramKeys": sorted(params.keys()),
        "params": safe_params,
    }


def _validate_init_data(init_data):
    if not init_data:
        raise MaxWebAppAuthError("MAX initData is missing")

    token = _max_webapp_bot_token()
    if not token:
        raise MaxWebAppAuthError("MAX webapp bot token is not configured", status=500)

    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MaxWebAppAuthError("MAX initData is malformed") from exc

    keys = [key for key, _value in pairs]
    if len(keys) != len(set(keys)):
        raise MaxWebAppAuthError("MAX initData contains duplicate keys")

    params = dict(pairs)
    original_hash = params.get("hash")
    if not original_hash:
        raise MaxWebAppAuthError("MAX initData hash is missing")

    launch_params = "\n".join(
        f"{key}={value}"
        for key, value in sorted(pairs, key=lambda item: item[0])
        if key != "hash"
    )
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, launch_params.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, original_hash):
        raise MaxWebAppAuthError("MAX initData signature is invalid")

    try:
        auth_date = int(params.get("auth_date", "0"))
    except ValueError as exc:
        raise MaxWebAppAuthError("MAX initData auth_date is invalid") from exc
    if auth_date <= 0 or time.time() - auth_date > INIT_DATA_MAX_AGE_SECONDS:
        raise MaxWebAppAuthError("MAX initData is expired")

    try:
        user = json.loads(params.get("user") or "{}")
    except json.JSONDecodeError as exc:
        raise MaxWebAppAuthError("MAX initData user is invalid") from exc

    identity = _resolve_max_webapp_identity(user, params)
    identity["max_launch"] = _safe_max_launch_payload(params, user, init_data)
    logger.info(
        "MAX webapp launch payload: %s",
        json.dumps(identity["max_launch"], ensure_ascii=False),
    )
    return identity


def _resolve_max_webapp_identity(max_user, init_params):
    try:
        max_user_id = int(max_user.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise MaxWebAppAuthError("MAX user id is invalid") from exc
    if max_user_id <= 0:
        raise MaxWebAppAuthError("MAX user id is missing")

    try:
        profile = UserProfile.objects.select_related("user").get(max_user_id=max_user_id)
    except UserProfile.DoesNotExist as exc:
        raise MaxWebAppAuthError("MAX user is not linked to an active system user", status=403) from exc

    django_user = profile.user
    if not django_user.is_active:
        raise MaxWebAppAuthError("Linked system user is disabled", status=403)

    memberships = list(
        UserCompanyMembership.objects.filter(
            user=django_user,
            is_active=True,
            date_to__isnull=True,
        )
        .select_related("company", "department")
        .order_by("-is_primary", "company__name", "department__department_name")
    )
    role_codes = {membership.role_code for membership in memberships}
    company_ids = sorted({membership.company_id for membership in memberships if membership.company_id})
    department_ids = sorted({membership.department_id for membership in memberships if membership.department_id})
    profile_role = profile.role or ""

    has_global_scope = (django_user.is_superuser or profile_role == "django_admin") and not company_ids
    if django_user.is_superuser or has_global_scope or role_codes & BOSS_ROLE_CODES or profile_role in BOSS_ROLE_CODES:
        interface_type = "boss"
    elif role_codes & EXECUTOR_ROLE_CODES or profile_role in EXECUTOR_ROLE_CODES:
        interface_type = "executor"
    else:
        interface_type = "uk_user"

    interface_labels = {
        "uk_user": "Пользователь УК",
        "executor": "Исполнитель",
        "boss": "Босс",
    }
    can_edit = interface_type in {"executor", "boss"}

    return {
        "max_user": max_user,
        "max_user_id": max_user_id,
        "max_username": max_user.get("username") or "",
        "max_first_name": max_user.get("first_name") or "",
        "max_last_name": max_user.get("last_name") or "",
        "max_name": max_user.get("name") or "",
        "max_language_code": max_user.get("language_code") or "",
        "max_photo_url": max_user.get("photo_url") or "",
        "max_auth_date": init_params.get("auth_date") or "",
        "max_query_id": init_params.get("query_id") or "",
        "max_chat_type": init_params.get("chat_type") or "",
        "max_chat_instance": init_params.get("chat_instance") or "",
        "max_start_param": init_params.get("start_param") or "",
        "django_user": django_user,
        "django_user_id": django_user.id,
        "django_username": django_user.username,
        "company_ids": company_ids,
        "department_ids": department_ids,
        "role_codes": sorted(role_codes or ({profile_role} if profile_role else set())),
        "profile_role": profile_role,
        "has_global_scope": has_global_scope,
        "memberships": memberships,
        "interface": {
            "type": interface_type,
            "label": interface_labels[interface_type],
            "canEdit": can_edit,
            "canCreateRequest": interface_type == "uk_user",
        },
        "bot_username": "id3662313265_1_bot",
    }


def _display_name(user):
    parts = [user.get("first_name"), user.get("last_name")]
    name = " ".join(part for part in parts if part)
    return name or user.get("username") or str(user.get("id") or "")


def _django_user_display(user):
    return user.get_full_name() or user.username or str(user.id)


def _identity_payload(identity):
    return {
        "id": identity["max_user_id"],
        "name": _display_name(identity["max_user"]),
        "djangoUserId": identity["django_user_id"],
        "djangoUserName": _django_user_display(identity["django_user"]),
    }


def _interface_payload(identity):
    return identity["interface"]


def _max_launch_payload(identity):
    return identity.get("max_launch", {})


def _json_error(message, status=400, code="error"):
    return _json({"ok": False, "error": message, "code": code}, status=status)


def _json(data, status=200):
    response = JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _request_json_payload(request, max_bytes=128 * 1024):
    raw_body = request.body[: max_bytes + 1]
    if len(raw_body) > max_bytes:
        raise ValueError("payload_too_large")
    if not raw_body:
        return {}
    return json.loads(raw_body.decode("utf-8"))


def _authenticated_max_identity(request):
    return _validate_init_data(request.headers.get("X-Max-Init-Data", ""))


def _voice_session_signer():
    return TimestampSigner(salt="max-webapp-voice-session")


def _voice_session_dir():
    path = config(
        "MAX_WEBAPP_VOICE_SESSION_DIR",
        default="/var/www/komunal-dom_ru/runtime/max_voice_sessions",
    )
    os.makedirs(path, exist_ok=True)
    return path


def _safe_voice_session_id(session_id):
    return str(uuid.UUID(str(session_id)))


def _voice_session_path(session_id):
    return os.path.join(_voice_session_dir(), f"{_safe_voice_session_id(session_id)}.json")


def _save_voice_session(session):
    with open(_voice_session_path(session["id"]), "w", encoding="utf-8") as file:
        json.dump(session, file, ensure_ascii=False)


def _load_voice_session(session_id):
    try:
        with open(_voice_session_path(session_id), "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise MaxWebAppAuthError("Сессия записи не найдена.", status=404) from exc


def _validate_voice_token(session_id, token):
    if not token:
        raise MaxWebAppAuthError("Токен сессии записи отсутствует.", status=403)
    try:
        unsigned_session_id = _voice_session_signer().unsign(
            token,
            max_age=VOICE_SESSION_MAX_AGE_SECONDS,
        )
    except SignatureExpired as exc:
        raise MaxWebAppAuthError("Сессия записи истекла.", status=403) from exc
    except BadSignature as exc:
        raise MaxWebAppAuthError("Токен сессии записи недействителен.", status=403) from exc
    if _safe_voice_session_id(unsigned_session_id) != _safe_voice_session_id(session_id):
        raise MaxWebAppAuthError("Токен сессии записи не совпадает.", status=403)


def _identity_matches_voice_session(identity, session):
    return (
        int(session.get("djangoUserId") or 0) == int(identity["django_user_id"])
        and int(session.get("maxUserId") or 0) == int(identity["max_user_id"])
    )


def _voice_session_payload(session):
    return {
        "id": session["id"],
        "status": session.get("status") or "created",
        "text": session.get("text") or "",
        "error": session.get("error") or "",
        "workOrderId": session.get("workOrderId") or None,
        "createdAt": session.get("createdAt") or "",
        "updatedAt": session.get("updatedAt") or "",
        "expiresAt": session.get("expiresAt") or "",
    }


def _append_voice_session_event(session, event, details=None, mark_error=False):
    now = timezone.localtime(timezone.now()).isoformat()
    events = list(session.get("events") or [])
    events.append(
        {
            "event": str(event or "")[:80],
            "details": details if isinstance(details, dict) else {},
            "createdAt": now,
        }
    )
    session["events"] = events[-20:]
    session["updatedAt"] = now
    if mark_error:
        session["status"] = "error"
        session["error"] = str(event or "Ошибка внешней записи")[:240]
    _save_voice_session(session)


def _actor_user(identity):
    return identity["django_user"]


def _base_work_order_queryset():
    return WorkOrder.objects.filter(is_test=False).select_related(
        "company",
        "current_internal_status",
        "department",
        "responsible_user",
        "service",
        "object",
    )


def _work_order_queryset(identity):
    queryset = _base_work_order_queryset()
    interface_type = identity["interface"]["type"]
    django_user = identity["django_user"]

    if interface_type == "boss":
        if identity["has_global_scope"]:
            return queryset
        if not identity["company_ids"]:
            return queryset.none()
        return queryset.filter(company_id__in=identity["company_ids"])

    if interface_type == "executor":
        assigned_filter = Q(responsible_user=django_user)
        unassigned_filter = Q(
            responsible_user__isnull=True,
            current_internal_status__is_terminal=False,
        )
        if identity["company_ids"]:
            unassigned_filter &= Q(company_id__in=identity["company_ids"])
        if identity["department_ids"]:
            unassigned_filter &= Q(department_id__in=identity["department_ids"])
        else:
            unassigned_filter &= Q(pk__in=[])
        return queryset.filter(assigned_filter | unassigned_filter).distinct()

    return queryset.filter(resident_user=django_user)


def _responsible_payload(user):
    if not user:
        return {"id": None, "name": ""}
    return {
        "id": user.id,
        "name": user.get_full_name() or user.username,
    }


def _assignment_candidates(work_order):
    if not work_order.department_id:
        return []

    from work_orders.models import UserCompanyMembership

    memberships = (
        UserCompanyMembership.objects.filter(
            company=work_order.company,
            department=work_order.department,
            is_active=True,
            date_to__isnull=True,
            role_code__in=["contractor", "executor"],
            user__is_active=True,
        )
        .select_related("user", "department")
        .order_by("user__last_name", "user__first_name", "user__username")
    )
    candidates = []
    seen_user_ids = set()
    for membership in memberships:
        if membership.user_id in seen_user_ids:
            continue
        seen_user_ids.add(membership.user_id)
        candidates.append(
            {
                "id": membership.user_id,
                "name": membership.user.get_full_name() or membership.user.username,
                "department": membership.department.department_name if membership.department_id else "",
            }
        )
    return candidates


def _active_action_payload(work_order, identity):
    if not identity["interface"]["canEdit"]:
        return None

    status_code = work_order.current_internal_status.short_code_en
    action_by_status = {
        "new_registered": "assign",
        "accepted_by_executor": "start",
        "in_progress": "localize",
        "localized": "complete",
        "completed": "close",
    }
    action = action_by_status.get(status_code)
    if not action:
        return None
    definition = ACTION_DEFINITIONS[action]
    return {
        "code": action,
        "label": definition["label"],
        "targetStatus": definition["target_status"],
        "requiresResolution": bool(definition.get("requires_resolution_text")),
        "requiresResponsible": bool(definition.get("requires_responsible_user")),
        "confirmWithoutPhoto": bool(definition.get("confirm_without_photo")),
    }


def _photo_payload(attachment):
    data_url = ""
    file_bytes = bytes(attachment.file_data or b"")
    if (
        file_bytes
        and attachment.mime_type
        and attachment.mime_type.startswith("image/")
        and len(file_bytes) <= PHOTO_INLINE_LIMIT_BYTES
    ):
        encoded = base64.b64encode(file_bytes).decode("ascii")
        data_url = f"data:{attachment.mime_type};base64,{encoded}"

    return {
        "id": attachment.id,
        "fileName": attachment.file_name,
        "mimeType": attachment.mime_type,
        "size": attachment.file_size,
        "uploadedAt": timezone.localtime(attachment.uploaded_at).isoformat(),
        "dataUrl": data_url,
    }


def _order_payload(order):
    service = order.service
    status = order.current_internal_status
    service_object = order.object

    try:
        address = service_object.get_address_display()
    except Exception:
        address = f"Объект #{order.object_id}"

    responsible = ""
    if order.responsible_user_id:
        responsible = order.responsible_user.get_full_name() or order.responsible_user.username

    return {
        "id": order.id,
        "number": order.work_order_no,
        "createdAt": timezone.localtime(order.created_at).isoformat(),
        "company": order.company.name,
        "status": {
            "code": status.short_code_en,
            "name": status.display_name_for_user or status.short_name_ru,
            "isTerminal": status.is_terminal,
        },
        "service": {
            "id": service.service_id,
            "name": service.scenario_name,
            "category": service.category_name,
            "type": service.type_name,
            "localization": service.localization_name,
        },
        "object": {
            "id": service_object.service_object_id,
            "address": address,
        },
        "department": order.department.department_name if order.department_id else "",
        "responsible": responsible,
        "responsibleId": order.responsible_user_id,
        "priority": {
            "code": order.priority_code,
            "name": order.get_priority_code_display(),
        },
        "isEmergency": order.is_emergency,
        "text": order.original_request_text,
        "additionalInfo": order.additional_info_text or "",
    }


def _detail_payload(order, identity):
    payload = _order_payload(order)
    photos = [_photo_payload(photo) for photo in get_result_photo_attachments(order)]
    candidates = _assignment_candidates(order)
    can_edit = identity["interface"]["canEdit"]
    payload.update(
        {
            "user": _identity_payload(identity),
            "interface": _interface_payload(identity),
            "sla": build_sla_rows(order),
            "responsibleUser": _responsible_payload(order.responsible_user),
            "assignment": {
                "editable": can_edit and order.responsible_user_id is None,
                "candidates": candidates,
            },
            "resolution": order.resolution_text or "",
            "photos": photos,
            "photoCount": len(photos),
            "activeAction": _active_action_payload(order, identity),
        }
    )
    return payload


def _save_resolution_if_changed(work_order, actor, resolution_text):
    resolution_text = (resolution_text or "").strip()
    if (work_order.resolution_text or "") == resolution_text:
        return False

    work_order.resolution_text = resolution_text
    work_order.save(update_fields=["resolution_text"])
    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code="resolution_updated",
        event_datetime=timezone.now(),
        author_user=actor,
        text_value="Обновлен текст решения по заявке.",
        is_visible_to_resident=False,
        is_test=work_order.is_test,
    )
    return True


def _assign_if_allowed(work_order, actor, responsible_user_id):
    responsible_user_id = (responsible_user_id or "").strip()
    if not responsible_user_id:
        return False

    if work_order.responsible_user_id:
        if str(work_order.responsible_user_id) == str(responsible_user_id):
            return False
        raise WorkflowError("Исполнитель уже назначен.", code="responsible_already_set")

    candidate_ids = {str(candidate["id"]) for candidate in _assignment_candidates(work_order)}
    if str(responsible_user_id) not in candidate_ids:
        raise WorkflowError("Выберите сотрудника отдела заявки.", code="responsible_user_invalid")

    if work_order.current_internal_status.short_code_en == "new_registered":
        apply_action(
            work_order=work_order,
            user=actor,
            action="assign",
            responsible_user_id=responsible_user_id,
        )
        work_order.refresh_from_db()
        return True

    target_user = User.objects.get(pk=responsible_user_id, is_active=True)
    work_order.responsible_user = target_user
    work_order.save(update_fields=["responsible_user"])
    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code="assigned",
        event_datetime=timezone.now(),
        author_user=actor,
        text_value=f"Назначен ответственный: {target_user.get_full_name() or target_user.username}.",
        new_responsible_user=target_user,
        is_visible_to_resident=False,
        is_test=work_order.is_test,
    )
    return True


def _yandex_stt_auth_header():
    api_key = config("YANDEX_API_KEY", default=None)
    if api_key:
        return f"Api-Key {api_key}", False

    iam_token = config("YANDEX_IAM_TOKEN", default=None)
    if iam_token:
        return f"Bearer {iam_token}", True

    raise MaxWebAppSpeechError("Yandex SpeechKit не настроен.", status=500, code="stt_not_configured")


def _recognize_yandex_audio(audio_bytes, identity, audio_format="lpcm", sample_rate_hertz=16000):
    if audio_format not in {"lpcm", "oggopus"}:
        raise MaxWebAppSpeechError("Неподдерживаемый формат аудио.", code="invalid_audio_format")
    if audio_format == "lpcm" and sample_rate_hertz not in YANDEX_STT_ALLOWED_RATES:
        raise MaxWebAppSpeechError("Неподдерживаемая частота аудио.", code="invalid_sample_rate")
    if not audio_bytes:
        raise MaxWebAppSpeechError("Аудио пустое.", code="empty_audio")
    if len(audio_bytes) > STT_AUDIO_LIMIT_BYTES:
        raise MaxWebAppSpeechError("Аудио слишком длинное. Запишите фразу короче.", status=413, code="audio_too_large")

    auth_header, requires_folder = _yandex_stt_auth_header()
    query = {
        "lang": "ru-RU",
        "format": audio_format,
    }
    if audio_format == "lpcm":
        query["sampleRateHertz"] = str(sample_rate_hertz)
    if requires_folder:
        folder_id = config("YANDEX_FOLDER_ID", default=None)
        if not folder_id:
            raise MaxWebAppSpeechError("YANDEX_FOLDER_ID не настроен.", status=500, code="stt_not_configured")
        query["folderId"] = folder_id

    url = f"{YANDEX_STT_ENDPOINT}?{urllib.parse.urlencode(query)}"
    logger.info(
        "MAX webapp STT request user=%s max_user=%s bytes=%s sample_rate=%s",
        identity["django_user_id"],
        identity["max_user_id"],
        len(audio_bytes),
        sample_rate_hertz if audio_format == "lpcm" else audio_format,
    )
    request = urllib.request.Request(
        url,
        data=audio_bytes,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/octet-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.warning("Yandex STT HTTP %s: %s", exc.code, error_body[:500])
        if exc.code == 401:
            raise MaxWebAppSpeechError(
                "Yandex SpeechKit API-ключ истек или недействителен. Обновите YANDEX_API_KEY на сервере.",
                status=502,
                code="stt_auth_error",
            ) from exc
        raise MaxWebAppSpeechError(
            "Yandex SpeechKit вернул ошибку распознавания.",
            status=502,
            code="stt_upstream_error",
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.exception("Yandex STT request failed")
        raise MaxWebAppSpeechError(
            "Не удалось связаться с Yandex SpeechKit.",
            status=502,
            code="stt_unavailable",
        ) from exc

    text = (payload.get("result") or "").strip()
    logger.info(
        "MAX webapp STT response user=%s chars=%s",
        identity["django_user_id"],
        len(text),
    )
    return text


def _recognize_yandex_lpcm(audio_bytes, sample_rate_hertz, identity):
    return _recognize_yandex_audio(audio_bytes, identity, "lpcm", sample_rate_hertz)


def _convert_audio_to_lpcm(uploaded_file):
    source_bytes = uploaded_file.read(STT_SOURCE_AUDIO_LIMIT_BYTES + 1)
    if len(source_bytes) > STT_SOURCE_AUDIO_LIMIT_BYTES:
        raise MaxWebAppSpeechError("Аудиофайл слишком большой.", status=413, code="audio_too_large")
    if not source_bytes:
        raise MaxWebAppSpeechError("Аудио пустое.", code="empty_audio")

    suffix = os.path.splitext(uploaded_file.name or "")[1] or ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as source:
        source.write(source_bytes)
        source_path = source.name
    output_path = f"{source_path}.pcm"
    try:
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            source_path,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            output_path,
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=30)
        except FileNotFoundError as exc:
            raise MaxWebAppSpeechError(
                "На сервере не установлен ffmpeg для распознавания системных аудиозаписей.",
                status=500,
                code="ffmpeg_missing",
            ) from exc
        except subprocess.CalledProcessError as exc:
            logger.warning("ffmpeg audio conversion failed: %s", exc.stderr.decode("utf-8", errors="replace")[:500])
            raise MaxWebAppSpeechError(
                "Не удалось обработать аудиофайл. Попробуйте другой формат.",
                code="audio_conversion_failed",
            ) from exc
        with open(output_path, "rb") as converted:
            converted_bytes = converted.read(STT_AUDIO_LIMIT_BYTES + 1)
        if len(converted_bytes) > STT_AUDIO_LIMIT_BYTES:
            raise MaxWebAppSpeechError("Аудио слишком длинное. Запишите фразу короче.", status=413, code="audio_too_large")
        return converted_bytes, 16000
    finally:
        for path in (source_path, output_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


@require_GET
def work_orders(request):
    try:
        identity = _authenticated_max_identity(request)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")

    queryset = _work_order_queryset(identity).order_by("-created_at")

    orders = [_order_payload(order) for order in queryset]
    status_counts = {}
    emergency_count = 0
    for order in orders:
        status_name = order["status"]["name"]
        status_counts[status_name] = status_counts.get(status_name, 0) + 1
        if order["isEmergency"]:
            emergency_count += 1

    return _json(
        {
            "ok": True,
            "user": _identity_payload(identity),
            "interface": _interface_payload(identity),
            "maxLaunch": _max_launch_payload(identity),
            "summary": {
                "total": len(orders),
                "emergency": emergency_count,
                "statuses": status_counts,
                "updatedAt": timezone.localtime(timezone.now()).isoformat(),
            },
            "orders": orders,
        },
    )


@require_GET
def work_order_detail(request, work_order_id):
    try:
        identity = _authenticated_max_identity(request)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")

    work_order = get_object_or_404(_work_order_queryset(identity), pk=work_order_id)
    return _json(
        {"ok": True, "order": _detail_payload(work_order, identity)},
    )


@csrf_exempt
@require_POST
def save_work_order(request, work_order_id):
    try:
        identity = _authenticated_max_identity(request)
        actor = _actor_user(identity)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")
    if not identity["interface"]["canEdit"]:
        return _json_error("Недостаточно прав для изменения обращения.", status=403, code="permission_denied")

    work_order = get_object_or_404(_work_order_queryset(identity), pk=work_order_id)
    try:
        with transaction.atomic():
            _assign_if_allowed(work_order, actor, request.POST.get("responsible_user_id"))
            _save_resolution_if_changed(work_order, actor, request.POST.get("resolution_text", ""))
            work_order.refresh_from_db()
    except WorkflowError as exc:
        return _json_error(exc.message, status=400, code=exc.code)

    return _json(
        {"ok": True, "order": _detail_payload(work_order, identity)},
    )


@csrf_exempt
@require_POST
def run_work_order_action(request, work_order_id):
    try:
        identity = _authenticated_max_identity(request)
        actor = _actor_user(identity)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")
    if not identity["interface"]["canEdit"]:
        return _json_error("Недостаточно прав для изменения статуса.", status=403, code="permission_denied")

    work_order = get_object_or_404(_work_order_queryset(identity), pk=work_order_id)
    action = (request.POST.get("action") or "").strip()
    if action not in ACTION_DEFINITIONS:
        return _json_error("Неизвестное действие.", code="unknown_action")

    try:
        with transaction.atomic():
            if action != "assign":
                _assign_if_allowed(work_order, actor, request.POST.get("responsible_user_id"))
                _save_resolution_if_changed(work_order, actor, request.POST.get("resolution_text", ""))
                work_order.refresh_from_db()

            updated_order = apply_action(
                work_order=work_order,
                user=actor,
                action=action,
                resolution_text=request.POST.get("resolution_text", ""),
                responsible_user_id=request.POST.get("responsible_user_id") or None,
                force_without_photo=request.POST.get("force_without_photo") == "1",
            )
            if action == "assign":
                _save_resolution_if_changed(updated_order, actor, request.POST.get("resolution_text", ""))
                updated_order.refresh_from_db()
    except WorkflowError as exc:
        status = 409 if exc.code == "photo_confirmation_required" else 400
        return _json_error(exc.message, status=status, code=exc.code)

    return _json(
        {"ok": True, "order": _detail_payload(updated_order, identity)},
    )


@csrf_exempt
@require_POST
def upload_work_order_photos(request, work_order_id):
    try:
        identity = _authenticated_max_identity(request)
        actor = _actor_user(identity)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")
    if not identity["interface"]["canEdit"]:
        return _json_error("Недостаточно прав для прикрепления фото.", status=403, code="permission_denied")

    work_order = get_object_or_404(_work_order_queryset(identity), pk=work_order_id)
    uploaded_files = request.FILES.getlist("photo") or request.FILES.getlist("photos")
    if not uploaded_files:
        return _json_error("Файл не передан.")

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    for uploaded_file in uploaded_files:
        if uploaded_file.content_type not in allowed_types:
            return _json_error("Допустимы только JPG, PNG и WEBP.")
        if uploaded_file.size > PHOTO_UPLOAD_LIMIT_BYTES:
            return _json_error("Размер одного фото не должен превышать 20 МБ.")

    for uploaded_file in uploaded_files:
        create_result_photo_attachment(work_order, uploaded_file, actor)

    work_order.refresh_from_db()
    return _json(
        {"ok": True, "order": _detail_payload(work_order, identity)},
    )


@csrf_exempt
@require_POST
def speech_to_text(request):
    try:
        identity = _authenticated_max_identity(request)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")
    if not identity["interface"]["canEdit"]:
        return _json_error("Недостаточно прав для диктовки решения.", status=403, code="permission_denied")

    uploaded_file = request.FILES.get("audio")
    if not uploaded_file:
        return _json_error("Аудио не передано.", code="audio_missing")

    try:
        if request.POST.get("sample_rate"):
            try:
                sample_rate = int(request.POST.get("sample_rate") or "16000")
            except ValueError:
                return _json_error("Некорректная частота аудио.", code="invalid_sample_rate")
            audio_bytes = uploaded_file.read(STT_AUDIO_LIMIT_BYTES + 1)
            text = _recognize_yandex_lpcm(audio_bytes, sample_rate, identity)
        else:
            audio_bytes, sample_rate = _convert_audio_to_lpcm(uploaded_file)
            text = _recognize_yandex_lpcm(audio_bytes, sample_rate, identity)
    except MaxWebAppSpeechError as exc:
        return _json_error(exc.message, status=exc.status, code=exc.code)

    return _json({"ok": True, "text": text})


@csrf_exempt
@require_POST
def microphone_diagnostics(request):
    try:
        identity = _authenticated_max_identity(request)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")

    try:
        payload = _request_json_payload(request)
    except ValueError:
        return _json_error("Диагностика слишком большая.", status=413, code="payload_too_large")
    except json.JSONDecodeError:
        return _json_error("Диагностика должна быть JSON.", code="invalid_json")

    event_name = str(payload.get("event") or "microphone_diagnostics")[:80]
    diagnostics = payload.get("diagnostics") or {}
    logger.warning(
        "MAX microphone diagnostics event=%s user=%s max_user=%s query_id=%s chat=%s payload=%s",
        event_name,
        identity["django_user_id"],
        identity["max_user_id"],
        identity.get("max_query_id") or "",
        identity.get("max_chat_instance") or identity.get("max_chat_type") or "",
        json.dumps(diagnostics, ensure_ascii=False)[:12000],
    )
    return _json({"ok": True, "savedAt": timezone.localtime(timezone.now()).isoformat()})


@csrf_exempt
@require_POST
def create_voice_session(request):
    try:
        identity = _authenticated_max_identity(request)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")
    if not identity["interface"]["canEdit"]:
        return _json_error("Недостаточно прав для диктовки решения.", status=403, code="permission_denied")

    request_payload = {}
    if request.body:
        try:
            request_payload = _request_json_payload(request, max_bytes=32 * 1024)
        except (ValueError, json.JSONDecodeError):
            return _json_error("Параметры сессии записи переданы в неверном формате.", code="invalid_voice_session")

    work_order = None
    work_order_id = request_payload.get("workOrderId") or request_payload.get("work_order_id")
    if work_order_id:
        try:
            work_order_id = int(work_order_id)
        except (TypeError, ValueError):
            return _json_error("Неверный идентификатор обращения для записи.", code="invalid_work_order")
        work_order = get_object_or_404(_work_order_queryset(identity), pk=work_order_id)

    now = timezone.now()
    session_id = str(uuid.uuid4())
    token = _voice_session_signer().sign(session_id)
    session = {
        "id": session_id,
        "status": "created",
        "text": "",
        "error": "",
        "createdAt": timezone.localtime(now).isoformat(),
        "updatedAt": timezone.localtime(now).isoformat(),
        "expiresAt": timezone.localtime(now + timedelta(seconds=VOICE_SESSION_MAX_AGE_SECONDS)).isoformat(),
        "djangoUserId": identity["django_user_id"],
        "maxUserId": identity["max_user_id"],
        "workOrderId": work_order.id if work_order else None,
        "maxQueryId": identity.get("max_query_id") or "",
        "maxChatType": identity.get("max_chat_type") or "",
        "userAgent": request.headers.get("User-Agent", ""),
    }
    _save_voice_session(session)
    query = urllib.parse.urlencode({"session": session_id, "token": token})
    record_url = request.build_absolute_uri(f"/voice-recorder.html?{query}")
    logger.info(
        "MAX voice session created session=%s user=%s max_user=%s work_order=%s",
        session_id,
        identity["django_user_id"],
        identity["max_user_id"],
        work_order.id if work_order else None,
    )
    return _json({"ok": True, "session": _voice_session_payload(session), "recordUrl": record_url})


@require_GET
def voice_session_status(request, session_id):
    try:
        identity = _authenticated_max_identity(request)
        session = _load_voice_session(session_id)
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")
    if not _identity_matches_voice_session(identity, session):
        return _json_error("Сессия записи принадлежит другому пользователю.", status=403, code="permission_denied")
    return _json({"ok": True, "session": _voice_session_payload(session)})


@csrf_exempt
@require_POST
def voice_session_event(request, session_id):
    try:
        session = _load_voice_session(session_id)
        payload = _request_json_payload(request, max_bytes=32 * 1024)
        _validate_voice_token(session_id, payload.get("token") or request.headers.get("X-Voice-Token"))
    except (ValueError, json.JSONDecodeError):
        return _json_error("Событие записи передано в неверном формате.", code="invalid_event")
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")

    event = str(payload.get("event") or "voice_recorder_event")[:80]
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    mark_error = bool(payload.get("markError"))
    _append_voice_session_event(session, event, details=details, mark_error=mark_error)
    logger.info(
        "MAX voice session event session=%s event=%s mark_error=%s details=%s",
        session["id"],
        event,
        mark_error,
        json.dumps(details, ensure_ascii=False),
    )
    return _json({"ok": True, "session": _voice_session_payload(session)})


@csrf_exempt
@require_POST
def recognize_voice_session(request, session_id):
    try:
        session = _load_voice_session(session_id)
        _validate_voice_token(session_id, request.POST.get("token") or request.headers.get("X-Voice-Token"))
    except MaxWebAppAuthError as exc:
        return _json_error(exc.message, status=exc.status, code="auth_error")

    uploaded_file = request.FILES.get("audio")
    if not uploaded_file:
        return _json_error("Аудио не передано.", code="audio_missing")

    session["status"] = "processing"
    session["updatedAt"] = timezone.localtime(timezone.now()).isoformat()
    _save_voice_session(session)

    speech_identity = {
        "django_user_id": session.get("djangoUserId") or 0,
        "max_user_id": session.get("maxUserId") or 0,
    }
    try:
        audio_bytes, sample_rate = _convert_audio_to_lpcm(uploaded_file)
        text = _recognize_yandex_lpcm(audio_bytes, sample_rate, speech_identity)
        session["status"] = "done"
        session["text"] = text
        session["error"] = ""
        logger.info("MAX voice session recognized session=%s chars=%s", session["id"], len(text))
    except MaxWebAppSpeechError as exc:
        session["status"] = "error"
        session["error"] = exc.message
        session["text"] = ""
        logger.warning("MAX voice session failed session=%s code=%s error=%s", session["id"], exc.code, exc.message)
        _save_voice_session(session)
        return _json_error(exc.message, status=exc.status, code=exc.code)

    session["updatedAt"] = timezone.localtime(timezone.now()).isoformat()
    _save_voice_session(session)
    return _json({"ok": True, "session": _voice_session_payload(session)})
