# Generated by Django 5.2 on 2025-06-15 08:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app1', '0008_transcriptmodel'),
    ]

    operations = [
        migrations.AddField(
            model_name='transcriptmodel',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
