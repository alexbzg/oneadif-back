#!/usr/bin/python3
#coding=utf-8

import pytest
import requests
import simplejson as json
import logging
import sys

sys.path.append('oneadif')
from db import DBConn
from conf import CONF

DB = DBConn(CONF.items('db'))
DB.verbose = True
DB.connect()


API_URI = 'https://dev.oneadif.com/api/'

LOGGER = logging.getLogger(__name__)

def test_register_user():
    user_data = {
        'login': 'test_reg_usr',
        'password': '11111111',
        'email': 'test@test.com'
        }
    DB.execute('delete from users where login = %(login)s', user_data)
    DB.conn.commit()
    req = requests.post(API_URI + 'register_user', json=user_data)
    LOGGER.debug(req.text)
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
    DB.conn.commit()
    del user_data['login']
    req = requests.post(API_URI + 'register_user', json=user_data)
    assert req.status_code == 400

