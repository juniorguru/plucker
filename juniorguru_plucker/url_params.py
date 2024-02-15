import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


UTM_PARAM_NAMES = ["utm_source", "utm_medium", "utm_campaign"]


def strip_params(url: str, param_names: list[str]) -> str:
    parts = urlparse(url)
    params = {
        name: value
        for name, value in parse_qs(parts.query).items()
        if name not in param_names
    }
    query = urlencode(params, doseq=True)
    return urlunparse(parts._replace(query=query))


def strip_utm_params(url: str) -> str:
    return strip_params(url, UTM_PARAM_NAMES)


def set_params(url: str, params: dict[str, str | None]) -> str:
    parts = urlparse(url)
    url_params = {name: value for name, value in parse_qs(parts.query).items()}
    for name, value in params.items():
        url_params[name] = ["" if value is None else str(value)]
    query = urlencode(url_params, doseq=True)
    return urlunparse(parts._replace(query=query))


def get_param(url: str, param_name: str) -> str | None:
    parts = urlparse(url)
    values = parse_qs(parts.query).get(param_name, [])
    return values[0] if values else None


def get_params(url: str) -> dict[str, str]:
    qs = urlparse(url).query
    return {name: values[0] for name, values in parse_qs(qs).items()}


def increment_param(url: str, param_name: str, inc: int = 1) -> str:
    parts = urlparse(url)
    params = parse_qs(parts.query)
    params.setdefault(param_name, ["0"])
    params[param_name] = [str(int(params[param_name][0]) + inc)]
    query = urlencode(params, doseq=True)
    return urlunparse(parts._replace(query=query))


def replace_in_params(
    url: str, s: str, repl: str, case_insensitive: bool = False
) -> str:
    parts = urlparse(url)
    params = parse_qs(parts.query)

    if case_insensitive:
        replace = lambda value: re.sub(re.escape(s), repl, value, flags=re.I)  # noqa: E731
    else:
        replace = lambda value: value.replace(s, repl)  # noqa: E731

    params = {
        param_name: [replace(value) for value in values]
        for param_name, values in params.items()
    }
    query = urlencode(params, doseq=True)
    return urlunparse(parts._replace(query=query))
