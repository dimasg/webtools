#!/usr/bin/python
# -*- coding: utf-8 -*-
""" myshows.ru utility """

import argparse
import cookielib
import json
import logging
#import pprint
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
            'Login url:{0}{1}'.format(self.api_url, self.config.url.login)
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

            print '{0}{1}: {2}/{3}, rating = {4}, '.format(
                    show_sign,
                    next_show['title'],
                    # next_show['ruTitle'],
                    next_show['watchedEpisodes'], next_show['totalEpisodes'],
                    next_show['rating']
                )

    def title_by_alias(self, alias):
        """ return show id by alias """
        logging.debug('title_by_alias({0})'.format(alias))
        if alias not in self.config.alias:
            print 'Unknown alias - {0}'.format(alias)
            exit(1)
        else:
            return self.config.alias[alias]

    def id_by_title(self, title):
        """ return show id by title """
        logging.debug('id_by_title({0})'.format(title))
        if not self.list_loaded_:
            self.load_shows()

        for show_id in self.shows_data:
            next_show = self.shows_data[show_id]
            if next_show['title'] == title:
                return next_show['showId']

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
        show_id = self.id_by_title(self.title_by_alias(alias))
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
        show_id = self.id_by_title(self.title_by_alias(alias))
        epis = self.load_episodes(show_id)
        episode_id = self.get_first_unwatched(show_id)
        episode = epis['episodes'][episode_id]
        print
        print 'First watch for {0} is s{1:02d}e{2:02d} ("{3}")'.format(
                epis['title'],
                episode['seasonNumber'], episode['episodeNumber'],
                episode['title'],
            )


def main():
    """ main subroutine """
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(help='commands')

    list_parser = subparsers.add_parser('list', help='show list of show')
    list_parser.set_defaults(list=True)

    last_parser = subparsers.add_parser('last', help='show last watched')
    last_parser.add_argument('last_alias', action='store', help='show alias')

    next_parser = subparsers.add_parser('next', help='show next to watch')
    next_parser.add_argument('next_alias', action='store', help='show alias')

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

    exit(0)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4
