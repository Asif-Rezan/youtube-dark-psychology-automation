"""Check each Groq credential with a real structured request, without logging secrets."""
import json
import os
from unittest.mock import patch
import requests
import workflow as w

payload = {'model': os.getenv('STORY_MODEL', 'openai/gpt-oss-120b'),
           'messages': [{'role': 'user', 'content': 'Return a JSON object with ok set to true.'}],
           'reasoning_effort': 'low', 'max_completion_tokens': 512,
           'response_format': {'type': 'json_schema', 'json_schema': {
               'name': 'groq_readiness', 'strict': True, 'schema': {
                   'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                   'required': ['ok'], 'additionalProperties': False}}}}


def main():
    usable = False
    for slot, name in enumerate(('GROQ_API_KEY', 'GROQ_API_KEY_FALLBACK'), 1):
        key = os.getenv(name, '')
        if not key:
            print(json.dumps({'key_slot': slot, 'configured': False}))
            continue
        try:
            with patch.dict(os.environ, {'GROQ_API_KEY': key, 'GROQ_API_KEY_FALLBACK': ''}):
                result = w.request_groq('chat/completions', payload)
            passed = json.loads(result['choices'][0]['message']['content']) == {'ok': True}
        except (RuntimeError, ValueError):
            passed = False
        print(json.dumps({'check': 'Groq structured readiness', 'key_slot': slot, 'passed': passed}))
        usable = usable or passed
    if not usable:
        raise SystemExit('No configured Groq key passed the structured request')


if __name__ == '__main__':
    main()
