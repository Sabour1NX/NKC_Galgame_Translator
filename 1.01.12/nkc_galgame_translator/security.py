# SPDX-License-Identifier: MIT
"""Shared, side-effect-free validation at credential/network trust boundaries."""

from .i18n import ui_source
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, unquote


class SecurityValidationError(ValueError):
    """Fixed diagnostics: never include the rejected value or credentials."""


def _unsafe(value):
    return any(unicodedata.category(c) in {'Cc', 'Cs', 'Cf'} for c in value)


def normalize_api_key(value):
    if not isinstance(value, str):
        raise SecurityValidationError(ui_source('API key must be text.'))
    if _unsafe(value):
        raise SecurityValidationError(ui_source('The API key contains control characters. Check the pasted value.'))
    key = value.strip()
    if key.upper() == 'YOUR_API_KEY':
        return ''
    if len(key) > 8192 or any(not 33 <= ord(c) <= 126 for c in key):
        raise SecurityValidationError(ui_source('API keys must be ASCII text without spaces, up to 8,192 characters.'))
    return key


def validate_model(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or _unsafe(value):
        raise SecurityValidationError(ui_source('Model ID is required, must be at most 256 characters, and cannot contain control characters.'))
    return value.strip()


def validate_language(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', value) or len(value) > 64:
        raise SecurityValidationError(ui_source('Use a valid language code such as en, ja, or zh-Hans, up to 64 characters.'))
    return value


def validate_api_url(value):
    """Allow public HTTPS or an explicit loopback service with a port."""
    message = ui_source('Use a public HTTPS address or a loopback address with an explicit port.')
    if (not isinstance(value, str) or len(value) > 2048 or not value or
            _unsafe(value) or any(c.isspace() for c in value) or '\\' in value):
        raise SecurityValidationError(message)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        loopback = host in ('localhost','127.0.0.1','::1') and parsed.port is not None
        if (parsed.scheme.lower() not in (('http','https') if loopback else ('https',)) or not host or parsed.username is not None or
                parsed.password is not None or parsed.query or parsed.fragment or
                '?' in value or '#' in value or '%' in host):
            raise ValueError()
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        decoded_path = unquote(parsed.path, errors='strict')
        if _unsafe(decoded_path) or '\\' in decoded_path or any(c.isspace() for c in decoded_path):
            raise ValueError()
        if loopback:
            if not re.fullmatch(r'(?:localhost|127\.0\.0\.1|\[::1\]):[0-9]+', parsed.netloc, re.I):
                raise ValueError()
            authority = '[::1]' if host=='::1' else '127.0.0.1'
            return urlunsplit((parsed.scheme, f'{authority}:{port}', parsed.path.rstrip('/') or '/v1', '', ''))
        host = host.rstrip('.').encode('idna').decode('ascii').lower()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if ('.' not in host or host.split('.')[-1].isdigit() or len(host) > 253 or
                    all(re.fullmatch(r'(?:[0-9]+|0x[0-9a-f]+)', part) for part in host.split('.')) or
                    not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.'))):
                raise ValueError()
            authority = host
        else:
            if not address.is_global:
                raise ValueError()
            authority = '[' + host + ']' if address.version == 6 else host
        if port is not None and port != 443:
            authority += ':' + str(port)
        return urlunsplit(('https', authority, parsed.path.rstrip('/'), '', ''))
    except (ValueError, UnicodeError):
        raise SecurityValidationError(message) from None
