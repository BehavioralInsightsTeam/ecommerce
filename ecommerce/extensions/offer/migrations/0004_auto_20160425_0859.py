# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('offer', '0003_range_course_seats'),
    ]

    operations = [
        migrations.RenameField(
            model_name='range',
            old_name='course_seats',
            new_name='course_seat_types',
        ),
        migrations.AddField(
            model_name='range',
            name='catalog_query',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
    ]
