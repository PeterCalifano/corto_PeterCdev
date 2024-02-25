import mathutils
import numpy as np
import csv
import os
import time
import math

# PeterCdev
import json
from pprint import pprint

from random import randint
from datetime import datetime

def read_parse_configJSON(configJSONfilePath):
    # Create empty configutation dictionaries
    body = {}
    geometry = {}
    scene = {}
    corto = {}

    # Load JSON file parsing numbers
    with open(configJSONfilePath, 'r') as json_file:
        ConfigDataJSON = json.load(json_file, parse_float=True, parse_int=True)

    # Test printing
    print(ConfigDataJSON)

    return body, geometry, scene, corto