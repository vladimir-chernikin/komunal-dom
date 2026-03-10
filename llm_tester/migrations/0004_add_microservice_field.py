# Generated manually 2026-02-24
# Добавление поля microservice для связки промптов с микросервисами

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('llm_tester', '0003_alter_promptpreset_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='prompttemplate',
            name='microservice',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name='Микросервис',
                help_text='Имя микросервиса для связки с логами (FilterDetectionService, MainAgent, ProblemAccumulationService и т.д.)'
            ),
        ),
    ]
