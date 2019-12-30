import sys
import os
# https://urllib3.readthedocs.org/en/latest/security.html#disabling-warnings
# http://quabr.com/27981545/surpress-insecurerequestwarning-unverified-https-request-is-being-made-in-pytho
# http://docs.python-requests.org/en/v2.4.3/user/advanced/#proxies
import argparse
import datetime
import dateutil.parser
import dateutil.tz
import logging
import ConfigParser
import collections
import pprint

try:
    import simplejson as json
    import requests
    requests.packages.urllib3.disable_warnings()
    import csv
except:
    sys.exit("Please use your favorite mehtod to install the following module requests and simplejson to use this script")

logging.basicConfig(
    datefmt='%Y-%m-%d %H:%M',
    # filename="{}.log".format(__file__.strip('.py')),
    filemode='a',
    format="%(asctime)-15s %(name)-5s %(levelname)-8s %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

_headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'User-Agent': 'Radarr Cleaner',
    'X-Api-Key': '',
    'Connection': 'Keep-Alive',
}


def filename_path(filename):
    if getattr(sys, 'frozen', False):
        _work_dir = os.path.dirname(sys.executable)
    elif __file__:
        _work_dir = os.path.dirname(__file__)
    else:
        _work_dir = ''

    return os.path.join(_work_dir, filename)


def read_config(options):
    _config_filename = filename_path(options.config)
    log.debug("Config: Loading %s", _config_filename)

    defaults = [
        ('RADARR', 'API_KEY', '', True),
        ('RADARR', 'BASEURL', '', True),
        ('SETTINGS', 'PROXY_HOST', 'https://127.0.0.1', True),
        ('SETTINGS', 'PROXY_PORT', '3128', True),
        ('SETTINGS', 'PROXY', 'False', True),
    ]
    try:
        if os.path.exists(_config_filename):
            config = ConfigParser.SafeConfigParser()
            config.read(_config_filename)
        else:
            log.warn("Config: %s was not found!, Creating...", _config_filename)
            config = ConfigParser.RawConfigParser()

        updated = False
        for section, option, value, required in defaults:
            if not config.has_section(section):
                log.debug('Config: Adding Section %s', section)
                config.add_section(section)
                updated = True
            if not config.has_option(section, option):
                log.debug('Config: Adding Option %s: %s', section, option)
                config.set(section, option, value)
                updated = True
        if updated:
            log.debug("Config: Additional defaults found")
            with open(_config_filename, 'wb') as config_file:
                config.write(config_file)
                log.info("Config: Updating %s", _config_filename)

        for section, option, value, required in defaults:
            if required and len(config.get(section, option)) == 0:
                log.error('Config: %s Required', option)
                sys.exit(1)
            elif len(config.get(section, option)) == 0:
                log.warning('Config: %s is Missing', option)

        return {s: dict(config.items(s)) for s in config.sections()}
    except:
        log.error("Config: Error reading/writing to %s", _config_filename)
        sys.exit(1)


def get_radarr_list(options, config):
    url = config['RADARR']['baseurl'] + '/movie'
    data = {'apikey': config['RADARR']['api_key']}

    if config['SETTINGS']['proxy'] == True:
        req = requests.get(url, headers=config['HEADERS'], params=data, proxies=config['PROXY'], timeout=(10, 60))
    else:
        req = requests.get(url, headers=config['HEADERS'], params=data, timeout=(5, 60))

    if req.status_code != 200:
        log.error("Download: Error fetching from %s", req.url)
        log.error("Download: Status Code given %s", req.status_code)
        return None
    log.debug("Download: Success! Return Headers: %s", req.headers)

    list_raw = json.loads(req.text)
    filename = filename_path("radarr.json")
    with open(filename, 'wb') as file:
        json.dump(list_raw, file)
        log.info("Download: Successfully downloaded %s", filename)


def stage_radarr_list(options, config):
    filename_radarr = filename_path('radarr.json')
    if options.force or not os.path.exists(filename_radarr):
        if not options.force:
            log.warning("Stage: %s not found, downloading", filename_radarr)
        get_radarr_list(options, config)
    with open(filename_radarr) as file:
        json_radarr = json.load(file)
        log.debug("Stage: reading data from %s", filename_radarr)

    stage = {
        "monitor": [],
        "delete": [],
        "download": [],
    }

    now = datetime.datetime.now(dateutil.tz.tzutc())
    duration_to_keep = datetime.timedelta(30)
    for movie in json_radarr:
        if not movie['monitored'] and not movie['tags'] == [2]:
            movie_added = dateutil.parser.parse(movie['added'])
            days_since_added = now - movie_added
            if movie['downloaded']:
                movie_downloaded = dateutil.parser.parse(movie['movieFile']['dateAdded'])
                days_since_downloaded = now - movie_downloaded
                if days_since_added > duration_to_keep and days_since_downloaded > duration_to_keep:
                    stage['delete'].append(movie)
                    statement = "DELETE [Downloaded, but not Monitored] - {title}".format(**movie)
                else:
                    stage['monitor'].append(movie)
                    statement = "REMONITOR [Downloaded, but not Monitored] - {title}".format(**movie)
            else:
                stage['delete'].append(movie)
                statement = "DELETE [Missing, but not Monitored] - {title}".format(**movie)
            log.debug("Stage: %s", statement)

    high_rating = None
    high_votes = None
    oldest = now
    for movie in json_radarr:
        if not movie['downloaded'] and movie['isAvailable']:
            if movie['ratings']:
                if movie['ratings']['votes'] and movie['ratings']['votes'] > high_votes:
                    high_votes = movie['ratings']['votes']
                if movie['ratings']['value'] and movie['ratings']['value'] > high_rating:
                    high_rating = movie['ratings']['value']
                if movie['inCinemas'] and dateutil.parser.parse(movie['inCinemas']) < oldest:
                    oldest = dateutil.parser.parse(movie['inCinemas'])

    for movie in json_radarr:
        if not movie['downloaded'] and movie['isAvailable']:
            if movie['ratings']:
                if movie['ratings']['votes'] >= high_votes * 0.99:
                    stage['download'].append(movie)
                    log.debug("Stage: DOWNLOAD [Missing, Monitored] - {title}".format(**movie))
                if movie['ratings']['value'] >= high_rating * 0.99:
                    stage['download'].append(movie)
                    log.debug("Stage: DOWNLOAD [Missing, Monitored] - {title}".format(**movie))
                if movie['inCinemas'] and dateutil.parser.parse(movie['inCinemas']) == oldest:
                    stage['download'].append(movie)
                    log.debug("Stage: DOWNLOAD [Missing, Monitored] - {title}".format(**movie))

    filename_stage = filename_path('radarr_stage.json')
    with open(filename_stage, 'wb') as file:
        json.dump(stage, file)
        log.info("Stage: Successfully analyzed and created %s", filename_stage)


def update_radarr_list(options, config):
    filename = filename_path('radarr_stage.json')
    if options.force or not os.path.exists(filename):
        if not options.force:
            log.warning("Stage: %s not found, downloading", filename)
        stage_radarr_list(options, config)
    with open(filename) as file:
        json_radarr = json.load(file)
        log.debug("Stage: reading data from %s", filename)

    def radarr_api_movie(method, command, data=None, status_code=200):
        url = config['RADARR']['baseurl'] + command

        if config['SETTINGS']['proxy'] == True:
            req = requests.request(method, url, headers=config['HEADERS'],
                                   data=json_data, proxies=config['PROXY'], timeout=(10, 60))
            pass
        else:
            # req = requests.put(url, headers=config['HEADERS'], data=json_data, timeout=(5, 60))
            req = requests.request(method, url, headers=config['HEADERS'], json=data, timeout=(5, 60))

        if req.status_code != status_code:
            log.error("Download: Error fetching from %s", req.url)
            log.error("Download: Status Code given %s", req.status_code)
            log.error("Download: Reponse %s", req.text)
            return None
        log.debug("Download: Success! Return Headers: %s", req.headers)

    # Re-Monitor Downloaded Movies
    for movie in json_radarr['monitor']:
        movie['monitored'] = True
        log.info("Update: Setting %s to Monitored", movie['title'])
        radarr_api_movie('put', '/movie', movie, status_code=202)

    # Delete non-monitored older than 30 day movies
    for movie in json_radarr['delete']:
        log.info("Update: Deleting %s", movie['title'])
        radarr_api_movie('delete', '/movie/{}'.format(movie['id']), {"id": movie['id'], "deleteFiles": True})

    # Search for top rated and popular missing movies
    movieIds = [m['id'] for m in json_radarr['download']]
    movies = [m['title'] for m in json_radarr['download']]
    log.info("Update: Search for %s", movies)
    radarr_api_movie('post', '/command', {'name': 'MoviesSearch', 'movieIds': movieIds}, status_code=201)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        version='%(prog)s 0.1',
        # description="""This program import Movies or TVShows IDs into Trakt.tv.""",
        # epilog="""Read a list of ID from 'imdb', 'tmdb', 'tvdb' or 'tvrage' or 'trakt'. Import them into a list in Trakt.tv, mark as seen if need.""",
    )
    parser.add_argument(
        '-V', '--verbose',
        dest='verbose',
        action='store_true',
        default=False,
        help='print additional verbose information, default %(default)s')
    parser.add_argument(
        '-c', '--config',
        dest='config',
        action='store',
        type=str,
        default="{}.ini".format(os.path.basename(__file__)),
        help='allow to overwrite default config filename, default %(default)s')
    parser.add_argument(
        '-d', '--download',
        action='store_true',
        default=False,
        help='Download current state')
    parser.add_argument(
        '-s', '--stage',
        action='store_true',
        default=False,
        help='Stage changes')
    parser.add_argument(
        '-u', '--update',
        action='store_true',
        default=False,
        help='Update Radarr with changes')
    parser.add_argument(
        '--force',
        action='store_true',
        default=False,
        help='Force staging')

    options = parser.parse_args()

    # Read parser options
    if options.verbose:
        log.setLevel(logging.DEBUG)
    log.debug("Options Parsed: %s", options)

    # Read configuration and validate
    config = read_config(options)
    log.debug("Radarr Settings: %s", config['RADARR'])

    config['PROXY'] = {
        "http": config['SETTINGS']['proxy_host'] + ':' + config['SETTINGS']['proxy_port'],
        "https": config['SETTINGS']['proxy_host'] + ':' + config['SETTINGS']['proxy_port'],
    }
    log.debug("Proxy Settings: %s", config['PROXY'])

    config['HEADERS'] = _headers
    config['HEADERS']['X-Api-Key'] = config['RADARR']['api_key']
    log.debug("Headers Settings: %s", config['HEADERS'])

    if options.download:
        get_radarr_list(options, config)

    elif options.stage:
        stage_radarr_list(options, config)

    elif options.update:
        update_radarr_list(options, config)

    else:
        print("No command given")
