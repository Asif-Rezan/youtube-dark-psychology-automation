"""Use the same in-process Qwen runtime as Rezan-After-Dark, without hosted APIs."""
from story_cpu import MODEL_ID as MODEL, request_story


def request(payload):
    return request_story('chat/completions', payload)
