from typing import Any, Dict, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from message_handler.models import VoiceCallSession, VoiceTurnRevision


VOICE_SCHEMA_V21 = 'asterisk_voice_v2.1'


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _as_positive_int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _call_defaults(
    *,
    session_id: str,
    user_id: Optional[str],
    call: Optional[Dict[str, Any]],
    schema_version: str = VOICE_SCHEMA_V21,
    status: str = 'active',
) -> Dict[str, Any]:
    call = call if isinstance(call, dict) else {}
    return {
        'schema_version': schema_version,
        'source': 'asterisk',
        'channel': 'voice',
        'user_id': _clean(user_id) or None,
        'direction': _clean(call.get('direction')) or None,
        'client_phone': _clean(call.get('client_phone')),
        'company_phone': _clean(call.get('company_phone')),
        'asterisk_channel_id': _clean(call.get('asterisk_channel_id')),
        'status': status,
        'call_payload': call,
    }


def touch_voice_call_session(
    *,
    session_id: str,
    user_id: Optional[str],
    call: Optional[Dict[str, Any]],
    schema_version: str = VOICE_SCHEMA_V21,
) -> VoiceCallSession:
    defaults = _call_defaults(
        session_id=session_id,
        user_id=user_id,
        call=call,
        schema_version=schema_version,
        status='active',
    )
    with transaction.atomic():
        session = VoiceCallSession.objects.select_for_update().filter(session_id=session_id).first()
        if not session:
            session = VoiceCallSession.objects.create(session_id=session_id, **defaults)
            return session

        for field, value in defaults.items():
            if field == 'status' and session.status == 'ended':
                continue
            setattr(session, field, value)
        session.save(
            update_fields=[
                'schema_version',
                'source',
                'channel',
                'user_id',
                'direction',
                'client_phone',
                'company_phone',
                'asterisk_channel_id',
                'status',
                'call_payload',
                'updated_at',
            ]
        )
    return session


def register_voice_turn_revision(
    *,
    session_id: str,
    turn_id: str,
    revision: int,
    supersedes_revision: Optional[int] = None,
    user_id: Optional[str] = None,
    message: str = '',
    call: Optional[Dict[str, Any]] = None,
    schema_version: str = VOICE_SCHEMA_V21,
) -> Dict[str, Any]:
    revision = _as_positive_int(revision)
    supersedes_revision = _as_positive_int(supersedes_revision)
    session_id = _clean(session_id)
    turn_id = _clean(turn_id)
    if not session_id or not turn_id or revision is None:
        return {
            'is_current': False,
            'latest_revision': None,
            'accepted': False,
            'error': 'invalid_revision_guard_input',
        }

    with transaction.atomic():
        call_session = touch_voice_call_session(
            session_id=session_id,
            user_id=user_id,
            call=call,
            schema_version=schema_version,
        )
        if call_session.status == 'ended':
            return {
                'is_current': False,
                'latest_revision': None,
                'accepted': False,
                'superseded': False,
                'session_ended': True,
            }
        try:
            turn_state = VoiceTurnRevision.objects.select_for_update().get(
                session_id=session_id,
                turn_id=turn_id,
            )
        except VoiceTurnRevision.DoesNotExist:
            try:
                turn_state = VoiceTurnRevision.objects.create(
                    session_id=session_id,
                    turn_id=turn_id,
                    latest_revision=0,
                    obsolete_revisions=[],
                    schema_version=schema_version,
                    user_id=_clean(user_id) or None,
                )
            except IntegrityError:
                turn_state = VoiceTurnRevision.objects.select_for_update().get(
                    session_id=session_id,
                    turn_id=turn_id,
                )

        latest_before = int(turn_state.latest_revision or 0)
        obsolete = set(int(item) for item in (turn_state.obsolete_revisions or []) if str(item).isdigit())

        if revision > latest_before:
            if revision <= 200:
                obsolete.update(range(1, revision))
            elif latest_before:
                obsolete.add(latest_before)
            if supersedes_revision:
                obsolete.add(supersedes_revision)
            obsolete.discard(revision)

            turn_state.latest_revision = revision
            turn_state.obsolete_revisions = sorted(obsolete)
            turn_state.supersedes_revision = supersedes_revision
            turn_state.schema_version = schema_version
            turn_state.user_id = _clean(user_id) or turn_state.user_id
            turn_state.message_preview = _clean(message)[:300]
            turn_state.save(
                update_fields=[
                    'latest_revision',
                    'obsolete_revisions',
                    'supersedes_revision',
                    'schema_version',
                    'user_id',
                    'message_preview',
                    'updated_at',
                ]
            )
            return {
                'is_current': True,
                'latest_revision': revision,
                'accepted': True,
                'superseded': False,
                'obsolete_revisions': sorted(obsolete),
            }

        if revision < latest_before:
            obsolete.add(revision)
            turn_state.obsolete_revisions = sorted(obsolete)
            turn_state.save(update_fields=['obsolete_revisions', 'updated_at'])
            return {
                'is_current': False,
                'latest_revision': latest_before,
                'accepted': False,
                'superseded': True,
                'obsolete_revisions': sorted(obsolete),
            }

        return {
            'is_current': True,
            'latest_revision': latest_before,
            'accepted': True,
            'superseded': False,
            'obsolete_revisions': sorted(obsolete),
        }


def is_current_voice_turn(*, session_id: str, turn_id: str, revision: int) -> bool:
    revision = _as_positive_int(revision)
    if not _clean(session_id) or not _clean(turn_id) or revision is None:
        return True
    turn_state = VoiceTurnRevision.objects.filter(
        session_id=_clean(session_id),
        turn_id=_clean(turn_id),
    ).only('latest_revision').first()
    if not turn_state:
        return True
    return int(turn_state.latest_revision or 0) == revision


def mark_voice_call_ended(
    *,
    session_id: str,
    user_id: Optional[str],
    reason: str,
    call: Optional[Dict[str, Any]],
    schema_version: str = VOICE_SCHEMA_V21,
) -> Dict[str, Any]:
    reason = _clean(reason) or 'unknown'
    defaults = _call_defaults(
        session_id=session_id,
        user_id=user_id,
        call=call,
        schema_version=schema_version,
        status='ended',
    )
    defaults.update(
        {
            'end_reason': reason,
            'ended_at': timezone.now(),
        }
    )
    session, _ = VoiceCallSession.objects.update_or_create(
        session_id=_clean(session_id),
        defaults=defaults,
    )
    return {
        'session_id': session.session_id,
        'status': session.status,
        'end_reason': session.end_reason,
        'ended_at': session.ended_at.isoformat() if session.ended_at else None,
    }
