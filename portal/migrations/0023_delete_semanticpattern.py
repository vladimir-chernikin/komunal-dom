from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0022_add_service_object_house_fias_and_indexes'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SemanticPattern',
        ),
    ]
