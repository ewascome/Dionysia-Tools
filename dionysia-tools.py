import click
import os
import pyfiglet
import schedule
import signal
import sys

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
    default=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "config.json")
)
@click.option(
    '--cachefile',
    envvar='DIONYSIA_TOOLS_CACHEFILE',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Cache file',
    show_default=True,
    default=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "cache.db")
)
@click.option(
    '--logfile',
    envvar='DIONYSIA_TOOLS_LOGFILE',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Log file',
    show_default=True,
    default=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "activity.log")
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
    from utils.config import Config
    cfg = Config(configfile=config, cachefile=cachefile, logfile=logfile).cfg
    if verbose:
        cfg['core']['debug'] = True

    # Load logger
    from utils.log import logger
    log = logger.get_logger('dionysia_tools')
    log.debug('Loaded')


############################################################
# Plex Update Recently Added
############################################################

@app.command(context_settings=dict(max_content_width=119))
@click.option(
    '--library', '-l',
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
    from interfaces.trakt import Trakt
    from interfaces.plex import Plex
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
        minutes += -1

############################################################
# Trakt Update
############################################################

@app.command(context_settings=dict(max_content_width=119))
@click.argument(
    'list-names',
    nargs=-1,
    required=True
)
@click.option(
    '--stage',
    help="Will analyze needed changes but will NOT update Trakt", is_flag=True
)
def trakt_update(list_names, stage):
    """Update Trakt with StevenLu type lists.

    The following LIST_NAMES are available:
    cfdvd, cftheater, stevenlu
    """
    from interfaces.trakt import Trakt
    from interfaces.stevenlu import StevenLu
    stevenlu = StevenLu(cfg)
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
    from interfaces.trakt import Trakt
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
