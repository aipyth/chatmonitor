# Generated by Django 2.2.3 on 2019-07-13 21:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bot', '0004_auto_20190712_1233'),
    ]

    operations = [
        migrations.AlterField(
            model_name='keyword',
            name='key',
            field=models.TextField(unique=True),
        ),
    ]
