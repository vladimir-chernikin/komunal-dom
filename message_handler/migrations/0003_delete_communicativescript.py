from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("message_handler", "0002_alter_messagelog_channel_apierrorlog"),
    ]

    operations = [
        migrations.DeleteModel(
            name="CommunicativeScript",
        ),
    ]
