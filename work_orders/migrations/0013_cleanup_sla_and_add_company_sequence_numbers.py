from django.db import migrations, models
import django.core.validators
from django.db.models import Q


WORK_ORDER_SQL = """
ALTER TABLE request_mgmt.work_order
    ADD COLUMN company_sequence_no integer;

WITH numbered AS (
    SELECT
        id,
        company_id,
        ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY created_at, id) AS seq
    FROM request_mgmt.work_order
)
UPDATE request_mgmt.work_order AS work_order
SET
    company_sequence_no = numbered.seq,
    work_order_no = numbered.company_id::text || '-' || numbered.seq::text
FROM numbered
WHERE work_order.id = numbered.id;

ALTER TABLE request_mgmt.work_order
    ALTER COLUMN company_sequence_no SET NOT NULL;

ALTER TABLE request_mgmt.work_order
    ADD CONSTRAINT uq_work_order_company_sequence_no UNIQUE (company_id, company_sequence_no);
"""

SLA_POLICY_DATA_SQL = """
UPDATE request_mgmt.sla_policy
SET localization_minutes = COALESCE(localization_minutes, resolution_minutes);

WITH ranked AS (
    SELECT
        id,
        FIRST_VALUE(id) OVER (
            PARTITION BY company_id, service_id, priority_code
            ORDER BY id
        ) AS keep_id,
        ROW_NUMBER() OVER (
            PARTITION BY company_id, service_id, priority_code
            ORDER BY id
        ) AS row_no
    FROM request_mgmt.sla_policy
),
repoint AS (
    UPDATE request_mgmt.sla_instance AS sla_instance
    SET sla_policy_id = ranked.keep_id
    FROM ranked
    WHERE sla_instance.sla_policy_id = ranked.id
      AND ranked.row_no > 1
    RETURNING sla_instance.id
)
DELETE FROM request_mgmt.sla_policy AS sla_policy
USING ranked
WHERE sla_policy.id = ranked.id
  AND ranked.row_no > 1;
"""

SLA_POLICY_SCHEMA_SQL = """
ALTER TABLE request_mgmt.sla_policy
    DROP CONSTRAINT uq_sla_policy_company_service_priority_emergency;

ALTER TABLE request_mgmt.sla_policy
    RENAME COLUMN work_start_minutes TO reaction_minutes;

ALTER TABLE request_mgmt.sla_policy
    RENAME COLUMN resolution_minutes TO completion_minutes;

ALTER TABLE request_mgmt.sla_policy
    ALTER COLUMN localization_minutes SET NOT NULL,
    ALTER COLUMN calendar_type SET DEFAULT '24x7',
    ALTER COLUMN policy_source SET DEFAULT 'company';

ALTER TABLE request_mgmt.sla_policy
    DROP COLUMN is_emergency,
    DROP COLUMN executor_assignment_minutes,
    DROP COLUMN resident_contact_minutes,
    DROP COLUMN auto_close_after_days;

ALTER TABLE request_mgmt.sla_policy
    ADD CONSTRAINT uq_sla_policy_company_service_priority UNIQUE (company_id, service_id, priority_code);
"""

SLA_INSTANCE_SCHEMA_SQL = """
DROP INDEX request_mgmt.idx_sla_inst_assign_wait;
DROP INDEX request_mgmt.idx_sla_inst_start_wait;
DROP INDEX request_mgmt.idx_sla_inst_contact_wait;
DROP INDEX request_mgmt.idx_sla_inst_resol_wait;
DROP INDEX request_mgmt.idx_sla_inst_close_wait;

ALTER TABLE request_mgmt.sla_instance
    RENAME COLUMN work_start_due_at TO reaction_due_at;

ALTER TABLE request_mgmt.sla_instance
    RENAME COLUMN work_start_stopped_at TO reaction_stopped_at;

ALTER TABLE request_mgmt.sla_instance
    RENAME COLUMN work_start_state TO reaction_state;

ALTER TABLE request_mgmt.sla_instance
    RENAME COLUMN resolution_due_at TO completion_due_at;

ALTER TABLE request_mgmt.sla_instance
    RENAME COLUMN resolution_stopped_at TO completion_stopped_at;

ALTER TABLE request_mgmt.sla_instance
    RENAME COLUMN resolution_state TO completion_state;

ALTER TABLE request_mgmt.sla_instance
    DROP COLUMN executor_assignment_due_at,
    DROP COLUMN executor_assignment_stopped_at,
    DROP COLUMN executor_assignment_state,
    DROP COLUMN resident_contact_due_at,
    DROP COLUMN resident_contact_stopped_at,
    DROP COLUMN resident_contact_state,
    DROP COLUMN auto_close_due_at,
    DROP COLUMN auto_close_stopped_at,
    DROP COLUMN auto_close_state;

CREATE INDEX idx_sla_inst_reaction_wait
    ON request_mgmt.sla_instance (reaction_due_at)
    WHERE reaction_state = 'waiting';

CREATE INDEX idx_sla_inst_completion_wait
    ON request_mgmt.sla_instance (completion_due_at)
    WHERE completion_state = 'waiting';
"""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('work_orders', '0012_refactor_ads_status_flow_and_drop_legacy_executor'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=WORK_ORDER_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=SLA_POLICY_DATA_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=SLA_POLICY_SCHEMA_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=SLA_INSTANCE_SCHEMA_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AlterModelTable(name='routeref', table='route_ref'),
                migrations.AlterModelTable(name='companydepartment', table='company_department'),
                migrations.AlterModelTable(name='contractororganization', table='contractor_organization'),
                migrations.AlterModelTable(name='companyroutemapping', table='company_route_mapping'),
                migrations.AlterModelTable(name='usercompanymembership', table='user_company_membership'),
                migrations.AlterModelTable(name='workorderstatusref', table='work_order_status_ref'),
                migrations.AlterModelTable(name='workorderstatustransition', table='work_order_status_transition'),
                migrations.AlterModelTable(name='slapolicy', table='sla_policy'),
                migrations.AlterModelTable(name='companyobjectserviceperiod', table='company_object_service_period'),
                migrations.AlterModelTable(name='requestintake', table='request_intake'),
                migrations.AlterModelTable(name='workorder', table='work_order'),
                migrations.AlterModelTable(name='workorderstatushistory', table='work_order_status_history'),
                migrations.AlterModelTable(name='slainstance', table='sla_instance'),
                migrations.AlterModelTable(name='workordereventlog', table='work_order_event_log'),
                migrations.AlterModelTable(name='workorderattachment', table='work_order_attachment'),
                migrations.AlterModelTable(name='notificationoutbox', table='notification_outbox'),
                migrations.AddField(
                    model_name='workorder',
                    name='company_sequence_no',
                    field=models.PositiveIntegerField(
                        editable=False,
                        verbose_name='Порядковый номер внутри компании',
                    ),
                ),
                migrations.AddConstraint(
                    model_name='workorder',
                    constraint=models.UniqueConstraint(
                        fields=('company', 'company_sequence_no'),
                        name='uq_work_order_company_sequence_no',
                    ),
                ),
                migrations.RemoveConstraint(
                    model_name='slapolicy',
                    name='uq_sla_policy_company_service_priority_emergency',
                ),
                migrations.RenameField(
                    model_name='slapolicy',
                    old_name='work_start_minutes',
                    new_name='reaction_minutes',
                ),
                migrations.RenameField(
                    model_name='slapolicy',
                    old_name='resolution_minutes',
                    new_name='completion_minutes',
                ),
                migrations.AlterField(
                    model_name='slapolicy',
                    name='calendar_type',
                    field=models.CharField(
                        choices=[('24x7', '24/7'), ('company_working_hours', 'Рабочие часы компании')],
                        default='24x7',
                        max_length=25,
                        verbose_name='Тип календаря',
                    ),
                ),
                migrations.AlterField(
                    model_name='slapolicy',
                    name='reaction_minutes',
                    field=models.IntegerField(
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name='SLA реакции (мин)',
                    ),
                ),
                migrations.AlterField(
                    model_name='slapolicy',
                    name='localization_minutes',
                    field=models.IntegerField(
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name='SLA локализации (мин)',
                    ),
                ),
                migrations.AlterField(
                    model_name='slapolicy',
                    name='completion_minutes',
                    field=models.IntegerField(
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name='SLA выполнения (мин)',
                    ),
                ),
                migrations.AlterField(
                    model_name='slapolicy',
                    name='policy_source',
                    field=models.CharField(
                        choices=[('normative', 'Нормативный'), ('company', 'Внутренний компании'), ('mixed', 'Смешанный')],
                        default='company',
                        max_length=20,
                        verbose_name='Источник политики',
                    ),
                ),
                migrations.RemoveField(
                    model_name='slapolicy',
                    name='is_emergency',
                ),
                migrations.RemoveField(
                    model_name='slapolicy',
                    name='executor_assignment_minutes',
                ),
                migrations.RemoveField(
                    model_name='slapolicy',
                    name='resident_contact_minutes',
                ),
                migrations.RemoveField(
                    model_name='slapolicy',
                    name='auto_close_after_days',
                ),
                migrations.AddConstraint(
                    model_name='slapolicy',
                    constraint=models.UniqueConstraint(
                        fields=('company', 'service', 'priority_code'),
                        name='uq_sla_policy_company_service_priority',
                    ),
                ),
                migrations.RemoveIndex(
                    model_name='slainstance',
                    name='idx_sla_inst_assign_wait',
                ),
                migrations.RemoveIndex(
                    model_name='slainstance',
                    name='idx_sla_inst_start_wait',
                ),
                migrations.RemoveIndex(
                    model_name='slainstance',
                    name='idx_sla_inst_contact_wait',
                ),
                migrations.RemoveIndex(
                    model_name='slainstance',
                    name='idx_sla_inst_resol_wait',
                ),
                migrations.RemoveIndex(
                    model_name='slainstance',
                    name='idx_sla_inst_close_wait',
                ),
                migrations.RenameField(
                    model_name='slainstance',
                    old_name='work_start_due_at',
                    new_name='reaction_due_at',
                ),
                migrations.RenameField(
                    model_name='slainstance',
                    old_name='work_start_stopped_at',
                    new_name='reaction_stopped_at',
                ),
                migrations.RenameField(
                    model_name='slainstance',
                    old_name='work_start_state',
                    new_name='reaction_state',
                ),
                migrations.RenameField(
                    model_name='slainstance',
                    old_name='resolution_due_at',
                    new_name='completion_due_at',
                ),
                migrations.RenameField(
                    model_name='slainstance',
                    old_name='resolution_stopped_at',
                    new_name='completion_stopped_at',
                ),
                migrations.RenameField(
                    model_name='slainstance',
                    old_name='resolution_state',
                    new_name='completion_state',
                ),
                migrations.AlterField(
                    model_name='slainstance',
                    name='reaction_due_at',
                    field=models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name='Дедлайн SLA реакции',
                    ),
                ),
                migrations.AlterField(
                    model_name='slainstance',
                    name='completion_due_at',
                    field=models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name='Дедлайн SLA выполнения',
                    ),
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='executor_assignment_due_at',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='executor_assignment_stopped_at',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='executor_assignment_state',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='resident_contact_due_at',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='resident_contact_stopped_at',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='resident_contact_state',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='auto_close_due_at',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='auto_close_stopped_at',
                ),
                migrations.RemoveField(
                    model_name='slainstance',
                    name='auto_close_state',
                ),
                migrations.AddIndex(
                    model_name='slainstance',
                    index=models.Index(
                        fields=['reaction_due_at'],
                        name='idx_sla_inst_reaction_wait',
                        condition=Q(reaction_state='waiting'),
                    ),
                ),
                migrations.AddIndex(
                    model_name='slainstance',
                    index=models.Index(
                        fields=['completion_due_at'],
                        name='idx_sla_inst_completion_wait',
                        condition=Q(completion_state='waiting'),
                    ),
                ),
            ],
        ),
    ]
