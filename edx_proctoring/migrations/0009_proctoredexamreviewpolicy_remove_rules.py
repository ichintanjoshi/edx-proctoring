# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-12-10 16:47
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('edx_proctoring', '0008_auto_20181116_1551'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='proctoredexamreviewpolicy',
            name='rules',
        ),
        migrations.RemoveField(
            model_name='proctoredexamreviewpolicyhistory',
            name='rules',
        ),
    ]