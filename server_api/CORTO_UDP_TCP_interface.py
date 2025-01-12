"""
    Summary:
    This script sets up a UDP/TCP server to receive data for rendering scenes in Blender. It reads configuration parameters from a YAML file, initializes Blender scene objects, and processes incoming data to update the scene and render images. 
    Extended Summary:
    The order of the data in the buffer must be as follows:
    - PQ vector of the Sun (7 doubles)
    - PQ vector of the Spacecraft (7 doubles)
    - PQ vector of the bodies (7 doubles per body)
    PQ vector is defined as follows: 
    - [position, quaternion] = [x, y, z, q0, q1, q2, q3] as requested by Blender.
    Operations in the script:
    - Loads configuration parameters from a YAML file.
    - Initializes Blender scene objects (camera, sun, bodies).
    - Sets up a UDP/TCP server to receive data.
    - Processes incoming data to update the scene and render images.
    - Sends rendered images back to the client.
    Limitations:
    - The script is designed to work with a specific number of bodies (1 or 2). Needs modifications to support more bodies.
    - Camera and Sun are always assumed to be present in the scene and in the data buffer.
    Raises:
        RuntimeError: If the received data array size is not as expected.
        ValueError: If the number of bodies computed from buffer size is not an integer.
        ValueError: If the number of bodies is not equal to the value set in the config file.
"""

import socket
import numpy as np
import bpy
import sys, os
import numpy as np
import yaml 

# Set configuration file path. Default is the same folder of the script. # DEVNOTE: may be improved, but suffices for basic usage.
script_path = os.path.dirname(os.path.realpath(__file__))
CORTO_SLX_CONFIG_PATH = os.path.join(script_path, "CORTO_SLX_CONFIG.yaml")

# Load the YAML configuration
with open(CORTO_SLX_CONFIG_PATH, "r") as file:
    config = yaml.safe_load(file)

    # Get parsed configuration dicts
    navcam_config = config.get("NavCam_params", {})
    rendering_engine_config = config.get("RenderingEngine_params", {})
    server_config = config.get("Server_params", {})
    blender_model_config = config.get("BlenderModel_params", {})

    # Pretty print the configuration
    print("Configuration loaded from YAML file:")
    print(config)

#### (1) PARAMETERS ####
try:
    # NAVCAM
    # [deg], Horizontal FOV of the NAVCAM
    FOV_x = navcam_config.get("FOV_x")
    # [deg], Vertical FOV of the NAVCAM
    FOV_y = navcam_config.get("FOX_y")

    # [pxl], Horizontal resolution of the images
    sensor_size_x = navcam_config.get("sensor_size_x")

    # [pxl], Vertical resolution of the images
    sensor_size_y = navcam_config.get("sensor_size_y")

    # [-], Number of channels of the images
    n_channels = navcam_config.get("n_channels")

    # [-], Number of bit per pixel
    bit_encoding = navcam_config.get("bit_encoding")

    # [-], Compression factor
    compression = navcam_config.get("compression")

    # RENDERING ENGINE
    bpy.context.scene.render.engine = rendering_engine_config.get(
        "render_engine")  # 'CYCLES' or 'BLENDER_EEVEE'
    bpy.context.scene.cycles.device = rendering_engine_config.get(
        "device")  # 'CPU' or 'GPU'
    bpy.context.scene.cycles.samples = rendering_engine_config.get(
        "samples")  # Number of samples for the rendering

    # To avoid diffused light from D1 to D2. (4) default
    bpy.context.scene.cycles.diffuse_bounces = rendering_engine_config.get(
        "diffuse_bounces")

    # Set tile size (NOTE: option name is as below in newer Blender versions)
    bpy.context.scene.cycles.tile_size = rendering_engine_config.get(
        "tile_size")

    # BLENDER MODEL
    # Number of bodies # TODO (PC) now used only for assert, generalize to support any number of bodies (replace model_name with dict)
    num_bodies = blender_model_config.get("num_bodies")

    # Name of the bodies in the Blender scene
    model_name_1 = blender_model_config.get("bodies_names")[0]
    if num_bodies > 1:
        model_name_2 = blender_model_config.get("bodies_names")[1]

    # Energy value of the sun-light in Blender
    sun_energy = blender_model_config.get("sun_energy")

    # Specular factor of the sun-light in Blender
    specular_factor = blender_model_config.get("specular_factor")

    # SERVER
    output_path = server_config.get("output_path")  # Output path for the images
    address = server_config.get("address")  # Address of the server
    port_M2B = server_config.get("port_M2B")  # Port from Matlab to Blender
    port_B2M = server_config.get("port_B2M")  # Port from Blender to Matlab
    DUMMY_OUTPUT = server_config.get("DUMMY_OUTPUT")  # Flag to use dummy output

    #### (2) SCENE SET UP ####
    CAM = bpy.data.objects["Camera"]
    SUN = bpy.data.objects["Sun"]
    BODY_1 = bpy.data.objects[model_name_1]
    if num_bodies > 1:
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
    if num_bodies > 1:
        BODY_2.rotation_mode = 'QUATERNION'
    CAM.rotation_mode = 'QUATERNION'
    SUN.rotation_mode = 'QUATERNION'

    BODY_1.rotation_quaternion = [1, 0, 0, 0]
    if num_bodies > 1:
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
        # TODO function to rework, generalize and make more readable

        SUN.location = [0,0,0] # Because in Blender it is indifferent where the sun is located
        CAM.location = [PQ_SC[0], PQ_SC[1], PQ_SC[2]]
        BODY_1.location = [PQ_Bodies[0,0],PQ_Bodies[0,1],PQ_Bodies[0,2]]

        if num_bodies > 1:
            BODY_2.location = [PQ_Bodies[1,0],PQ_Bodies[1,1],PQ_Bodies[1,2]]

        SUN.rotation_quaternion = [PQ_Sun[3], PQ_Sun[4], PQ_Sun[5], PQ_Sun[6]]
        CAM.rotation_quaternion = [PQ_SC[3], PQ_SC[4], PQ_SC[5], PQ_SC[6]]
        BODY_1.rotation_quaternion = [PQ_Bodies[0,3], PQ_Bodies[0,4], PQ_Bodies[0,5], PQ_Bodies[0,6]]

        if num_bodies > 1:
            BODY_2.rotation_quaternion = [PQ_Bodies[1,3], PQ_Bodies[1,4], PQ_Bodies[1,5], PQ_Bodies[1,6]]

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
    print('Client connected from', address,' as receiver\n')

    #### (6) RECEIVE DATA AND RENDERING ####
    receiving_flag = 1
    ii = 0

    # TODO (PC) server management to be improved (error handling to avoid server crashes in certain cases)
    while receiving_flag:

        print("Waiting for data...\n")
        try:
            # data, address_recv = r.recvfrom(512)
            data_buffer, address_recv = r.recvfrom(512)  

            # NOTE 28 doubles harcoded size of the data packet
            numOfValues = int(len(data_buffer) / 8)
            print(f"Received {len(data_buffer)} bytes from {address_recv}\n")
            print(f"Received number of doubles: {numOfValues} values\n")

            if not (numOfValues == 14 + 7 * num_bodies): 
                raise RuntimeError("ACHTUNG: array size is not as expected!")
            
        except RuntimeError as e:
            print(f"RuntimeError: {e}\n")
            print("Server will continue listening for new data...")
            continue

        # Casting to numpy array
        dtype = np.dtype(np.float64)  # Big-endian float64
        numpy_data_array = np.frombuffer(data_buffer, dtype=dtype)

        #data = struct.unpack('>' + 'd' * numOfValues, data) # Unpack bytes in data to double big-endian
        print('Array received: ', numpy_data_array)
        print(f"Array shape: {numpy_data_array.shape}\n")

        # Number of bodies apart from CAM and SUN
        # Number of bodies apart from CAM and SUN
        n_bodies = (numOfValues - 14)/7  # Must be integer!

        if n_bodies % 1 != 0:
            raise ValueError("ACHTUNG: Number of bodies computed from buffer size is not an integer!")
        else:
            n_bodies = int(n_bodies)

        if n_bodies != num_bodies:
            raise ValueError(
                "ACHTUNG: Number of bodies is not equal to the value set in config file! Found: {n_bodies}, Expected: {num_bodies}")

        # Extract the PQ vectors from data received from cuborg
        PQ_Sun = numpy_data_array[0:7]
        PQ_SC = numpy_data_array[7:14]
        PQ_Bodies = numpy_data_array[14:]
        PQ_Bodies = np.reshape(PQ_Bodies,(int(n_bodies),7))

        # Print the PQ vector info
        print('SUN:   POS ' +  str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
        print('SC:    POS ' +  str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))

        for jj in np.arange(0,n_bodies):
            print('BODY (' + str(jj) + '):   POS: ' +  str(PQ_Bodies[int(jj),0:3]) + ' - Q ' + str(PQ_Bodies[int(jj),3:7]))

        # Position all bodies in the scene
        PositionAll(PQ_SC,PQ_Bodies,PQ_Sun)

        if not DUMMY_OUTPUT: # DEVNOTE: DUMMY_OUTPUT is a flag to test the server without rendering
            Render(ii) # Render function call, uses data set by PositionAll
            # Read the pixels from the saved image
            img_read = bpy.data.images.load(filepath=output_path + '/' + '{:06d}.png'.format(int(ii))) 

            # Get the type of the first pixel value
            pixel_dtype = type(img_read.pixels[0])
            print(f"Image datatype: {pixel_dtype}\n")
            
            # Convert to a NumPy array using the same type
            img_reshaped_vec = np.array(img_read.pixels[:]) # Flatten the RGBA image to a vector
            print(f"Image datatype interpreted by numpy: {type(img_reshaped_vec)}\n")

        else:
            img_reshaped_vec = np.float64(np.random.rand(4*sensor_size_x * sensor_size_y)).flatten() # Random image for testing (4 is because of RGBA)

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
            
        #continue on the iteration
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

