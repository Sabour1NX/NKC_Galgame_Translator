# SPDX-License-Identifier: MIT
"""Provider presets and Chat Completions wire options for the active slot."""
import re
from urllib.parse import urlsplit
from .security import validate_api_url, SecurityValidationError

PRESETS = {
    'deepseek': ('https://api.deepseek.com','deepseek-flash'),
    'openai': ('https://api.openai.com/v1','gpt-4.1-mini'),
    'custom': ('',''),
    'ollama': ('http://127.0.0.1:11434/v1',''),
    'local': ('http://127.0.0.1:1234/v1',''),
}


def provider_for(url,local_provider=None):
    try:
        normalized=validate_api_url(url)
    except SecurityValidationError:
        return 'custom'
    parsed=urlsplit(normalized)
    if parsed.hostname in ('127.0.0.1','::1'):
        if local_provider in ('ollama','local'):
            return local_provider
        return 'ollama' if parsed.port==11434 else 'local'
    if normalized in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
        return 'deepseek'
    if normalized in ('https://api.openai.com','https://api.openai.com/v1'):
        return 'openai'
    return 'custom'


def local_endpoint(url):
    return provider_for(url) in ('local','ollama')


def api_headers(key,accept):
    headers={'Accept':accept,'Accept-Encoding':'identity'}
    if key:
        headers['Authorization']='Bearer '+key
    return headers


def chat_endpoint(base_url):
    if provider_for(base_url)=='openai':
        return PRESETS['openai'][0]+'/chat/completions'
    return base_url.rstrip('/')+'/chat/completions'


def chat_options(payload,base_url):
    service=provider_for(base_url)
    if service!='deepseek':
        payload.pop('thinking',None)
    if service=='openai' or re.match(r'^(?:gpt-[5-9]|o[1-9])',payload.get('model',''),re.I):
        if 'max_tokens' in payload:
            payload['max_completion_tokens']=payload.pop('max_tokens')
        payload.pop('temperature',None)
    return payload
