#!/usr/bin/python3
#coding=utf-8

import pytest
import simplejson as json
import logging
import sys
import base64
import os
from multiprocessing.connection import Client

sys.path.append('oneadif')
from db import DBConn, splice_params
from conf import CONF
from upload_srv import upload_client

DB = DBConn(CONF.items('db'))
DB.verbose = True
DB.connect()

LOGIN = 'ADMIN'
FILENAME = 'RZ3DC MO-72.adi'
adif = None

with open(os.path.dirname(os.path.abspath(__file__)) + '/adif/' + FILENAME, 'rb') as _tf:
    _adif = _tf.read()
    adif = ',' + base64.b64encode(_adif).decode()
DATA = {
    'dev.cfmrda': {
        'stationCallsignField': 'OPERATOR',
        'rdaFieldEnable': False
    }}
FILE = {'name': FILENAME, 'file': adif, 'rda': 'MO-72'}

def test_upload():
    accounts = DB.execute("select * from accounts where login = %(login)s", {'login': LOGIN}, keys=True)
    for account in accounts:
        upload_id = None
        with upload_client() as conn:
            conn.send(('upload', (account['account_id'], FILE, DATA[account['elog']])))
            upload_id = conn.recv()
            logging.debug('upload id: ' + str(upload_id))
        with upload_client() as conn:
            conn.send(('cancel', upload_id))
            rsp = conn.recv()
            logging.debug(rsp)

