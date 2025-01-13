from operator import le
import socket
import struct
import numpy as np
import time

# Server configuration
server_address = '127.0.0.1'
UDP_localPort = 51000
port_M2B = 51001 # UDP port for sending data
port_B2M = 30001 # TCP port for receiving data
buffer_size = 512  # Buffer size

# Generate test data
num_doubles = 28
data_to_send = np.ones(num_doubles, dtype=np.float64)  # Array of ones
data_bytes = data_to_send.tobytes()  # Convert doubles to bytes

# Convert first 8 bytes to double to check if the data is sent correctly, using python
print(len(data_bytes[0:8]))
first_double = np.frombuffer(data_bytes[0:8], dtype=np.float64)
print("First double sent:", first_double)

try:
    # Step 1: Create UDP socket and send data
    print("Creating UDP socket and sending data to server...")
    udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_client.sendto(data_bytes, (server_address, port_M2B))
    print(f"Sent {len(data_bytes)} bytes via UDP.\n")

    # Step 2: Create TCP socket and receive response
    print("Creating TCP socket and waiting for response from server...")
    tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_client.connect((server_address, port_B2M))

    # Wait for the server's response
    print("Waiting for server response...")
    response_data = tcp_client.recv(buffer_size)

    if not response_data:
        raise ValueError("No response received from server.")

    print(f"Received {len(response_data)} bytes from server via TCP.\n")

    # Step 3: Unpack response data
    received_values = struct.unpack(
        '>' + 'd' * (len(response_data) // 8), response_data)
    print("Received values from server:", received_values)

    # Step 4: Validate response
    print("Validating server response...")
    if len(received_values) != num_doubles:
        raise ValueError("Server response size does not match expected size.")

    # Optional: Compare sent and received data if server echoes back
    if np.allclose(received_values, data_to_send):
        print("Server response matches the sent data. Test passed!")
    else:
        raise ValueError("Mismatch in server response. Test failed!")

except Exception as e:
    print(f"Test failed: {e}")

finally:
    # Cleanup
    udp_client.close()
    tcp_client.close()
    print("Test complete.")
