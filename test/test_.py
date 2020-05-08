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

logging.basicConfig( level = logging.DEBUG,
        format='%(asctime)s %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S' )

#DB = DBConn(CONF.items('db'))
#DB.connect()

def test_register_user():
    user_data = {
        'login': 'test_reg_usr',
        'password': '11111111',
        'email': 'test@test.com'
        }
    req = requests.post(API_URI + 'register_user', json=user_data)
    req.raise_for_status()
    assert DB.get_object('users', user_data, create=False)
    DB.execute('delete from users where login = %(login)s', user_data)
    del user_data['login']
    req = requests.post(API_URI + 'register_user', json=user_data)
    assert req.status_code == 400

