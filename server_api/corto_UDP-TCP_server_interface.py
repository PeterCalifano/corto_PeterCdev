# WIP: rework for RAMSES  
# This script is used to render the Didymos scene from input transmitted by the milani-gnc prototype.
# This CORTO interface works by transmitting directly the image vector to Simulink as loaded from the output_path folder.
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
import sys
import os
import yaml
import numpy as np

output_path = '/home/peterc/devDir/projects-DART/milani-gnc/artifacts/.tmpMilaniBlender'

#### (1) STATIC PARAMETERS ####
try:
    # NAVCAM
    FOV_x = 21  # [deg], Horizontal FOV of the NAVCAM
    FOV_y = 16  # [deg], Vertical FOV of the NAVCAM
    sensor_size_x = 2048  # [pxl], Horizontal resolution of the images
    sensor_size_y = 1536  # [pxl], Vertical resolution of the images
    n_channels = 3  # [-], Number of channels of the images
    bit_encoding = 8  # [-], Number of bit per pixel
    compression = 15  # [-], Compression factor

    # RENDERING ENGINE
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'GPU'  # 'CPU' or 'GPU'
    bpy.context.scene.cycles.samples = 64  # number of samples
    # To avoid diffused light from D1 to D2. (4) default
    bpy.context.scene.cycles.diffuse_bounces = 0
    bpy.context.scene.cycles.tile_size = 64  # tile size(x)
    # bpy.context.scene.cycles.tile_y = 64  # tile size(y)

    # OTHERS

    n_zfills = 6  # Number of digits used in the image name
    model_name_1 = 'Didymos'
    model_name_2 = 'Dimorphos'
    sun_energy = 2  # Energy value of the sun-light in Blender
    specular_factor = 0  # Specularity value for the sun-light in Blender
    address = "127.0.0.1"
    port_M2B = 51001  # Port from Matlab to Blender
    port_B2M = 30001  # Port from Blender to Matlab
    DUMMY_OUTPUT = False

    #### (2) SCENE SET UP ####
    CAM = bpy.data.objects["Camera"]
    SUN = bpy.data.objects["Sun"]
    BODY_1 = bpy.data.objects[model_name_1]
    BODY_2 = bpy.data.objects[model_name_2]

    # Camera parameters
    CAM.data.type = 'PERSP'
    CAM.data.lens_unit = 'FOV'
    CAM.data.angle = FOV_x * np.pi / 180
    CAM.data.clip_start = 0.5  # [m] in Blender, but scaled in km
    CAM.data.clip_end = 100  # [m] in Blender, but scaled in km
    bpy.context.scene.render.pixel_aspect_x = 1
    bpy.context.scene.render.pixel_aspect_y = 1
    bpy.context.scene.render.resolution_x = sensor_size_x  # CAM resolution (x)
    bpy.context.scene.render.resolution_y = sensor_size_y  # CAM resolution (y)

    # Light parameters
    SUN.data.type = 'SUN'
    SUN.data.energy = sun_energy  # To perform quantitative analysis
    SUN.data.specular_factor = specular_factor

    # Environment parameters
    bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (
        0, 0, 0, 1)

    if n_channels == 1:
        bpy.context.scene.render.image_settings.color_mode = 'BW'
    elif n_channels == 3:
        bpy.context.scene.render.image_settings.color_mode = 'RGB'
    elif n_channels == 4:
        bpy.context.scene.render.image_settings.color_mode = 'RGBA'

    bpy.context.scene.render.image_settings.color_depth = str(bit_encoding)
    bpy.context.scene.render.image_settings.compression = compression

    #### (3) DYNAMIC PARAMETERS ####
    # Initialization of Bodies, Cam and Sun
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

    def PositionAll(PQ_SC, PQ_Bodies, PQ_Sun):

        # Because in Blender it is indifferent where the sun is located
        SUN.location = [0, 0, 0]
        CAM.location = [PQ_SC[0], PQ_SC[1], PQ_SC[2]]
        BODY_1.location = [PQ_Bodies[0, 0], PQ_Bodies[0, 1], PQ_Bodies[0, 2]]
        BODY_2.location = [PQ_Bodies[1, 0], PQ_Bodies[1, 1], PQ_Bodies[1, 2]]
        SUN.rotation_quaternion = [PQ_Sun[3], PQ_Sun[4], PQ_Sun[5], PQ_Sun[6]]
        CAM.rotation_quaternion = [PQ_SC[3], PQ_SC[4], PQ_SC[5], PQ_SC[6]]
        BODY_1.rotation_quaternion = [
            PQ_Bodies[0, 3], PQ_Bodies[0, 4], PQ_Bodies[0, 5], PQ_Bodies[0, 6]]
        BODY_2.rotation_quaternion = [
            PQ_Bodies[1, 3], PQ_Bodies[1, 4], PQ_Bodies[1, 5], PQ_Bodies[1, 6]]

        return

    #### (5) ESTABLISH UDP/TCP CONNECTION ####
    print("Starting the UDP/TCP server...\n")

    r = socket.socket(socket.AF_INET, type=socket.SOCK_DGRAM)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

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

    # r.listen()  # Not needed for UDP
    s.listen()
    (clientsocket_send, address) = s.accept()
    print('Client connected from', address, ' as receiver\n')

    #### (6) RECEIVE DATA AND RENDERING ####
    receiving_flag = 1
    ii = 0
    # (clientsocket_recv, address_recv) = r.accept()

    while receiving_flag:

        print("Waiting for data...\n")
        try:
            # data, address_recv = r.recvfrom(512)
            data_buffer, address_recv = r.recvfrom(512)

            # NOTE 28 doubles harcoded size of the data packet
            numOfValues = int(len(data_buffer) / 8)
            print(f"Received {len(data_buffer)} bytes from {address_recv}\n")
            print(f"Received number of doubles: {numOfValues} values\n")

            if not (numOfValues == 28):
                raise RuntimeError("ACHTUNG: array size is not as expected!")

        except RuntimeError as e:
            print(f"RuntimeError: {e}\n")
            print("Server will continue listening for new data...")
            continue

        # Casting to numpy array
        dtype = np.dtype(np.float64)  # Big-endian float64
        numpy_data_array = np.frombuffer(data_buffer, dtype=dtype)

        # data = struct.unpack('>' + 'd' * numOfValues, data) # Unpack bytes in data to double big-endian
        print('Array received: ', numpy_data_array)
        print(f"Array shape: {numpy_data_array.shape}\n")

        # Number of bodies apart from CAM and SUN
        n_bodies = 2  # DEVNOTE hardcoded because the computation present before is not working properly?
        print(f"Number of bodies: {n_bodies}\n")

        # Extract the PQ vectors from data received from cuborg
        PQ_Sun = numpy_data_array[0:7]
        PQ_SC = numpy_data_array[7:14]
        PQ_Bodies = numpy_data_array[14:]
        PQ_Bodies = np.reshape(PQ_Bodies, (int(n_bodies), 7))

        # Print the PQ vector info
        print('SUN:   POS ' + str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
        print('SC:    POS ' + str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))

        for jj in np.arange(0, n_bodies):
            print('BODY (' + str(jj) + '):   POS: ' +
                  str(PQ_Bodies[int(jj), 0:3]) + ' - Q ' + str(PQ_Bodies[int(jj), 3:7]))

        # Position all bodies in the scene
        PositionAll(PQ_SC, PQ_Bodies, PQ_Sun)

        if not DUMMY_OUTPUT:
            Render(ii)  # Render function call, uses data set by PositionAll
            # Read the pixels from the saved image
            img_read = bpy.data.images.load(
                filepath=output_path + '/' + '{:06d}.png'.format(int(ii)))

            # Get the type of the first pixel value
            pixel_dtype = type(img_read.pixels[0])
            print(f"Image datatype: {pixel_dtype}\n")
            # Convert to a NumPy array using the same type
            # Flatten the RGBA image to a vector
            img_reshaped_vec = np.array(img_read.pixels[:])
            print(f"Image datatype interpreted by numpy: {
                  type(img_reshaped_vec)}\n")

        else:
            # Random image for testing (4 is because of RGBA)
            img_reshaped_vec = np.float64(np.random.rand(
                4*sensor_size_x * sensor_size_y)).flatten()

        # Pack the RGBA image as vector and transmit over TCP using numpy
        img_pack = img_reshaped_vec.tobytes()

        print("Sending image vector to client...\n")
        clientsocket_send.send(img_pack)
        print("Image sent correctly\n")

        print('------------------ Summary of operations for monitoring ------------------')
        print(f"Received data from {address_recv} with {numOfValues} values\n")
        print(f"Number of bodies: {n_bodies}\n")
        print('SUN:   POS ' + str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
        print('SC:    POS ' + str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))
        for jj in np.arange(0, n_bodies):
            print('BODY (' + str(jj) + '):   POS: ' +
                  str(PQ_Bodies[int(jj), 0:3]) + ' - Q ' + str(PQ_Bodies[int(jj), 3:7]))

        # continue on the iteration
        ii = ii + 1
except KeyboardInterrupt:
    print("KeyboardInterrupt: Closing the server...\n")
    r.close()
    s.close()
    sys.exit(0)
except RuntimeError as e:
    print(f"Exception: {e}\n")
    r.close()
    s.close()
    sys.exit(1)
