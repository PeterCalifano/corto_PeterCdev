# WIP 
# This script is used to render the Didymos scene from input transmitted by the milani-gnc prototype.
# This CORTO interface works by transmitting directly the image vector to Simulink as loaded from the output_path folder.
# Because the input image is sent to Simulink as seen from the viewer node of the composite, the image is encoded in linear space
# A gamma-correction is applied on Simulink. This model works with the NAVCAM_HF_1_b model, the actual image is transmitted from Blender to Simulink,
# but it is transmitted encoded in linear space.

import socket
import struct
import time
import numpy as np
import bpy
import mathutils
import sys, os
import pickle
import logging

logging.getLogger('bpy.context').setLevel(logging.WARNING)  # Or logging.ERROR
bpy.app.debug = False  # Ensure debug mode is off

output_path = '/home/peterc/devDir/projects-DART/milani-gnc/artifacts/.tmpMilaniBlender'

#### (1) STATIC PARAMETERS ####

#NAVCAM
FOV_x = 21 # [deg], Horizontal FOV of the NAVCAM
FOV_y = 16 # [deg], Vertical FOV of the NAVCAM
sensor_size_x = 2048 #[pxl], Horizontal resolution of the images
sensor_size_y = 1536 #[pxl], Vertical resolution of the images
n_channels = 3 #[-], Number of channels of the images
bit_encoding = 8 #[-], Number of bit per pixel
compression = 15 #[-], Compression factor

#RENDERING ENGINE
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'GPU' # 'CPU' or 'GPU'
bpy.context.scene.cycles.samples = 64 # number of samples
bpy.context.scene.cycles.diffuse_bounces = 0 #To avoid diffused light from D1 to D2. (4) default
bpy.context.scene.cycles.tile_size = 64  # tile size(x)
#bpy.context.scene.cycles.tile_y = 64  # tile size(y)

#OTHERS

n_zfills = 6 #Number of digits used in the image name
model_name_1 = 'Didymos'
model_name_2 = 'Dimorphos'
sun_energy = 2 #Energy value of the sun-light in Blender
specular_factor = 0 #Specularity value for the sun-light in Blender
address = "0.0.0.0"
port_M2B = 51001 #  Port from Matlab to Blender
port_B2M = 30001 #  Port from Blender to Matlab

#### (2) SCENE SET UP ####
CAM = bpy.data.objects["Camera"]
SUN = bpy.data.objects["Sun"]
BODY_1 = bpy.data.objects[model_name_1]
BODY_2 = bpy.data.objects[model_name_2]

# Camera parameters
CAM.data.type = 'PERSP'
CAM.data.lens_unit = 'FOV'
CAM.data.angle = FOV_x * np.pi / 180
CAM.data.clip_start = 0.5 # [m] in Blender, but scaled in km
CAM.data.clip_end = 100 # [m] in Blender, but scaled in km
bpy.context.scene.render.pixel_aspect_x = 1
bpy.context.scene.render.pixel_aspect_y = 1
bpy.context.scene.render.resolution_x = sensor_size_x # CAM resolution (x)
bpy.context.scene.render.resolution_y = sensor_size_y # CAM resolution (y)

# Light parameters
SUN.data.type = 'SUN'
SUN.data.energy = sun_energy  # To perform quantitative analysis
SUN.data.specular_factor = specular_factor

# Environment parameters
bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)

if n_channels == 1:
    bpy.context.scene.render.image_settings.color_mode = 'BW'
elif n_channels == 3:
    bpy.context.scene.render.image_settings.color_mode = 'RGB'
elif n_channels == 4:
    bpy.context.scene.render.image_settings.color_mode = 'RGBA'

bpy.context.scene.render.image_settings.color_depth = str(bit_encoding)
bpy.context.scene.render.image_settings.compression = compression

#### (3) DYNAMIC PARAMETERS ####
#Initialization of Bodies, Cam and Sun
BODY_1.location = [0, 0, 0]
BODY_2.location = [0, 0, 0]
CAM.location = [10, 0, 0]
SUN.location = [0, 0, 0]

BODY_1.rotation_mode = 'QUATERNION'
BODY_2.rotation_mode = 'QUATERNION'
CAM.rotation_mode = 'QUATERNION'
SUN.rotation_mode = 'QUATERNION'

BODY_1.rotation_quaternion = [1, 0, 0, 0]
BODY_2.rotation_quaternion = [1, 0, 0, 0]
CAM.rotation_quaternion = [1, 0, 0, 0]
SUN.rotation_quaternion = [1, 0, 0, 0]

#### (4) FUNCTION DEFINITIONS ####
def Render(ii):
    name = '{:06d}.png'.format(int(ii))
    bpy.context.scene.render.filepath = output_path + '/' + name
    bpy.ops.render.render(write_still=1)
    return

def PositionAll(PQ_SC,PQ_Bodies,PQ_Sun):
    SUN.location = [0,0,0] # Because in Blender it is indifferent where the sun is located
    CAM.location = [PQ_SC[0], PQ_SC[1], PQ_SC[2]]
    BODY_1.location = [PQ_Bodies[0,0],PQ_Bodies[0,1],PQ_Bodies[0,2]]
    BODY_2.location = [PQ_Bodies[1,0],PQ_Bodies[1,1],PQ_Bodies[1,2]]
    SUN.rotation_quaternion = [PQ_Sun[3], PQ_Sun[4], PQ_Sun[5], PQ_Sun[6]]
    CAM.rotation_quaternion = [PQ_SC[3], PQ_SC[4], PQ_SC[5], PQ_SC[6]]
    BODY_1.rotation_quaternion = [PQ_Bodies[0,3], PQ_Bodies[0,4], PQ_Bodies[0,5], PQ_Bodies[0,6]]
    BODY_2.rotation_quaternion = [PQ_Bodies[1,3], PQ_Bodies[1,4], PQ_Bodies[1,5], PQ_Bodies[1,6]]
    return

#### (5) ESTABLISH UDP/TCP CONNECTION ####
print("Starting the UDP/TCP server...\n")
#print("Starting the TCP/IP server...\n")

#r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
r = socket.socket(socket.AF_INET, type=socket.SOCK_DGRAM)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    r.bind((address, port_M2B))
    print(f"Socket successfully bound to {address}:{port_M2B}")
except OSError as e:
    print(f"Failed to bind socket: {e}")

try:
    s.bind((address, port_B2M))
    print(f"Socket successfully bound to {address}:{port_B2M}")
except OSError as e:
    print(f"Failed to bind socket: {e}")

print(f"Binding successful. Starting listening to connection on port", port_M2B, "\n")
print(f"Data will be sent through port:", port_B2M, "\n")

print('Client connected from', address, ' as sender\n')

s.listen(5)
(clientsocket_send, address) = s.accept()
print('Client connected from', address, ' as receiver\n')

print("Waiting for data...\n")

#### (6) RECEIVE DATA AND RENDERING ####
# TODO remove render to avoid overhead while debugging the interface

receiving_flag = 1
ii = 0
while receiving_flag:
    #data, addr = r.recvfrom(512)
    data, addr = r.recvfrom(28*8) 
    numOfValues = int(len(data) / 8)
    print(f"Received data from {addr} with {numOfValues} values\n")
    data = struct.unpack('>' + 'd' * numOfValues, data) # Unpack bytes in data to double big-endian
    print('Data received: ', data)
    assert len(data) == 28, "ACHTUNG: data size is not as expected"
    n_bodies = len(data)/7-2 #Number of bodies apart from CAM and SUN
    print(f"Number of bodies: {n_bodies}\n")
    # Extract the PQ vectors from data received from cuborg
    PQ_Sun = data[0:7]
    PQ_SC = data[7:14]
    PQ_Bodies = data[14:]
    PQ_Bodies = np.reshape(PQ_Bodies,(int(n_bodies),7))
    # Print the PQ vector info
    print('SUN:   POS ' +  str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
    print('SC:    POS ' +  str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))
    for jj in np.arange(0,n_bodies):
        print('BODY (' + str(jj) + '):   POS: ' +  str(PQ_Bodies[int(jj),0:3]) + ' - Q ' + str(PQ_Bodies[int(jj),3:7]))
    #Position all bodies in the scene
    PositionAll(PQ_SC,PQ_Bodies,PQ_Sun)

    # Redirect stdout and stderr
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        # Take a picture without printing logs...
        Render(ii)
    finally:
        # Restore stdout and stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    # Read the pixels from the saved image
    img_read = bpy.data.images.load(filepath=output_path + '/' + '{:06d}.png'.format(int(ii))) 
    img_reshaped_vec = img_read.pixels[:] # Flatten the RGBA image to a vector
    # Pack the RGBA image as vector and transmit over TCP
    format_pack = '@' + str(len(img_reshaped_vec)) + 'd'
    print("Packing image vector as bytes...\n")
    img_pack = struct.pack(format_pack,*img_reshaped_vec)
    print("Sending image vector to client...\n")
    clientsocket_send.send(img_pack)
    print("Image sent correctly\n")
    
    print('------------------ Summary of operations for debug ------------------')
    print(f"Received data from {addr} with {numOfValues} values\n")
    print('Data received: ', data)
    print(f"Number of bodies: {n_bodies}\n")
    print('SUN:   POS ' + str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
    print('SC:    POS ' + str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))
    for jj in np.arange(0, n_bodies):
        print('BODY (' + str(jj) + '):   POS: ' +
              str(PQ_Bodies[int(jj), 0:3]) + ' - Q ' + str(PQ_Bodies[int(jj), 3:7]))
        
    #continue on the iteration
    ii = ii + 1
