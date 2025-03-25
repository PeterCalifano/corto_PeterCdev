"""
    Summary:
    This script sets up a UDP/TCP server to receive data for rendering scenes in Blender. It reads configuration parameters from a YAML file, initializes Blender scene objects, and processes incoming data to update the scene and render images. The Blender file it will use is provided by user when calling Blender with this script. Make sure to match the number of bodies. Tested with python >=3.10 and Blender >=4.0.0.
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

DEBUG_MODE = True # Set to True to enable additional printout

import socket
from time import sleep
import numpy as np
import bpy
import sys, os
import copy
import numpy as np
# Check if yaml is installed and attempt automatic installation if not
try:
    import yaml 
except ImportError:
    print("PyYAML is not installed. Please install it before using this script.")
    print("To do so, first find which interpreted Blender is using by running in Blender scripting section:")
    print("import sys")
    print("print(sys.executable)")
    print("Then, in the terminal, run:")
    print("/path/to/blender/python -m pip install pyyaml")
    print("Finally, check if the installation was successful by running:")
    print("/path/to/blender/python -m pip show pyyaml")

    print("\n\nBut... since PC likes to make everything automagic, let's try to install it for you. It will likely work only for Linux :)")
    try:
        import subprocess
        import sys
        import os

        # Get the Python interpreter path used by Blender
        blender_python_path = sys.executable
        
        # Ensure pip is installed and up-to-date using the Python interpreter used by Blender
        subprocess.check_call([blender_python_path, "-m", "ensurepip", "--upgrade"])
        
        # Install PyYAML using the Python interpreter used by Blender
        subprocess.check_call([blender_python_path, "-m", "pip", "install", "pyyaml"])

        # Check if the installation was successful
        subprocess.check_call([blender_python_path, "-m", "pip", "show", "pyyaml"])
        
        # Import yaml
        import yaml
        print("PyYAML was successfully installed and imported :D")

    except subprocess.CalledProcessError as e:
        print(f"Automatic installation failed. Error details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Automatic installation failed. Error details: {e}")
        sys.exit(1)
    

# Set configuration file path. Default is the same folder of the script. # DEVNOTE: may be improved, but suffices for basic usage.
script_path = os.path.dirname(os.path.realpath(__file__))
# Check if file ext is .blend
if not script_path.endswith(".blend"):
    CONFIG_PATH = os.path.join(script_path, "BlenderPy_UDP_TCP_CONFIG.yml")
else: 
    # Use hardcoded path (within blender)
    CONFIG_PATH = os.path.join("/home/peterc/devDir/rendering-sw/corto_PeterCdev/server_api/BlenderPy_UDP_TCP_CONFIG.yml")

def is_socket_closed(sock: socket.socket) -> bool:
    """
    is_socket_closed _summary_

    _extended_summary_

    :param sock: _description_
    :type sock: socket.socket
    :return: _description_
    :rtype: bool
    """
    try:
        # This will try to read bytes without blocking and also without removing them from buffer (peek only)
        data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
        if len(data) == 0:
            return True
    except BlockingIOError:
        return False  # socket is open and reading from it would block
    except ConnectionResetError:
        return True  # socket was closed for some other reason
    except Exception as e:
        print(f"Error occurred while checking client socket status: {e}")
        return False
    return False


# Load the YAML configuration
with open(CONFIG_PATH, "r") as file:
    config = yaml.safe_load(file)

    # Get parsed configuration dicts
    camera_config = config.get("Camera_params", {})
    rendering_engine_config = config.get("RenderingEngine_params", {})
    server_config = config.get("Server_params", {})
    blender_model_config = config.get("BlenderModel_params", {})

    # Pretty print the configuration
    print("Configuration loaded from YAML file:")
    print(config)

#### (1) PARAMETERS ####
try:
    print('Assigning parameters from the configuration file...\n')
    # CAMERA
    # [deg], Horizontal FOV of the CAMERA
    FOV_x = camera_config.get("FOV_x")
    # [deg], Vertical FOV of the CAMERA
    FOV_y = camera_config.get("FOX_y")

    # [pxl], Horizontal resolution of the images
    sensor_size_x = camera_config.get("sensor_size_x")

    # [pxl], Vertical resolution of the images
    sensor_size_y = camera_config.get("sensor_size_y")

    # [-], Number of channels of the images
    n_channels = camera_config.get("n_channels")

    # [-], Number of bit per pixel
    bit_encoding = camera_config.get("bit_encoding")

    # [-], Compression factor
    compression = camera_config.get("compression")

    # RENDERING ENGINE
    bpy.context.scene.render.engine = rendering_engine_config.get(
        "render_engine")  # 'CYCLES' or 'BLENDER_EEVEE'
    bpy.context.scene.cycles.device = rendering_engine_config.get(
        "device")  # 'CPU' or 'GPU' # NOTE This is a read-only property!
    bpy.context.scene.cycles.samples = rendering_engine_config.get(
        "samples")  # Number of samples for the rendering

    # To avoid diffused light from D1 to D2. (4) default
    bpy.context.scene.cycles.diffuse_bounces = rendering_engine_config.get(
        "diffuse_bounces")

    # Set tile size (NOTE: option name is as below in newer Blender versions)
    bpy.context.scene.cycles.tile_size = rendering_engine_config.get(
        "tile_size")
    
    # Print rendering parameters
    print('Rendering engine set to: ', bpy.context.scene.render.engine)
    print('Rendering device set to: ', bpy.context.scene.cycles.device)
    print('Number of samples set to: ', bpy.context.scene.cycles.samples)
    print('Diffuse bounces set to: ', bpy.context.scene.cycles.diffuse_bounces)
    print('Tile size set to: ', bpy.context.scene.cycles.tile_size)

    # BLENDER MODEL
    # Number of bodies # TODO (PC) now used only for assert, generalize to support any number of bodies (replace model_name with dict)
    num_bodies = blender_model_config.get("num_bodies")

    # Name of the bodies in the Blender scene
    model_name_1 = blender_model_config.get("bodies_names")[0]
    if num_bodies > 1:
        model_name_2 = blender_model_config.get("bodies_names")[1]

    # Light object name
    light_names = blender_model_config.get("light_names")

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
    tcpTimeOutValue = 120 # [s]
    tcpTimeOutValue = 120 # [s]

    print('Parameters loaded successfully!\n')

    # Check if output_path exists, if not create it
    if not os.path.exists(output_path):
        print('Output path does not exist. Creating it...')
        os.makedirs(output_path)
    else:
        # If it exists, check if it contains a file named "000001.png" and modify output path to avoid overwriting
        image_test_path = os.path.join(output_path, "000001.png")
        if os.path.exists(image_test_path):
            counter = 0
            new_output_path = f"{output_path}_{counter}"
            # Keep incrementing the counter until we find a folder that does not contain a "000000.png" file
            while os.path.exists(new_output_path) and os.path.exists(os.path.join(new_output_path, "000000.png")):
                counter += 1
                new_output_path = f"{output_path}_{counter}"
            print(f'Found file pattern 000001.png in {output_path}.\n' 
                  f'Changing output path to {new_output_path}')
            os.makedirs(new_output_path, exist_ok=True)
            output_path = new_output_path

    print('Output path set up correctly: ', output_path)

    print('Setting up Blender file...\n')
    #### (2) SCENE SET UP ####
    print('Getting Blender objects...', end='')
    CAM = bpy.data.objects["Camera"]

    # Get name of light object
    if len(light_names) > 1:
        raise NotImplementedError("ACHTUNG: More than one light object is not supported yet!")

    SUN = bpy.data.objects[light_names[0]]
    BODY_1 = bpy.data.objects[model_name_1]
    if num_bodies > 1:
        BODY_2 = bpy.data.objects[model_name_2]
    print('OK')

    # Camera parameters
    print('Setting up Camera objects properties...', end='')
    CAM.data.type = 'PERSP'
    CAM.data.lens_unit = 'FOV'
    CAM.data.angle = FOV_x * np.pi / 180
    CAM.data.clip_start = 0.5 # [m] in Blender, but scaled in km
    CAM.data.clip_end = 100 # [m] in Blender, but scaled in km
    print('OK')

    print('Setting up scene.render properties...', end='')
    bpy.context.scene.render.pixel_aspect_x = 1
    bpy.context.scene.render.pixel_aspect_y = 1
    bpy.context.scene.render.resolution_x = sensor_size_x # CAM resolution (x)
    bpy.context.scene.render.resolution_y = sensor_size_y # CAM resolution (y)
    print('OK')

    # Light parameters    
    print('Setting up light properties...', end='')
    SUN.data.type = 'SUN'
    SUN.data.energy = sun_energy  # To perform quantitative analysis
    SUN.data.specular_factor = specular_factor
    print('OK')

    # Environment parameters
    print('Setting up Blender environment parameters...', end='')
    bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)

    if n_channels == 1:
        bpy.context.scene.render.image_settings.color_mode = 'BW'
    elif n_channels == 3:
        bpy.context.scene.render.image_settings.color_mode = 'RGB'
    elif n_channels == 4:
        bpy.context.scene.render.image_settings.color_mode = 'RGBA'

    bpy.context.scene.render.image_settings.color_depth = str(bit_encoding)
    bpy.context.scene.render.image_settings.compression = compression
    print('OK')

    #### (3) DYNAMIC PARAMETERS ####
    print('Initializing objects scene properties...', end='')
    body_has_changed = False
    disable_caching = server_config.get("disable_caching", False)
    
    # Initialization of Bodies, Cam and Sun

    CAM.location = [10, 0, 0]
    SUN.location = [0, 0, 0]

    CAM.rotation_mode = 'QUATERNION'
    SUN.rotation_mode = 'QUATERNION'

    CAM.rotation_quaternion = [1, 0, 0, 0]
    SUN.rotation_quaternion = [1, 0, 0, 0]

    BODY_1.location = [0, 0, 0]
    BODY_1.rotation_mode = 'QUATERNION'
    BODY_1.rotation_quaternion = [1, 0, 0, 0]

    if num_bodies > 1:
        BODY_2.location = [0, 0, 0]
        BODY_2.rotation_mode = 'QUATERNION'
        BODY_2.rotation_quaternion = [1, 0, 0, 0]

    print('OK')

    # Initialize to identity with number of rows equal to the number of bodies
    #PQ_Bodies_prev = np.repeat([0, 0, 0, 1, 0, 0, 0], num_bodies) # 1D array shaped
    PQ_Bodies_prev = np.tile(A=[0, 0, 0, 1, 0, 0, 0], reps=(1, num_bodies))

    print('Defining rendering functions...', end='')
    # TODO (PC) declare these functions at the beginning of the script
    # TODO (PC) wrap the relevant code in the main program
    #### (4) FUNCTION DEFINITIONS ####
    def Render(ii) -> None:
        name = '{:06d}.png'.format(int(ii))
        bpy.context.scene.render.filepath = output_path + '/' + name
        bpy.ops.render.render(write_still=1)
        return

    def PositionAll(PQ_SC, PQ_Bodies, PQ_Sun, body_has_changed: bool = True, disable_caching: bool = False) -> None:
        # TODO function to rework, generalize and make more readable
        # Add also a check on the quaternions (must be unit quaternions)
        print('Setting Light and Camera poses...')
        SUN.location = [0, 0, 0]  # Because in Blender it is indifferent where the sun is located
        CAM.location = [PQ_SC[0], PQ_SC[1], PQ_SC[2]]

        if body_has_changed or disable_caching:
            print("Setting bodies' poses...")
            BODY_1.location = [PQ_Bodies[0, 0], PQ_Bodies[0, 1], PQ_Bodies[0, 2]]
            BODY_1.rotation_quaternion = [PQ_Bodies[0, 3], PQ_Bodies[0, 4], PQ_Bodies[0, 5], PQ_Bodies[0, 6]]

            if num_bodies > 1:
                BODY_2.location = [PQ_Bodies[1, 0], PQ_Bodies[1, 1], PQ_Bodies[1, 2]]
                BODY_2.rotation_quaternion = [PQ_Bodies[1, 3], PQ_Bodies[1, 4], PQ_Bodies[1, 5], PQ_Bodies[1, 6]]
        else:
            print("Bodies' poses did not change. Kept still.")

        SUN.rotation_quaternion = [PQ_Sun[3], PQ_Sun[4], PQ_Sun[5], PQ_Sun[6]]
        CAM.rotation_quaternion = [PQ_SC[3], PQ_SC[4], PQ_SC[5], PQ_SC[6]]

        return
    print('OK')

    #### (5) ESTABLISH UDP/TCP CONNECTION ####
    print("Starting the UDP/TCP server...\n")

    UDPrecvSocket = socket.socket(socket.AF_INET, type=socket.SOCK_DGRAM)
    TCPsendSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Set TCP server socket
    TCPsendSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    TCPsendSocket.settimeout(tcpTimeOutValue)

    try:
        UDPrecvSocket.bind((address, port_M2B))
        UDPrecvSocket.setblocking(False)  # Non-blocking for receiving data
        print(f"Socket successfully bound to {address}:{port_M2B}")
    except OSError as e:
        print(f"Failed to bind socket: {e}")
        sys.exit(1)

    try:
        TCPsendSocket.bind((address, port_B2M))
        print(f"Socket successfully bound to {address}:{port_B2M}")
    except OSError as e:
        print(f"Failed to bind socket: {e}")
        sys.exit(1)


    print(f"Binding successful. Starting listening to connection on port", port_M2B, "\n")
    print(f"Data will be sent through port:", port_B2M)

    # r.listen()  # Not needed for UDP
    print(f'Waiting for data from client receiver on port {port_M2B}...')
    TCPsendSocket.listen() 
    (clientsocket_send, address) = TCPsendSocket.accept()
    print('Client connected from', address,' as receiver\n')

    #### (6) RECEIVE DATA AND RENDERING ####
    receiving_flag = True
    disconnect_flag = False
    bytes_recv_udp = 0
    numpy_data_array_prev = None
    max_timeout_counter = 0.5*120*2 # approx. 120 seconds of no data before closing the server
    timeout_counter = 0
    ii = 0

    # TODO (PC) server management to be improved (error handling to avoid server crashes in certain cases)
    while receiving_flag:
        try:
            while bytes_recv_udp == 0:
                # Wait for new connection
                if disconnect_flag: # DEVNOTE (PC) definitely not a good coding pattern, but sufficient for now
                    # Reset flags and arrays
                    numpy_data_array_prev = None
                    data_buffer = None
                    ii = 0

                    print(f"Waiting for new connection from client receiver on port {port_M2B}. Timeout set equal to {tcpTimeOutValue}...")
                    (clientsocket_send, address) = TCPsendSocket.accept() # FIXME new client connection fails with connection reset error

                    print('Client connected from', address,' as receiver\n')
                    disconnect_flag = False
                    no_client_counter = 0  # Reset the counter

                try:
                    # Check if timeout counter is reached
                    if timeout_counter > max_timeout_counter:
                        clientsocket_send.close()
                        raise ConnectionResetError( "ACHTUNG: No data received from client for too long, disconnecting...")
                    
                    print("Attempting to get data from client...\n")  
                    data_buffer, address_recv = UDPrecvSocket.recvfrom(512)  
                    bytes_recv_udp = len(data_buffer)

                    #data_checksum = sum(data_buffer)

                    if bytes_recv_udp == 0 or data_buffer is None:
                        raise BlockingIOError("ACHTUNG: No data received from client, but !")
                    else:
                        timeout_counter = 0  # Reset the timeout counter


                except BlockingIOError:
                    if not DEBUG_MODE:
                        print(f"BlockingIOError: No data received yet. Waiting for other {0.5 * (max_timeout_counter-timeout_counter)} [s]...")                
                    # Socket is open and reading from it would block, do nothing
                    bytes_recv_udp = 0
                    data_buffer = None
                    if not DEBUG_MODE:
                        timeout_counter += 1
                    sleep(0.5) 
                    continue  

                #if exists(data_buffer):
                #    bytes_recv_udp = len(data_buffer)
                #else:
                #    bytes_recv_udp = 0

            #if data_buffer is None:
            #    raise RuntimeError("ACHTUNG: data_buffer is None type. Failed to receive data from client!")
            
            # NOTE 28 doubles harcoded size of the data packet
            numOfValues = int(len(data_buffer) / 8)
            print(f"Received {len(data_buffer)} bytes from {address_recv}")
            print(f"Received number of doubles: {numOfValues} values")

            if not (numOfValues == 14 + 7 * num_bodies): 
                raise RuntimeError("ACHTUNG: incorrect message format. Expected 14 doubles for Camera and Sun + 7 doubles for each body! Found {}, expected: {}.".format((numOfValues - 14)//7, num_bodies))
            
            # Check if TCP socket is still alive
            print('Checking if client is still connected...')
            
            #checkByte = clientsocket_send.recvfrom(0, socket.MSG_DONTWAIT | socket.MSG_PEEK) # Try to read 1 byte without blocking and without removing it from buffer (peek only)

        except (ConnectionResetError):
            print("\nConnectionResetError: no open connection or client disconnection.")
            print("Server will continue operation waiting for a reconnection...")
            disconnect_flag = True  # Make the server wait for a reconnection
            bytes_recv_udp = 0
            clientsocket_send.close()
            continue 

        except (BrokenPipeError):
            print("\nBrokenPipeError: no open connection or client disconnection.")
            print("Server will continue operation waiting for a reconnection...")
            disconnect_flag = True  # Make the server wait for a reconnection
            bytes_recv_udp = 0
            clientsocket_send.close()
            continue

        except RuntimeError as e:
            print(f"\nRuntimeError: {e}")
            print("Server will continue operation waiting for a reconnection...")
            disconnect_flag = True  # Make the server wait for a reconnection
            bytes_recv_udp = 0
            clientsocket_send.close()
            continue

        except KeyboardInterrupt:
            print("\nKeyboardInterrupt: Closing the server...\n")
            UDPrecvSocket.close()
            clientsocket_send.close()
            TCPsendSocket.close()
            sys.exit(0)

        except socket.error as socket_err:
            print(f"Unrecoverable exception occurred: {socket_err}\n")
            UDPrecvSocket.close()
            clientsocket_send.close()
            TCPsendSocket.close()
            sys.exit(1) 


        # Casting to numpy array
        dtype = np.dtype(np.float64)  # Big-endian float64
        numpy_data_array = np.frombuffer(data_buffer, dtype=dtype)

        # Clear data_buffer after processing
        data_buffer = None
        bytes_recv_udp = 0

        #data = struct.unpack('>' + 'd' * numOfValues, data) # Unpack bytes in data to double big-endian
        print('Array received: ', numpy_data_array)
        print(f"Array shape: {numpy_data_array.shape}\n")

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
        PQ_Bodies = np.reshape(PQ_Bodies,(int(n_bodies),7)) # TODO check this operation is performed correctly

        # Check if the bodies' poses have changed
        if numpy_data_array_prev is not None:
            if (PQ_Bodies == PQ_Bodies_prev).all():
                body_has_changed = False
            else:
                body_has_changed = True
        else:
            body_has_changed = True

        # Print the PQ vector info
        print('SUN:   POS ' +  str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
        print('SC:    POS ' +  str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))

        if body_has_changed:
            print("Bodies' poses changed. Scene was updated.")
        else:
            print("Static scene detected. Bodies' poses did not change and were not updated.")

        for jj in np.arange(0,n_bodies):                
            print('BODY (' + str(jj) + '):   POS: ' +  str(PQ_Bodies[int(jj),0:3]) + ' - Q ' + str(PQ_Bodies[int(jj),3:7]))

        # Position all bodies in the scene
        PositionAll(PQ_SC, PQ_Bodies, PQ_Sun, body_has_changed=body_has_changed, disable_caching=disable_caching)

        # Force refreshing of Blender UI (little hack here)
        if not(bpy.app.background):
            bpy.context.view_layer.update() # Call update to apply the changes to the scene
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        # Check data freshness
        if numpy_data_array_prev is not None:
            if (numpy_data_array_prev == numpy_data_array).all():
                raise RuntimeError("ACHTUNG: data freshness check failed. Server received same data as previous communication. Execution stop: closing connection to client.")
        try:
            if not DUMMY_OUTPUT: # DEVNOTE: DUMMY_OUTPUT is a flag to test the server without rendering
                Render(ii) # Render function call, uses data set by PositionAll
                #data_freshness_flag = False # Set freshness data to false

                # Read the pixels from the saved image
                img_read = bpy.data.images.load(filepath=output_path + '/' + '{:06d}.png'.format(int(ii))) 

                # FIXME: image is RGB regardless of the color mode set in the config file! 

                # Get the type of the first pixel value
                pixel_dtype = type(img_read.pixels[0])
                print(f"\tImage datatype: {pixel_dtype}")
                
                # Convert to a NumPy array using the same type
                img_reshaped_vec = np.array(img_read.pixels[:]) # Flatten the image matrix to a linear array
                print(f"\tImage datatype interpreted by numpy: {img_reshaped_vec.dtype}")

            else:
                # DOUBT: why 4 channels if Blender is using 3 (RGB) for rendering? Set in bpy.context.scene.render.image_settings.color_mode property
                img_reshaped_vec = np.float64(np.random.rand(4*sensor_size_x * sensor_size_y)).flatten() # Random image for testing (4 is because of RGBA)

            # Pack the RGBA image as vector and transmit over TCP using numpy
            img_pack = img_reshaped_vec.tobytes() # DEVNOTE: which endianness here? # TODO add specification in config file! 

            print(f"Sending image buffer of size {len(img_pack)} to client...\n")

            clientsocket_send.send(img_pack)
            


        except KeyboardInterrupt:
            print("KeyboardInterrupt: Closing the server...\n")
            UDPrecvSocket.close()
            TCPsendSocket.close()
            sys.exit(0)

        except (socket.error, BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"Error sending image data to client: {e}. Closing connection to client...\n")
            receiving_flag = True  # Stop the server loop
            disconnect_flag = True  # Close the connection to the client

            # Disconnect the client
            clientsocket_send.close()
            bytes_recv_udp = 0

            continue

        print("Image sent correctly.\n")
        
        print('------------------ Summary of operations and image state for monitoring ------------------')
        print(f"Received data from {address_recv} with {numOfValues} values\n")
        print(f"Current frame: {ii}")
        print(f"Number of bodies: {n_bodies}\n")
        print('SUN:   POS ' + str(PQ_Sun[0:3]) + ' - Q ' + str(PQ_Sun[3:7]))
        print('SC:    POS ' + str(PQ_SC[0:3]) + ' - Q ' + str(PQ_SC[3:7]))
        for jj in np.arange(0, n_bodies):
            print('BODY (' + str(jj) + '):   POS: ' +
                str(PQ_Bodies[int(jj), 0:3]) + ' - Q ' + str(PQ_Bodies[int(jj), 3:7]))

        if body_has_changed:
            print("Bodies' poses changed. Scene was updated.")
        else:
            print("Static scene detected. Bodies' poses did not change and were not updated.")
        
        print('Previous poses: ', PQ_Bodies_prev)
                  
        if DEBUG_MODE:
            # Print DCMs corresponding to quaternions using the Blender API
            print('Body 1 DCM: ', BODY_1.rotation_quaternion.to_matrix())
            print('Camera DCM: ', CAM.rotation_quaternion.to_matrix())
            print('Sun DCM: ', SUN.rotation_quaternion.to_matrix())

        # Copy sent bytes for error checking # FIXME, not sure this is working as intended
        numpy_data_array_prev = copy.deepcopy(numpy_data_array)

        # Store the previous PQ_Bodies for next scene
        PQ_Bodies_prev = copy.deepcopy(PQ_Bodies)

        #continue on the iteration
        ii = ii + 1


except KeyboardInterrupt:
    print("KeyboardInterrupt: Closing the server...\n")
    UDPrecvSocket.close()
    TCPsendSocket.close()
    sys.exit(0)
except (socket.error, RuntimeError, OSError) as e:
    print(f"Unrecoverable exception occurred: {e}\n")
    UDPrecvSocket.close()
    TCPsendSocket.close()
    sys.exit(1)

