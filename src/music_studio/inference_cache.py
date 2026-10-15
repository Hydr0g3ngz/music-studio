"""Opt-in model reuse for benchmark batches; normal song workers still exit per stage."""

import gc
import os

_MODELS = {}


def inference_model(key, factory):
    if os.environ.get("MUSIC_STUDIO_REUSE_RECOGNIZER") != "1":
        return factory()
    if key not in _MODELS:
        _MODELS[key] = factory()
    return _MODELS[key]


def clear_models():
    _MODELS.clear()
    gc.collect()
