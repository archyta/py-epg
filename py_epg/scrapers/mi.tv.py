#!/usr/bin/env python3
import logging
import re
from datetime import date
from datetime import datetime
from pprint import pprint
from string import Template
from typing import List

import roman
from bs4 import BeautifulSoup
from dateutil import tz
from dateutil.parser import parse
from py_epg.common.epg_scraper import EpgScraper
from py_epg.common.utils import clean_text
from xmltv.models import (Actor, Channel, Credits, Desc, DisplayName,Category,
                          EpisodeNum, Icon, Programme, SubTitle, Title)

RE_MIXED_DESCRIPTION = re.compile(
    # Group 1 (opt): (title in orig lang)
    r'^(?:\((.*)\)\n\n)'
    # Group 2 (opt): description
    r'?(?:(.*?)(?=Rendezte:|Rendező:|Főszereplők:|$))?'
    # Group 3 (opt): director
    r'(?:(?:Rendezte:|Rendező:)\s*(.*?)(?=Főszereplők:|$))?'
    # Group 4 (opt): cast
    r'(?:\s*Főszereplők:\s*(.*))?',
    flags=re.S
)

RE_SEASON_EPISODE = re.compile(
    "((?=[MDCLXVI])M*D?C{0,4}L?X{0,4}V?I{0,4})\.\/([0-9]+)\.")
RE_EPISODE_RANGE = re.compile("([0-9]+)\.-([0-9]+)\.")
RE_SINGLE_EPISODE = re.compile("([0-9]+)\.")


class MiTV(EpgScraper):
    def __init__(self, proxy=None, user_agent=None):
        super().__init__(name=__name__, proxy=proxy, user_agent=user_agent)
        self._site_id = "mi.tv"
        # self._base_url = 'https://mi.tv/br/programacao'
        self._base_url = 'https://mi.tv'
        self._page_encoding = 'utf-8'
        self._chan_id_tpl = Template('$chan_id.' + self._site_id)
        self._day_url_tpl = Template(
            self._base_url + '/br/async/channel/$chan_site_id/$date/480')   # https://mi.tv/br/async/channel/record/2024-03-06/480
        # https://mi.tv/br/canais/record/2024-02-23
        # https://mi.tv/br/programacao/2024-02-18
        # https://mi.tv/br/async/channel/record/2024-02-18/480
        self._tz_utc = tz.tzutc()
        self._tz_local = tz.tzlocal()

    def site_name(self) -> str:
        return self._site_id

    def fetch_channel(self, chan_site_id, name) -> Channel:
        today_str = date.today().strftime("%Y-%m-%d")
        url = self._day_url_tpl.substitute(
            chan_site_id=chan_site_id, date=today_str)
        self._log.info(f'Fetching channel {chan_site_id} from {url}')
        soup = self._get_soup(url)
        channel_id = self._chan_id_tpl.substitute(chan_id=chan_site_id).upper()
        channel_logo = soup.select_one('img')
        channel_logo_src = channel_logo.attrs['src'] if channel_logo else None
        return Channel(
            id=channel_id,
            display_name=[DisplayName(content=[name])],
            icon=Icon(src=channel_logo_src) if channel_logo_src else None)

    def fetch_programs(self, channel: Channel, channel_site_id: str, fetch_date: date) -> List[Programme]:
        date_str = fetch_date.strftime("%Y-%m-%d")
        url = self._day_url_tpl.substitute(chan_site_id=channel_site_id, date=date_str)
        channel_daily_progs_page = self._get_soup(url)
        programs_selector = 'a[class="program-link"]'
        programs = []
        for prg in channel_daily_progs_page.select(programs_selector):
            program = self._get_program(channel_site_id, fetch_date, prg)
            if program:
                programs.append(program)
        return programs

    def _get_program(self, chan_site_id: str, fetch_date: date, prg: BeautifulSoup) -> Programme:
        # 1. Fetch basic program info from the daily listing page
        channel_id = self._chan_id_tpl.substitute(chan_id=chan_site_id).upper()
        prg_title = prg.select_one('h2')
        prg_title = prg_title.get_text(strip=True) if prg_title else None
        sub_title = prg.select_one('span[class="sub-title"]')
        sub_title = sub_title.get_text(strip=True) if sub_title else None
        program = Programme(channel=channel_id,
                            title=[Title(content=[prg_title])] if prg_title else None,
                            sub_title=[SubTitle(content=[sub_title])] if sub_title else None,
                            clumpidx=None)

        self._set_prg_sub_title_and_year(program, prg)
        self._set_prg_episode_info(program, prg_title)

        # 2. Fetch category
        prg_category = prg.select_one('span[class="sub-title"]').get_text(strip=True)
        program.category = [prg_category]

        # 2. Fetch extended program info from program details page
        prg_details_link = prg.attrs['href']
        program.url = [self._base_url + prg_details_link]
        prg_details_page = self._get_soup(program.url)

        pg = prg_details_page.select_one('div[class="meta"]')
        if pg:
            pg_title = pg.select_one('h1').get_text(strip=True)
            category = pg.select_one('h2').get_text(strip=True)
            program.category = [Category(content=[category])]
            description = pg.select_one('div[class="description"]').select_one('p').get_text(strip=True)
            program.desc = [Desc(content=[description])]
            lang = prg_details_page.select_one('html')
            lang = lang.attrs['lang'] if lang else 'pt'
            program.title = [Title(content=[pg_title], lang=lang)] if pg_title else program.title

            prg_start = self._set_prg_start_end(program, pg)
            # skip program starting < 00:00 or > 23:59
            # if prg_start.date() != fetch_date:
            #     return None

        # self._set_prg_icon(program, prg_details_page)  # 暂时不取icon
        # self._set_prg_fields_from_mixed_description(program, prg_details_page)

        self._log.trace(
            f'New program CH: {channel_id} ENC: {prg.original_encoding} P: {prg_title}')
        return program

    def _set_prg_start_end(self, program, prg):
        # start = prg.select_one(
        #     'span[itemprop="startDate"]').attrs['content']
        start_timestamp = prg.select_one('span[class="time"]')
        start_timestamp = start_timestamp.attrs['data-raw-start'] if start_timestamp and hasattr(start_timestamp, 'data-raw-start') else None
        end_timestamp = prg.select_one('span[class="time"]')
        end_timestamp = end_timestamp.attrs['data-raw-end'] if end_timestamp and hasattr(end_timestamp, 'data-raw-end') else None
        # 时间戳是毫秒，直接用。不转化。
        program.start = start_timestamp
        program.stop = end_timestamp

        # 如果要转换，调用系统API，转化成UTC时间
        # start = datetime.utcfromtimestamp(int(start_timestamp) / 1000)
        # stop = datetime.utcfromtimestamp(int(end_timestamp) / 1000)
        # start = start.replace(tzinfo=self._tz_utc)
        # start = start.astimezone(self._tz_local)
        # program.start = start.strftime('%Y%m%d%H%M%S %z')
        # program.stop = stop.strftime('%Y%m%d%H%M%S %z')
        return start_timestamp

    def _set_prg_episode_info(self, program, title):
        # TV Shows - Season, Episode info in title
        m0 = RE_SEASON_EPISODE.search(title)
        # m1 = re_episode_range.search(title)
        m2 = RE_SINGLE_EPISODE.search(title)
        if m0 or m2:
            season = 0
            episode = 0
            if m0:
                season = roman.fromRoman(m0.group(1))
                episode = int(m0.group(2))
                title = title.split(str(m0.group()))[0].strip()
            if m2:
                episode = int(m2.group(1))
                title = title.split(str(m2.group()))[0].strip()
            onscreen = f'S{season:02d}E{episode:02d}' if season > 0 else f'S--E{episode:02d}'
            xmltv_ns = f'{season - 1}.{episode - 1}.' if season > 0 else f'.{episode - 1}.'
            program.episode_num = [EpisodeNum(content=[onscreen], system='onscreen'),
                                   EpisodeNum(content=[xmltv_ns], system='xmltv_ns')]
            stripped_title = title.rsplit(' ', 1)[0]
            program.title = [Title(content=[stripped_title], lang='hu')]

    def _set_prg_sub_title_and_year(self, program, prg):
        prg_sub_title = prg.select_one('div[itemprop="description"]')
        if prg_sub_title:
            subtitle = prg_sub_title.get_text(strip=True)
            parts = subtitle.split(',')
            if len(parts) > 1:
                year = parts[-1]
                if '-' in year:
                    # 2005-2010 => pick end year, eg. 2010
                    year = year.split('-')[-1]
                program.date = [year]
                subtitle = SubTitle(content=[','.join(parts[:-1])], lang='hu')
                program.sub_title = [subtitle] + program.sub_title
            else:
                # edge case: no subtitle, just a year
                if subtitle.isnumeric():
                    program.date = [subtitle]
                else:
                    program.sub_title = [subtitle]

    def _set_prg_icon(self, program, prg_details_page):
        prg_icon = prg_details_page.select_one('img[itemprop="image"]')
        if prg_icon:
            program.icon = [Icon(src=self._base_url + prg_icon.attrs['src'])]

    def _set_prg_fields_from_mixed_description(self, program, prg_details_page):
        prg_mixed_desc = clean_text(
            prg_details_page.select_one('div.eventinfolongdescinner')).strip()

        if prg_mixed_desc:
            if len(prg_mixed_desc.splitlines()) == 1:
                program.desc.append(Desc(content=[prg_mixed_desc]))
                return

            # pprint(prg_mixed_desc)
            result = RE_MIXED_DESCRIPTION.search(prg_mixed_desc)
            if result and len(result.groups()):
                # pprint(result.groups())
                # title in orig lang
                if result.group(1):
                    program.title.append(
                        Title(content=[result.group(1)], lang='en'))

                if result.group(2):
                    content = result.group(2).strip()
                    parts = content.split('\n\n')
                    if len(parts) >= 2:
                        # sub-title + description
                        program.sub_title.append(
                            SubTitle(content=[parts[0].strip()]))
                        desc = '\n'.join(parts[1:]).strip()
                        if desc:
                            program.desc.append(Desc(content=[desc]))
                    elif content:
                        # description only
                        program.desc.append(Desc(content=[content]))
                # director, cast
                if result.group(3) or result.group(4):
                    separator = re.compile('[,;]+ ')
                    credits = Credits()
                    if result.group(3):
                        credits.director = separator.split(
                            result.group(3).strip())
                    if result.group(4):
                        actors = separator.split(result.group(4).strip())
                        credits.actor = [Actor(content=[actor])
                                         for actor in actors]
                    program.credits = credits

    def _get_soup(self, url) -> BeautifulSoup:
        page = self._http.get(url)
        return BeautifulSoup(page.text, "html.parser")


if __name__ == '__main__':
    scraper = MiTV()
    chan = scraper.fetch_channel('record', 'record')
    pprint(chan)
    progs = scraper.fetch_programs(chan, 'record', date.today())
    pprint(progs)
    print(f'Fetched {len(progs)} programs.')
    print('Done.')