import os.path
import backoff
import datetime
import dateutil.parser
import dateutil.tz
import requests

from cashier import cache
from .arr import ARR
from ..helpers.misc import (backoff_handler, dict_merge, number_suffix)
from ..utils.log import logger
from ..utils.config import Config

log = logger.get_logger(__name__)
cachefile = Config().cachefile


class Radarr(ARR):

    def __init__(self, cfg):
        self.cfg = cfg
        ARR.__init__(self, cfg['radarr']['baseurl'], cfg['radarr']['api_key'])

    def get_objects(self):
        return self._get_objects('movie')

    def get_exclusions(self):
        return self._get_objects('exclusions')

    @cache(cache_file=cachefile, cache_time=300, retry_if_blank=True)
    def get_all_movies(self):
        return self._get_objects('movie')

    @cache(cache_file=cachefile, cache_time=300, retry_if_blank=True)
    def _tags(self):
        _tags = {}
        for d in self._get_objects('tag'):
            _tags[d['label']] = d['id']
        return _tags

    @property
    def tags(self):
        return self._tags()

    def get_stats(self, downloaded=False, available=True):
        high_rating = 0
        high_votes = 0
        oldest = datetime.datetime.now(dateutil.tz.tzutc())
        for movie in self.get_all_movies():
            if movie['downloaded'] == downloaded and movie['isAvailable'] == available:
                if movie['ratings']:
                    if movie['ratings']['votes'] and movie['ratings']['votes'] > high_votes:
                        high_votes = movie['ratings']['votes']
                    if movie['ratings']['value'] and movie['ratings']['value'] > high_rating:
                        high_rating = movie['ratings']['value']
                    if movie['inCinemas'] and dateutil.parser.parse(movie['inCinemas']) < oldest:
                        oldest = dateutil.parser.parse(movie['inCinemas'])
        return dict(
            highest_rating=high_rating,
            highest_votes=high_votes,
            oldest=oldest,
        )

    @backoff.on_predicate(backoff.expo, lambda x: x is None, max_tries=4, on_backoff=backoff_handler)
    def _command(self, endpoint, data=None, method='get', success_status_code=200):
        try:
            # make request
            req = requests.request(
                method=method,
                url=self.server_url + '/api/' + endpoint,
                headers=self.headers,
                json=data,
                timeout=60,
                allow_redirects=False
            )
            log.debug("Request URL: %s %s", method.upper(), req.url)
            log.debug("Request Data: %s", data)
            log.debug("Request Response: %d", req.status_code)

            if req.status_code == success_status_code:
                resp_json = req.json()
                return resp_json
            else:
                log.error("Failed, request response: %d", req.status_code)
        except Exception:
            log.exception("Exception retrieving objects: ")
        return None

    def movie_search(self, id):
        return self._command(
            method='post',
            endpoint='command',
            data={'name': 'MoviesSearch',
                  'movieIds': [id]},
            success_status_code=201)

    def movie_delete(self, id, delete_files=True, add_exclusion=False):
        return self._command(
            method='delete',
            endpoint="/movie/{}".format(id),
            data={'id': [id],
                  'deleteFiles': delete_files,
                  'addExclusion': add_exclusion}) == {}

    def search_missing_oldest(self, cutoff=0.99, stage=False):
        oldest = self.get_stats()['oldest']
        adjustment_days = (datetime.datetime.now(dateutil.tz.tzutc()) - oldest).days * (1-cutoff)
        adjustment = datetime.timedelta(days=adjustment_days)
        log.debug("Searching for Movies older than %s", (oldest + adjustment).strftime('%x'))
        for movie in self.get_all_movies():
            if not movie['downloaded'] and movie['isAvailable']:
                if movie['inCinemas'] and dateutil.parser.parse(movie['inCinemas']) <= oldest + adjustment:
                    title = "{m[title]} ({m[year]})".format(m=movie)
                    id = movie['id']
                    if stage:
                        log.info('STAGE: Trigger Search for [%s] %s', id, title)
                    elif self.movie_search(id):
                        log.info('Triggered Search for [%s] %s', id, title)
                    else:
                        log.warning('Unable to search for [%s] %s', id, title)

    def search_missing_high_rating(self, cutoff=0.99, stage=False):
        high_rating = self.get_stats()['highest_rating']
        log.debug("Searching for Movies with a rating higher than %s", cutoff * high_rating)
        for movie in self.get_all_movies():
            if not movie['downloaded'] and movie['isAvailable']:
                if movie['ratings']:
                    if movie['ratings']['value'] >= high_rating * 0.99:
                        title = "{m[title]} ({m[year]})".format(m=movie)
                        id = movie['id']
                        if stage:
                            log.info('STAGE: Trigger Search for [%s] %s', id, title)
                        elif self.movie_search(id):
                            log.info('Triggered Search for [%s] %s', id, title)
                        else:
                            log.warning('Unable to search for [%s] %s', id, title)

    def search_missing_high_votes(self, cutoff=0.99, stage=False):
        high_votes = self.get_stats()['highest_votes']
        log.debug("Searching for Movies with more votes than %s", cutoff * high_votes)
        for movie in self.get_all_movies():
            if not movie['downloaded'] and movie['isAvailable']:
                if movie['ratings']:
                    if movie['ratings']['votes'] >= high_votes * 0.99:
                        title = u"{m[title]} ({m[year]})".format(m=movie)
                        id = movie['id']
                        if stage:
                            log.info('STAGE: Trigger Search for [%s] %s', id, title)
                        elif self.movie_search(id):
                            log.info('Triggered Search for [%s] %s', id, title)
                        else:
                            log.warning('Unable to search for [%s] %s', id, title)

    def purge_missing_unmonitored(self, stage=True, tag_to_protect='watched', delete_files=True, add_exclusion=False):
        tag_id_to_protect = self.tags[tag_to_protect] if tag_to_protect in self.tags else -1
        now = datetime.datetime.now(dateutil.tz.tzutc())
        log.debug("Searching for Movies that are Unmonitored and Missing")
        for movie in self.get_all_movies():
            if not movie['downloaded'] and not movie['monitored']:
                title = u"{m[title]} ({m[year]})".format(m=movie)
                id = movie['id']
                if tag_id_to_protect not in movie['tags']:
                    if stage:
                        log.info('STAGE: Remove Missing and Unmonitored [%s] %s', id, title)
                    elif self.movie_delete(id, delete_files, add_exclusion):
                        log.info('Removed the Missing and Unmonitored [%s] %s', id, title)
                    else:
                        log.warning('Unable to remove [%s] %s', id, title)
                else:
                    log.debug("Skipping [%s] %s, tagged with '%s'", id, title, tag_to_protect)

    def purge_downloaded_unmonitored(self, days_to_keep, stage=True):
        now = datetime.datetime.now(dateutil.tz.tzutc())
        duration_to_keep = datetime.timedelta(90)
        for movie in json_radarr:
            if not movie['monitored'] and not movie['tags'] == [2]:
                movie_added = dateutil.parser.parse(movie['added'])
                days_since_added = now - movie_added
                if movie['downloaded']:
                    movie_downloaded = dateutil.parser.parse(movie['movieFile']['dateAdded'])
                    days_since_downloaded = now - movie_downloaded
                    if days_since_added > duration_to_keep and days_since_downloaded > duration_to_keep:
                        stage['delete'].append(movie)
                        statement = u"DELETE [Added {dsa.days} days ago, Downloaded {dsa.days} days ago, but not Monitored] - {title}".format(
                            dsd=days_since_downloaded, dsa=days_since_added, **movie)
                    else:
                        stage['monitor'].append(movie)
                        statement = u"REMONITOR [Added {dsa.days} days ago, Downloaded {dsd.days} days ago, but not Monitored] - {title}".format(
                            dsd=days_since_downloaded, dsa=days_since_added, **movie)
                else:
                    stage['remove'].append(movie)
                    statement = u"REMOVE [Missing, but not Monitored] - {title}".format(**movie)
                log.debug("Stage: %s", statement)
