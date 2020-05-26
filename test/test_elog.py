#!/usr/bin/python3
#coding=utf-8

import pytest
import simplejson as json
import logging
import sys
import base64
import os

sys.path.append('oneadif')
from db import DBConn, splice_params
from conf import CONF
from elog import ELog

DB = DBConn(CONF.items('db'))
DB.verbose = True
DB.connect()

LOGIN = 'ADMIN'
FILENAME = 'RK0UN.adi'
adif = None

def upload_callback(progress):
    logging.debug('Progress: {:.0%}'.format(progress))

with open(os.path.dirname(os.path.abspath(__file__)) + '/adif/' + FILENAME, 'r') as _tf:
    _adif = _tf.read()
    adif = ',' + base64.b64encode(_adif.encode()).decode()
DATA = {
    'dev.cfmrda': {
        'stationCallsignField': 'OPERATOR',
        'rdaField': 'STATE',
        'files': [{'name': FILENAME, 'file': adif}]}
    }

def test_upload():
    accounts = DB.execute("select * from accounts where login = %(login)s", {'login': LOGIN}, keys=True)
    for account in accounts:
        elog_type = account['elog']
        elog = ELog(elog_type)
        assert elog.login(account['login_data'])
        if elog_type in DATA:
            elog.upload(DATA[elog_type], upload_callback)


