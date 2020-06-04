#!/usr/bin/python3
#coding=utf-8

import multiprocessing
from multiprocessing.connection import Listener
import threading
import logging
import time
import uuid
import socket
import signal
import sys
from asyncio import CancelledError

from db import DBConn, splice_params
from conf import CONF, start_logging
from elog import ELog

UPLOAD_PROCESSES = {}
DB = DBConn(CONF.items('db'))
DB.connect()
DB.verbose = True

class PipeListener(threading.Thread):

    def __init__(self, pipe, callback):
        self.__pipe = pipe
        self.__callback = callback
        super().__init__(self)

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
        super().__init__(self, self.on_pipe_data)

    def on_pipe_data(self, state):
        up_record = UPLOAD_PROCESSES[self.upload_id]
        up_record['state'] = state
        up_record['time'] = time.time()
        if state in ['login failed', 'upload failed', 'success', 'cancelled']:
            self.__upload_process.join()

class UploadProcess(multiprocessing.Process):
    STATES = {\
            'init': 0,\
            'login': 1,\
            'login failed': 2,\
            'upload': 3,\
            'upload failed': 4,\
            'success': 5,\
            'cancelled': 6}

    def __init__(self, pipe, elog_type, login_data, file, params):
        self.upload_id = str(uuid.uuid1())
        self.elog_type = elog_type
        self.login_data = login_data
        self.file = file
        self.params = params
        self.status_file_path = CONF['web']['root'] + '/uploads/' + self.upload_id
        self.__progress = 0
        self.__state = 'init'
        self.__pipe = pipe
        self.__export_status()
        self.__cancel_event = threading.Event()
        super().__init__(self)

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
            logging.debug('upload ' + self.upload_id + ' state:')
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
        logging.debug('upload ' + self.upload_id + ' progress:')
        logging.debug(progress)
        self.progress = progress

    def __call__(self):
        try:
            logging.debug('upload ' + self.upload_id + ' start')
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
    logging.debug('Received data:')
    logging.debug(data)
    if data[0] == 'upload':
        pipe_process, pipe_connector = multiprocessing.Pipe()
        upload_process = UploadProcess(pipe_process, *data[1])
        upload_connector = UploadConnector(pipe_connector, upload_process)
        _up[upload_process.upload_id] = {\
            'connector': upload_connector,\
            'state': 'init'}
        upload_process.start()
        upload_connector.start()
        conn.send(upload_process.upload_id)
    elif data[0] == 'cancel':
        upload_id = data[0]
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