from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import (
    SLAInstance,
    SLAPolicy,
    UserCompanyMembership,
    WorkOrderAttachment,
    WorkOrderEventLog,
    WorkOrderStatusHistory,
    WorkOrderStatusRef,
)


MANAGER_ROLE_CODES = {'chief_engineer', 'direktor_uk', 'django_admin'}
EXECUTOR_ROLE_CODES = {'executor', 'contractor'}
CLOSE_ROLE_CODES = MANAGER_ROLE_CODES

ACTION_DEFINITIONS = {
    'assign': {
        'label': 'Установить ответственного',
        'from_statuses': {'new_registered'},
        'target_status': 'accepted_by_executor',
        'allowed_roles': EXECUTOR_ROLE_CODES | MANAGER_ROLE_CODES,
        'requires_responsible_user': True,
    },
    'start': {
        'label': 'Взять в работу',
        'from_statuses': {'accepted_by_executor'},
        'target_status': 'in_progress',
        'allowed_roles': EXECUTOR_ROLE_CODES,
    },
    'localize': {
        'label': 'Локализовать',
        'from_statuses': {'in_progress'},
        'target_status': 'localized',
        'allowed_roles': EXECUTOR_ROLE_CODES,
        'requires_resolution_text': True,
        'confirm_without_photo': True,
    },
    'complete': {
        'label': 'Выполнить',
        'from_statuses': {'localized'},
        'target_status': 'completed',
        'allowed_roles': EXECUTOR_ROLE_CODES | MANAGER_ROLE_CODES,
        'requires_resolution_text': True,
        'confirm_without_photo': True,
    },
    'close': {
        'label': 'Закрыть',
        'from_statuses': {'completed'},
        'target_status': 'closed',
        'allowed_roles': CLOSE_ROLE_CODES,
    },
}


class WorkflowError(Exception):
    def __init__(self, message, code='workflow_error'):
        super().__init__(message)
        self.message = message
        self.code = code


def get_user_role_codes(user, company_id=None):
    if not getattr(user, 'is_authenticated', False):
        return set()
    if user.is_superuser:
        return {'django_admin', 'superuser'}

    queryset = UserCompanyMembership.objects.filter(
        user=user,
        is_active=True,
        date_to__isnull=True,
    )
    if company_id:
        queryset = queryset.filter(company_id=company_id)
    return set(queryset.values_list('role_code', flat=True))


def get_assignment_candidates(work_order):
    memberships = (
        UserCompanyMembership.objects
        .filter(
            company=work_order.company,
            is_active=True,
            date_to__isnull=True,
            role_code__in=sorted(EXECUTOR_ROLE_CODES),
        )
        .select_related('user', 'department')
        .order_by('user__last_name', 'user__first_name', 'user__username')
    )

    candidates = []
    seen_user_ids = set()
    for membership in memberships:
        if membership.user_id in seen_user_ids:
            continue
        seen_user_ids.add(membership.user_id)
        label = membership.user.get_full_name() or membership.user.username
        if membership.department:
            label = f'{label} ({membership.department.department_name})'
        candidates.append(
            {
                'id': membership.user_id,
                'label': label,
                'department_id': membership.department_id,
            }
        )
    return candidates


def can_upload_result_photo(user, work_order):
    role_codes = get_user_role_codes(user, work_order.company_id)
    return (
        user.is_superuser
        or work_order.responsible_user_id == user.id
        or bool(role_codes & MANAGER_ROLE_CODES)
    )


def get_result_photo_attachments(work_order):
    return list(
        work_order.attachments.filter(attachment_kind='result_photo').order_by('-uploaded_at')
    )


def get_result_photo_count(work_order):
    return work_order.attachments.filter(attachment_kind='result_photo').count()


def get_active_action(user, work_order):
    status_code = work_order.current_internal_status.short_code_en
    role_codes = get_user_role_codes(user, work_order.company_id)
    is_responsible = work_order.responsible_user_id == user.id

    if status_code == 'new_registered':
        if user.is_superuser or role_codes & (EXECUTOR_ROLE_CODES | MANAGER_ROLE_CODES):
            return ACTION_DEFINITIONS['assign']
        return None

    if status_code == 'accepted_by_executor' and is_responsible:
        return ACTION_DEFINITIONS['start']

    if status_code == 'in_progress' and is_responsible:
        return ACTION_DEFINITIONS['localize']

    if status_code == 'localized' and (is_responsible or user.is_superuser or role_codes & MANAGER_ROLE_CODES):
        return ACTION_DEFINITIONS['complete']

    return None


def can_close_work_order(user, work_order):
    if work_order.current_internal_status.short_code_en != 'completed':
        return False
    role_codes = get_user_role_codes(user, work_order.company_id)
    return user.is_superuser or bool(role_codes & CLOSE_ROLE_CODES)


def resolve_sla_policy(work_order):
    return (
        SLAPolicy.objects.filter(
            company=work_order.company,
            service=work_order.service,
            is_active=True,
        )
        .order_by('id')
        .first()
    )


def _get_due_at(started_at, minutes):
    if minutes is None:
        return None
    return started_at + timedelta(minutes=int(minutes))


def _first_status_changed_at(work_order, status_code):
    entry = (
        work_order.status_history
        .filter(status__short_code_en=status_code)
        .order_by('changed_at')
        .first()
    )
    return entry.changed_at if entry else None


def _stop_timer(instance, due_attr, stop_attr, state_attr, stopped_at):
    if not stopped_at:
        return
    due_at = getattr(instance, due_attr)
    setattr(instance, stop_attr, stopped_at)
    if due_at and stopped_at > due_at:
        setattr(instance, state_attr, 'overdue')
    else:
        setattr(instance, state_attr, 'met')


def synchronize_sla_instance(work_order, instance=None, save=True):
    instance = instance or getattr(work_order, 'sla_instance', None)
    if instance is None:
        return None

    now = timezone.now()
    in_progress_at = _first_status_changed_at(work_order, 'in_progress')
    localized_at = _first_status_changed_at(work_order, 'localized')
    completed_at = _first_status_changed_at(work_order, 'completed')

    if in_progress_at:
        _stop_timer(instance, 'reaction_due_at', 'reaction_stopped_at', 'reaction_state', in_progress_at)
    elif instance.reaction_due_at:
        instance.reaction_state = 'overdue' if now > instance.reaction_due_at else 'waiting'

    localization_stop_at = localized_at or completed_at
    if localization_stop_at:
        _stop_timer(
            instance,
            'localization_due_at',
            'localization_stopped_at',
            'localization_state',
            localization_stop_at,
        )
    elif instance.localization_due_at:
        instance.localization_state = 'overdue' if now > instance.localization_due_at else 'waiting'

    if completed_at:
        _stop_timer(instance, 'completion_due_at', 'completion_stopped_at', 'completion_state', completed_at)
    elif instance.completion_due_at:
        instance.completion_state = 'overdue' if now > instance.completion_due_at else 'waiting'

    if save:
        instance.save(
            update_fields=[
                'reaction_stopped_at',
                'reaction_state',
                'localization_stopped_at',
                'localization_state',
                'completion_stopped_at',
                'completion_state',
                'updated_at',
            ]
        )
    return instance


def ensure_sla_instance(work_order):
    existing = getattr(work_order, 'sla_instance', None)
    if existing:
        return synchronize_sla_instance(work_order, existing)

    policy = resolve_sla_policy(work_order)
    if policy is None:
        return None

    instance = SLAInstance.objects.create(
        work_order=work_order,
        company=work_order.company,
        sla_policy=policy,
        calendar_type=policy.calendar_type,
        reaction_due_at=_get_due_at(work_order.created_at, policy.reaction_minutes),
        reaction_state='waiting',
        localization_due_at=_get_due_at(work_order.created_at, policy.localization_minutes),
        localization_state='waiting',
        completion_due_at=_get_due_at(work_order.created_at, policy.completion_minutes),
        completion_state='waiting',
        is_test=work_order.is_test,
    )
    return synchronize_sla_instance(work_order, instance)


def build_sla_rows(work_order):
    instance = ensure_sla_instance(work_order)
    if instance is None:
        return [
            {
                'label': 'SLA реакции',
                'state': 'missing',
                'text': 'Политика SLA не назначена',
            },
            {
                'label': 'SLA локализации',
                'state': 'missing',
                'text': 'Политика SLA не назначена',
            },
            {
                'label': 'SLA выполнения',
                'state': 'missing',
                'text': 'Политика SLA не назначена',
            },
        ]

    return [
        {
            'label': 'SLA реакции',
            'state': instance.reaction_state,
            'due_at': instance.reaction_due_at.isoformat() if instance.reaction_due_at else '',
            'stopped_at': instance.reaction_stopped_at.isoformat() if instance.reaction_stopped_at else '',
        },
        {
            'label': 'SLA локализации',
            'state': instance.localization_state,
            'due_at': instance.localization_due_at.isoformat() if instance.localization_due_at else '',
            'stopped_at': instance.localization_stopped_at.isoformat() if instance.localization_stopped_at else '',
        },
        {
            'label': 'SLA выполнения',
            'state': instance.completion_state,
            'due_at': instance.completion_due_at.isoformat() if instance.completion_due_at else '',
            'stopped_at': instance.completion_stopped_at.isoformat() if instance.completion_stopped_at else '',
        },
    ]


def _build_event_payload(action, user, work_order, old_status, new_status, old_responsible_user, target_user):
    actor_name = user.get_full_name() or user.username
    target_name = ''
    if target_user:
        target_name = target_user.get_full_name() or target_user.username

    if action == 'assign':
        text = f'Назначен ответственный: {target_name}. Действие выполнил {actor_name}.'
        event_type_code = 'assigned'
    elif action == 'start':
        text = f'Заявка переведена в статус "В работе". Исполнитель: {actor_name}.'
        event_type_code = 'status_changed'
    elif action == 'localize':
        text = f'Заявка локализована. Исполнитель: {actor_name}.'
        event_type_code = 'localized'
    elif action == 'complete':
        text = f'Заявка выполнена. Исполнитель: {actor_name}.'
        event_type_code = 'completed'
    else:
        text = f'Заявка закрыта. Действие выполнил {actor_name}.'
        event_type_code = 'closed'

    return {
        'work_order': work_order,
        'company': work_order.company,
        'department': work_order.department,
        'event_type_code': event_type_code,
        'event_datetime': timezone.now(),
        'author_user': user,
        'text_value': text,
        'old_status': old_status,
        'new_status': new_status,
        'old_responsible_user': old_responsible_user,
        'new_responsible_user': target_user if action == 'assign' else work_order.responsible_user,
        'is_visible_to_resident': action in {'start', 'localize', 'complete', 'close'},
        'is_test': work_order.is_test,
    }


def _validate_assignee(user, work_order, responsible_user_id):
    role_codes = get_user_role_codes(user, work_order.company_id)
    target_user = None

    if user.is_superuser or role_codes & MANAGER_ROLE_CODES:
        if not responsible_user_id:
            raise WorkflowError('Выберите ответственного исполнителя.', code='responsible_user_required')
        target_user = User.objects.filter(pk=responsible_user_id, is_active=True).first()
        if target_user is None:
            raise WorkflowError('Исполнитель не найден.', code='responsible_user_missing')
        has_membership = UserCompanyMembership.objects.filter(
            user=target_user,
            company=work_order.company,
            is_active=True,
            date_to__isnull=True,
            role_code__in=sorted(EXECUTOR_ROLE_CODES),
        ).exists()
        if not has_membership:
            raise WorkflowError('Выбранный пользователь не привязан к компании как исполнитель/подрядчик.', code='responsible_user_invalid')
        return target_user

    if role_codes & EXECUTOR_ROLE_CODES:
        has_self_membership = UserCompanyMembership.objects.filter(
            user=user,
            company=work_order.company,
            is_active=True,
            date_to__isnull=True,
            role_code__in=sorted(EXECUTOR_ROLE_CODES),
        ).exists()
        if not has_self_membership:
            raise WorkflowError('У вас нет прав на принятие этой заявки.', code='assign_forbidden')
        return user

    raise WorkflowError('У вас нет прав на назначение ответственного.', code='assign_forbidden')


@transaction.atomic
def apply_action(work_order, user, action, resolution_text='', responsible_user_id=None, force_without_photo=False):
    definition = ACTION_DEFINITIONS.get(action)
    if definition is None:
        raise WorkflowError('Неизвестное действие.', code='unknown_action')

    current_status_code = work_order.current_internal_status.short_code_en
    if current_status_code not in definition['from_statuses']:
        raise WorkflowError('Переход из текущего статуса недоступен.', code='invalid_status_transition')

    role_codes = get_user_role_codes(user, work_order.company_id)
    if not user.is_superuser and not (role_codes & definition['allowed_roles']):
        raise WorkflowError('У вас нет прав на это действие.', code='forbidden')

    resolution_text = (resolution_text or '').strip()
    if definition.get('requires_resolution_text') and not resolution_text:
        raise WorkflowError('Заполните решение по заявке.', code='resolution_required')

    if definition.get('confirm_without_photo') and not get_result_photo_count(work_order) and not force_without_photo:
        raise WorkflowError(
            'ФОТО НЕ ПРИВЯЗАНЫ. Вы точно хотите изменить статус заявки?',
            code='photo_confirmation_required',
        )

    old_responsible_user = work_order.responsible_user
    target_user = work_order.responsible_user
    if action == 'assign':
        target_user = _validate_assignee(user, work_order, responsible_user_id)
        work_order.responsible_user = target_user

    if action in {'localize', 'complete'}:
        work_order.resolution_text = resolution_text

    new_status = WorkOrderStatusRef.objects.get(short_code_en=definition['target_status'])
    old_status = work_order.current_internal_status
    work_order.current_internal_status = new_status
    work_order.save()

    WorkOrderStatusHistory.objects.create(
        work_order=work_order,
        status=new_status,
        changed_by=user,
        is_test=work_order.is_test,
    )

    WorkOrderEventLog.objects.create(
        **_build_event_payload(action, user, work_order, old_status, new_status, old_responsible_user, target_user)
    )

    ensure_sla_instance(work_order)
    return work_order


def create_result_photo_attachment(work_order, uploaded_file, user):
    attachment = WorkOrderAttachment.objects.create(
        work_order=work_order,
        uploaded_by_user=user,
        attachment_kind='result_photo',
        mime_type=uploaded_file.content_type or 'application/octet-stream',
        file_name=uploaded_file.name,
        file_size=uploaded_file.size,
        file_data=uploaded_file.read(),
        is_visible_to_resident=False,
        is_test=work_order.is_test,
    )

    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code='result_photo_uploaded',
        event_datetime=timezone.now(),
        author_user=user,
        text_value=f'К заявке добавлено фото результата: {attachment.file_name}',
        is_visible_to_resident=False,
        is_test=work_order.is_test,
    )
    return attachment
