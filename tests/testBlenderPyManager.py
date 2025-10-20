import socket
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from server_api.BlenderPyManager_UDP_TCP_withCaching import (
    StandaloneRenderServer,
    ensure_output_directories,
)


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DummyBridge:
    def close(self) -> None:
        pass


class StandaloneServerTest(unittest.TestCase):
    def test_dummy_round_trip(self) -> None:
        udp_port = _get_free_port()
        tcp_port = _get_free_port()

        camera_cfg = {
            "FOV_x": 10.0,
            "FOV_y": 10.0,
            "sensor_size_x": 4,
            "sensor_size_y": 4,
            "n_channels": 3,
            "bit_encoding": 8,
            "compression": 15,
        }

        render_cfg = {
            "file_format": "PNG",
            "render_engine": "CYCLES",
            "device": "CPU",
            "samples": 1,
            "diffuse_bounces": 0,
            "tile_size": 16,
            "bSaveGeomVisibilityBoolMask": False,
        }

        model_cfg = {
            "num_bodies": 1,
            "light_names": ["Light"],
            "bodies_names": ["Body"],
            "sun_energy": 2.0,
            "specular_factor": 0.0,
        }

        server_cfg = {
            "output_path": "",
            "max_inactivity_timeout": 2,
            "address": "127.0.0.1",
            "port_M2B": udp_port,
            "port_B2M": tcp_port,
            "DUMMY_OUTPUT": True,
            "image_dtype": "double",
            "disable_caching": False,
        }

        config = {
            "Camera_params": camera_cfg,
            "RenderingEngine_params": render_cfg,
            "BlenderModel_params": model_cfg,
            "Server_params": server_cfg,
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "dataset"
            server_cfg["output_path"] = str(output_path)
            paths = ensure_output_directories(output_path, save_binary_mask=False)

            server = StandaloneRenderServer(config, paths, bridge=None)
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()

            udp_client: socket.socket | None = None
            try:
                deadline = time.time() + 5
                tcp_client: socket.socket | None = None
                while time.time() < deadline:
                    try:
                        tcp_client = socket.create_connection(("127.0.0.1", tcp_port), timeout=0.5)
                        break
                    except (ConnectionRefusedError, OSError):
                        time.sleep(0.1)
                self.assertIsNotNone(tcp_client, "TCP client failed to connect to the server.")
                assert tcp_client is not None

                udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                sun = np.array([0, 0, 0, 1, 0, 0, 0], dtype=np.float64)
                spacecraft = np.array([1, 0, 0, 1, 0, 0, 0], dtype=np.float64)
                body = np.array([0, 1, 0, 1, 0, 0, 0], dtype=np.float64).reshape(1, 7)

                payload = np.concatenate([sun, spacecraft, body.flatten()])
                udp_client.sendto(payload.tobytes(), ("127.0.0.1", udp_port))

                expected_bytes = 4 * camera_cfg["sensor_size_x"] * camera_cfg["sensor_size_y"] * 8
                received = bytearray()
                while len(received) < expected_bytes:
                    chunk = tcp_client.recv(expected_bytes - len(received))
                    if not chunk:
                        break
                    received.extend(chunk)

                self.assertEqual(
                    len(received),
                    expected_bytes,
                    "Server did not return the expected amount of image data.",
                )

            finally:
                if udp_client is not None:
                    udp_client.close()
                if tcp_client is not None:
                    tcp_client.close()
                try:
                    server.request_shutdown()
                finally:
                    server_thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
