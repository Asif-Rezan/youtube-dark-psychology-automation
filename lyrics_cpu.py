"""Run Qwen3-4B-Instruct-2507 locally; no hosted text API or credentials."""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import time

from jsonschema import Draft202012Validator, ValidationError

MODEL_ID = 'Qwen/Qwen3-4B-Instruct-2507'
GGUF_REPO = 'unsloth/Qwen3-4B-Instruct-2507-GGUF'
GGUF_REVISION = 'a06e946bb6b655725eafa393f4a9745d460374c9'
GGUF_FILE = 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
GGUF_SHA256 = '3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597'
CONTEXT_TOKENS = 16384
# A small, bounded word grammar is safe to retain; large prose bounds are not.
LYRIC_WORD_PATTERN = r'^[A-Za-z]+( [A-Za-z]+){3,11}[.!?]?$'
_model = None


class StoryGenerationError(RuntimeError):
    """Static message plus safe structured diagnostics; never raw model/API text."""
    def __init__(self, message, *, code='lyrics_generation', details=None, retryable=False):
        super().__init__(message)
        self.code=code
        self.details=details or {}
        self.retryable=retryable


def bounded_metadata(data, schema, fields):
    """Constrain opted-in planning prose, never truncate sung lyrics or scene actions."""
    result=copy.deepcopy(data)
    changed=[]
    if not isinstance(result,dict):
        return result,changed
    for field in fields:
        # Only known non-lyrical prose is permitted, even if callers opt in.
        # Visual identity is normalized before verses are written, so all scenes
        # use the same saved description; never shorten individual scene actions.
        if field not in ('description', 'title', 'characters', 'visual_world') or not isinstance(result.get(field),str):
            continue
        spec=schema.get('properties',{}).get(field,{})
        maximum=spec.get('maxLength')
        if type(maximum) is not int or maximum<1:
            continue
        value=' '.join(result[field].split())
        if len(value)<=maximum:
            result[field]=value
            continue
        prefix=value[:maximum]
        if field in ('description', 'characters', 'visual_world'):
            stops=[m.end() for m in re.finditer(r'[.!?](?=\s|$)',prefix)]
            minimum=max(spec.get('minLength',0),maximum//2)
            if stops and stops[-1]>=minimum:
                value=prefix[:stops[-1]]
            else:
                value=prefix.rsplit(' ',1)[0].rstrip(' ,;:')
                value=value[:maximum-1].rstrip(' ,;:.')+'.'
        else:
            value=prefix if len(value)==maximum or value[maximum].isspace() else prefix.rsplit(' ',1)[0]
        result[field]=value
        changed.append(field)
    return result,changed


def verify_model(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == GGUF_SHA256


def load_model():
    global _model
    if _model is not None:
        return _model
    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama
    for attempt in range(3):
        try:
            path = hf_hub_download(repo_id=GGUF_REPO, filename=GGUF_FILE,
                revision=GGUF_REVISION, token=False, force_download=attempt > 0)
            if not verify_model(path):
                raise StoryGenerationError('Qwen model checksum verification failed')
            break
        except Exception:
            if attempt == 2:
                raise StoryGenerationError('Qwen model download or checksum failed after three attempts') from None
            print(json.dumps({'check': 'Qwen model download retry', 'attempt': attempt + 1}), flush=True)
            time.sleep(2 ** (attempt + 1))
    threads = min(max(1, int(os.getenv('OMP_NUM_THREADS', '4'))), os.cpu_count() or 1)
    try:
        _model = Llama(model_path=path, n_ctx=CONTEXT_TOKENS, n_threads=threads,
            n_threads_batch=threads, n_gpu_layers=0, n_batch=256, use_mmap=True,
            chat_format='chatml', verbose=False)
    except Exception:
        raise StoryGenerationError('Qwen CPU runtime could not load the verified model') from None
    print(json.dumps({'check': 'Qwen CPU model loaded', 'model': MODEL_ID,
        'quantization': 'Q4_K_M', 'threads': threads}), flush=True)
    return _model


def request_story(endpoint, payload):
    if endpoint != 'chat/completions':
        raise StoryGenerationError('Qwen supports lyrics JSON generation only')
    if payload.get('model', MODEL_ID) != MODEL_ID or os.getenv('LYRICS_MODEL', MODEL_ID) != MODEL_ID:
        raise StoryGenerationError('LYRICS_MODEL must be Qwen/Qwen3-4B-Instruct-2507')
    schema = payload.get('response_format', {}).get('json_schema', {}).get('schema')
    if not isinstance(schema, dict):
        raise StoryGenerationError('Lyrics generation requires an explicit JSON schema')
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    messages = copy.deepcopy(payload['messages'])
    messages.append({'role': 'user', 'content': 'Return only JSON matching this schema. '
        'Do not add commentary or markdown. JSON Schema: ' + json.dumps(schema)})
    limit = int(payload.get('max_completion_tokens', 4200))
    if not 1 <= limit <= 6000:
        raise StoryGenerationError('Lyrics output token budget must be between 1 and 6000')
    # Bounds remain enforced by jsonschema. Expanding thousands of optional
    # characters in llama.cpp's grammar can overflow its native parser stack.
    grammar_schema = copy.deepcopy(schema)
    def remove_string_bounds(node):
        if isinstance(node, dict):
            node.pop('minLength', None)
            node.pop('maxLength', None)
            if node.get('pattern') != LYRIC_WORD_PATTERN:
                node.pop('pattern', None)
            for value in node.values():
                remove_string_bounds(value)
        elif isinstance(node, list):
            for value in node:
                remove_string_bounds(value)
    remove_string_bounds(grammar_schema)
    seed = payload.get('seed', 1700)
    if type(seed) is not int or not 0 <= seed <= 2**31 - 3:
        raise StoryGenerationError('Lyrics seed must be a nonnegative 31-bit integer')
    model = load_model()
    for attempt in range(3):
        # Retry instructions also consume context; check before every inference.
        prompt_tokens=sum(len(model.tokenize(message['content'].encode(),add_bos=False))+16 for message in messages)+32
        if prompt_tokens+limit>CONTEXT_TOKENS:
            raise StoryGenerationError('Qwen context budget exceeded; reduce recent-story context',code='lyrics_context')
        started = time.monotonic()
        try:
            result = model.create_chat_completion(messages=messages,
                response_format={'type': 'json_object', 'schema': grammar_schema},
                max_tokens=limit, temperature=max(.2, float(payload.get('temperature', .7)) - .15 * attempt),
                top_p=.8, top_k=20, repeat_penalty=1.05, seed=seed + attempt)
        except Exception:
            # Runtime/configuration errors are not content errors; don't spin on them.
            raise StoryGenerationError('Qwen CPU generation failed; inspect runner memory and runtime compatibility') from None
        issue, field, bound, actual = None, '$', None, None
        try:
            choice = result['choices'][0]
            if choice.get('finish_reason') != 'stop':
                issue = 'incomplete_output'
                raise ValueError('Incomplete output')
            original=json.loads(choice['message']['content'])
            candidate,adjusted=bounded_metadata(original,schema,payload.get('bounded_metadata_fields',[]))
            validator.validate(candidate)
            if candidate != original:
                choice['message']['content']=json.dumps(candidate,ensure_ascii=False)
            if adjusted:
                print(json.dumps({'check':'metadata length normalized','fields':adjusted}),flush=True)
        except ValidationError as error:
            issue = error.validator
            path = list(error.absolute_path)
            if path and path[0] in schema.get('properties', {}):
                field = path[0]
            if isinstance(error.validator_value, int):
                bound = error.validator_value
            if isinstance(error.instance,(str,list,dict)):
                actual=len(error.instance)
        except (ValueError, TypeError, KeyError, IndexError):
            issue = issue or 'invalid_json_or_response'
        if issue:
            # Report schema constraints and counters, never generated content or raw errors.
            print(json.dumps({'check': 'Qwen JSON validation retry', 'attempt': attempt + 1,
                'constraint': issue, 'field': field, 'bound': bound, 'actual_length': actual,
                'completion_tokens': result.get('usage', {}).get('completion_tokens')}), flush=True)
            if attempt == 2:
                raise StoryGenerationError('Qwen returned incomplete or invalid lyrics JSON after three attempts',
                    code='lyrics_schema_validation',details={'constraint':issue,'field':field,'bound':bound,'actual_length':actual,'attempts':3},retryable=True) from None
            correction = f'The previous response failed {issue} for field {field}.'
            if bound is not None:
                correction += f' The required {issue} is {bound}; the prior length was {actual}.'
                if issue=='maxLength':
                    correction += f' Write this field in no more than {max(1,int(bound*.65))} characters including spaces. Characters are not words.'
            if issue == 'pattern':
                correction += ' Every lyric must have 4 to 12 plain English words, single spaces, no apostrophes or hyphens. Aim for 6 words.'
            if issue == 'incomplete_output':
                correction += ' Shorten prose and lyric lines so the entire JSON fits the output budget.'
            messages.append({'role': 'user', 'content': correction +
                ' Regenerate the complete JSON matching the supplied schema. Follow every field length limit. '
                'Follow the original task language requirements for every field. Do not add fields or commentary.'})
            continue
        print(json.dumps({'check': 'Qwen lyrics JSON', 'passed': True,
            'seconds': round(time.monotonic() - started, 1),
            'completion_tokens': result.get('usage', {}).get('completion_tokens')}), flush=True)
        return result
