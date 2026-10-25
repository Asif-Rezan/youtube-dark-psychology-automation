"""Structured text generation using a loopback-only Qwen3.5 llama.cpp server."""
import json
import os
from urllib.parse import urlsplit
import requests

MODEL = 'Qwen/Qwen3.5-9B'


def request(payload):
    base = os.getenv('QWEN_BASE_URL', 'http://127.0.0.1:8080/v1').rstrip('/')
    url = urlsplit(base)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or url.username or url.password:
        raise RuntimeError('Qwen must use a local loopback server')
    candidate = {key: value for key, value in payload.items()
                 if key in ('messages', 'response_format', 'temperature', 'top_p')}
    candidate.update(model=MODEL, max_tokens=payload.get('max_completion_tokens', 4400),
                     chat_template_kwargs={'enable_thinking': False})
    try:
        response = requests.post(base + '/chat/completions', json=candidate,
                                 timeout=(10, 3600))
        if not response.ok:
            raise RuntimeError(f'Local Qwen request failed with HTTP {response.status_code}')
        result = response.json()
        choice = result['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('Incomplete response')
        content = choice['message']['content']
        if not isinstance(json.loads(content), dict):
            raise ValueError('Expected JSON object')
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError('Local Qwen failed or returned incomplete JSON; no external fallback was called') from None
    print(json.dumps({'check': 'Local Qwen text', 'model': MODEL, 'passed': True}), flush=True)
    return result
