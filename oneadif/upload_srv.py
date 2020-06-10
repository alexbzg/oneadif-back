#!/usr/bin/python3
#coding=utf-8

import multiprocessing
from multiprocessing.connection import Listener, Client
import threading
import logging
import time
import uuid
import socket
import signal
import sys
from asyncio import CancelledError

from db import DBConn
from conf import CONF, start_logging
from elog import ELog

UPLOAD_PROCESSES = {}
DB = DBConn(CONF.items('db'))
DB.connect()
DB.verbose = True

class PipeListener(threading.Thread):

    def __init__(self, pipe, callback):
        threading.Thread.__init__(self)
        self.__pipe = pipe
        self.__callback = callback

    def run(self):
        while True:
            data = self.__pipe.recv()
            self.__callback(data)

    def send(self, data):
        self.__pipe.send(data)

class UploadConnector(PipeListener):

    def __init__(self, pipe, upload_process):
        self.upload_id = upload_process.upload_id
        self.__upload_process = upload_process
        super().__init__(pipe, self.on_pipe_data)

    def on_pipe_data(self, state):
        up_record = UPLOAD_PROCESSES[self.upload_id]
        up_record['state'] = state
        up_record['time'] = time.time()
        if state in ['login failed', 'upload failed', 'success', 'cancelled']:
            self.__upload_process.join()
        DB.param_update('uploads', {'upload_id': self.upload_id}, {'state': state})
        logging.debug('upload ' + str(self.upload_id) + ' state: ' + state)

class UploadProcess(multiprocessing.Process):
    STATES = {\
            'init': 0,\
            'login': 1,\
            'login failed': 2,\
            'upload': 3,\
            'upload failed': 4,\
            'success': 5,\
            'cancelled': 6,\
            'internal error': 7}

    def __init__(self, pipe, account_id, file, params):
        logging.debug('upload process init start')
        logging.debug('upload process super init call')
        multiprocessing.Process.__init__(self)
        account = DB.get_object('accounts', {'account_id': account_id})
        self.elog_type = account['elog']
        self.login_data = account['login_data']
        upload_rec = DB.get_object('uploads', {'account_id': account_id}, create=True)
        logging.debug('upload db record created')
        logging.debug(upload_rec)
        self.upload_id = upload_rec['upload_id']
        logging.debug('upload id: ' + str(self.upload_id))
        self.file = file
        self.params = params
        self.status_file_path = CONF['web']['root'] + '/uploads/' + str(self.upload_id)
        self.__progress = 0
        self.__state = 'init'
        self.__pipe = pipe
        self.__export_status()
        logging.debug('upload process status file init')
        self.__cancel_event = threading.Event()
        logging.debug('upload process init completed')

    def on_pipe_data(self, data):
        if data == 'cancel':
            self.__cancel_event.set()

    def __export_status(self):
        with open(self.status_file_path, 'wb') as status_file:
            status_bytes = [UploadProcess.STATES[self.state], int(round(self.progress, 2)*100)]
            status_file.write(bytearray(status_bytes))

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, value):
        if self.__state != value:
            logging.debug('upload ' + str(self.upload_id) + ' state:')
            logging.debug(self.state)
            self.__state = value
            self.__export_status()

    @property
    def progress(self):
        return self.__progress

    @progress.setter
    def progress(self, value):
        if self.__progress != value:
            self.__progress = value
            self.__export_status()

    def __raise_for_cancel(self):
        if self.__cancel_event.is_set():
            raise CancelledError('The upload was cancelled')

    def upload_callback(self, progress):
        logging.debug('upload ' + str(self.upload_id) + ' progress:')
        logging.debug(progress)
        self.progress = progress

    def run(self):
        try:
            logging.debug('upload ' + str(self.upload_id) + ' start')
            pipe_listener = PipeListener(self.__pipe, self.on_pipe_data)
            pipe_listener.start()
            self.state = 'login'
            elog = ELog(self.elog_type)
            self.__raise_for_cancel()
            if elog.login(self.login_data):
                self.__raise_for_cancel()
                self.state = 'upload'
                if elog.upload(self.file, self.params, callback=self.upload_callback,\
                    cancel_event=self.__cancel_event):
                    self.state = 'success'
                else:
                    self.state = 'upload failed'
            else:
                self.state = 'login failed'
        except CancelledError:
            self.state = 'cancelled'
        except Exception:
            self.state = 'internal error'
            logging.exception('Upload thread error')
        finally:
            self.__pipe.send(self.state)

def conn_worker(conn, _up=UPLOAD_PROCESSES):
    logging.debug('Connection received')
    data = conn.recv()
    if data[0] == 'upload':
        logging.debug('start upload')
        pipe_process, pipe_connector = multiprocessing.Pipe()
        logging.debug('pipes created')
        upload_process = UploadProcess(pipe_process, *data[1])
        logging.debug('upload process created, id: ' + str(upload_process.upload_id))
        upload_connector = UploadConnector(pipe_connector, upload_process)
        logging.debug('upload connector created')
        _up[upload_process.upload_id] = {\
            'connector': upload_connector,\
            'state': 'init'}
        upload_process.start()
        upload_connector.start()
        logging.debug('upload process started')
        conn.send(upload_process.upload_id)
        logging.debug('id sent to client')
    elif data[0] == 'cancel':
        upload_id = data[1]
        error = None
        if upload_id in _up:
            upload = _up[upload_id]
            if upload['state'] in ['init', 'login', 'upload']:
                upload['connector'].send('cancel')
            else:
                error = 'Upload cannot be cancelled'
        else:
            error = 'Upload not found'
        conn.send(error if error else 'ok')
    elif data[0] == 'test':
        conn.send(data)
    conn.close()

def __sigterm(signum, frame):
    logging.debug('Term signal')
    sys.exit(0)

def upload_client():
    return Client(CONF['files']['upload_server_socket'], 'AF_UNIX')

def serve_forever(address, family):
    try:
        logging.info('Starting server')
        signal.signal(signal.SIGTERM, __sigterm)
        with Listener(address, family) as listener:
            listener._listener._socket.settimeout(0.1)
            listener._listener._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            while True:
                try:
                    conn = listener.accept()
                    conn_thread = threading.Thread(target=conn_worker, args=(conn,))
                    conn_thread.daemon = True
                    conn_thread.start()
                except socket.timeout:
                    continue
    except Exception as exc:
        logging.exception('Stopping server')
        raise exc

if __name__ == "__main__":
    start_logging('upload_srv', CONF['logs']['upload_srv_level'])
    serve_forever(CONF['files']['upload_server_socket'], 'AF_UNIX')
