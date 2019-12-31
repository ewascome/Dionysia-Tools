import backoff
import json
import requests

from cashier import cache
from ..helpers.misc import (backoff_handler, dict_merge, number_suffix)
from ..utils.log import logger
from ..utils.config import Config

log = logger.get_logger(__name__)
cachefile = Config().cachefile


class JSONList:

    def __init__(self, cfg):
        self.cfg = cfg

    ############################################################
    # Requests
    ############################################################

    def _make_request(self, url, payload=None, request_type='get'):
        headers = {'Content-Type': 'application/json',
                   'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/71.0.3578.80 Safari/537.36'}

        if payload is None:
            payload = {}

        # make request
        resp_data = b''
        if request_type == 'delete':
            with requests.delete(url, headers=headers, params=payload, timeout=30, stream=True) as req:
                for chunk in req.iter_content(chunk_size=250000, decode_unicode=True):
                    if chunk:
                        resp_data += chunk
        else:
            with requests.get(url, headers=headers, params=payload, timeout=30, stream=True) as req:
                for chunk in req.iter_content(chunk_size=250000, decode_unicode=False):
                    if chunk:
                        resp_data += chunk

        log.debug("Request URL: %s", req.url)
        log.debug("Request Payload: %s", payload)
        log.debug("Response Code: %d", req.status_code)
        return req, resp_data

    @backoff.on_predicate(backoff.expo, lambda x: x is None, max_tries=4, on_backoff=backoff_handler)
    def _make_item_request(self, url, object_name, payload=None):

        if payload is None:
            payload = {}

        try:
            req, resp_data = self._make_request(url, payload)

            if req.status_code == 200 and len(resp_data):
                log.info("Retrieved %s", object_name)
                resp_json = json.loads(resp_data.decode())
                return resp_json
            else:
                log.error("Failed to retrieve %s, request response: %d", object_name, req.status_code)
                return None
        except Exception:
            log.exception("Exception retrieving %s: ", object_name)
        return None

    def get_list(self, url, list_name):
        return self._make_item_request(url, "{l} json feed".format(l=list_name))

    @cache(cache_file=cachefile, cache_time=3600, retry_if_blank=True)
    def get_list_imdb(self, url, list_name):
        return [i['imdb_id'] for i in self.get_list(url, list_name)]
