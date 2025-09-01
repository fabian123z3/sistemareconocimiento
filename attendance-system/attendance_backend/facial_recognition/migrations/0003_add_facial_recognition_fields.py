# Generated migration for facial recognition fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facial_recognition', '0002_remove_attendancerecord_confidence_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='face_encoding',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='employee',
            name='has_face_registered',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='employee',
            name='face_quality_score',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='employee',
            name='face_registration_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='face_confidence',
            field=models.FloatField(default=0),
        ),
    ]