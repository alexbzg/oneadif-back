#!/usr/bin/python3
#coding=utf-8
"""flask request object validation"""
import logging

import jsonschema
import requests
import simplejson as json

from conf import CONF
from json_utils import load_json

def check_recaptcha(response):
    """queries google for recaptcha validity
    returns true/false"""
    try:
        rc_data = {'secret': CONF['recaptcha']['secret'],\
                'response': response}
        resp = requests.post(CONF['recaptcha']['verifyURL'],\
                data=rc_data)
        resp.raise_for_status()
        resp_data = json.loads(resp.text)
        return resp_data['success']
    except Exception:
        logging.exception('Recaptcha error')
        return False

SCHEMAS = load_json(CONF['web']['root'] + '/schemas.json')
def _validate_dict(data, schema):
    """validates dict data with one of predefined jsonschemas
    return true/false"""
    try:
        jsonschema.validate(data, SCHEMAS[schema])
        return True
    except jsonschema.exceptions.ValidationError as exc:
        logging.error('Error validating json data. Schema: ' + schema)
        logging.error(data)
        logging.error(exc.message)
        return False

class Validator:

    def __init__(self):
        self.dev_mode = False

    def validate(self, request, json_schema=None, recaptcha_field=None):
        """validates flask request object by all relevant means
        returns true/false"""
        if json_schema:
            if not _validate_dict(request.get_json(), json_schema):
                logging.debug('json validation failed')
                return False
            logging.debug('json was validated successfully')
        if recaptcha_field and not self.dev_mode:
            logging.debug('recaptcha check is started')
            json_data = request.get_json()
            if recaptcha_field in json_data:
                return check_recaptcha(json_data[recaptcha_field])
            else:
                return False
        return True


