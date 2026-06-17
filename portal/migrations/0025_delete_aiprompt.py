from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0024_drop_file_manager"),
    ]

    operations = [
        migrations.DeleteModel(
            name="AIPrompt",
        ),
    ]
