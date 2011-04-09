#!/usr/bin/python
# -*- coding: utf-8 -*-
""" myshows.ru utility """

import argparse
import cookielib
import json
import logging
#import pprint
import re
import urllib
import urllib2

import config


class MyShowsRu:
    """ work with api.myshows.ru """
    def __init__(self, config_name_name):
        cfg_file = file(config_name_name)
        self.config = config.Config(cfg_file)
        logging.info('Config file {0} loaded!'.format(config_name_name))
        self.cookie_jar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(
                urllib2.HTTPCookieProcessor(self.cookie_jar)
            )
        self.logged_ = False
        self.list_loaded_ = False
        self.api_url = 'http://' + self.config.api_domain
        self.shows_data = {}
        self.episodes_data = {}
        self.watched_data = {}

    def do_login(self):
        """ authorization """
        if self.logged_:
            return
        req_data = urllib.urlencode({
            'login': self.config.login.name,
            'password': self.config.login.md5pass},
            )
        logging.debug(
            'Login url:{0}{1}{2}'.format(
                self.api_url, self.config.url.login, req_data
            )
        )
        request = urllib2.Request(
            self.api_url + self.config.url.login, req_data
        )
        # handle = urllib2.urlopen(request)
        handle = self.opener.open(request)
        logging.debug('Login result: {0}/{1}'.format(
            handle.headers, handle.read())
        )
        self.cookie_jar.clear(
            self.config.api_domain, '/', 'SiteUser[login]'
        )
        self.cookie_jar.clear(
            self.config.api_domain, '/', 'SiteUser[password]'
        )
        self.logged_ = True

    def load_shows(self):
        """ load user shows """
        if self.list_loaded_:
            return
        if not self.logged_:
            self.do_login()
        logging.debug(
            'Login: {0}{1}'.format(self.api_url, self.config.url.list_shows)
        )
        request = urllib2.Request(
            self.api_url + self.config.url.list_shows
        )
        handle = self.opener.open(request)
        self.shows_data = json.loads(handle.read())
        self.list_loaded_ = True

    def list_shows(self):
        """ list user shows """
        if not self.list_loaded_:
            self.load_shows()

        print
        for show_id in self.shows_data:
            next_show = self.shows_data[show_id]
            if next_show['watchedEpisodes'] <= 0:
                show_sign = '-'
            elif next_show['watchedEpisodes'] < next_show['totalEpisodes']:
                show_sign = '+'
            else:
                show_sign = ' '

            print '{0}{1}: {2}/{3}, rating = {4}({5})'.format(
                    show_sign,
                    next_show['title'],
                    # next_show['ruTitle'],
                    next_show['watchedEpisodes'], next_show['totalEpisodes'],
                    next_show['rating'],
                    next_show['watchStatus'][0]
                )
        print

    def title_by_alias(self, alias):
        """ return show id by alias """
        logging.debug('title_by_alias({0})'.format(alias))
        if alias not in self.config.alias:
            print 'Unknown alias - {0}'.format(alias)
            exit(1)
        else:
            logging.debug(
                'title_by_alias({0}) = {1}'.format(
                    alias, self.config.alias[alias]
                ))
            return self.config.alias[alias]

    def id_by_title(self, title):
        """ return show id by title """
        logging.debug('id_by_title({0})'.format(title))
        if not self.list_loaded_:
            self.load_shows()

        for show_id in self.shows_data:
            next_show = self.shows_data[show_id]
            if next_show['title'] == title:
                logging.debug('id_by_title({0}) = {1}'.format(title, show_id))
                return show_id

        return None

    def load_episodes(self, show_id):
        """ load episode data by show id """
        if not self.logged_:
            self.do_login()
        if show_id not in  self.episodes_data:
            logging.debug(
                'Load episodes: {0}{1}'.format(
                    self.api_url, self.config.url.list_episodes.format(show_id)
            ))
            request = urllib2.Request(
                self.api_url + self.config.url.list_episodes.format(show_id)
            )
            handle = self.opener.open(request)
            self.episodes_data[show_id] = json.loads(handle.read())

        return self.episodes_data[show_id]

    def load_watched(self, show_id):
        """ load watched data by show id """
        if not self.logged_:
            self.do_login()
        if show_id not in  self.watched_data:
            logging.debug(
                'Load watched: {0}{1}'.format(
                    self.api_url, self.config.url.list_watched.format(show_id)
            ))
            request = urllib2.Request(
                self.api_url + self.config.url.list_watched.format(show_id)
            )
            handle = self.opener.open(request)
            self.watched_data[show_id] = json.loads(handle.read())

        return self.watched_data[show_id]

    def get_last_watched(self, show_id):
        """ return last watched episode for show id """
        episodes = self.load_episodes(show_id)['episodes']
        watched = self.load_watched(show_id)

        last_number = 0
        episode_id = None
        for epi_id in watched:
            next_episode = episodes[epi_id]
            if last_number < next_episode['sequenceNumber']:
                last_number = next_episode['sequenceNumber']
                episode_id = epi_id

        return episode_id

    def show_last_watched(self, alias):
        """ show last watched episode for alias """
        show_id = self.id_by_title(self.title_by_alias(alias.lower()))
        epis = self.load_episodes(show_id)
        watched = self.load_watched(show_id)
        episode_id = self.get_last_watched(show_id)
        episode = epis['episodes'][episode_id]
        print
        print 'Last for {0} is s{1:02d}e{2:02d} ("{3}") at {4}'.format(
                epis['title'],
                episode['seasonNumber'], episode['episodeNumber'],
                episode['title'],
                watched[episode_id]['watchDate']
            )

    def get_first_unwatched(self, show_id):
        """ return first unwathced episode for show id """
        episodes = self.load_episodes(show_id)['episodes']
        last_watched = \
            episodes[self.get_last_watched(show_id)]['sequenceNumber']

        episode_id = 0
        first_unwatched = None
        for epi_id in episodes:
            next_episode = episodes[epi_id]
            if (first_unwatched > next_episode['sequenceNumber']\
                    or not first_unwatched)\
                and last_watched < next_episode['sequenceNumber']:
                #
                first_unwatched = next_episode['sequenceNumber']
                episode_id = epi_id

        return episode_id

    def show_next_for_watch(self, alias):
        """ show next episode for watch for alias """
        show_id = self.id_by_title(self.title_by_alias(alias.lower()))
        epis = self.load_episodes(show_id)
        episode_id = self.get_first_unwatched(show_id)
        episode = epis['episodes'][episode_id]
        print
        print 'First watch for {0} is s{1:02d}e{2:02d} ("{3}")'.format(
                epis['title'],
                episode['seasonNumber'], episode['episodeNumber'],
                episode['title'],
            )

    def set_episode_check(self, epi, check):
        """ set epi episode as watched """
        re_m = re.match('(\w+)s(\d{1,2})e(\d{1,2})', epi.lower())
        if not re_m:
            print 'Bad format for check - "{0}"'.format(epi)
        else:
            alias = re_m.group(1)
            season = int(re_m.group(2))
            episode = int(re_m.group(3))
            epis = self.load_episodes(
                self.id_by_title(self.title_by_alias(alias))
            )
            episodes = epis['episodes']
            for epi_id in episodes:
                next_episode = episodes[epi_id]
                if next_episode['seasonNumber'] == season\
                  and next_episode['episodeNumber'] == episode:
                    if check:
                        url = self.config.url.check_episode.format(epi_id)
                        msg = 'checked'
                    else:
                        url = self.config.url.uncheck_episode.format(epi_id)
                        msg = 'unchecked'
                    logging.debug(
                            'Set checked: {0}{1}'.format(self.api_url, url))
                    request = urllib2.Request(self.api_url + url)
                    self.opener.open(request)
                    print
                    print \
                        'Episode "{0}" (s{1:02d}e{2:02d}) of "{3}" set {4}'\
                        .format(next_episode['title'],
                                next_episode['seasonNumber'],
                                next_episode['episodeNumber'],
                                epis['title'],
                                msg)
                    break

    def search_show(self, query):
        """ search show """
        if not self.logged_:
            self.do_login()
        req_data = urllib.urlencode({
            'q': query,
            })
        logging.debug(
            'Search url/data:{0}{1}{2}'.format(
                self.api_url, self.config.url.search, req_data
            )
        )
        request = urllib2.Request(
            self.api_url + self.config.url.search, req_data
        )
        handle = self.opener.open(request)
        search_result = json.loads(handle.read())
        logging.debug('Search result: {0}'.format(search_result))
        return search_result

    def show_search_result(self, query):
        """ show search result """
        search_result = self.search_show(query)
        print
        for show_id in search_result:
            show = search_result[show_id]
            print '"{1}", started: {2} (id={0})'.format(
                    show_id, show['title'], show['started']
            )

    def set_show_status(self, alias, status):
        """ set show status """
        search_result = self.search_show(self.title_by_alias(alias.lower()))
        for show_id in search_result:
            show = search_result[show_id]
            url = self.config.url.status.format(show['id'], status)
            logging.debug(
                    'Set show status: {0}{1}'.format(self.api_url, url))
            request = urllib2.Request(self.api_url + url)
            self.opener.open(request)
            print
            print 'Show "{0}" status set to {1}'.format(show['title'], status)


def main():
    """ main subroutine """
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(help='commands')

    list_parser = subparsers.add_parser('list', help='show list of show')
    list_parser.set_defaults(list=True)

    last_parser = subparsers.add_parser('last', help='show last watched')
    last_parser.add_argument('last_alias', action='store', help='show alias')

    next_parser = subparsers.add_parser('next', help='show next to watch')
    next_parser.add_argument('next_alias', action='store', help='next alias')

    check_parser = subparsers.add_parser(
        'check', help='check episode as watched, gaS01E02 for example'
    )
    check_parser.add_argument(
        'check_alias', action='store', help='check alias'
    )
    uncheck_parser = subparsers.add_parser(
        'uncheck', help='uncheck episode as watched, tgS01E02 for example'
    )
    uncheck_parser.add_argument(
        'uncheck_alias', action='store', help='uncheck alias'
    )
    search_parser = subparsers.add_parser(
        'search', help='search show'
    )
    search_parser.add_argument(
        'search_alias', action='store', help='search alias'
    )
    status_parser = subparsers.add_parser(
        'status', help='set show status'
    )
    status_parser.add_argument(
        'status_alias', action='store', help='show alias'
    )
    status_parser.add_argument(
        'status_value', action='store', help='show status',
        choices=['watching', 'later', 'cancelled', 'remove']
    )

    parser.add_argument(
        '--debug', action='store_const',
        const=logging.DEBUG, default=logging.ERROR,
        help='debug output'
    )
    parser.add_argument(
        '--config', action='store', default='myshows.cfg',
        help='config file'
    )
    parser.add_argument(
        '--info', action='store_const', dest='debug',
        const=logging.INFO, default=logging.ERROR,
        help='info output'
    )
    cmd_args = parser.parse_args()

    logging.basicConfig(level=cmd_args.debug,
            format='%(asctime)s %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
    logging.debug('Parsed command line args: {0}'.format(cmd_args))

    myshows = MyShowsRu(cmd_args.config)

    if 'list' in cmd_args:
        myshows.list_shows()
    elif 'last_alias' in cmd_args:
        myshows.show_last_watched(cmd_args.last_alias)
    elif 'next_alias' in cmd_args:
        myshows.show_next_for_watch(cmd_args.next_alias)
    elif 'check_alias' in cmd_args:
        myshows.set_episode_check(cmd_args.check_alias, True)
    elif 'uncheck_alias' in cmd_args:
        myshows.set_episode_check(cmd_args.uncheck_alias, False)
    elif 'search_alias' in cmd_args:
        myshows.show_search_result(cmd_args.search_alias)
    elif 'status_alias' in cmd_args:
        myshows.set_show_status(cmd_args.status_alias, cmd_args.status_value)
    else:
        parser.print_usage()

    exit(0)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4
