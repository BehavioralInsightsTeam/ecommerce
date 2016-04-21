# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('offer', '0002_range_catalog'),
    ]

    operations = [
        migrations.AddField(
            model_name='range',
            name='course_seats',
            field=jsonfield.fields.JSONField(null=True),
        ),
    ]
