#!/usr/bin/python3
#coding=utf-8
import logging

from flask import Flask, request, abort
from validator import Validator

from conf import CONF, APP_NAME
ENV = CONF['flask']['env']
DEBUG = CONF['flask']['debug']

APP = Flask(APP_NAME)
APP.config.from_object(__name__)

logging.basicConfig(level=logging.DEBUG)
logging.debug('starting in debug mode')

VALIDATOR = Validator()
VALIDATOR.dev_mode = APP.env == 'development'

@APP.route('/api/test', methods=['GET', 'POST'])
def test():
    return "Ok %s" % request.method

@APP.route('/api/register_user', methods=['POST'])
def register_user():
    logging.debug('APP.env: ' + APP.env)
    if VALIDATOR.validate(request, json_schema='register_user', recaptcha_field='recaptcha'):
        return 'Ok'
    else:
        abort(400)

if __name__ == "__main__":
    APP.run(host='127.0.0.1')

