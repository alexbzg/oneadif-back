#!/usr/bin/python3
#coding=utf-8

import pytest
import requests
import simplejson as json
import logging
import sys
import string
import time
from random import sample, choice
CHARS = string.ascii_letters + string.digits

sys.path.append('oneadif')
from secret import get_secret, create_token
from db import DBConn, splice_params
from conf import CONF

DB = DBConn(CONF.items('db'))
DB.verbose = True
DB.connect()

API_URI = 'https://dev.oneadif.com/api/'

LOGGER = logging.getLogger(__name__)

SECRET = get_secret(CONF.get('files', 'secret'))
def _create_token(data):
    return create_token(data, SECRET)
LOGIN = 'ADMIN'
PASSWORD = '18231823'

def rnd_string(length=8):
    return ''.join(choice(CHARS) for _ in range(length))

def update_data(data, update):
    if update:
        for field in update:
            if update[field] == '___DELETE___':
                del data[field]
            else:
                data[field] = update[field]

def cmp_data(db_data, post_data):
    assert db_data
    for key in post_data:
        assert key in db_data
        assert db_data[key] == post_data[key]

def test_register_login():
    user_data = {
        'login': 'test_reg_usr',
        'password': '11111111',
        'email': 'test@test.com'
        }
    DB.execute('delete from users where login = %(login)s', user_data)
    req = requests.post(API_URI + 'register_user', json=user_data)
    req.raise_for_status()
    srv_data = json.loads(req.text)
    assert srv_data
    assert srv_data['token']
    logging.getLogger().info(srv_data)
    db_user_data = DB.get_object('users', user_data, create=False)
    assert db_user_data
    for key in user_data:
        assert user_data[key] == db_user_data[key]
    req = requests.post(API_URI + 'register_user', json=user_data)
    assert req.status_code == 400
    LOGGER.debug(req.text)
    DB.execute('delete from users where login = %(login)s', user_data)
    req = requests.post(API_URI + 'register_user', json=user_data)
    req.raise_for_status()
    login = user_data['login']
    del user_data['login']
    req = requests.post(API_URI + 'register_user', json=user_data)
    assert req.status_code == 400
    user_data['login'] = login
    del user_data['email']
    req = requests.post(API_URI + 'login', json=user_data)
    req.raise_for_status()
    srv_data = json.loads(req.text)
    assert srv_data
    assert srv_data['token']
    user_data['password'] += '___'
    req = requests.post(API_URI + 'login', json=user_data)
    assert req.status_code == 400
    LOGGER.debug(req.text)
    del user_data['password']
    req = requests.post(API_URI + 'login', json=user_data)
    assert req.status_code == 400
    LOGGER.debug(req.text)
    DB.execute('delete from users where login = %(login)s', user_data)

def test_password_recovery_request():
    #request
    #--good user
    req = requests.post(API_URI + 'password_recovery_request', json={'login': LOGIN})
    req.raise_for_status()
    #--bad user
    req = requests.post(API_URI + 'password_recovery_request', json={'login': LOGIN + '_'})
    assert req.status_code == 400

def test_password_recovery():
    #change
    password = rnd_string()

    def post(update_token=None, update_post=None):
        data = {}
        token_data = {
            'login': LOGIN,
            'type': 'passwordRecovery',
            'expires': time.time() + 60 * 60 * 60}
        update_data(token_data, update_token)
        post_data = {'login': LOGIN,
            'token': _create_token(token_data),
            'password': password}
        update_data(post_data, update_post)
        return requests.post(API_URI + 'password_recovery', json=post_data)

    #--good request
    req = post()
    req.raise_for_status()
    db_user_data = DB.get_object('users', {'login': LOGIN}, create=False)
    assert db_user_data['password'] == password
    #--bad request
    #----expired
    req = post(update_token={'expires': time.time() - 1})
    assert req.status_code == 400
    logging.debug(req.text)
    #----missing expires field
    req = post(update_token={'expires': '___DELETE___'})
    assert req.status_code == 400
    logging.debug(req.text)
    #----wrong token type
    req = post(update_token={'type': 'blah'})
    assert req.status_code == 400
    logging.debug(req.text)
    #----missing token type
    req = post(update_token={'type': '___DELETE___'})
    assert req.status_code == 400
    logging.debug(req.text)
    #----wrong login
    req = post(update_token={'login': LOGIN + '_'})
    assert req.status_code == 400
    logging.debug(req.text)
    #----user not exists
    req = post(update_token={'login': LOGIN + '_'},update_post={'login': LOGIN + '_'})
    assert req.status_code == 400
    logging.debug(req.text)
    #----missing token
    req = post(update_post={'token': '___DELETE___'})
    assert req.status_code == 400
    logging.debug(req.text)
    DB.param_update('users', {'login': LOGIN}, {'password': PASSWORD})

def test_account():
    #elogs accounts management
    data = {}
    token_data = {
        'login': LOGIN,
        'type': 'auth'}
    login_data = {'callsign': 'TEST1ADIF', 'password': '18231823'}
    post_data = {'login': LOGIN, 
        'token': _create_token(token_data), 
        'elog': 'dev.cfmrda',
        'login_data': login_data}
    login_data['password'] += '_'
    acc_key = splice_params(post_data, 'login', 'elog')
    DB.param_delete('accounts', acc_key)
    #--create / wrong elog password
    req = requests.post(API_URI + 'account', json=post_data)
    req.raise_for_status()
    logging.debug(req.text)
    rsp_data = req.json()
    assert 'status' in rsp_data
    assert not rsp_data['status']
    db_data = DB.get_object('accounts', acc_key, create=False)
    assert db_data
    del db_data['status']
    cmp_data(db_data['login_data'], post_data['login_data'])
    #--update / good elog password
    post_data['login_data']['password'] = '18231823'
    req = requests.post(API_URI + 'account', json=post_data)
    req.raise_for_status()
    logging.debug(req.text)
    rsp_data = req.json()
    assert 'status' in rsp_data
    assert rsp_data['status']
    db_data = DB.get_object('accounts', acc_key, create=False)
    assert db_data
    del db_data['status']
    cmp_data(db_data['login_data'], post_data['login_data'])
    #--delete
    del post_data['login_data']
    req = requests.delete(API_URI + 'account', json=post_data)
    req.raise_for_status()
    db_data = DB.get_object('accounts', acc_key, create=False)
    assert not db_data
    post_data['login_data'] = login_data
    req = requests.post(API_URI + 'account', json=post_data)
