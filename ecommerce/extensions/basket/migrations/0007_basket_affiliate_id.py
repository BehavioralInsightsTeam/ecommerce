# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basket', '0006_basket_site'),
    ]

    operations = [
        migrations.AddField(
            model_name='basket',
            name='affiliate_id',
            field=models.CharField(default=None, max_length=255, null=True, verbose_name='Affiliate ID'),
        ),
    ]
