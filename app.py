import os
import time

import requests
from flask import Flask, send_from_directory
from epg import EPG_URL, update_epg
import threading
import schedule
import logging.config

logging.config.fileConfig('logging.ini')
logger = logging.getLogger('app')

app = Flask(__name__)

last_checksum = None
update_lock = threading.Lock()


@app.route('/update')
@app.route('/api/update')
def update_with_lock():
    start_scheduler()
    with update_lock:
        return update()


@app.route('/')
@app.route('/checksum')
@app.route('/api/checksum')
def checksum():
    global last_checksum
    if not last_checksum:
        if os.path.exists('EPG_DATA/checksum.txt'):
            logger.debug('checksum.txt exists, read checksum from it')
            with open('EPG_DATA/checksum.txt', 'r') as f:
                last_checksum = f.read()
        else:
            logger.debug('epg checksum.txt not exists, update epg index')
            update_with_lock()
    return f'{last_checksum}<br/><a href="/EPG_DATA/epg_index_{last_checksum}.json">epg_index_{last_checksum}.json</a>'


@app.route('/EPG_DATA/<path:path>')
def send_epg_data(path):
    return send_from_directory('EPG_DATA', path)


def update():
    global last_checksum
    # 从 URL 下载 EPG 文件
    EPG_FILE = 'EPG_DATA/brazil.xml'
    try:
        if os.path.exists(EPG_FILE):
            os.unlink(EPG_FILE)  # 删除旧的EPG文件
        os.makedirs(os.path.dirname(EPG_FILE), exist_ok=True)
        logger.info(f'从 {EPG_URL} 下载 EPG 文件到 {EPG_FILE}')
        r = requests.get(EPG_URL)
        with open(EPG_FILE, 'wb') as f:
            f.write(r.content)
        _checksum, index = update_epg(EPG_FILE)
        last_checksum = _checksum if _checksum else last_checksum

        # 返回json格式的校验和和epg_index文件名
        return {'code': 0, 'message': 'ok', 'data': {'checksum': checksum, 'index_file': index}}
    except Exception as e:
        return {'code': 1, 'message': str(e), 'data': {}}


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(5)


scheduler_thread = None


@app.route('/api/start')
def start_scheduler():
    global scheduler_thread
    if not scheduler_thread:
        schedule.every(10).minutes.do(update_with_lock)
        logger.info('启动定时任务')
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.start()


if __name__ == '__main__':
    start_scheduler()
    app.run(host='0.0.0.0', port=2096)