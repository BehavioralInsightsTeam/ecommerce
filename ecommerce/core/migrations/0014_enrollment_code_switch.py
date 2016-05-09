# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


def create_switch(apps, schema_editor):
    """Create a switch for automatic creation of enrollment code products."""
    Switch = apps.get_model('waffle', 'Switch')
    Switch.objects.get_or_create(name=settings.ENROLLMENT_CODE_SWITCH, defaults={'active': False})


def remove_switch(apps, schema_editor):
    """Remove enrollment code switch."""
    Switch = apps.get_model('waffle', 'Switch')
    Switch.objects.filter(name='create_enrollment_codes').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('core', '0013_siteconfiguration_segment_key')
    ]
    operations = [
        migrations.RunPython(create_switch, remove_switch)
    ]
