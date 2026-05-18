from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('message_handler', '0004_fias_request_log_and_bot_order_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='VoiceCallSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('schema_version', models.CharField(default='asterisk_voice_v2.1', max_length=32)),
                ('source', models.CharField(default='asterisk', max_length=50)),
                ('channel', models.CharField(default='voice', max_length=50)),
                ('user_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('direction', models.CharField(blank=True, max_length=20, null=True)),
                ('client_phone', models.CharField(blank=True, max_length=40)),
                ('company_phone', models.CharField(blank=True, max_length=40)),
                ('asterisk_channel_id', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('active', 'Active'), ('ended', 'Ended')], db_index=True, default='active', max_length=20)),
                ('end_reason', models.CharField(blank=True, max_length=40)),
                ('call_payload', models.JSONField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Voice call session',
                'verbose_name_plural': 'Voice call sessions',
                'db_table': 'message_handler_voice_call_sessions',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='VoiceTurnRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_id', models.CharField(db_index=True, max_length=255)),
                ('turn_id', models.CharField(db_index=True, max_length=255)),
                ('latest_revision', models.PositiveIntegerField(default=0)),
                ('obsolete_revisions', models.JSONField(blank=True, default=list)),
                ('supersedes_revision', models.PositiveIntegerField(blank=True, null=True)),
                ('schema_version', models.CharField(default='asterisk_voice_v2.1', max_length=32)),
                ('user_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('message_preview', models.CharField(blank=True, max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Voice turn revision',
                'verbose_name_plural': 'Voice turn revisions',
                'db_table': 'message_handler_voice_turn_revisions',
                'ordering': ['-updated_at'],
                'unique_together': {('session_id', 'turn_id')},
            },
        ),
        migrations.AddIndex(
            model_name='voicecallsession',
            index=models.Index(fields=['session_id', 'status'], name='message_han_session_39e510_idx'),
        ),
        migrations.AddIndex(
            model_name='voicecallsession',
            index=models.Index(fields=['client_phone', 'updated_at'], name='message_han_client__544abd_idx'),
        ),
        migrations.AddIndex(
            model_name='voicecallsession',
            index=models.Index(fields=['asterisk_channel_id'], name='message_han_asteri_5163d7_idx'),
        ),
        migrations.AddIndex(
            model_name='voiceturnrevision',
            index=models.Index(fields=['session_id', 'turn_id'], name='message_han_session_88aceb_idx'),
        ),
        migrations.AddIndex(
            model_name='voiceturnrevision',
            index=models.Index(fields=['session_id', 'updated_at'], name='message_han_session_d9f34e_idx'),
        ),
        migrations.AddIndex(
            model_name='voiceturnrevision',
            index=models.Index(fields=['user_id', 'updated_at'], name='message_han_user_id_b05df2_idx'),
        ),
    ]
