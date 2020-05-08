#!/usr/bin/python3
#coding=utf-8

import logging
import simplejson as json

import psycopg2
from psycopg2.extensions import TRANSACTION_STATUS_IDLE

class OneadifDbException(Exception):

    def __init__(self, message):
        msg_trim = message.splitlines()[0].split('oneadif_db_error:')[1]
        super().__init__(msg_trim)

def to_dict(cur, keys=None):
    if cur and cur.rowcount:
        columns_names = [col.name for col in cur.description]
        if cur.rowcount == 1 and not keys:
            data = yield from cur.fetchone()
            if len(columns_names) == 1:
                return data[0]
            else:
                return dict(zip(columns_names, data))
        else:
            data = yield from cur.fetchall()
            if ('id' in columns_names) and keys:
                id_idx = columns_names.index('id')
                return {row[id_idx]: dict(zip(columns_names, row)) \
                        for row in data}
            else:
                if len(columns_names) == 1:
                    return [row[0] for row in data]
                else:
                    return [dict(zip(columns_names, row)) for\
                        row in data]
    else:
        return False

def typed_values_list(_list, _type=None):
    """convert list to values string, skips values not of specified type if
    type is specified"""
    return '(' + ', '.join((str(x) for x in _list\
        if not _type or isinstance(x, _type))) + ')'

def params_str(params, str_delim):
    """converts params dict to string for appending to sql"""
    return str_delim.join([x + " = %(" + x + ")s" for x in params.keys()])

def splice_params(data, params):
    """splices dict and converts subdicts to json strings"""
    return {param: json.dumps(data[param]) \
            if isinstance(data[param], dict) else data[param] \
        for param in params \
        if param in data}

def init_connection(conn):
    conn.set_client_encoding('UTF8')
    logging.debug('new db connection')

def exec_cur(cur, sql, params=None):
    try:
        cur.execute(sql, params)
        return True
    except Exception as exc:
        trap_db_exception(exc, sql, params)
        return False

def trap_db_exception(exc, sql, params=None):
    if isinstance(exc, psycopg2.InternalError) or\
        isinstance(exc, psycopg2.DatabaseError):
        logging.debug(exc.pgerror)
        if 'oneadif_db_error' in exc.pgerror:
            raise OneadifDbException(exc.pgerror)
    logging.exception("Error executing: " + sql + "\n",\
        exc_info=True)
    if params and isinstance(params, dict):
        logging.error("Params: ")
        logging.error(params)

class DBConn:

    def __init__(self, db_params, verbose=False):
        self.dsn = ' '.join([k + "='" + v + "'" for k, v in db_params])
        self.verbose = verbose
        self.pool = None
        self.error = None
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(self.dsn)
            init_connection(self.conn)
            logging.debug('db connection was created')
        except Exception:
            logging.exception('Error creating db connection')
            logging.error(self.dsn)

    def param_update(self, table, id_params, upd_params):
        return self.execute('update ' + table + \
                ' set ' + params_str(upd_params, ', ') + \
                " where " + params_str(id_params, ' and '), \
                dict(id_params, **upd_params))

    def param_delete(self, table, id_params):
        return self.execute('delete from ' + table + \
                " where " + params_str(id_params, ' and ') +\
                " returning *", id_params)

    def param_update_insert(self, table, id_params, upd_params):
        lookup = self.get_object(table, id_params, False, True)
        res = None
        if lookup:
            res = self.param_update(table, id_params, upd_params)
        else:
            res = self.get_object(table, dict(id_params, **upd_params),\
                    True)
        return res


    def execute(self, sql, params=None, keys=None, progress=None):
        res = False
        with self.conn.cursor() as cur:
            try:
                if self.verbose:
                    logging.debug(sql)
                    logging.debug(params)
                if not params or isinstance(params, dict):
                    cur.execute(sql, params)
                    res = to_dict(cur, keys)\
                        if cur.description != None else True
                else:
                    cnt = 0
                    cnt0 = 0
                    for item in params:
                        cnt0 += 1
                        cur.execute(sql, item)
                        if cnt0 == 100:
                            cnt += cnt0
                            cnt0 = 0
                            if progress:
                                logging.debug(str(cnt) + '/' + str(len(params)))
                    res = True
                self.conn.commit()
            except Exception as exc:
                self.conn.rollback()
                trap_db_exception(exc, sql, params)
        return res

    def get_object(self, table, params, create=None):
        sql = ''
        res = False
        if create != True:
            sql = "select * from %s where %s" %\
                (table,\
                " and ".join([k + " = %(" + k + ")s"\
                    if params[k] != None\
                    else k + " is null"\
                    for k in params.keys()]))
            res = self.execute(sql, params)
        if create or (not res and create != False):
            keys = params.keys()
            sql = "insert into " + table + " (" + \
                ", ".join(keys) + ") values (" + \
                ', '.join(["%(" + k + ")s" for k in keys]) + \
                ") returning *"
            logging.debug('creating object in db')
            res = self.execute(sql, params)
        return res

