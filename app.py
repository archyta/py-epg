import os
import requests
from flask import Flask, send_from_directory
from epg import EPG_URL, update_epg

app = Flask(__name__)


@app.route('/EPG_DATA/<path:path>')
def send_epg_data(path):
    return send_from_directory('EPG_DATA', path)


@app.route('/update')
def update():
    # 从 URL 下载 EPG 文件
    EPG_FILE = 'EPG_DATA/brazil.xml'
    try:
        os.unlink(EPG_FILE)  # 删除旧的EPG文件
        r = requests.get(EPG_URL)
        os.makedirs(os.path.dirname(EPG_FILE), exist_ok=True)
        with open(EPG_FILE, 'wb') as f:
            f.write(r.content)
        checksum, index = update_epg(EPG_FILE)

        # 返回json格式的校验和和epg_index文件名
        return {'code': 0, 'message': 'ok', 'data': {'checksum': checksum, 'index_file': index}}
    except Exception as e:
        return {'code': 1, 'message': str(e), 'data': {}}


if __name__ == '__main__':
    app.run(port=2096)
