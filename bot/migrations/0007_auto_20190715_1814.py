# Generated by Django 2.2.3 on 2019-07-15 15:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bot', '0006_auto_20190714_2026'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='chat',
            name='active',
        ),
        migrations.RemoveField(
            model_name='chat',
            name='user',
        ),
        migrations.CreateModel(
            name='Relation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=True)),
                ('chat', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bot.Chat')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bot.User')),
            ],
        ),
        migrations.AddField(
            model_name='chat',
            name='user',
            field=models.ManyToManyField(related_name='chats', through='bot.Relation', to='bot.User'),
        ),
    ]
