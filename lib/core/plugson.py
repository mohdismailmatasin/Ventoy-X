import json
import os

PLUGIN_PATHS = [
    os.path.expanduser('~/ventoy/ventoy.json'),
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ventoy/ventoy.json')),
]

def find_plugin_json():
    for path in PLUGIN_PATHS:
        if os.path.isfile(path):
            return path
    return None

def load_plugin_json():
    path = find_plugin_json()
    if not path:
        return None, None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f), path

def save_plugin_json(data, path=None):
    if not path:
        path = find_plugin_json()
    if not path:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return True
