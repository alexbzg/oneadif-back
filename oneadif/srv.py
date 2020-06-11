#!/usr/bin/python3
#coding=utf-8
"""onedif backend"""
import logging
import time

from flask import Flask, request, jsonify
from werkzeug.exceptions import InternalServerError

from validator import validate, bad_request
from db import DBConn, splice_params
from conf import CONF, APP_NAME, start_logging
from secret import get_secret, create_token
import send_email
from elog import ELog
from upload_srv import upload_client

APP = Flask(APP_NAME)
APP.config.update(CONF['flask'])
APP.secret_key = get_secret(CONF['files']['secret'])

with APP.app_context():
    start_logging('srv', CONF['logs']['srv_level'])
logging.debug('starting in debug mode')

DB = DBConn(CONF.items('db'))
DB.connect()
DB.verbose = True
APP.db = DB

def _create_token(data):
    return create_token(data, APP.secret_key)

@APP.errorhandler(InternalServerError)
def internal_error(exception):
    'Internal server error interceptor; logs exception'
    response = jsonify({'message': 'Server error'})
    response.status_code = 500
    logging.exception(exception)
    return response

@APP.route('/api/test', methods=['GET', 'POST'])
def test():
    """test if api is up"""
    return "Ok %s" % request.method

@APP.route('/api/register_user', methods=['POST'])
@validate(request_schema='login', recaptcha_field='recaptcha')
def register_user():
    """registers user and returns user data with token"""
    user_data = request.get_json()
    user_exists = DB.get_object('users', {'login': user_data['login']}, create=False)
    if user_exists:
        return bad_request('Пользователь с этим именем уже зарегистрирован.\n' +\
                'This username is already exists.')
    return send_user_data(user_data, create=True)

@APP.route('/api/login', methods=['POST'])
@validate(request_schema='login')
def login():
    """check login data and returns user data with token"""
    return send_user_data(request.get_json())

@APP.route('/api/password_recovery_request', methods=['POST'])
@validate(request_schema='passwordRecoveryRequest', recaptcha_field='recaptcha')
def password_recovery_request():
    """check login data and returns user data with token"""
    req_data = request.get_json()
    user_data = DB.get_object('users', req_data, create=False)
    if not user_data or not user_data['email']:
        return bad_request('Пользователь или email не зарегистрирован.\n' +\
            'The username or email address is not registered.')
    token = _create_token({
        'login': req_data['login'],
        'type': 'passwordRecovery',
        'expires': time.time() + 60 * 60 * 60})
    text = """Пройдите по ссылкe, чтобы сменить пароль на ONEADIF.com: """\
        + CONF.get('web', 'address')\
        + '/#/passwordRecovery?token=' + token + """

Если вы не запрашивали смену пароля на ONEADIF.com, просто игнорируйте это письмо.
Ссылка будет действительна в течение 1 часа.

Follow this link to change your ONEADIF.com password: """ \
        + CONF.get('web', 'address')\
        + '/#/passwordRecovery?token=' + token + """

Ignore this message if you did not request password change


Служба поддержки ONEADIF.com support"""
    send_email.send_email(text=text,\
        fr=CONF.get('email', 'address'),\
        to=user_data['email'],\
        subject="ONEADIF.com - password change")
    return jsonify({'message':\
        'На ваш почтовый адрес было отправлено письмо с инструкциями по ' +\
        'сменен пароля.\n' +\
        'The message with password change instrunctions was sent to your ' +\
        'email address'})

def ok_response():
    return jsonify({'message': 'Ok'})

@APP.route('/api/password_recovery', methods=['POST'])
@validate(request_schema='login', token_schema='passwordRecovery', recaptcha_field='recaptcha',\
        login=True)
def password_recovery():
    """check login data and returns user data with token"""
    req_data = request.get_json()
    if not DB.param_update('users',\
        {'login': req_data['login']}, {'password': req_data['password']}):
        raise Exception('Password change failed')
    return ok_response()

def splice_request(*params):
    return splice_params(request.get_json(), *params)

@APP.route('/api/account', methods=['POST', 'DELETE'])
@validate(request_schema='account', token_schema='auth', login=True)
def account():
    """checks login data and returns user data with token"""
    req_data = request.get_json()
    account_key = splice_params(req_data, 'login', 'elog')
    if request.method == 'POST':
        elog = ELog(account_key['elog'])
        status = False
        try:
            status = bool(elog.login(req_data['login_data']))
        except Exception:
            logging.exception(req_data['elog'] + ' login error')
        account_data = splice_params(req_data, 'login_data')
        account_data['status'] = status
        if not DB.param_upsert('accounts', account_key, account_data):
            raise Exception('Account update or creation failed')
        return jsonify({'status': status})
    else:
        if not DB.param_delete('accounts', account_key):
            raise Exception('Account delete failed')
    return ok_response()

@APP.route('/api/upload', methods=['POST'])
@validate(request_schema='upload', token_schema='auth', login=True)
def upload():
    req_data = request.get_json()
    uploads = {}
    for upload_data in req_data['uploads']:        
        account_id = upload_data['account_id']
        if DB.get_object('accounts', {'account_id': account_id, 'login': req_data['login']},\
            create=False):
            with upload_client() as conn:
                conn.send(('upload', (account_id, req_data['file'], upload_data['params'])))
                uploads[account_id] = conn.recv()

    return jsonify(uploads)

@APP.route('/api/uploads_list', methods=['POST'])
@validate(token_schema='auth', login=True)
def uploads_list():
    req_data = request.get_json()
    uploads = DB.execute("""
        select upload_id, elog, login_data, state
        from uploads join accounts on uploads.account_id = accounts.account_id
        where accounts.login = %(login)s""", req_data, keys=True)
    return jsonify(uploads)

@APP.route('/api/uploads_list', methods=['DELETE'])
@validate(request_schema='upload_cancel', token_schema='auth', login=True)
def uploads_list_delete():
    req_data = request.get_json()
    if DB.execute("""
        delete from uploads 
        where upload_id = %(upload_id)s and account_id in
            (select account_id 
            from accounts 
            where login = %(login)s)""", req_data):
        return ok_response()
    else:
        raise Exception('Upload record delete failed.')

@APP.route('/api/upload', methods=['DELETE'])
@validate(request_schema='upload_cancel', token_schema='auth', login=True)
def upload_cancel():
    req_data = request.get_json()
    if DB.execute("""select upload_id
        from uploads join accounts on uploads.account_id = accounts.account_id
        where upload_id = %(upload_id)s and login = %(login)s""", req_data):
        with upload_client() as conn:
            conn.send(('cancel', req_data['upload_id']))
            rsp = conn.recv()
            return jsonify(rsp)
    else:
        return bad_request('Загрузка не найдена.\n' +\
                'Upload not found')

def send_user_data(user_data, create=False):
    """returns user data with auth token as json response"""
    data = DB.get_object('users', user_data, create=create)
    if data:
        token = _create_token({'login': data['login'], 'type': 'auth'})
        del data['password']
        data['token'] = token
        return jsonify(data)
    else:
        if create:
            raise Exception("User creation failed")
        else:
            return bad_request('Неверное имя пользователя или пароль.\n' +\
                    'Wrong username or password')

if __name__ == "__main__":
    APP.run(host='127.0.0.1')
