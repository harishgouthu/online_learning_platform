# Generated by Django 5.2 on 2025-06-15 09:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app1', '0009_transcriptmodel_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='transcriptmodel',
            name='transcript_text',
            field=models.TextField(blank=True, null=True),
        ),
    ]
