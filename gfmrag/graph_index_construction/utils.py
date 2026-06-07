import json
import os
import re
import uuid
from typing import Any

KG_DELIMITER = ","


def processing_phrases(phrase: str) -> str:
    if isinstance(phrase, int):
        return str(phrase)  # deal with the int values
    return re.sub("[^A-Za-z0-9 ]", " ", phrase.lower()).strip()


def directory_exists(path: str) -> None:
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)


def extract_json_dict(text: str) -> str | dict | list:
    obj_pattern = r"\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\})*)*\})*)*\}"
    match = re.search(obj_pattern, text)

    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fall back to a top-level JSON array. Non-OpenAI backends (e.g. Ollama) often
    # return a bare list (e.g. NER as ["a", "b"]) instead of {"named_entities": [...]}.
    arr_pattern = r"\[(?:[^\[\]]|(?:\[(?:[^\[\]]|(?:\[[^\[\]]*\])*)*\])*)*\]"
    match = re.search(arr_pattern, text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return ""

    return ""


def generate_uuid(obj: Any) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_X500, str(obj)))
