import datetime
import requests

from plexapi.server import PlexServer, CONFIG
from cashier import cache
from ..utils.log import logger
from ..utils.config import Config

log = logger.get_logger(__name__)
cachefile = Config().cachefile


class Plex:

    def __init__(self, cfg):
        self.cfg = cfg
        self.plex = self.get_plex()

    def get_plex(self):
        url = self.cfg['plex']['url']
        token = self.cfg['plex']['token']

        session = requests.Session()
        # Ignore verifying the SSL certificate
        session.verify = False  # '/path/to/certfile'
        # If verify is set to a path to a directory,
        # the directory must have been processed using the c_rehash utility supplied
        # with OpenSSL.
        if session.verify is False:
            log.debug('Disable the warning that the request is insecure, we know that...')
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        return PlexServer(url, token, session)

    def add_tag(self, video, tag, key='collections'):
        video.reload()
        current_tags = [t.tag for t in getattr(video, key)]
        if tag not in current_tags:
            params = {
                "collection[{}].tag.tag".format(len(current_tags)): tag
            }
            video.edit(**params)
            log.info("Updated %s with the following '%s'", video, params)
            video.reload()

    def remove_tag(self, video, tag, key='collections'):
        params = {
            "collection[].tag.tag-": tag
        }
        video.edit(**params)
        log.info("Updated %s with the following '%s'", video, params)
        video.reload()

    def update_addedAt(self, video, addedAt=None):
        if not addedAt:
            addedAt = datetime.datetime.now()
        params = {
            'addedAt.value': addedAt.strftime('%Y-%m-%d %H:%M:%S'),
        }
        video.edit(**params)
        log.info("Updated %s with the following '%s'", video, params)
        video.reload()

    def get_movie(self, section, title, year):
        section = self.plex.library.section(section)
        movies = section.search(title=title, year=year)

        log.debug("Searched Plex for %s (%s) and found the following %s", title, year, movies)
        for movie in movies:
            if movie.title == title and movie.year == year:
                return movie
        else:
            return None

    def get_movie_then_push_addedAt(self, section, title, year, timedelta_minutes=240):
        addedAt = datetime.datetime.now()
        addedAt += datetime.timedelta(minutes=-timedelta_minutes)
        movie = self.get_movie(section, title, year)
        if movie and movie.media[0].videoResolution in ['1080', '4K']:
            self.add_tag(movie, 'Trakt Trending', 'collections')
            self.update_addedAt(movie, addedAt)

    def get_collection(self, section, collection):
        section = self.plex.library.section(section)
        videos = section.search(collection=collection)
        log.debug("Searched for '%s' Collection and found %s videos", collection, len(videos))
        return videos

    def update_collection(self, section, list_of_titles_years, collection_name, stage=False):
        list_collection = []
        for list_movie in list_of_titles_years:
            current_year = datetime.datetime.now().year
            movie = self.get_movie(section, list_movie['title'], list_movie['year'] or current_year)
            if movie:
                list_collection.append(movie)

        plex_collection = self.get_collection(section, collection_name)

        remove_collection = set(plex_collection) - set(list_collection)
        for video in remove_collection:
            if stage:
                log.info("STAGING: %s, will REMOVE %s", video, collection_name)
            else:
                self.remove_tag(video, collection_name, 'collections')

        add_collection = set(list_collection) - set(plex_collection)
        for video in add_collection:
            if stage:
                log.info("STAGING: %s, will ADD %s", video, collection_name)
            else:
                self.add_tag(video, collection_name, 'collections')
