import numpy as np
import csv
import os
import time
import math

import sys
import subprocess # Needed to run shell commands in python script

# PeterCdev
import json
from pprint import pprint

from random import randint
from datetime import datetime


filenameext = 'DEFAULT TXT CONFIG PATH'

####### [-] HANDLE SHELL ARGUMENTS [-] #######
'''
if ('-v' in sys.argv) or ('--verbose' in sys.argv):
    # VERBOSE MODE: print arguments
    print('\nVERBOSE MODE')
    print('N° of input arguments:', len(sys.argv)) # DEBUG PRINTING:
    print('Arguments list:')
    for arg in sys.argv:
        print(arg)

# Check if input config file is specified
if ('-c' in sys.argv) or ('--config' in sys.argv):
    # Get '-c' or '--config' and its index in sys.argv
    index = [id for id,x in enumerate(sys.argv) if (x=='-c' or x=='--config')] 
    # Get subsequent input (the config file path)
    configFilePath = sys.argv[index+1]
    # Normalize path to UNIX-style
    configFilePath = os.path.normpath(configFilePath) 

    # Load file. Throw error if not found
    print('Loading config file from:\n', configFilePath)
    if not(os.path.isfile(configFilePath)):
        raise Exception('ERROR while loading specified config. file: NOT FOUND! Check input path.')
    else:
        # Split path and get extension
        (path2folder, filenameext) = os.path.split(configFilePath)
        (filename, ext) = os.path.splitext(filenameext)

        if ext == '.json':
            import json
            from pprint import pprint
else:
    print('Using .txt config mode from default config file:', filenameext)
    time.sleep(1)

'''

def read_parse_configJSON(configJSONfilePath):
    # Create empty configutation dictionaries
    body = {}
    geometry = {}
    scene = {}
    corto = {}
    # Load JSON file parsing numbers
    with open(configJSONfilePath, 'r') as json_file:
        ConfigDataJSON = json.load(json_file, parse_float=float, parse_int=int)
    # Test printing
    print(ConfigDataJSON)


    # Display loaded variables
    for key, value in body.items():
        print(f"{key}: {value}")
    print('')
    for key, value in geometry.items():
        print(f"{key}: {value}")
    print('')
    for key, value in scene.items():
        print(f"{key}: {value}")
    print('')
    for key, value in corto.items():
        print(f"{key}: {value}")
    print('')

    return body, geometry, scene, corto

if __name__ == '__main__':
    configJSONfilePath = os.path.abspath('C:\\devDir\\corto_PeterCdev\\functions\\rendering\\CORTO_CONFIG.json')
    ConfigDataJSON = read_parse_configJSON(configJSONfilePath)

    #read_parse_configJSON(configJSONfilePath)
    print('EXECUTION TERMINATION LINE')

    # Test input arguments (recall that the script name is actually an argument [0], just like in calling a main program in cpp)
    #print('\nCheck size of input arguments:', len(sys.argv)) # prints python_script.py
    #subprocess.run(['powershell', 'clear']) # powershell must be called first to allows use of UNIX commands
    #print('\nPrinting all arguments:')
    #for arg in sys.argv:
    #    print(arg)