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

    if len(index) != 1:
        raise Exception('\nExecution stopped: multiple specifications of -c/--config argument detected. ')

    if len(sys.argv) == index[0]+1 or (sys.argv[index[0]+1][0] == '-'):
        raise Exception('\nExecution stopped: invalid or missing argument after -c/-config specifier.')

    # Get subsequent input (the config file path)
    configFilePath = sys.argv[(index[0]+1)]
    # Normalize path to UNIX-style
    configFilePath = os.path.normpath(configFilePath) 
    # Load file. Throw error if not found
    print('\nLoading config file from:', configFilePath,'\n')
    if not(os.path.isfile(configFilePath)):
        raise Exception('\nERROR while loading specified config. file: NOT FOUND! Check input path.')
    else:
        # Split path and get extension
        (path2folder, filenameext) = os.path.split(configFilePath)
        (filename, ext) = os.path.splitext(filenameext)

        if ext == '.json':
            import json
            from pprint import pprint
        else: 
            raise Exception('\nExecution stopped: config. path does not point to a valid .json file.')
else:
    print('Using .txt config mode from default config file:', filenameext)
    time.sleep(1)



def read_parse_configJSON(configJSONfilePath):
    # Create empty configutation dictionaries
    body = {}
    geometry = {}
    scene = {}
    corto = {}
    scenarioData = {}

    # Load JSON file parsing numbers
    with open(configJSONfilePath, 'r') as json_file:
        ConfigDataJSONdict = json.load(json_file) # Load JSON as dict

    if isinstance(ConfigDataJSONdict, dict):
        # Get JSONdict scenarioData
        CameraData = ConfigDataJSONdict['CameraData']
        BlenderOpts = ConfigDataJSONdict['BlenderOpts']
        SceneData = ConfigDataJSONdict['SceneData']

    elif isinstance(ConfigDataJSONdict, list):
        # Pretty Printing has been enabled in MATLAB I guess...
        raise Exception('\nDecoded JSON as list not yet handled by this implementation. If JSON comes from MATLAB jsonencode(), disable PrettyPrint option.')

    # Manual Mapping to current CORTO version (26 Feb 2024)
    # SCENE

    # Required fields in:
    # CameraData: fov, resx, resy
    # SceneData: qFromTFtoIN, qFromCAMtoIN, rSun, rTargetBody, rStateCam
    # BlenderOpts: savepath, filmexposure, viewtransform, scattering, viewSamples, rendSamples, encoding

    scene['fov']         = CameraData['fov'  ]
    scene['resx']        = CameraData['resx' ]
    scene['resy']        = CameraData['resy' ]
    scene['labelDepth']  =  SceneData['labelDepth'] 
    scene['labelID']     =  SceneData['labelID'] 
    scene['labelSlopes'] =  SceneData['labelSlopes'] 

    # BODY
    #body['name'] = SceneData['scenarioName']
    #body['num'] = 1

    # BLENDER OPTIONS
    #scene['encoding'] = BlenderOpts['encoding']
    #scene['rendSamples'] = BlenderOpts['rendSamples']
    #scene['viewSamples'] = BlenderOpts['viewSamples']
    #scene['scattering'] = BlenderOpts['scattering']
    #scene['viewtransform'] = BlenderOpts['viewtransform']
    #scene['filmexposure'] = BlenderOpts['filmexposure']
    
    # Handle invalid savepath specification defaulting to "output" folder
    if 'savepath' in BlenderOpts and os.path.isdir(os.path.normpath(BlenderOpts['savepath'])):
        corto['savepath'] = os.path.normpath(BlenderOpts['savepath'])
    else:
        print('Specified savepath not found. Defaulting to repository "output" folder:')
        currentPath = os.path.dirname(os.path.normpath(__file__)) # Save current path
        os.chdir('../output') # Go to output path
        corto['savepath'] = os.path.abspath(os.getcwd()) # Save savepath into corto list
        os.chdir(currentPath) # Return to script execution directory
        print(corto['savepath'])
            
    # CAMERA, TARGET and ILLUMINATION
    scenarioData['rStateCam']    = np.array(SceneData['rStateCam'])    
    scenarioData['rTargetBody']  = np.array(SceneData['rTargetBody'])
    scenarioData['rSun']         = np.array(SceneData['rSun'])         
    scenarioData['qFromCAMtoIN'] = np.array(SceneData['qFromCAMtoIN'])
    scenarioData['qFromTFtoIN']  = np.array(SceneData['qFromTFtoIN'])  
    scenarioData['ID'] = np.arange(len(SceneData['rStateCam'])).flatten()

    geometry['ii0'] = 0 # Initial index for rendering

    # Display loaded configuration variables
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

    return body, geometry, scene, corto, scenarioData

if __name__ == '__main__':
    configJSONfilePath = os.path.abspath('C:\\devDir\\corto_PeterCdev\\functions\\rendering\\CORTO_CONFIG.json')
    body, geometry, scene, corto, scenarioData = read_parse_configJSON(configJSONfilePath)
    scale_BU = 1
    # ID
    ID_pose = scenarioData['ID']
    # Body
    R_pos_BODY = scenarioData['rTargetBody']*scale_BU # (BU) 
    R_q_BODY = scenarioData['qFromTFtoIN'] #from_txt[:,4:8] # (-) 
    # Camera
    R_pos_SC = scenarioData['rStateCam']*scale_BU #from_txt[:,8:11]*scale_BU # (BU) 
    R_q_SC = scenarioData['qFromCAMtoIN'] # from_txt[:,11:15] # (-) 
    # Sun 
    R_pos_SUN = scenarioData['rSun'] #from_txt[:,15:18] # (BU) 
    
    #read_parse_configJSON(configJSONfilePath)
    print('EXECUTION TERMINATION LINE')

    # Test input arguments (recall that the script name is actually an argument [0], just like in calling a main program in cpp)
    #print('\nCheck size of input arguments:', len(sys.argv)) # prints python_script.py
    #subprocess.run(['powershell', 'clear']) # powershell must be called first to allows use of UNIX commands
    #print('\nPrinting all arguments:')
    #for arg in sys.argv:
    #    print(arg)