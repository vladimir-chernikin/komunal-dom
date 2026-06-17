# -*- coding: utf-8 -*-
from django.db import migrations, models


MAX_OWNER_USER_ID = 1
MAX_OWNER_MAX_USER_ID = 209166551


def set_initial_max_user_id(apps, schema_editor):
    UserProfile = apps.get_model("portal", "UserProfile")

    UserProfile.objects.filter(max_user_id=MAX_OWNER_MAX_USER_ID).exclude(
        user_id=MAX_OWNER_USER_ID
    ).update(max_user_id=None)

    profile, _ = UserProfile.objects.get_or_create(
        user_id=MAX_OWNER_USER_ID,
        defaults={"role": "django_admin"},
    )
    profile.max_user_id = MAX_OWNER_MAX_USER_ID
    profile.save(update_fields=["max_user_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0027_drop_service_object_house_fias"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="max_user_id",
            field=models.BigIntegerField(
                blank=True,
                help_text="Числовой ID пользователя из initData.user.id мини-приложения MAX.",
                null=True,
                unique=True,
                verbose_name="MAX user ID",
            ),
        ),
        migrations.RunPython(set_initial_max_user_id, migrations.RunPython.noop),
    ]
