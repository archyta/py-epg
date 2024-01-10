import hashlib
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
import json
import requests
import gzip
import shutil


def compress_to_gzip(input_file):
    with open(input_file, 'rb') as f_in:
        with gzip.open(input_file + '.gz', 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)


EPG_INDEX_NO_CHANGE = 0
EPG_INDEX_CHANGED = 1
EPG_INDEX_NOT_FOUND = 2

EPG_URL = 'https://www.bevy.be/bevyfiles/brazil.xml'


def generate_checksum(filename):
    # 打开文件并读取内容
    with open(filename, 'rb') as file:
        data = file.read()

    # 生成 SHA-256 校验和
    _checksum = hashlib.sha256(data).hexdigest()

    return _checksum


def update_epg(xml_file):
    # 解析XML文件
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # 创建一个字典来存储每个channel的programme元素
    programmes_by_channel_and_date = defaultdict(list)
    channels = defaultdict(list)

    for channel in root.iter('channel'):
        # 提取channel的id属性
        channel_id = channel.attrib['id'].lower()
        channels[channel_id].append(channel)

    # 遍历所有的programme元素
    for programme in root.iter('programme'):
        # 提取channel和start属性
        channel = programme.attrib['channel'].lower()
        start = programme.attrib['start']

        # 从start属性中提取日期
        date = datetime.strptime(start, "%Y%m%d%H%M%S %z").date()

        # 将programme元素添加到相应的字典条目中
        programmes_by_channel_and_date[(channel, date)].append(programme)

    epg_index = {}

    # 遍历字典，为每个channel和日期创建一个新的XML文件
    for (channel, date), programmes in programmes_by_channel_and_date.items():
        # 创建一个新的XML树
        new_tree = ET.ElementTree(ET.Element('tv'))
        new_root = new_tree.getroot()
        new_root.append(channels[channel][0])

        # 将programme元素添加到新的XML树中
        for programme in programmes:
            new_root.append(programme)

        # 将新的XML树写入文件
        os.makedirs(f'EPG_DATA/{date}', exist_ok=True)
        file_name = f'EPG_DATA/{date}/{channel}_{date}.xml'
        new_tree.write(file_name, encoding='utf-8')
        if os.path.exists(file_name):
            _sum = generate_checksum(file_name)[0:8]  # 取前8位就够了
            # 重命名文件，加上checksum
            file_name_new = f'EPG_DATA/{date}/{channel}_{date}_{_sum}.xml'
            os.rename(file_name, file_name_new)
            # 压缩成gzip格式
            compress_to_gzip(file_name_new)
            os.unlink(file_name_new)
            file_name_new = f'{file_name_new}.gz'
            date = date.strftime("%Y-%m-%d")
            _epg_index = {'channel': channel, 'date': date, 'checksum': _sum, 'file': file_name_new}
            # 将文件名和checksum添加到epg_index中
            if date not in epg_index:
                epg_index[date] = []
            epg_index[date].append(_epg_index)

    # 将epg_index写入文件，并计算checksum
    index_file = 'EPG_DATA/epg_index.json'
    with open(index_file, 'w') as f:
        json.dump(epg_index, f, indent=4)
    if os.path.exists(index_file):
        _sum = generate_checksum(index_file)[0:8]
        # 将checksum写到checksum.txt文件中
        with open('EPG_DATA/checksum.txt', 'w') as f:
            # 注意，配置CDN访问时，需要设置缓存失效时间（比如1分钟），否则CDN不会重新获取文件
            f.write(_sum)

        # 重命名文件，加上checksum
        index_file_new = f'EPG_DATA/epg_index_{_sum}.json'
        if os.path.exists(index_file_new):  # 如果已经存在，说明没有变化，不用更新
            os.unlink(index_file)
            return _sum, index_file_new
        else:
            # 删除所有旧的epg_index.json文件
            for file in os.listdir('EPG_DATA'):
                if file.startswith('epg_index_') and file.endswith('.json'):
                    os.remove(f'EPG_DATA/{file}')
            os.rename(index_file, index_file_new)
            return _sum, index_file_new  # 返回checksum和文件名，表示已经生成了新的epg_index.json，需要通知客户端更新

    return None, None  # 返回None，表示没有生成epg_index.json


if __name__ == '__main__':
    # 从 URL 下载 EPG 文件
    EPG_FILE = 'EPG_DATA/brazil.xml'
    r = requests.get(EPG_URL)
    with open(EPG_FILE, 'wb') as f:
        f.write(r.content)
    checksum, index = update_epg(EPG_FILE)
