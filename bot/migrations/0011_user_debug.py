# Generated by Django 2.2.3 on 2020-02-16 11:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bot', '0010_auto_20200128_1208'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='debug',
            field=models.BooleanField(default=False),
        ),
    ]