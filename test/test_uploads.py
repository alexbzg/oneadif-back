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

def create_upload_data():

    data = {'login': 'ADMIN', 'uploads': []}
    params =  {
        'dev.cfmrda': {
            'rda': 'MO-72', 
            'stationCallsignField': 'OPERATOR'
        }}

    
    accounts = DB.execute("select * from accounts where login = %(login)s", data, keys=True)
    for account in accounts:
        data['uploads'].append({'account_id': account['account_id'], 'params': params[account['elog']]})

    filename = 'RZ3DC MO-72.adi'
    adif = None
    with open(os.path.dirname(os.path.abspath(__file__)) + '/adif/' + filename, 'rb') as _tf:
        _adif = _tf.read()
        adif = ',' + base64.b64encode(_adif).decode()
    data['file'] = {'name': filename}
    logging.debug(data)
    data['file']['file'] = adif

    return data


def test_upload():
    upload_data = create_upload_data()
    for account in upload_data['uploads']:

        def create_upload():
            with upload_client() as conn:
                conn.send(('upload', (account['account_id'], upload_data['file'], account['params'])))
                upload_id = conn.recv()
                logging.debug('upload id: ' + str(upload_id))
                return upload_id

        upload_id = create_upload()

        with upload_client() as conn:
            conn.send(('cancel', upload_id))
            rsp = conn.recv()
            logging.debug(rsp)

        create_upload()

