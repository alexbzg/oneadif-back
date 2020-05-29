#!/usr/bin/python3
#coding=utf-8
"""onedif backend"""
import logging
import time
import threading
import uuid

from flask import Flask, request, jsonify
from werkzeug.exceptions import InternalServerError

from validator import validate, bad_request
from db import DBConn, splice_params
from conf import CONF, APP_NAME, start_logging
from secret import get_secret, create_token
import send_email
from elog import ELog
from cancellable_thread import async_raise, CancellableThread
from json_utils import load_json, save_json

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


class UploadThreads():

    def __init__(self, path):
        self.__path = path

    def __load(self):
        return load_json(self.__path)

    def __save(self, threads):
        save_json(threads, self.__path)

    def get(self, upload_id):
        threads = self.__load()
        if not threads or upload_id not in threads:
            return None
        else:
            return threads[upload_id]

    def set(self, upload_id, thread_data):
        threads = self.__load()
        if not threads:
            threads = {}
        threads[upload_id] = thread_data
        self.__save(threads)

    def delete(self, upload_id):
        threads = self.__load()
        if threads and upload_id in threads:
            del threads[upload_id]
            self.__save(threads)

UPLOAD_THREADS = UploadThreads(CONF['files']['upload_threads'])

class UploadThread(CancellableThread):
    STATES = {\
            'init': 0,\
            'login': 1,\
            'login failed': 2,\
            'upload': 3,\
            'upload failed': 4,\
            'success': 5\
            }

    def __init__(self, elog_type, login_data, file, params):
        self.upload_id = str(uuid.uuid1())
        self.elog_type = elog_type
        self.login_data = login_data
        self.file = file
        self.params = params
        self.status_file_path = CONF['web']['root'] + '/uploads/' + self.upload_id
        self.__progress = 0
        self.__state = 'init'
        self.__export_status()
        super().__init__()

    def __export_status(self):
        with open(self.status_file_path, 'wb') as status_file:
            status_bytes = [UploadThread.STATES[self.state], int(round(self.progress, 2)*100)]
            status_file.write(bytearray(status_bytes))

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, value):
        if self.__state != value:
            logging.debug('upload ' + self.upload_id + ' state:')
            logging.debug(self.state)
            self.__state = value
            self.__export_status()

    @property
    def progress(self):
        return self.__progress

    @progress.setter
    def progress(self, value):
        if self.__progress != value:
            self.__progress = value
            self.__export_status()

    def upload_callback(self, progress):
        logging.debug('upload ' + self.upload_id + ' progress:')
        logging.debug(progress)
        self.progress = progress

    def run(self):
        try:
            logging.debug('upload ' + self.upload_id + ' start')
            self.state = 'login'
            elog = ELog(self.elog_type)
            if elog.login(self.login_data):
                self.state = 'upload'
                if elog.upload(self.file, self.params, self.upload_callback):
                    self.state = 'success'
                else:
                    self.state = 'upload failed'
            else:
                self.state = 'login failed'
        except Exception:
            self.state = 'internal error'
            logging.exception('Upload thread error')
        finally:
            UPLOAD_THREADS.delete(self.upload_id)

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

@APP.route('/api/upload', methods=['POST', 'DELETE'])
@validate(request_schema='upload', token_schema='auth', login=True)
def upload():
    req_data = request.get_json()
    uploads = {}
    for upload_data in req_data['uploads']:
        elog_type = upload_data['elog']
        account_data = DB.get_object('accounts',\
                {'login': req_data['login'], 'elog': elog_type},\
                create=False)
        if account_data['status']:
            upload_thread = UploadThread(elog_type,\
                    account_data['login_data'],\
                    req_data['file'],\
                    upload_data['params'])
            uploads[elog_type] = upload_thread.upload_id
            upload_thread.start()
            UPLOAD_THREADS.set(upload_thread.upload_id,\
                {'login': req_data['login'],\
                'thread_id': upload_thread._get_my_tid()})

    return jsonify(uploads)

@APP.route('/api/upload_cancel', methods=['POST', 'DELETE'])
@validate(request_schema='uploadCancel', token_schema='auth', login=True)
def upload_cancel():
    req_data = request.get_json()
    upload_id = req_data['id']
    logging.debug('upload cancel request: ' + upload_id)
    thread_data = UPLOAD_THREADS.get(upload_id)
    if thread_data:
        if thread_data['login'] == req_data['login']:
            async_raise(thread_data['thread_id'], SystemExit)
        #    UPLOAD_THREADS.delete(upload_id)
        else:
            raise Exception('Not authenticated for this operation')
    else:
        raise Exception('Thread not found')
    return ok_response()

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
