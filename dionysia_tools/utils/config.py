import attrdict
import json
import pathlib
import os
import sys


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)

        return cls._instances[cls]


class AttrConfig(attrdict.AttrDict):
    """
    Simple AttrDict subclass to return None when requested attribute does not exist
    """

    def __init__(self, config):
        super().__init__(config)

    def __getattr__(self, item):
        try:
            return super().__getattr__(item)
        except AttributeError:
            pass
        # Default behaviour
        return None


class Config(object, metaclass=Singleton):
    base_config = {
        'core': {
            'debug': False
        },
        'trakt-update': {
            'cfdvd': {
                'user': 'ewascome',
                'list_id': 'certified-fresh-on-dvd',
                'type': 'movie',
                'stevenlu_url': 'https://ketchup.cogwheel.net/cf-dvd-streaming-all.json'
            },
            'cftheater': {
                'user': 'ewascome',
                'list_id': 'certified-fresh-in-theaters',
                'type': 'movie',
                'stevenlu_url': 'https://ketchup.cogwheel.net/cf-in-theaters.json'
            },
            'stevenlu': {
                'user': 'ewascome',
                'list_id': 'stevenlu',
                'type': 'movie',
                'stevenlu_url': 'https://s3.amazonaws.com/popular-movies/movies.json'
            }
        },
        'plex-collections': {
            'standard': {
                'agent': 'json',
                'url': 'https://api.jsonbin.io/b/5e0b7de402ce5777b8b566d3/latest'
            },
            'christmas': {
                'agent': 'trakt',
                'user': 'ewascome',
                'list_id': 'christmas-favorites',
                'type': 'movie',
                'name': 'Christmas Favorites'
            },
        },
        'plex': {
            'url': '',
            'token': '',
        },
        'radarr': {
            'api_key': '',
            'minimum_availability': 'released',
            'quality': 'HD-1080p',
            'root_folder': '/movies/',
            'baseurl': 'http://localhost:7878/'
        },
        'sonarr': {
            'api_key': '',
            'language': 'English',
            'quality': 'HD-1080p',
            'root_folder': '/tv/',
            'tags': {
            },
            'baseurl': 'http://localhost:8989/'
        },
        'omdb': {
            'api_key': ''
        },
        'trakt': {
            'client_id': '',
            'client_secret': '',
            'baseurl': 'https://api.trakt.tv'
        }
    }

    def __init__(self, configfile, cachefile, logfile):
        """Initializes config"""
        self.conf = None

        pathlib.Path(os.path.split(configfile)[0]).mkdir(parents=True, exist_ok=True)
        pathlib.Path(os.path.split(cachefile)[0]).mkdir(parents=True, exist_ok=True)
        pathlib.Path(os.path.split(logfile)[0]).mkdir(parents=True, exist_ok=True)

        self.config_path = configfile
        self.cache_path = cachefile
        self.log_path = logfile

    @property
    def cfg(self):

        # Return existing loaded config
        if self.conf:
            return self.conf

        # Built initial config if it doesn't exist
        if self.build_config():
            print("Please edit the default configuration before running again!")
            sys.exit(0)
        # Load config, upgrade if necessary
        else:
            tmp = self.load_config()
            self.conf, upgraded = self.upgrade_settings(tmp)

            # Save config if upgraded
            if upgraded:
                self.dump_config()
                print("New config options were added, adjust and restart!")
                sys.exit(0)

            return self.conf

    @property
    def cachefile(self):
        return self.cache_path

    @property
    def logfile(self):
        return self.log_path

    def build_config(self):
        if not os.path.exists(self.config_path):
            print("Dumping default config to: {}".format(self.config_path))
            with open(self.config_path, 'w') as fp:
                json.dump(self.base_config, fp, sort_keys=True, indent=2)
            return True
        else:
            return False

    def dump_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'w') as fp:
                json.dump(self.conf, fp, sort_keys=True, indent=2)
            return True
        else:
            return False

    def load_config(self):
        with open(self.config_path, 'r') as fp:
            return AttrConfig(json.load(fp))

    def __inner_upgrade(self, settings1, settings2, key=None, overwrite=False):
        sub_upgraded = False
        merged = settings2.copy()

        if isinstance(settings1, dict):
            for k, v in settings1.items():
                # missing k
                if k not in settings2:
                    merged[k] = v
                    sub_upgraded = True
                    if not key:
                        print("Added %r config option: %s" % (str(k), str(v)))
                    else:
                        print("Added %r to config option %r: %s" % (str(k), str(key), str(v)))
                    continue

                # iterate children
                if isinstance(v, dict) or isinstance(v, list):
                    merged[k], did_upgrade = self.__inner_upgrade(settings1[k], settings2[k], key=k,
                                                                  overwrite=overwrite)
                    sub_upgraded = did_upgrade if did_upgrade else sub_upgraded
                elif settings1[k] != settings2[k] and overwrite:
                    merged = settings1
                    sub_upgraded = True
        elif isinstance(settings1, list) and key:
            for v in settings1:
                if v not in settings2:
                    merged.append(v)
                    sub_upgraded = True
                    print("Added to config option %r: %s" % (str(key), str(v)))
                    continue

        return merged, sub_upgraded

    def upgrade_settings(self, currents):
        upgraded_settings, upgraded = self.__inner_upgrade(self.base_config, currents)
        return AttrConfig(upgraded_settings), upgraded

    def merge_settings(self, settings_to_merge):
        upgraded_settings, upgraded = self.__inner_upgrade(settings_to_merge, self.conf, overwrite=True)

        self.conf = upgraded_settings

        if upgraded:
            self.dump_config()

        return AttrConfig(upgraded_settings), upgraded
