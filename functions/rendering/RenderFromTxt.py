import bpy
import mathutils
import numpy as np
import csv
import os
import time
import math
import sys

from random import randint
from datetime import datetime

######[1]  (START) INPUT SECTION (START) [1]######
filenameext = 'C:\\devDir\\corto_PeterCdev\\input\\ALL.txt'
#filenameext = 'ENTER THE PATH where your "ALL.txt" is saved '
######[1]  (END) INPUT SECTION (END) [1]######

####### [-] HANDLE SHELL ARGUMENTS [-] #######
if ('-v' in sys.argv) or ('--verbose' in sys.argv):
    # VERBOSE MODE: print arguments
    print('\nVERBOSE MODE')
    print('Number of input arguments:', len(sys.argv)) # DEBUG PRINTING:
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
    configFilePath = os.path.abspath(configFilePath) 
    # Load file. Throw error if not found
    print('\nLoading config file from:', configFilePath,'\n')
    if not(os.path.isfile(configFilePath)):
        raise Exception('\nERROR while loading specified config. file: NOT FOUND! Check input path.')
    else:
        # Split path and get extension
        (path2folder, filenameext) = os.path.split(configFilePath)
        (filename, configExt) = os.path.splitext(filenameext)

        if configExt == '.json':
            import json
            from pprint import pprint
        else: 
            raise Exception('\nExecution stopped: config. path does not point to a valid .json file.')
else:
    print('Using .txt config mode from default config file:', filenameext)
    configFilePath = filenameext
    configExt = '.txt'
    time.sleep(1)


###### [2] PARSER FUNCTIONS DEFINITIONS [2]###### 

def read_parse_configJSON(configJSONfilePath):
    # Create empty configutation dictionaries
    body = {}
    geometry = {}
    scene = {}
    corto = {}
    data = {}
    
    # Load JSON file parsing numbers
    if os.path.isfile(configJSONfilePath):
        print('CONFIG file FOUND, loading...')
    else:
        raise Exception('CONFIG file NOT FOUND. Check input path.')

    with open(configJSONfilePath, 'r') as json_file:
        try:
            ConfigDataJSONdict = json.load(json_file) # Load JSON as dict
        except Exception as exceptInstance:
            raise Exception('ERROR occurred:', exceptInstance.args)
        print('Config file: LOADED.')

    if isinstance(ConfigDataJSONdict, dict):
        # Get JSONdict data
        CameraData = ConfigDataJSONdict['CameraData']
        BlenderOpts = ConfigDataJSONdict['BlenderOpts']
        SceneData = ConfigDataJSONdict['SceneData']
    elif isinstance(ConfigDataJSONdict, list):
        # Pretty Printing has been enabled in MATLAB I guess...
        raise Exception('Decoded JSON as list not yet handled by this implementation. If JSON comes from MATLAB jsonencode(), make sure you are providing a struct() as input and not a cell.')
    else: 
        raise Exception('ERROR: incorrect JSON file formatting')

    # Manual Mapping to current CORTO version (26 Feb 2024). DEVNOTE: not optimal. It should be improved.
    # Required fields in:
    # CameraData: fov, resx, resy
    # SceneData: qFromTFtoIN, qFromCAMtoIN, rSun, rTargetBody, rStateCam
    # BlenderOpts: savepath, filmexposure, viewtransform, scattering, viewSamples, rendSamples, encoding

    # SCENE
    scene['fov']         = CameraData['fov'  ]
    scene['resx']        = CameraData['resx' ]
    scene['resy']        = CameraData['resy' ]
    scene['labelDepth']  = SceneData['labelDepth'] 
    scene['labelID']     = SceneData['labelID'] 
    scene['labelSlopes'] = SceneData['labelSlopes'] 

    # BODY
    body['name'] = SceneData['scenarioName']
    body['num'] = 1

    # BLENDER OPTIONS
    scene['encoding']      = BlenderOpts['encoding']
    scene['rendSamples']   = BlenderOpts['rendSamples']
    scene['viewSamples']   = BlenderOpts['viewSamples']
    scene['scattering']    = BlenderOpts['scattering']
    scene['viewtransform'] = BlenderOpts['viewtransform']
    scene['filmexposure']  = BlenderOpts['filmexposure']

    corto['savepath'] = os.path.normpath(BlenderOpts['savepath'])
    corto['redirect_output'] = BlenderOpts.get('redirect_output', False)

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

    # CAMERA, TARGET and ILLUMINATIONs
    data['rStateCam']    = np.array(SceneData['rStateCam'])    
    data['rTargetBody']  = np.array(SceneData['rTargetBody'])
    data['rSun']         = np.array(SceneData['rSun'])         
    data['qFromCAMtoIN'] = np.array(SceneData['qFromINtoCAM'])
    data['qFromTFtoIN']  = np.array(SceneData['qFromINtoTF'])  
    data['ID']           = np.arange(len(SceneData['rStateCam'])).flatten()

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

    json_file.close()
    return body, geometry, scene, corto, data

def read_parse_configTXT(configTXTfilePath):
    body = {}
    geometry = {}
    scene = {}
    corto = {}
    with open(configTXTfilePath, 'r') as file:
        for line in file:
            # Skip comments and empty lines
            if line.strip() == '' or line.startswith('#'):
                continue
            # Split the line at the '=' sign
            key, value = map(str.strip, line.split('='))
            # Extract the first word before the underscore
            category = key.split('_')[0]
            # Convert the value to the appropriate type (int or float if possible)
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass  # Keep it as a string if it can't be converted
            # Save the variable to the corresponding dictionary
            if category == 'body':
                body[key.split('_')[1]] = value
            elif category == 'geometry':
                geometry[key.split('_')[1]] = value
            elif category == 'scene':
                scene[key.split('_')[1]] = value
            elif category == 'corto':
                corto[key.split('_')[1]] = value
    # Display the loaded variables
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
    
    file.close()
    return body, geometry, scene, corto

###### [1] SETUP FUNCTIONS DEFINITIONS [1]######

def PositionAll(ii):
    POS_BODY_ii = R_pos_BODY[ii,:]
    OR_BODY_ii = R_q_BODY[ii,:]
    POS_SC_ii = R_pos_SC[ii,:]
    OR_SC_ii = R_q_SC[ii,:]
    POS_SUN_ii = R_pos_SUN[ii,:]
    # BODY position
    BODY.location[0] = POS_BODY_ii[0]
    BODY.location[1] = POS_BODY_ii[1]
    BODY.location[2] = POS_BODY_ii[2]
    # BODY orientation
    BODY.rotation_mode = 'QUATERNION'
    BODY.rotation_quaternion[0] = OR_BODY_ii[0]
    BODY.rotation_quaternion[1] = OR_BODY_ii[1]
    BODY.rotation_quaternion[2] = OR_BODY_ii[2]
    BODY.rotation_quaternion[3] = OR_BODY_ii[3]
    # CAM position
    CAM.location[0] = POS_SC_ii[0]
    CAM.location[1] = POS_SC_ii[1]
    CAM.location[2] = POS_SC_ii[2]
    print('CAM POSITION:', POS_SC_ii)
    # CAM orientation
    CAM.rotation_mode = 'QUATERNION'
    CAM.rotation_quaternion[0] = OR_SC_ii[0]
    CAM.rotation_quaternion[1] = OR_SC_ii[1]
    CAM.rotation_quaternion[2] = OR_SC_ii[2]
    CAM.rotation_quaternion[3] = OR_SC_ii[3]
    print('CAM QUATERNION:', OR_SC_ii)
    # SUN position 
    SunVector = POS_SUN_ii
    print('SUN POSITION:', POS_SUN_ii)
    direction = mathutils.Vector(SunVector/np.linalg.norm(SunVector))
    rot_quat = direction.to_track_quat('Z', 'Y')
    SUN.location[0] = POS_SUN_ii[0]
    SUN.location[1] = POS_SUN_ii[1]
    SUN.location[2] = POS_SUN_ii[2]
    SUN.rotation_mode = 'QUATERNION'
    SUN.rotation_quaternion = rot_quat# Camera
    return

def ApplyScattering(SG_name,POS_camera_ii, POS_SUN_ii, function, albedo):
    SG_name.nodes["CAM_X"].outputs[0].default_value = POS_camera_ii[0]
    SG_name.nodes["CAM_Y"].outputs[0].default_value = POS_camera_ii[1]
    SG_name.nodes["CAM_Z"].outputs[0].default_value = POS_camera_ii[2]
    SG_name.nodes["SUN_X"].outputs[0].default_value = POS_SUN_ii[0]
    SG_name.nodes["SUN_Y"].outputs[0].default_value = POS_SUN_ii[1]
    SG_name.nodes["SUN_Z"].outputs[0].default_value = POS_SUN_ii[2]
    SG_name.nodes["P_PHFunction"].outputs[0].default_value = function
    SG_name.nodes["P_Albedo"].outputs[0].default_value = albedo

def Render(ii):
    name = '{}.png'.format(str(int(ii+1)).zfill(6))
    bpy.context.scene.render.filepath = os.path.join(output_img_savepath,name)
    bpy.ops.render.render(write_still = 1)    
    return

def MakeDir(path):
    try:
        os.mkdir(path)
    except OSError:
        print ('Creation of the directory %s failed' % path)
    else:
        print ('Successfully created the directory %s ' % path)

# Set the keyframe
def SetKeyframe(ii):
    bpy.context.scene.frame_current = ii

def SaveDepth(ii):
    """Obtains depth map from Blender render.
    return: The depth map of the rendered camera view as a numpy array of size (H,W).
    """
    z = bpy.data.images['Viewer Node'] # Get output array from Blender 
    height, width = z.size
    print("Got Depth map of size: ", z.size)

    dmap = np.array(z.pixels, dtype=np.int16) # convert to numpy array
    # Reshape into image array as [H, W, Depth]
    dmap = np.reshape(dmap, (height, width, 4))[:,:,0]
    
    dmap = np.rot90(dmap, k=2)
    dmap = np.fliplr(dmap)
    txtname = '{num:06d}'
    np.savetxt(os.path.join(output_label_savepath, 'depth', txtname.format(num=(ii+1)) + '.txt'), dmap, delimiter=' ',fmt='%.5f')
    return

def GenerateTimestamp():
    timestamp = datetime.now()
    formatted_timestamp = timestamp.strftime("%Y_%m_%d_%H_%M_%S")
    return formatted_timestamp


##################### MAIN STARTS HERE ###########################
if __name__ == '__main__': # Blender call makes this script to run as main
    try:
        if configExt == '.json':
            print('USING JSON config mode... ')
            body, geometry, scene, corto, scenarioData = read_parse_configJSON(configFilePath)
            print('CONFIG file loading: COMPLETED')
            time.sleep(1)

        elif configExt == '.txt':
            print('USING TXT config mode')
            body, geometry, scene, corto = read_parse_configTXT(configFilePath)
            print('CONFIG file loading: COMPLETED')
            time.sleep(1)   
        else:
            raise Exception('Invalid configuration file extension. Supported: [.json, .txt]')

        ######[2]  SETUP OBJ PROPERTIES [2]######
        # PeterC dev. note: ideally scale_BU should be read from the Blender model, such that input units are allowed to be in the agreed SI units, i.e. km without modifications
        # Set object names
        try:
            CAM = bpy.data.objects["Camera"]
            SUN = bpy.data.objects["Sun"]
            if body['name'] == 'S1_Eros':
                albedo = 0.15 # TBD
                SUN_energy = 7 # TBD
                BODY = bpy.data.objects["Eros"]
                scale_BU = 10 
                texture_name = 'Eros Grayscale'
            elif body['name'] == 'S2_Itokawa':
                albedo = 0.15 # TBD
                SUN_energy = 5 # TBD
                BODY = bpy.data.objects["Itokawa"]
                scale_BU = 0.2 # MODIFIED, was 0.2
                texture_name = 'Itokawa Grayscale'
            elif body['name'] == 'S4_Bennu':
                albedo = 0.15 # TBD
                SUN_energy = 7 # TBD
                BODY = bpy.data.objects["Bennu"]
                scale_BU = 0.2
                texture_name = 'Bennu_global_FB34_FB56_ShapeV28_GndControl_MinnaertPhase30_PAN_8bit'
            elif body['name'] == 'S5_Didymos':
                albedo = 0.15 # TBD
                SUN_energy = 7 # TBD
                BODY = bpy.data.objects["Didymos"]
                BODY_Secondary = bpy.data.objects["Dimorphos"]
                scale_BU = 0.2
            elif body['name'] == 'S5_Didymos_Milani':
                albedo = 0.15 # TBD
                SUN_energy = 7 # TBD
                BODY = bpy.data.objects["Didymos"]
                BODY_Secondary = bpy.data.objects["Dimorphos"]
                scale_BU = 0.5
            elif body['name'] == 'S6_Moon':
                albedo = 0.169 # TBD
                SUN_energy = 30 # TBD
                BODY = bpy.data.objects["Moon"]
                scale_BU = 1 # Does nothing!
                displacement_name = 'ldem_64' # Does nothing!
                texture_name = 'lroc_color_poles_64k' # Does nothing!
            elif body['name'] == 'S7_MoonFlat':
                albedo = 0.169 # TBD
                SUN_energy = 30 # TBD
                BODY = bpy.data.objects["Moon"]
                scale_BU = 1 # Does nothing!
                texture_name = 'lroc_color_poles_64k' # Does nothing!
            else:
                raise Exception('Input model name',body['name'],'not found.')
        except Exception as inst:
            print('ERROR occurred during objects properties setup:', inst.args)
            raise Exception('ERROR occurred during objects properties setup:', inst.args)
        # CAM properties
        CAM.data.type = 'PERSP'
        CAM.data.lens_unit = 'FOV'
        CAM.data.angle = scene['fov'] * np.pi / 180
        CAM.data.clip_start = 0.1 # [m]
        CAM.data.clip_end = 10000 # [m]

        bpy.context.scene.cycles.film_exposure = scene['filmexposure']
        bpy.context.scene.view_settings.view_transform = scene['viewtransform']
        bpy.context.scene.render.pixel_aspect_x = 1
        bpy.context.scene.render.pixel_aspect_y = 1

        bpy.context.scene.render.resolution_x = scene['resx'] # CAM resolution (x)
        bpy.context.scene.render.resolution_y = scene['resy'] # CAM resolution (y)
        bpy.context.scene.render.image_settings.color_mode = 'BW'
        bpy.context.scene.render.image_settings.color_depth = str(scene['encoding'])
        if body['name'] == 'S5_Didymos' or body['name'] == 'S5_Didymos_Milani':
            bpy.context.scene.cycles.diffuse_bounces = 0 

        # SUN properties
        SUN.data.type = 'SUN'
        SUN.data.energy = SUN_energy  # To perform quantitative analysis
        SUN.data.angle = 0.53*np.pi/180

        # BODY properties
        BODY.location = [0,0,0]
        BODY.rotation_mode = 'XYZ'
        BODY.rotation_euler = [0,0,0]
        if body['name'] == 'S5_Didymos' or body['name'] == 'S5_Didymos_Milani':
            bpy.context.scene.cycles.diffuse_bounces = 0 
            BODY.pass_index = 1
            BODY_Secondary.pass_index = 2
            BODY_Secondary.location = [1.2,0,0]
            BODY_Secondary.rotation_mode = 'XYZ'
            BODY_Secondary.rotation_euler = [0,0,0]
            if body['name'] == 'S5_Didymos_Milani':
                BODY.scale = [1,1,0.78]
                BODY_Secondary.scale = [0.850, 1.080, 0.840]     
        # WORLD properties
        bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)

        # RENDERING ENGINE properties 
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.device = 'GPU'
        bpy.context.scene.cycles.samples = scene['rendSamples']
        bpy.context.scene.cycles.preview_samples = scene['viewSamples']

        # Set the device_type
        bpy.context.preferences.addons["cycles"].preferences.compute_device_type = "CUDA"

        ######[3]  EXTRACT DATA FROM CONFIG FILE [3]######
        try:
            print('DATA Loading: STARTED')
            if configExt == '.json':
                # ID
                ID_pose = scenarioData['ID']
                HOW_MANY_FRAMES = len(ID_pose)
                print(HOW_MANY_FRAMES)
                # Body
                R_pos_BODY = scenarioData['rTargetBody']*scale_BU # (BU) 
                R_q_BODY = scenarioData['qFromTFtoIN'] #from_txt[:,4:8] # (-) 
                # Camera
                R_pos_SC = scenarioData['rStateCam']*scale_BU #from_txt[:,8:11]*scale_BU # (BU) 
                R_q_SC = scenarioData['qFromCAMtoIN'] # from_txt[:,11:15] # (-) 
                # Sun 
                R_pos_SUN = scenarioData['rSun'] #from_txt[:,15:18] # (BU) 
            elif configExt == '.txt':
                    #I/O pathsSSSSS
                home_path = bpy.path.abspath("//")
                txt_path = os.path.join(home_path, geometry['name'] + '.txt')
                n_rows = len(open(os.path.join(txt_path)).readlines())
                n_col = 18 # HARDCODED: PeterC comment: SPLIT is critically dependend on this value!
                HOW_MANY_FRAMES = n_rows
                from_txt = np.zeros((n_rows,n_col))

                file = open(os.path.join(txt_path),'r',newline = '')
                ii=0
                for line in file:
                    fields = line.split(" ")
                    for jj in range(0,n_col,1):
                        from_txt[ii,jj] = float(fields[jj])
                    ii = ii+1

                file.close()
                # [0] ID or ET
                # [1,2,3] Body pos [BU] and [4,5,6,7] orientation [-]
                # [8,9,10] Camera pos [BU] and [11,12,13,14] orientation [-] # TO CHECK: WHICH QUATERNION CONVENTION?
                # [15,16,17] Sun pos [BU]

                # ID
                ID_pose = from_txt[:,0]
                # Body
                R_pos_BODY = from_txt[:,1:4]*scale_BU # (BU) 
                R_q_BODY = from_txt[:,4:8] # (-) 
                # Camera
                R_pos_SC = from_txt[:,8:11]*scale_BU # (BU) 
                R_q_SC = from_txt[:,11:15] # (-) 
                # Sun 
                R_pos_SUN = from_txt[:,15:18] # (BU) 

            print('DATA Loading: COMPLETED')
        except Exception as inst:
            print('ERROR occurred during DATA formatting:', inst.args)
            raise Exception('ERROR occurred during DATA formatting:', inst.args)



        ### CYCLIC RENDERINGS ###
        print('RENDERING routine: STARTED')

        if corto['redirect_output'] == False:
            output_timestamp = GenerateTimestamp()
            output_folderName = body['name'] + '_' + output_timestamp
            output_savepath = os.path.join(corto['savepath'],output_folderName)
            output_img_savepath = os.path.join(output_savepath,'img')
            output_label_savepath = os.path.join(output_savepath,'label')
        else:
            output_savepath = corto['savepath']
            output_img_savepath = os.path.join(output_savepath,'images')
            output_label_savepath = os.path.join(output_savepath,'label')


        if not(os.path.isdir(output_savepath)):
            MakeDir(output_savepath)

        if not(os.path.isdir(output_img_savepath)):
            MakeDir(output_img_savepath)

        try:
            if scene['labelDepth'] == 1 or scene['labelID'] == 1 or scene['labelSlopes'] == 1:
                MakeDir(output_label_savepath)
                if scene['labelDepth'] == 1:
                    MakeDir(os.path.join(output_label_savepath,'depth'))
                if scene['labelID'] == 1:
                    MakeDir(os.path.join(output_label_savepath,'IDmask'))
                    bpy.data.scenes["Scene"].node_tree.nodes["MaskOutput"].base_path = output_label_savepath
                    bpy.data.scenes["Scene"].node_tree.nodes['MaskOutput'].file_slots[0].path="\IDmask\Mask_1\######" 
                    bpy.data.scenes["Scene"].node_tree.nodes['MaskOutput'].file_slots[1].path="\IDmask\Mask_1_shadow\######" 
                    bpy.data.scenes["Scene"].node_tree.nodes['MaskOutput'].file_slots[2].path="\IDmask\Mask_2\######"
                    bpy.data.scenes["Scene"].node_tree.nodes['MaskOutput'].file_slots[3].path="\IDmask\Mask_2_shadow\######"
                if scene['labelSlopes'] == 1:
                    MakeDir(os.path.join(output_label_savepath,'slopes'))
                    bpy.data.scenes["Scene"].node_tree.nodes["SlopeOutput"].base_path = output_label_savepath
                    bpy.data.scenes["Scene"].node_tree.nodes['SlopeOutput'].file_slots[0].path="\slopes\######" 
        except:
            print('Scene labels assignments failed: SKIPPING')

        ## Cyclic rendering
        SetKeyframe(1)
        print('RENDERING of', HOW_MANY_FRAMES, ': STARTING...')
        time.sleep(0.5)
        for ii in range(0, HOW_MANY_FRAMES,1):
            SetKeyframe(ii+1)
            print('---------------Preparing for case: ',ii,'---------------')
            print('Position bodies')
            PositionAll(ii)
            bpy.context.view_layer.update()
            if ii<geometry['ii0']:
                print('--------------Not rendering---------------')
            else:
                bpy.context.view_layer.update()
                print('Apply scattering body')
                #ApplyScattering(bpy.data.node_groups["ScatteringGroup_D1"],R_pos_SC[ii],R_pos_SUN[ii],scene['scattering'],albedo)
                bpy.context.view_layer.update()
                time.sleep(2) # For contingency
                print('--------------Rendering---------------')
                Render(ii)
                if scene['labelDepth'] == 1:
                    SaveDepth(ii)

                # ADD SCENE FIGURE DISPLAY AND UPDATING AFTER EACH RENDERING  
                # MAKE IT OPTIONAL  
    except Exception as errInst:
        print('Error occurred during RenderFromTxt execution from Blender:\n', errInst.args)
        raise ('Error occurred during RenderFromTxt execution from Blender:\n', errInst.args)