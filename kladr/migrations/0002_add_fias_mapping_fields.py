from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kladr', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='building',
            name='fias_address_type',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Вид адреса ФИАС'),
        ),
        migrations.AddField(
            model_name='building',
            name='fias_full_name',
            field=models.CharField(blank=True, max_length=500, null=True, verbose_name='Полный адрес ФИАС'),
        ),
        migrations.AddField(
            model_name='building',
            name='fias_level_id',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Уровень ФИАС'),
        ),
        migrations.AddField(
            model_name='building',
            name='fias_object_guid',
            field=models.UUIDField(blank=True, null=True, verbose_name='GUID ФИАС'),
        ),
        migrations.AddField(
            model_name='building',
            name='fias_object_id',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='ID ФИАС'),
        ),
        migrations.AddField(
            model_name='kladraddressobject',
            name='fias_address_type',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Вид адреса ФИАС'),
        ),
        migrations.AddField(
            model_name='kladraddressobject',
            name='fias_level_id',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Уровень ФИАС'),
        ),
        migrations.AddField(
            model_name='kladraddressobject',
            name='fias_object_guid',
            field=models.UUIDField(blank=True, null=True, verbose_name='GUID ФИАС'),
        ),
        migrations.AddField(
            model_name='kladraddressobject',
            name='fias_object_id',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='ID ФИАС'),
        ),
        migrations.AddIndex(
            model_name='building',
            index=models.Index(fields=['fias_object_id'], name='kladr_buildi_fias_ob_3fc564_idx'),
        ),
        migrations.AddIndex(
            model_name='building',
            index=models.Index(fields=['fias_object_guid'], name='kladr_buildi_fias_ob_11984a_idx'),
        ),
        migrations.AddIndex(
            model_name='building',
            index=models.Index(fields=['fias_level_id'], name='kladr_buildi_fias_le_0d0859_idx'),
        ),
        migrations.AddIndex(
            model_name='kladraddressobject',
            index=models.Index(fields=['fias_object_id'], name='kladr_kladr_fias_ob_8974d8_idx'),
        ),
        migrations.AddIndex(
            model_name='kladraddressobject',
            index=models.Index(fields=['fias_object_guid'], name='kladr_kladr_fias_ob_a40b4f_idx'),
        ),
        migrations.AddIndex(
            model_name='kladraddressobject',
            index=models.Index(fields=['fias_level_id'], name='kladr_kladr_fias_le_7ff0f4_idx'),
        ),
    ]
