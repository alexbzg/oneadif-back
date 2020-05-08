#!/usr/bin/python3
#coding=utf-8
import logging

from flask import Flask, request, abort
from validator import validate

from db import DBConn
from conf import CONF, APP_NAME, start_logging
ENV = CONF['flask']['env']
DEBUG = CONF['flask']['debug']

APP = Flask(APP_NAME)
APP.config.from_object(__name__)

start_logging('srv', CONF['logs']['srv_level'])
logging.debug('starting in debug mode')

DB = DBConn(CONF.items('db'))
DB.connect()
DB.verbose = True

@APP.route('/api/test', methods=['GET', 'POST'])
def test():
    return "Ok %s" % request.method

@APP.route('/api/register_user', methods=['POST'])
@validate(json_schema='register_user', recaptcha_field='recaptcha')
def register_user():
    user_data = request.get_json()
    if DB.get_object('users', user_data, create=True):
        return 'Ok'
    else:
        abort(500)

if __name__ == "__main__":
    APP.run(host='127.0.0.1')

