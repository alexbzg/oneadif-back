#!/usr/bin/python3
#coding=utf-8
"""onedif backend"""
import logging

from flask import Flask, request, jsonify
from werkzeug.exceptions import InternalServerError

from validator import validate
from db import DBConn
from conf import CONF, APP_NAME, start_logging
from secret import get_secret, create_token

APP = Flask(APP_NAME)
APP.config.update(CONF['flask'])
APP.secret_key = get_secret(CONF.get('files', 'secret'))

with APP.app_context():
    start_logging('srv', CONF['logs']['srv_level'])
logging.debug('starting in debug mode')

DB = DBConn(CONF.items('db'))
DB.connect()
DB.verbose = True

def bad_request(message):
    logging.debug('bad_request entry')
    response = jsonify({'message': message})
    response.status_code = 400
    return response

@APP.errorhandler(InternalServerError)
def internal_error(exception):
    response = jsonify({'message': 'Server error'})
    response.status_code = 500
    logging.exception(exception)
    return response

@APP.route('/api/test', methods=['GET', 'POST'])
def test():
    """test if api is up"""
    return "Ok %s" % request.method

@APP.route('/api/register_user', methods=['POST'])
@validate(json_schema='register_user', recaptcha_field='recaptcha')
def register_user():
    """registers user and returns user data with token"""
    user_data = request.get_json()
    user_exists = DB.get_object('users', {'login': user_data['login']}, create=False)
    if user_exists:
        return bad_request('Пользователь с этим именем уже зарегистрирован.\n' +\
                'This username is already exists.')
    return send_user_data(request.get_json(), create=True)

def send_user_data(user_data, create=False):
    """returns user data with auth token as json response"""
    data = DB.get_object('users', user_data, create=create)
    if data:
        token = create_token({'login': data['login']})
        data['token'] = token
        return jsonify(data)
    else:
        abort(500)

if __name__ == "__main__":
    APP.run(host='127.0.0.1')
