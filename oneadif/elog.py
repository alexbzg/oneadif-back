#!/usr/bin/python3
#coding=utf-8
"""class for working with web-loggers. Currenly supported: LOTW"""
import logging
import io
from asyncio import CancelledError

import requests
import simplejson as json

class ELogException(Exception):
    """Login failed"""
    pass

def eqsl_date_format(_dt):
    """formats date for eqsl url params: mm%2Fdd%2Fyyyy"""
    return _dt.strftime('%m%%2F%d%%2F%Y')

class ProgressBufferReader(io.BytesIO):
    def __init__(self, buf, callback=None, cancel_event=None):
        self._callback = callback
        self._cancel_event = cancel_event
        bbuf = buf.encode()
        self._len = len(bbuf)
        self._progress = 0
        io.BytesIO.__init__(self, bbuf)

    def __len__(self):
        return self._len

    def read(self, n=-1):
        if self._cancel_event and self._cancel_event.is_set():
            raise CancelledError('The upload was cancelled.')
        chunk = io.BytesIO.read(self, n)
        self._progress += int(len(chunk))
        if self._callback:
            self._callback(self._progress/self._len)
        return chunk

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

    def upload(self, file, params, callback=None, cancel_event=None):

        data = {}
        data.update(params)
        url = None
        data_string = None

        if self.type == 'dev.cfmrda':
            file_entry = {}
            file_entry.update(file)
            file_entry['rda'] = data['rda']
            del data['rda']
            data.update({
                'stationCallsignFieldEnable': True,
                'rdaFieldEnable': False,
                'token': self.auth_token,
                'files': [file_entry]
                })
            url = 'https://dev.cfmrda.ru/aiohttp/adif'
            data_string = json.dumps(data)

        try:
            data_buffer = ProgressBufferReader(data_string, callback, cancel_event)
            rsp = requests.post(url, data=data_buffer)
            rsp.raise_for_status()
            logging.debug(rsp.text)
            return True
        except CancelledError:
            raise CancelledError
        except Exception:
            logging.exception(self.type + ' upload error')
            return False
