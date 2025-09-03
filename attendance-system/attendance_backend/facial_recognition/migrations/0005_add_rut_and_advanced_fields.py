# Generated migration for RUT and advanced facial recognition fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facial_recognition', '0004_alter_attendancerecord_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='rut',
            field=models.CharField(max_length=12, unique=True, help_text="RUT con formato 12345678-9", default='00000000-0'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='employee',
            name='face_variations_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='verification_method',
            field=models.CharField(
                max_length=10,
                choices=[('facial', 'Reconocimiento Facial'), ('qr', 'Código QR'), ('manual', 'Manual/GPS')],
                default='manual'
            ),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='qr_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='device_info',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='employee',
            name='face_encoding',
            field=models.TextField(blank=True, null=True, help_text="JSON con múltiples encodings faciales"),
        ),
        # Agregar índice para mejorar rendimiento en consultas de RUT
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_employee_rut ON facial_recognition_employee(rut);",
            reverse_sql="DROP INDEX IF EXISTS idx_employee_rut;"
        ),
    ]