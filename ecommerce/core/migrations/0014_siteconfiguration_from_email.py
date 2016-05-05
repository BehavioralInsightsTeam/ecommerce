# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_siteconfiguration_segment_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='siteconfiguration',
            name='from_email',
            field=models.CharField(help_text='Address from which emails are sent.', max_length=255, null=False, verbose_name='From email', blank=False),
        ),
    ]
