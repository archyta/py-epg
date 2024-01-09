#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
from pymongo import MongoClient
from datetime import datetime
import json


def xml_to_dict(xml_file):
    # 读取XML文件
    with open(xml_file, 'r') as f:
        xml_string = f.read()
    # 解析XML
    element = ET.fromstring(xml_string)

    # 创建一个字典来保存元素的数据
    element_dict = {element.tag: {} if element.attrib else None}
    children = list(element)
    if children:
        dd = {}
        for dc in map(xml_to_dict, children):
            for k, v in dc.items():
                if k not in dd:
                    dd[k] = v
                else:
                    if type(dd[k]) is list:
                        dd[k].append(v)
                    else:
                        dd[k] = [dd[k], v]
        element_dict = {element.tag: dd}
    if element.attrib:
        element_dict[element.tag].update(('@' + k, v) for k, v in element.attrib.items())
    if element.text:
        text = element.text.strip()
        if children or element.attrib:
            if text:
                element_dict[element.tag]['#text'] = text
        else:
            element_dict[element.tag] = text
    return element_dict


def parse_programme(xml_dict):
    channels = {}
    programme = xml_dict['tv']['programme'] if 'tv' in xml_dict and 'programme' in xml_dict['tv'] else None
    for p in programme:
        p_date = datetime.strptime(p['@start'], "%Y%m%d%H%M%S %z").strftime("%Y-%m-%d") if '@start' in p else None
        channel = p['@channel'].lower() if '@channel' in p else None
        channels[channel][p_date]['programme'] = p if p_date in channels[channel] else None
        p['@channel'] = p['@channel'].split('.')[0]

    # xml_dict = xml_to_dict(root)
    # # 转换为JSON
    # json_data = json.dumps(xml_dict, indent=4)


def parse_and_store_epgs():
    # Parse the XML file
    tree = ET.parse('epg.xml')
    root = tree.getroot()

    # Initialize a dictionary to store the programmes
    programmes = {}

    # Iterate over all programme elements in the XML tree
    for programme in root.iter('programme'):
        # Extract the start and stop attributes
        start = programme.attrib['start']
        stop = programme.attrib['stop']

        # Extract the date from the start and stop attributes
        date = datetime.strptime(start, "%Y%m%d%H%M%S %z").date()

        # Add the programme to the dictionary
        if date not in programmes:
            programmes[date] = []
        programmes[date].append(programme.attrib)

    # Create a MongoDB client
    client = MongoClient('mongodb://localhost:27017/')

    # Connect to your database
    db = client['epg']

    # Insert the programmes into the database
    for date, progs in programmes.items():
        db.programmes.insert_one({'date': date, 'programmes': progs})


if __name__ == '__main__':
    dt = xml_to_dict('guide.xml')
    js = dict_to_json(dt)
    parse_and_store_epgs()
