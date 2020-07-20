from ..utils.log import logger
log = logger.get_logger(__name__)


def backoff_handler(details):
    log.warning("Backing off {wait:0.1f} seconds afters {tries} tries "
                "calling function {target} with args {args} and kwargs "
                "{kwargs}".format(**details))


def dict_merge(dct, merge_dct):
    for k, v in merge_dct.items():
        import collections

        if k in dct and isinstance(dct[k], dict) and isinstance(merge_dct[k], collections.Mapping):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]

    return dct


def number_suffix(i):
    return {1: "st", 2: "nd", 3: "rd"}.get(i % 10*(i % 100 not in [11, 12, 13]), "th")


def ensure_endswith(data, endswith_key):
    if not data.strip().endswith(endswith_key):
        return "%s%s" % (data.strip(), endswith_key)
    else:
        return data
