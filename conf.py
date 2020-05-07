#!/usr/bin/python3
#coding=utf-8

import configparser
from os import path

APP_ROOT = path.dirname(path.abspath(__file__))
APP_NAME = 'oneadif'

CONF = configparser.ConfigParser()
CONF.optionxform = str
CONF.read(APP_ROOT + '/site.conf')

