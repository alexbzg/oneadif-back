#!/usr/bin/python3
#coding=utf-8
"""class for working with web-loggers. Currenly supported: LOTW"""
import logging

import requests
import simplejson as json

class ELogException(Exception):
    """Login failed"""
    pass

def eqsl_date_format(_dt):
    """formats date for eqsl url params: mm%2Fdd%2Fyyyy"""
    return _dt.strftime('%m%%2F%d%%2F%Y')

class ELog():

    default_login_data_fields = ['login', 'password']

    types = {'LoTW': {},\
            'eQSL': {\
                 'loginDataFields': ['Callsign', 'EnteredPassword'],\
                 'schema': 'extLoggersLoginEQSL'\
                }
            }

    states = {0: 'OK',\
            1: 'Не удалось войти на сайт. Login attempt failed'}

    def __init__(self, logger_type):
        self.type = logger_type
        self.session = None
        self.login_data = None
        self.auth_token = None

    def login(self, login_data):
        ssn = requests.Session()
        rsp = None
        ssn.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36'})
        data = {}
        data.update(login_data)

        if self.type == 'LoTW':
            data.update({\
                'acct_sel': '',\
                'thisForm': 'login'\
            })
            rsp = ssn.post('https://lotw.arrl.org/lotwuser/login', data=data)
            rsp.raise_for_status()
            if 'Username/password incorrect' in rsp.text:
                raise ELogException("Login failed.")

        elif self.type == 'HAMLOG':
            rsp = ssn.post('https://hamlog.ru/lk/login.php', data=data)
            rsp.raise_for_status()
            if 'Ошибка! Неверный адрес и/или пароль' in rsp.text:
                raise ELogException("Login failed.")

        elif self.type == 'eQSL':
            data.update({\
                'Login': 'Go'\
            })
            rsp = ssn.post('https://www.eqsl.cc/QSLCard/LoginFinish.cfm', data=data)
            rsp.raise_for_status()
            if 'Callsign or Password Error!' in rsp.text:
                raise ELogException("Login failed.")

        elif self.type == 'dev.cfmrda':
            data.update({'mode': 'login'})
            rsp = ssn.post('https://dev.cfmrda.ru/aiohttp/login', data=json.dumps(data))            
            rsp.raise_for_status()
            rsp_data = rsp.json()
            self.auth_token = rsp_data['token']

        self.login_data = login_data
        self.session = ssn

        return ssn
