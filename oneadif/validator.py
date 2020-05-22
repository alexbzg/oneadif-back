#!/usr/bin/python3
#coding=utf-8
"""flask request object validation"""
import logging
import time
from functools import wraps

from flask import request, current_app, jsonify
import jwt
import jsonschema
import requests
import simplejson as json

from conf import CONF, APP_ROOT
from json_utils import load_json

def bad_request(message):
    'Bad request helper function'
    response = jsonify({'message': message})
    response.status_code = 400
    return response

def check_recaptcha(response):
    """queries google for recaptcha validity
    returns true/false"""
    try:
        rc_data = {'secret': CONF['recaptcha']['secret'],\
                'response': response}
        resp = requests.post(CONF['recaptcha']['verifyURL'],\
                data=rc_data)
        resp.raise_for_status()
        resp_data = json.loads(resp.text)
        return resp_data['success']
    except Exception:
        logging.exception('Recaptcha error')
        return False

def _json_validator(schemas_path):

    schemas = load_json(schemas_path)
    def _validate_dict(data, schema):
        """validates dict data with one of predefined jsonschemas
        return true/false"""
        try:
            jsonschema.validate(data, schemas[schema])
            return (True, None)
        except jsonschema.exceptions.ValidationError as exc:
            logging.error('Error validating json data. Schema: ' + schema)
            logging.error(data)
            logging.error(exc.message)
            return (False, exc.message)

    return _validate_dict

def decode_token(token):
    try:
        return jwt.decode(token, current_app.secret_key, algorithms=['HS256'])
    except jwt.exceptions.DecodeError:
        return None

def validate(request_schema=None, token_schema=None, recaptcha_field=None, login=False):
    """validates flask request object by all relevant means
    returns true/false"""

    request_validator = _json_validator(CONF['web']['root'] + '/schemas.json')
    token_validator = _json_validator(APP_ROOT + '/token_schemas.json')

    def wrapper(func):

        @wraps(func)
        def wrapped(*args, **kwargs):
            request_data = request.get_json()
            error_message = None
            if request_data:
                if request_schema:
                    validated, error = request_validator(request_data, request_schema)
                    if not validated:
                        error_message = 'Invalid request data: ' + error
                if recaptcha_field and current_app.config['ENV'] != 'development':
                    if recaptcha_field not in request_data or not request_data[recaptcha_field] or\
                        not check_recaptcha(request_data[recaptcha_field]):
                        error_message = 'Проверка на робота не пройдена. Попробуйте еще раз.\n' +\
                            'Recaptcha check failed. Please try again.'
                if token_schema:
                    if 'token' in request_data and request_data['token']:
                        token_data = decode_token(request_data['token'])
                        logging.debug('token deciphered:')
                        logging.debug(token_data)
                        logging.debug('current time: ')
                        logging.debug(time.time())
                        validated, error = token_validator(token_data, token_schema)
                        if not validated or\
                            ('expires' in token_data and token_data['expires'] < time.time()) or\
                            token_data['login'] != request_data['login']:
                            error_message = 'Неверные или устаревшие данные аутентификации. ' +\
                                'Попробуйте перелогиниться и/или повторить операцию.\n' +\
                                'Invalid or obsolete authentification data. ' +\
                                'Try relogin and/or repeat the operation.'
                    else:
                        error_message = 'Отсутствуют данные аутентификации. ' +\
                            'Попробуйте перелогиниться и/или повторить операцию.\n' +\
                            'No authentification data. ' +\
                            'Try relogin and/or repeat the operation.'
                if login:
                    user_data = current_app.db.get_object('users', {'login': request_data['login']}, create=None)
                    if not user_data:
                        error_message = 'Пользователь не зарегистрирован.\n' +\
                            'The username is not registered.'

            else:
                error_message = 'No request data found.'

            if error_message:
                return bad_request(error_message)
            else:
                return func(*args, **kwargs)

        return wrapped

    return wrapper
