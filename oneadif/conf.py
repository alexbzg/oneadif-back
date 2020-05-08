#!/usr/bin/python3
#coding=utf-8

import configparser
import logging
import logging.handlers
from os import path

APP_ROOT = path.dirname(path.abspath(__file__))
APP_NAME = 'oneadif'

CONF = configparser.ConfigParser()
CONF.optionxform = str
CONF.read(APP_ROOT + '/site.conf')

def start_logging(log_type, level=logging.DEBUG):
    """starts logging to file"""
    fp_log = CONF['logs'][log_type]
    logger = logging.getLogger('')
    logger.setLevel(level)
    handler = logging.handlers.WatchedFileHandler(fp_log)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(\
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
    logger.addHandler(handler)
