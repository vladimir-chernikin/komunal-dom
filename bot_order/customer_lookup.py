import re
from typing import Any, Dict, Optional


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def _profile_lookup_payload(profile: Any, matched_by: str) -> Dict[str, Any]:
    user = profile.user
    phone = normalize_phone(getattr(profile, "phone", ""))
    return {
        "name": user.get_full_name() or user.username,
        "contacts": {
            "id_in_system": str(user.id),
            "id_max": str(profile.max_user_id or ""),
            "telefon": f"+{phone}" if phone else "",
        },
        "matched_by": matched_by,
        "addresses": [],
    }


def _find_profile_by_phone(phone: str) -> Optional[Any]:
    if not phone:
        return None
    try:
        from portal.models import UserProfile
    except Exception:
        return None

    for profile in UserProfile.objects.select_related("user").exclude(phone__isnull=True).exclude(phone=""):
        if normalize_phone(profile.phone) == phone and profile.user.is_active:
            return profile
    return None


def lookup_known_customer(identifiers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Look up a known contact by stable identifiers available at channel intake.

    Expected identifiers by channel:
    - API/voice: telefon
    - Telegram: id_tg
    - MAX: id_max
    - WebChat: id_in_system
    """
    phone = normalize_phone(identifiers.get("telefon") or identifiers.get("phone"))
    internal_id = str(identifiers.get("id_in_system") or "").strip()
    telegram = str(
        identifiers.get("id_tg")
        or identifiers.get("telegram")
        or identifiers.get("telegram_username")
        or ""
    ).strip().lstrip("@")
    max_id = str(
        identifiers.get("id_max")
        or identifiers.get("max")
        or identifiers.get("max_username")
        or ""
    ).strip().lstrip("@")

    # Temporary hardcoded Vladimir identity stub is disabled.
    # A real implementation must look up verified contacts in the database.
    # if phone == "79202119023" or telegram.lower() == "v_v_ch19xx":
    #     return {
    #         "name": "<disabled hardcoded display name>",
    #         "contacts": {
    #             "id_in_system": internal_id,
    #             "id_tg": "v_v_ch19xx",
    #             "id_max": max_id,
    #             "telefon": "+79202119023",
    #         },
    #         "matched_by": "telefon" if phone == "79202119023" else "id_tg",
    #         "addresses": [],
    #     }

    try:
        from portal.models import UserProfile
    except Exception:
        UserProfile = None

    if UserProfile is not None:
        if internal_id.isdigit():
            profile = (
                UserProfile.objects.select_related("user")
                .filter(user_id=int(internal_id), user__is_active=True)
                .first()
            )
            if profile:
                return _profile_lookup_payload(profile, "id_in_system")

        if max_id.isdigit():
            profile = (
                UserProfile.objects.select_related("user")
                .filter(max_user_id=int(max_id), user__is_active=True)
                .first()
            )
            if profile:
                return _profile_lookup_payload(profile, "id_max")

    profile = _find_profile_by_phone(phone)
    if profile:
        return _profile_lookup_payload(profile, "telefon")

    return {
        "name": "",
        "contacts": {},
        "matched_by": "",
        "addresses": [],
        "lookup_input": {
            "id_in_system": internal_id,
            "id_tg": telegram,
            "id_max": max_id,
            "telefon": f"+{phone}" if phone else "",
        },
    }
