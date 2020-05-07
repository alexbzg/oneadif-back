#!/usr/bin/python3
#coding=utf-8

import pytest
import requests
import simplejson as json
import logging

API_URI = 'https://dev.oneadif.com/api/'

logging.basicConfig( level = logging.DEBUG,
        format='%(asctime)s %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S' )

def test_register_user():
    user_data = {
        'login': 'test_reg_usr',
        'password': '11111111',
        'email': 'test@test.com'
        }
    req = requests.post(API_URI + 'register_user', json=user_data)
    req.raise_for_status()
    logging.info(req.text)
    logging.info('info')
    logging.debug('debug')

