from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('nsi', '0004_remove_reflocalization_llm_description_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='EquipmentType',
        ),
    ]
