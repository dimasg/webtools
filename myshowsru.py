#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" myshows.ru utility """

import argparse
import datetime
import http.cookiejar
import json
import logging
#import pprint
import re
from sys import stderr
import urllib


def tr_out(from_str):
    """ translate unshowed symbols """
    return from_str.encode('utf-8').decode('ascii', 'ignore')
#    return from_str.replace(u'\u2026', '...')


class MyShowsRu(object):
    """ work with api.myshows.ru """
    def __init__(self, config_name_name):
        cfg_file = open(config_name_name)
        self.config = json.load(cfg_file)
        logging.debug('Parsed config file %s result: %s', config_name_name, self.config)

        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.logged_ = False
        self.list_loaded_ = False
        self.api_url = 'http://' + self.config['api_domain']
        self.shows_data = {}
        self.episodes_data = {}
        self.watched_data = {}

    def do_login(self):
        """ authorization """
        if self.logged_:
            return
        try:
            req_data = urllib.parse.urlencode({
                'login': self.config['login']['name'],
                'password': self.config['login']['md5pass']
            })
            logging.debug(
                'Login, url: %s%s, data: %s', self.api_url, self.config['url']['login'], req_data
            )
            request = urllib.request.Request(
                self.api_url + self.config['url']['login'], req_data.encode('utf-8')
            )
            handle = self.opener.open(request)
            logging.debug('Login result: %s/%s', handle.headers, handle.readall().decode('utf-8'))
            self.cookie_jar.clear(
                self.config['api_domain'], '/', 'SiteUser[login]'
            )
            self.cookie_jar.clear(
                self.config['api_domain'], '/', 'SiteUser[password]'
            )
        except urllib.error.HTTPError as ex:
            if ex.code == 403:
                stderr.write('Bad login name or password!\n')
            else:
                stderr.write('Login error!\n')
            logging.debug('HTTP error #%s: %s\n', ex.code, ex.read())
            exit(1)
        except urllib.error.URLError as ex:
            stderr.write('Login error!\n')
            logging.debug('URLError - %s\n', ex.reason)
            exit(1)

        self.logged_ = True

    def load_shows(self):
        """ load user shows """
        if self.list_loaded_:
            return
        if not self.logged_:
            self.do_login()
        logging.debug('Login: %s%s', self.api_url, self.config['url']['list_shows'])
        request = urllib.request.Request(
            self.api_url + self.config['url']['list_shows']
        )
        handle = self.opener.open(request)
        self.shows_data = json.loads(handle.readall().decode('utf-8'))
        self.list_loaded_ = True

    def list_all_shows(self):
        """ list all user shows """
        self.load_shows()
        print()
        for show_id in sorted(
            self.shows_data, key=lambda show_id: self.shows_data[show_id]['title']
        ):
            next_show = self.shows_data[show_id]
            if next_show['watchedEpisodes'] <= 0:
                show_sign = '-'
            elif next_show['watchedEpisodes'] < next_show['totalEpisodes']:
                show_sign = '+'
            else:
                show_sign = ' '

            alias = self.alias_by_title(next_show['title'])
            if not alias:
                alias = '-'

            print('{0}{1}({7}): {2}/{3} ({4}%), rating = {5}({6})'.format(
                show_sign,
                tr_out(next_show['title']),
                # next_show['ruTitle'],
                next_show['watchedEpisodes'], next_show['totalEpisodes'],
                100 * next_show['watchedEpisodes'] / next_show['totalEpisodes'],
                next_show['rating'],
                next_show['watchStatus'][0],
                alias
            ))
        print()

    def list_show(self, alias):
        """ list user show by alias """
        re_m = re.match(r'^(.*\D)(\d{1,2}){0,1}$', alias)
        if not re_m:
            print('Bad format for list - "{0}"'.format(alias))
        else:
            season = -1
            if re_m.lastindex == 2:
                season = int(re_m.group(2))
            show_id = self.id_by_title(
                self.title_by_alias(re_m.group(1), no_exit=True)
            )
            epis = self.load_episodes(show_id)
            episodes = epis['episodes']
            list_map = {}
            for epi_id in episodes:
                next_episode = episodes[epi_id]
                if season == -1 or next_episode['seasonNumber'] == season:
                    list_map[
                        next_episode['seasonNumber'] * 1000
                        + next_episode['episodeNumber']
                    ] = next_episode

            watched = self.load_watched(show_id)
            current_season = -1
            for epi_num in sorted(list_map.keys()):
                next_episode = list_map[epi_num]
                next_season = next_episode['seasonNumber']
                if current_season != next_season:
                    current_season = next_season
                    print('{0} Season {1}:'.format(
                        tr_out(epis['title']), current_season
                    ))
                comment = ''
                epi_id = str(next_episode['id'])
                if epi_id in watched:
                    comment = 'watched ' + watched[epi_id]['watchDate']
                print('  "{0}" (s{1:02d}e{2:02d}) {3}'.format(
                    tr_out(next_episode['title']),
                    next_episode['seasonNumber'],
                    next_episode['episodeNumber'],
                    comment
                ))

    def list_shows(self, alias):
        """ list user shows """
        if alias == 'all':
            self.list_all_shows()
        else:
            self.list_show(alias)

    def title_by_alias(self, query, no_exit=False):
        """ return show id by alias """
        logging.debug('title_by_alias(%s)', query)
        alias = query.lower()
        if alias not in self.config['alias']:
            logging.debug('Unknown alias - "%s"', alias)
            if no_exit:
                print('Cannot find alias "{0}", will try it as title!'.format(query))
                return query
            else:
                print('Unknown alias - {0}'.format(query))
                exit(1)
        else:
            logging.debug('title_by_alias(%s) = %s', query, self.config['alias'][alias])
            return self.config['alias'][alias]

    def alias_by_title(self, title):
        """ return show alias by title """
        logging.debug('alias_by_title(%s)', title)
        for alias, a_title in self.config['alias'].items():
            if a_title == title:
                return alias

        return ''

    def id_by_title(self, title):
        """ return show id by title """
        logging.debug('id_by_title(%s)', title)
        if not self.list_loaded_:
            self.load_shows()

        for show_id in self.shows_data:
            next_show = self.shows_data[show_id]
            logging.debug('id_by_title(%s) = %s', next_show['title'], show_id)
            if next_show['title'] == title:
                logging.debug('Found id_by_title(%s) = %s', title, show_id)
                return show_id

        print('Unknown title - {0}'.format(title))
        exit(1)

    def load_episodes(self, show_id):
        """ load episode data by show id """
        if not self.logged_:
            self.do_login()
        if show_id not in self.episodes_data:
            logging.debug(
                'Load episodes: %s%s',
                self.api_url, self.config['url']['list_episodes'].format(show_id)
            )
            request = urllib.request.Request(
                self.api_url + self.config['url']['list_episodes'].format(show_id)
            )
            handle = self.opener.open(request)
            self.episodes_data[show_id] = json.loads(handle.readall().decode('utf-8'))

        return self.episodes_data[show_id]

    def load_watched(self, show_id):
        """ load watched data by show id """
        if not self.logged_:
            self.do_login()
        if show_id not in self.watched_data:
            logging.debug(
                'Load watched: %s%s',
                self.api_url, self.config['url']['list_watched'].format(show_id)
            )
            request = urllib.request.Request(
                self.api_url + self.config['url']['list_watched'].format(show_id)
            )
            handle = self.opener.open(request)
            self.watched_data[show_id] = json.loads(handle.readall().decode('utf-8'))

        return self.watched_data[show_id]

    def get_last_watched(self, show_id):
        """ return last watched episode id for show id """
        logging.debug('Searching last watched for show %s', show_id)
        episodes = self.load_episodes(show_id)['episodes']
        watched = self.load_watched(show_id)

        last_number = 0
        episode_id = None
        for epi_id in watched:
            logging.debug('Next watched id: %s', epi_id)
            next_episode = episodes[epi_id]
            logging.debug(
                'Trying next episode: %s - %s (id: %s/seq: %s)',
                next_episode['shortName'], next_episode['title'],
                next_episode['id'], next_episode['sequenceNumber']
            )
            if last_number < next_episode['sequenceNumber']:
                last_number = next_episode['sequenceNumber']
                episode_id = epi_id
                logging.debug(
                    'Saved next last episode: %s - %s (id: %s)',
                    next_episode['shortName'], next_episode['title'], episode_id
                )

        logging.debug('Found last watched %s', episode_id)

        return episode_id

    def show_last_watched_by_alias(self, alias):
        """ show last watched episode for alias """
        show_id = self.id_by_title(self.title_by_alias(alias, no_exit=True))
        epis = self.load_episodes(show_id)
        watched = self.load_watched(show_id)
        episode_id = self.get_last_watched(show_id)
        print()
        if episode_id is None:
            print('{0} is unwatched'.format(tr_out(epis['title'])))
        else:
            episode = epis['episodes'][episode_id]
            print('Last for {0} is s{1:02d}e{2:02d} ("{3}") at {4}'.format(
                tr_out(epis['title']),
                episode['seasonNumber'], episode['episodeNumber'],
                tr_out(episode['title']),
                watched[episode_id]['watchDate']
            ))
        print()

    def show_last_watched_by_date(self, alias):
        """ show last watched episode(s) for date """
        date_to = datetime.date.today()
        if alias == 'day':
            date_from = date_to + datetime.timedelta(days=-1)
        elif alias == 'week':
            date_from = date_to + datetime.timedelta(days=-7)
        elif alias == 'month':
            prev_month = date_to.replace(day=1) + datetime.timedelta(days=-1)
            date_from = date_to + datetime.timedelta(days=-prev_month.day)
        else:
            print('Unknown alias - {0}'.format(alias))
            exit(1)

        self.load_shows()
        print()
        print('Watched from {0} to {1}'.format(
            date_from.strftime('%Y-%m-%d'),
            date_to.strftime('%Y-%m-%d')
        ))
        print()
        re_c = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')
        count = 0
        for show_id in self.shows_data:
            next_show = self.shows_data[show_id]
            if next_show['watchedEpisodes'] <= 0:
                continue
            watched = self.load_watched(next_show['showId'])
            epis = None
            last_map = {}
            for epi_id in watched:
                next_episode = watched[epi_id]
                re_m = re_c.match(next_episode['watchDate'])
                if not re_m:
                    print('Warning: unknown date format - {0}'.format(
                        next_episode['watchDate']))
                    continue
                dtv = [int(s) for s in re_m.group(3, 2, 1)]
                epi_date = datetime.date(dtv[0], dtv[1], dtv[2])
                if date_from <= epi_date and epi_date <= date_to:
                    if not epis:
                        epis = self.load_episodes(show_id)
                    count += 1
                    if epi_id not in epis['episodes']:
                        print('Episode not found: {0}'.format(epi_id))
                        logging.debug('Episodes:')
                        logging.debug(epis)
                        continue
                    else:
                        episode = epis['episodes'][epi_id]
                        date_key = epi_date.toordinal() * 1000\
                            + episode['seasonNumber'] * 10\
                            + episode['episodeNumber']
                        last_map[date_key] = episode

            for date_key in sorted(last_map.keys()):
                episode = last_map[date_key]
                print('{0} s{1:02d}e{2:02d} "{3}" at {4}'.format(
                    tr_out(epis['title']),
                    episode['seasonNumber'], episode['episodeNumber'],
                    tr_out(episode['title']),
                    watched[str(episode['id'])]['watchDate']
                ))
        print()
        print('Total count: {0}'.format(count))
        print()

    def show_last_watched(self, query):
        """ show last watched episode(s) """
        alias = query.lower()
        if alias in ['day', 'week', 'month']:
            self.show_last_watched_by_date(alias)
        else:
            self.show_last_watched_by_alias(query)

    def get_first_unwatched(self, show_id):
        """ return first unwathced episode for show id """
        logging.debug('Searching first unwatched for show %s', show_id)
        episodes = self.load_episodes(show_id)['episodes']
        last_watched = self.get_last_watched(show_id)
        if last_watched is None:
            last_watched = 0
        else:
            logging.debug(
                'Last watched is: %s - %s (%s)',
                episodes[last_watched]['shortName'], episodes[last_watched]['title'],
                episodes[last_watched]['sequenceNumber']
            )
            last_watched = episodes[last_watched]['sequenceNumber']

        logging.debug('Last watched: %s', last_watched)

        episode_id = None
        first_unwatched = None
        for epi_id in episodes:
            next_episode = episodes[epi_id]
            logging.debug(
                'Trying next episode: %s - %s (%s)',
                next_episode['shortName'], next_episode['title'],
                next_episode['sequenceNumber']
            )
            if (
                (first_unwatched > next_episode['sequenceNumber']
                or not first_unwatched)
                and last_watched < next_episode['sequenceNumber']
            ):
                #
                first_unwatched = next_episode['sequenceNumber']
                episode_id = epi_id
                logging.debug(
                    'Saved next last unwatched: %s - %s (%s)',
                    next_episode['shortName'], next_episode['title'],
                    next_episode['sequenceNumber']
                )

        return episode_id

    def show_next_for_watch(self, alias):
        """ show next episode for watch for alias """
        show_id = self.id_by_title(self.title_by_alias(alias, no_exit=True))
        epis = self.load_episodes(show_id)
        episode_id = self.get_first_unwatched(show_id)
        if episode_id is None:
            print("\nCannot find first watch for {0}\n".format(tr_out(epis['title'])))
        else:
            episode = epis['episodes'][episode_id]
            print('\nFirst watch for {0} is s{1:02d}e{2:02d} ("{3}")\n'.format(
                tr_out(epis['title']),
                episode['seasonNumber'], episode['episodeNumber'],
                tr_out(episode['title']),
            ))

    def set_episode_check(self, alias, epi, check):
        """ set epi episode as watched """
        re_m = re.match(r's(\d{1,2})e(\d{1,2})', epi.lower())
        if not re_m:
            print('Bad format for check - "{0}"'.format(epi))
        else:
            season = int(re_m.group(1))
            episode = int(re_m.group(2))
            show_id = self.id_by_title(self.title_by_alias(alias, no_exit=True))
            epis = self.load_episodes(show_id)
            watched = self.load_watched(show_id)
            episodes = epis['episodes']
            for epi_id in episodes:
                next_episode = episodes[epi_id]
                if (
                    next_episode['seasonNumber'] == season
                    and next_episode['episodeNumber'] == episode
                ):
                    valid_op = False
                    old_date = ''
                    if check:
                        msg = 'checked'
                        if epi_id in watched:
                            old_date = watched[epi_id]['watchDate']
                        else:
                            url = self.config['url']['check_episode'].format(epi_id)
                            valid_op = True
                    else:
                        msg = 'unchecked'
                        if epi_id in watched:
                            url = self.config['url']['uncheck_episode'].format(epi_id)
                            valid_op = True

                    if not valid_op:
                        print()
                        print('Episode "{0}" (s{1:02d}e{2:02d}) of "{3}" already {4} {5}'\
                             .format(
                                 tr_out(next_episode['title']),
                                 next_episode['seasonNumber'],
                                 next_episode['episodeNumber'],
                                 tr_out(epis['title']),
                                 msg,
                                 old_date
                             ))
                    else:
                        logging.debug('Set checked: %s%s', self.api_url, url)
                        request = urllib.request.Request(self.api_url + url)
                        self.opener.open(request)
                        print()
                        print(
                            'Episode "{0}" (s{1:02d}e{2:02d}) of "{3}" set {4}'\
                            .format(
                                tr_out(next_episode['title']),
                                next_episode['seasonNumber'],
                                next_episode['episodeNumber'],
                                tr_out(epis['title']),
                                msg
                            ))
                    break

    def search_show(self, query):
        """ search show """
        if not self.logged_:
            self.do_login()
        req_data = urllib.parse.urlencode({
            'q': query,
        })
        logging.debug(
            'Search url/data: %s%s%s',
            self.api_url, self.config['url']['search'], req_data
        )
        request = urllib.request.Request(
            self.api_url + self.config['url']['search'], req_data.encode('utf-8')
        )
        handle = self.opener.open(request)
        search_result = json.loads(handle.readall().decode('utf-8'))
        logging.debug('Search result: %s', search_result)
        return search_result

    def show_search_result(self, query):
        """ show search result """
        search_result = self.search_show(query)
        print()
        for show_id in search_result:
            show = search_result[show_id]
            print('"{1}", started: {2} (id={0})'.format(
                show_id, tr_out(show['title']), show['started']
            ))
        print()

    def set_show_status(self, alias, status, accurate):
        """ set show status """
        title = self.title_by_alias(alias, no_exit=True)

        search_result = self.search_show(title)
        for show_id in search_result:
            show = search_result[show_id]
            if accurate and show['title'] != alias:
                continue
            url = self.config['url']['status'].format(show['id'], status)
            logging.debug('Set show status: %s%s', self.api_url, url)
            request = urllib.request.Request(self.api_url + url)
            self.opener.open(request)
            print('Show "{0}" status set to {1}'.format(
                tr_out(show['title']), status
            ))
            print()


def main():
    """ main subroutine """
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(help='commands')

    list_parser = subparsers.add_parser('list', help='show list of show(s)')
    list_parser.add_argument(
        'list_alias', default='all',
        action='store', help='show alias for list one show'
    )

    last_parser = subparsers.add_parser('last', help='show last watched')
    last_parser.add_argument(
        'last_alias', action='store',
        help='show alias or period - day, week of month'
    )

    next_parser = subparsers.add_parser('next', help='show next to watch')
    next_parser.add_argument('next_alias', action='store', help='next alias')

    check_parser = subparsers.add_parser(
        'check', help='check episode as watched, gaS01E02 for example'
    )
    check_parser.add_argument(
        'check_alias', action='store', help='show alias'
    )
    check_parser.add_argument(
        'episode', action='store', help='episode'
    )
    uncheck_parser = subparsers.add_parser(
        'uncheck', help='uncheck episode as watched, tgS01E02 for example'
    )
    uncheck_parser.add_argument(
        'uncheck_alias', action='store', help='show alias'
    )
    uncheck_parser.add_argument(
        'episode', action='store', help='episode'
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
    status_parser.add_argument(
        '--accurate', action='store_const',
        const=True, default=False,
        help='Exact name comparsion'
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

    logging.basicConfig(
        level=cmd_args.debug,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.debug('Parsed command line args: %s', cmd_args)

    myshows = MyShowsRu(cmd_args.config)

    if 'list_alias' in cmd_args:
        myshows.list_shows(cmd_args.list_alias)
    elif 'last_alias' in cmd_args:
        myshows.show_last_watched(cmd_args.last_alias)
    elif 'next_alias' in cmd_args:
        myshows.show_next_for_watch(cmd_args.next_alias)
    elif 'check_alias' in cmd_args:
        myshows.set_episode_check(cmd_args.check_alias, cmd_args.episode, True)
    elif 'uncheck_alias' in cmd_args:
        myshows.set_episode_check(
            cmd_args.uncheck_alias, cmd_args.episode, False
        )
    elif 'search_alias' in cmd_args:
        myshows.show_search_result(cmd_args.search_alias)
    elif 'status_alias' in cmd_args:
        myshows.set_show_status(cmd_args.status_alias, cmd_args.status_value, cmd_args.accurate)
    else:
        parser.print_usage()

    exit(0)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4
