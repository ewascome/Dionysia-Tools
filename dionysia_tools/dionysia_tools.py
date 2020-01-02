import click
import os
import pyfiglet
import schedule
import signal
import sys

from appdirs import AppDirs
dirs = AppDirs("Dionysia-Tools")

############################################################
# INIT
############################################################
cfg = None
log = None
notify = None

# Click
@click.group(help='Various tools to manage my plex server.')
@click.version_option('0.1.0a', prog_name='Dionsyia_Tools')
@click.option(
    '--config',
    envvar='DIONYSIA_TOOLS_CONFIG',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Configuration file',
    show_default=True,
    default=os.path.join(dirs.user_config_dir, "config.json")
)
@click.option(
    '--cachefile',
    envvar='DIONYSIA_TOOLS_CACHEFILE',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Cache file',
    show_default=True,
    default=os.path.join(dirs.user_cache_dir, "cache.db")
)
@click.option(
    '--logfile',
    envvar='DIONYSIA_TOOLS_LOGFILE',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Log file',
    show_default=True,
    default=os.path.join(dirs.user_log_dir, "activity.log")
)
@click.option(
    '--verbose',
    help='DEBUG logging level',
    is_flag=True
)
def app(config, cachefile, logfile, verbose):
    # Setup global variables
    global cfg, log, notify

    # Load config
    from .utils.config import Config
    cfg = Config(configfile=config, cachefile=cachefile, logfile=logfile).cfg
    if verbose:
        cfg['core']['debug'] = True

    # Load logger
    from .utils.log import logger
    log = logger.get_logger('dionysia_tools')
    log.debug('Loaded')


############################################################
# Plex Update Collections
############################################################

@app.command(context_settings=dict(max_content_width=119))
@click.option(
    '--list-names', '-l',
    multiple=True,
    help="Run a specific CONFIG specified list i.e. standard..."
)
@click.option(
    '--trending', '-t',
    help="Add/Update the Trakt 'Trending Collection'",
    is_flag=True
)
@click.option(
    '--popular', '-w',
    help="Add/Update the Trakt 'Trending Popular'",
    is_flag=True
)
@click.option(
    '--library',
    default='Movies',
    show_default=True,
    help="Name of the Movie library to update",
)
@click.option(
    '--stage',
    help="Will analyze needed changes but will NOT update Plex",
    is_flag=True
)
def plex_collections(library, trending, popular, list_names, stage):
    """Will update Plex's Collections based on lists per the config file.
    It can also create a dynamic Trending and Watched (Popular) trakt collections.
    """
    if not list_names:
        list_names = cfg['plex-collections'].keys()

    from .interfaces.trakt import Trakt
    from .interfaces.plex import Plex
    from .interfaces.json import JSONList
    plex = Plex(cfg)
    trakt = Trakt(cfg)
    json_list = JSONList(cfg)

    for name in list_names:
        if name not in cfg['plex-collections']:
            example = {
                name: {
                    "list_id": "[Trakt List ID]",
                    "stevenlu_url": "[JSON URL]",
                    "type": "movie",
                    "user": "[Trakt List Username]"
                }}
            example = {
                name: {
                    'url': '[JSON URL]'
                }}
            log.error("You will need to add '%s' to {'plex-collections':{}} in the Configuration file", example)
            break
        list_details = cfg['plex-collections'][name]
        if list_details['agent'] == 'json':
            list_items = json_list.get_list(list_details['url'], name)
            for collection in list_items:
                plex.update_collection(library,
                                       collection['list_movies'],
                                       collection['collection_name'],
                                       stage)
        if list_details['agent'] == 'trakt':
            trakt_movies = trakt.get_user_list_movies(list_details['user'], list_details['list_id'])
            trakt_movie_list = []
            for trakt_movie in trakt_movies:
                trakt_movie_list.append({
                    'title': trakt_movie['movie']['title'],
                    'year': trakt_movie['movie']['year'],
                })
            plex.update_collection(library,
                                   trakt_movie_list,
                                   list_details['name'],
                                   stage)

    if trending:
        trakt_movies = trakt.get_top_trending_movies(30)
        trakt_movie_list = []
        for trakt_movie in trakt_movies:
            trakt_movie_list.append({
                'title': trakt_movie['movie']['title'],
                'year': trakt_movie['movie']['year'],
            })
        plex.update_collection(library,
                               trakt_movie_list,
                               'Trakt Trending',
                               stage)

    if popular:
        trakt_movies = trakt.get_top_most_watched_movies(30)
        trakt_movie_list = []
        for trakt_movie in trakt_movies:
            trakt_movie_list.append({
                'title': trakt_movie['movie']['title'],
                'year': trakt_movie['movie']['year'],
            })
        plex.update_collection(library,
                               trakt_movie_list,
                               'Trakt Popular',
                               stage)


############################################################
# Plex Update Recently Added
############################################################

@app.command(context_settings=dict(max_content_width=119))
@click.option(
    '--library',
    default='Movies',
    show_default=True,
    help="Name of the Movie library to update",
)
@click.option(
    '--number', '-n',
    default=10,
    show_default=True,
    type=int,
    help="Number of Trakt Trending titles to move to beginning of the list",
)
def plex_recently_added(library, number):
    """Will update Plex's Recently added list
    to have available Trakt Trending titles
    near the beginning.
    """
    from .interfaces.trakt import Trakt
    from .interfaces.plex import Plex
    plex = Plex(cfg)
    trakt = Trakt(cfg)

    trakt_trending = trakt.get_top_trending_movies(number)
    minutes = 240 + number
    for trakt_movie in trakt_trending:
        plex.get_movie_then_push_addedAt(
            section=library,
            title=trakt_movie['movie']['title'],
            year=trakt_movie['movie']['year'],
            timedelta_minutes=minutes
        )
        minutes += 1


############################################################
# Radarr Search
############################################################

@app.command(context_settings=dict(max_content_width=119))
@click.option(
    '--oldest', '-o',
    help="Download Older Missing, Monitored, and Available",
    is_flag=True
)
@click.option(
    '--rating', '-r',
    help="Download Higher Rated Missing, Monitored, and Available",
    is_flag=True
)
@click.option(
    '--votes', '-v',
    help="Download Higher Voted Missing, Monitored, and Available",
    is_flag=True
)
@click.option(
    '--cutoff',
    help="Percent of the Older/Vote/Rating to include.",
    type=float,
    show_default=True,
    default=99,
)
@click.option(
    '--stage',
    help="Will analyze needed changes but will NOT trigger Radarr",
    is_flag=True
)
def radarr_missing(oldest, rating, votes, cutoff, stage):
    """
    Download Missing, Monitored and considered Available movies from Radarr
    """
    from .interfaces.radarr import Radarr
    radarr = Radarr(cfg)
    cutoff /= 100

    if oldest:
        radarr.search_missing_oldest(cutoff, stage)
    if rating:
        radarr.search_missing_high_rating(cutoff, stage)
    if votes:
        radarr.search_missing_high_votes(cutoff, stage)

############################################################
# Radarr Search
############################################################


@app.command(context_settings=dict(max_content_width=119))
@click.option(
    '--tag_to_protect', '-t',
    help="Avoid deleting movies in Radarr with the following tag",
    show_default=True,
    default='watched'
)
@click.option(
    '--delete_files/--no-delete_files',
    help="Will keep the files but will remove from Radarr",
    show_default=True,
    default=True,
    is_flag=True
)
@click.option(
    '--exclude/--no-exclude',
    help="Will exclude movie from being readded automatically by Radarr in the future",
    show_default=True,
    default=False,
    is_flag=True
)
@click.option(
    '--stage/--no-stage',
    help="Will analyze needed changes but will NOT trigger Radarr",
    default=True,
    is_flag=True
)
def radarr_purge(stage, tag_to_protect, delete_files, exclude):
    """
    Purge Downloaded, but not Monitored AND Missing, but not Monitored from Radarr
    """
    from .interfaces.radarr import Radarr
    radarr = Radarr(cfg)

    radarr.purge_missing_unmonitored(stage,
                                     tag_to_protect,
                                     delete_files=delete_files,
                                     add_exclusion=exclude)


############################################################
# Trakt Update
############################################################


@app.command(context_settings=dict(max_content_width=119))
@click.option(
    '--list-names', '-l',
    multiple=True,
    help="Run a specific CONFIG specified list i.e. cfdvd, cftheater, stevenlu..."
)
@click.option(
    '--stage',
    help="Will analyze needed changes but will NOT update Trakt",
    is_flag=True
)
def trakt_update(list_names, stage):
    """
    Update Trakt with StevenLu type lists.
    """
    if not list_names:
        list_names = cfg['trakt-update'].keys()

    from .interfaces.trakt import Trakt
    from .interfaces.json import JSONList
    stevenlu = JSONList(cfg)
    trakt = Trakt(cfg)

    for name in list_names:
        if name not in cfg['trakt-update']:
            example = {
                name: {
                    "list_id": "[Trakt List ID]",
                    "stevenlu_url": "[JSON URL]",
                    "type": "movie",
                    "user": "[Trakt List Username]"
                }}
            log.error("You will need to add '%s' to {'trakt-update':{}} in the Configuration file", example)
            break
        list_details = cfg['trakt-update'][name]
        list_items = set(stevenlu.get_list_imdb(list_details['stevenlu_url'], name))
        trakt_items = set(trakt.get_user_list_movies_imdb(list_details['user'], list_details['list_id']))

        remove_ids = list(trakt_items.difference(list_items))
        add_ids = list(list_items.difference(trakt_items))
        other_ids = list(list_items.intersection(trakt_items))

        if stage:
            log.info("STAGING: %s, will REMOVE %s", name, remove_ids)
            log.info("STAGING: %s, will ADD %s", name, add_ids)
            log.info("STAGING: %s, will NOT CHANGE %s", name, other_ids)
        else:
            if add_ids:
                trakt.post_user_list_movies_imdb(list_details['user'], list_details['list_id'], add_ids)
            if remove_ids:
                trakt.delete_user_list_movies_imdb(list_details['user'], list_details['list_id'], remove_ids)


############################################################
# Trakt OAuth
############################################################

@app.command(help='Authenticate Trakt with Dionysia Tools.')
def trakt_authentication():
    from .interfaces.trakt import Trakt
    trakt = Trakt(cfg)

    if trakt.oauth_authentication():
        log.info("Authentication information saved. Please restart the application.")
        exit()


# Handles exit signals, cancels jobs and exits cleanly
# noinspection PyUnusedLocal
def exit_handler(signum, frame):
    log.info("Received %s, canceling jobs and exiting.", signal.Signals(signum).name)
    schedule.clear()
    exit()


############################################################
# MAIN
############################################################

if __name__ == "__main__":

    f = pyfiglet.Figlet(font='slant')
    click.echo(f.renderText('Dionysia Tools'))
    click.echo("""
#########################################################################
# Author:   ewascome                                                    #
# URL:      https://github.com/ewascome/Dionysia-Tools                  #
# --                                                                    #
#########################################################################
#                   GNU General Public License v3.0                     #
#########################################################################
""")

    # Register the signal handlers
    signal.signal(signal.SIGTERM, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)

    # Start application
    app()
