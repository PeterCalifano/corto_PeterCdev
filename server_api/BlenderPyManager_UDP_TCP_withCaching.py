#!/usr/bin/env python3
"""
Standalone UDP/TCP render bridge for Blender.

This module can be executed in two modes:

1. Server mode (default):
       python BlenderPy_UDP_TCP_interface_withCaching.py \
           --blender-exec /path/to/blender \
           --blend-file /path/to/scene.blend \
           [--config /path/to/BlenderPy_UDP_TCP_CONFIG.yml]

   The server runs outside Blender, hosts the UDP/TCP endpoints, forwards pose
   packets to a background Blender process, receives rendered images, and sends
   them back to the TCP client.

2. Worker mode (internal):
       blender -b /path/to/scene.blend \
           -P BlenderPy_UDP_TCP_interface_withCaching.py -- \
           --worker --ipc-host 127.0.0.1 --ipc-port <port> --authkey <hex>

   The worker mode is launched automatically by the server. It must never be started
   manually except for debugging.
"""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import socket
import subprocess
import sys
from pathlib import Path
from time import sleep
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yaml
from multiprocessing.connection import Listener, Client

DEBUG_MODE = False
DEFAULT_CONFIG_NAME = "BlenderPy_UDP_TCP_CONFIG.yml"
TCP_TIMEOUT_SECONDS = 300


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone UDP/TCP server that offloads rendering to Blender.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    default_config = Path(__file__).resolve().with_name(DEFAULT_CONFIG_NAME)
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help="Path to the YAML configuration file used previously inside Blender.",
    )
    parser.add_argument(
        "--blender-exec",
        type=Path,
        help="Absolute path to the Blender executable (server mode only).",
    )
    parser.add_argument(
        "--blend-file",
        type=Path,
        help="Absolute path to the .blend file that must stay resident in Blender.",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help="Internal flag: run in Blender worker mode (server spawns this automatically).",
    )
    parser.add_argument(
        "--ipc-host",
        help="Internal flag: IPC host passed to the Blender worker.",
    )
    parser.add_argument(
        "--ipc-port",
        type=int,
        help="Internal flag: IPC port passed to the Blender worker.",
    )
    parser.add_argument(
        "--authkey",
        help="Internal flag: IPC auth key passed to the Blender worker (hex encoded).",
    )
    return parser.parse_args([] if argv is None else argv)


def load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not data:
        raise ValueError(f"Configuration file {path} is empty.")
    return data


def ensure_output_directories(base_path: Path, save_binary_mask: bool) -> Tuple[Path, Path, Optional[Path]]:
    """
    Replicates the original folder preparation logic (including numbered suffixes).
    """
    path = base_path
    if path.name == "images":
        path = path.parent

    path = path.expanduser().resolve()

    if not path.exists():
        print(f"Creating dataset root at {path}")
        path.mkdir(parents=True, exist_ok=False)
    else:
        image_test = path / "images" / "000001.png"
        legacy_test = path / "000001.png"
        if image_test.exists() or legacy_test.exists():
            counter = 0
            while True:
                candidate = path.parent / f"{path.name}_ID{counter:01d}"
                candidate_images = candidate / "images" / "000001.png"
                candidate_legacy = candidate / "000001.png"
                if not candidate.exists() or (not candidate_images.exists() and not candidate_legacy.exists()):
                    candidate.mkdir(parents=True, exist_ok=True)
                    path = candidate
                    print(
                        f"Existing renders detected. Redirecting output to {path} "
                        f"to avoid overwriting previous data."
                    )
                    break
                counter += 1

    images_path = path / "images"
    images_path.mkdir(parents=True, exist_ok=True)
    masks_path = None
    if save_binary_mask:
        masks_path = path / "binary_masks"
        masks_path.mkdir(parents=True, exist_ok=True)

    return path, images_path, masks_path


def resolve_blender_paths(args: argparse.Namespace, config: Dict[str, Any]) -> Tuple[Path, Path]:
    standalone_cfg = config.get("Standalone_params", {})
    blender_exec = args.blender_exec or standalone_cfg.get(
        "blender_executable") or os.environ.get("BLENDER_EXECUTABLE")
    blend_file = args.blend_file or standalone_cfg.get("blend_file")

    if not blender_exec:
        raise ValueError(
            "Blender executable path is required. Pass --blender-exec, set "
            "Standalone_params.blender_executable in the YAML config, or export BLENDER_EXECUTABLE."
        )
    if not blend_file:
        raise ValueError(
            "Blend file path is required. Pass --blend-file or set Standalone_params.blend_file in the YAML config."
        )

    blender_exec = Path(blender_exec).expanduser().resolve()
    blend_file = Path(blend_file).expanduser().resolve()

    if not blender_exec.exists():
        raise FileNotFoundError(
            f"Blender executable not found at {blender_exec}")
    if not blend_file.exists():
        raise FileNotFoundError(f"Blend file not found at {blend_file}")

    return blender_exec, blend_file


# -----------------------------------------------------------------------------
# Blender worker bridge
# -----------------------------------------------------------------------------
class BlenderBridge:
    def __init__(self, blender_exec: Path, blend_file: Path, init_payload: Dict[str, Any]) -> None:
        authkey = secrets.token_bytes(16)
        self._listener = Listener(("127.0.0.1", 0), authkey=authkey)
        host, port = self._listener.address
        script_path = Path(__file__).resolve()

        worker_cmd = [
            str(blender_exec),
            "-b",
            str(blend_file),
            "--python",
            str(script_path),
            "--",
            "--worker",
            f"--ipc-host={host}",
            f"--ipc-port={port}",
            f"--authkey={authkey.hex()}",
        ]

        print("Spawning Blender worker:", " ".join(worker_cmd))
        env = os.environ.copy()

        self._proc = subprocess.Popen(
            worker_cmd,
            cwd=str(blend_file.parent),
            env=env,
            stdout=None if DEBUG_MODE else subprocess.DEVNULL,
            stderr=None if DEBUG_MODE else subprocess.DEVNULL,
        )

        self._conn = self._listener.accept()
        self._conn.send({"command": "init", "payload": init_payload})
        init_reply = self._conn.recv()
        if init_reply.get("status") != "ok":
            raise RuntimeError(
                f"Blender worker failed to initialise: {init_reply.get('error')}")

        print("Blender worker initialised successfully.")
        self._closed = False

    def render_frame(
        self,
        frame_index: int,
        PQ_SC: np.ndarray,
        PQ_Bodies: np.ndarray,
        PQ_Sun: np.ndarray,
        body_has_changed: bool,
    ) -> bytes:
        if self._closed:
            raise RuntimeError("Attempted to render after bridge shutdown.")

        message = {
            "command": "render_frame",
            "frame_index": int(frame_index),
            "spacecraft": PQ_SC.tolist(),
            "bodies": PQ_Bodies.tolist(),
            "sun": PQ_Sun.tolist(),
            "body_has_changed": bool(body_has_changed),
        }
        self._conn.send(message)
        reply = self._conn.recv()
        if reply.get("status") != "ok":
            raise RuntimeError(f"Blender worker error: {reply.get('error')}")
        return reply["image_bytes"]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._conn:
                self._conn.send({"command": "shutdown"})
                self._conn.recv()  # Ack
        except Exception:
            pass
        finally:
            try:
                if self._conn:
                    self._conn.close()
            except Exception:
                pass
            try:
                if self._listener:
                    self._listener.close()
            except Exception:
                pass
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        print("Blender worker stopped.")

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Standalone server implementation
# -----------------------------------------------------------------------------
class StandaloneRenderServer:
    def __init__(
        self,
        config: Dict[str, Any],
        paths: Tuple[Path, Path, Optional[Path]],
        bridge: BlenderBridge,
    ) -> None:
        self.config = config
        self.camera_cfg = config.get("Camera_params", {})
        self.render_cfg = config.get("RenderingEngine_params", {})
        self.server_cfg = config.get("Server_params", {})
        self.model_cfg = config.get("BlenderModel_params", {})

        self.output_root, self.output_images, self.output_masks = paths
        self.bridge = bridge

        self.address = self.server_cfg.get("address", "127.0.0.1")
        self.port_m2b = int(self.server_cfg.get("port_M2B"))
        self.port_b2m = int(self.server_cfg.get("port_B2M"))

        self.sensor_size_x = int(self.camera_cfg.get("sensor_size_x"))
        self.sensor_size_y = int(self.camera_cfg.get("sensor_size_y"))
        self.n_channels = int(self.camera_cfg.get("n_channels"))
        if self.n_channels not in (1, 3, 4):
            raise ValueError(
                f"Unsupported number of channels: {self.n_channels}")

        self.num_img_array_channels = 4 if self.n_channels in (3, 4) else 1

        self.num_bodies = int(self.model_cfg.get("num_bodies"))
        self.disable_caching = bool(
            self.server_cfg.get("disable_caching", False))
        self.dummy_output = bool(self.server_cfg.get("DUMMY_OUTPUT", False))
        self.max_inactivity_timeout = int(
            self.server_cfg.get("max_inactivity_timeout", -1))

        self.tcp_timeout = TCP_TIMEOUT_SECONDS

    def _dummy_image_bytes(self) -> bytes:
        total_values = self.num_img_array_channels * \
            self.sensor_size_x * self.sensor_size_y
        dummy = np.random.rand(total_values)
        return np.float64(dummy).tobytes()

    def run(self) -> None:
        print("Starting standalone UDP/TCP server...")
        print(f"UDP listen address: {self.address}:{self.port_m2b}")
        print(f"TCP listen address: {self.address}:{self.port_b2m}")
        print(f"Rendering output root: {self.output_root}")

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_socket.settimeout(self.tcp_timeout)

        try:
            udp_socket.bind((self.address, self.port_m2b))
            udp_socket.setblocking(False)
            tcp_socket.bind((self.address, self.port_b2m))
            tcp_socket.listen()
        except OSError as exc:
            udp_socket.close()
            tcp_socket.close()
            raise RuntimeError(f"Failed to bind sockets: {exc}") from exc

        print("Waiting for TCP client connection...")
        clientsocket_send, client_address = tcp_socket.accept()
        print(f"TCP client connected from {client_address}")

        receiving_flag = True
        disconnect_flag = False
        bytes_recv_udp = 0
        numpy_data_array_prev = None
        PQ_Bodies_prev = np.zeros((self.num_bodies, 7), dtype=np.float64)
        PQ_Bodies_prev[:, 3] = 1.0

        timeout_counter = 0
        frame_index = 0

        try:
            while receiving_flag:
                try:
                    while bytes_recv_udp == 0:
                        if disconnect_flag:
                            numpy_data_array_prev = None
                            PQ_Bodies_prev[:, :] = 0.0
                            PQ_Bodies_prev[:, 3] = 1.0
                            frame_index = 0
                            print(
                                f"Waiting for a new TCP client on {self.port_b2m}...")
                            clientsocket_send, client_address = tcp_socket.accept()
                            print(
                                f"TCP client reconnected from {client_address}")
                            disconnect_flag = False

                        try:
                            if (
                                self.max_inactivity_timeout != -1
                                and timeout_counter > self.max_inactivity_timeout
                            ):
                                clientsocket_send.close()
                                raise ConnectionResetError(
                                    "No UDP data received within the configured inactivity timeout."
                                )

                            if DEBUG_MODE:
                                print("Attempting to receive UDP packet...")
                            data_buffer, address_recv = udp_socket.recvfrom(
                                512)
                            bytes_recv_udp = len(data_buffer)

                            if bytes_recv_udp == 0:
                                raise BlockingIOError(
                                    "Empty UDP packet received.")
                            timeout_counter = 0
                        except BlockingIOError:
                            bytes_recv_udp = 0
                            data_buffer = None
                            if not DEBUG_MODE and self.max_inactivity_timeout != -1:
                                remaining = self.max_inactivity_timeout - timeout_counter
                                print(
                                    f"No data yet. Waiting {remaining} more seconds...")
                                timeout_counter += 1
                            sleep(1.0)
                            continue

                except ConnectionResetError as exc:
                    print(
                        f"ConnectionResetError: {exc}. Waiting for reconnection.")
                    disconnect_flag = True
                    bytes_recv_udp = 0
                    continue

                num_values = int(len(data_buffer) / 8)
                print(f"Received {len(data_buffer)} bytes from {address_recv}")
                print(f"Decoded doubles: {num_values}")

                expected = 14 + 7 * self.num_bodies
                if num_values != expected:
                    raise RuntimeError(
                        f"Incorrect payload size: expected {expected} doubles, received {num_values}."
                    )

                numpy_data_array = np.frombuffer(data_buffer, dtype=np.float64)
                data_buffer = None
                bytes_recv_udp = 0

                PQ_Sun = numpy_data_array[0:7]
                PQ_SC = numpy_data_array[7:14]
                PQ_Bodies = numpy_data_array[14:].reshape((self.num_bodies, 7))

                if numpy_data_array_prev is not None and np.array_equal(numpy_data_array_prev, numpy_data_array):
                    raise RuntimeError(
                        "Data freshness check failed: received identical pose packet as previous frame."
                    )

                body_has_changed = True
                if not self.disable_caching and numpy_data_array_prev is not None:
                    body_has_changed = not np.array_equal(
                        PQ_Bodies, PQ_Bodies_prev)

                print(f"Frame {frame_index}")
                print(f"SUN: POS {PQ_Sun[0:3]} - QUAT {PQ_Sun[3:7]}")
                print(f"SC:  POS {PQ_SC[0:3]} - QUAT {PQ_SC[3:7]}")
                for jj in range(self.num_bodies):
                    print(
                        f"BODY ({jj}): POS {PQ_Bodies[jj, 0:3]} - QUAT {PQ_Bodies[jj, 3:7]}"
                    )
                print(
                    "Bodies changed: {}".format(
                        "YES" if body_has_changed or self.disable_caching else "NO")
                )

                if self.dummy_output:
                    image_bytes = self._dummy_image_bytes()
                else:
                    image_bytes = self.bridge.render_frame(
                        frame_index=frame_index,
                        PQ_SC=PQ_SC,
                        PQ_Bodies=PQ_Bodies,
                        PQ_Sun=PQ_Sun,
                        body_has_changed=body_has_changed,
                    )

                try:
                    clientsocket_send.sendall(image_bytes)
                except (socket.error, BrokenPipeError, ConnectionResetError) as exc:
                    print(f"Error sending image to TCP client: {exc}")
                    clientsocket_send.close()
                    disconnect_flag = True
                    continue

                numpy_data_array_prev = np.copy(numpy_data_array)
                PQ_Bodies_prev = np.copy(PQ_Bodies)
                frame_index += 1
                print("Image sent successfully.\n")

        except KeyboardInterrupt:
            print("KeyboardInterrupt: shutting down server.")
        finally:
            udp_socket.close()
            clientsocket_send.close()
            tcp_socket.close()
            self.bridge.close()


# -----------------------------------------------------------------------------
# Blender worker implementation (executed inside Blender)
# -----------------------------------------------------------------------------
def run_worker(args: argparse.Namespace) -> None:
    if not args.ipc_host or not args.ipc_port or not args.authkey:
        raise ValueError(
            "Worker mode requires --ipc-host, --ipc-port, and --authkey.")

    import bpy  # type: ignore

    class BlenderWorkerRuntime:
        def __init__(self, conn: Client) -> None:
            self.conn = conn
            self.initialised = False
            self.camera_cfg: Dict[str, Any] = {}
            self.render_cfg: Dict[str, Any] = {}
            self.model_cfg: Dict[str, Any] = {}
            self.disable_caching = False
            self.save_binary_mask_output = False

            self.scene = bpy.context.scene
            self.cam_obj = None
            self.sun_obj = None
            self.body_objects = []
            self.num_bodies = 0
            self.n_channels = 0
            self.num_img_array_channels = 0
            self.sensor_size_x = 0
            self.sensor_size_y = 0
            self.file_format = "PNG"
            self.file_ext = "png"

            self.output_images = None
            self.output_masks = None
            self.mask_output_node = None

        def loop(self) -> None:
            while True:
                message = self.conn.recv()
                command = message.get("command")
                if command == "init":
                    try:
                        response = self.handle_init(message["payload"])
                    except Exception as exc:
                        response = {"status": "error", "error": repr(exc)}
                    self.conn.send(response)
                elif command == "render_frame":
                    try:
                        response = self.handle_render_frame(message)
                    except Exception as exc:
                        response = {"status": "error", "error": repr(exc)}
                    self.conn.send(response)
                elif command == "shutdown":
                    self.conn.send({"status": "ok"})
                    break
                else:
                    self.conn.send(
                        {"status": "error", "error": f"Unknown command {command}"})

        def handle_init(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            self.camera_cfg = payload["camera"]
            self.render_cfg = payload["rendering"]
            self.model_cfg = payload["model"]
            paths = payload["paths"]
            options = payload["options"]

            self.disable_caching = bool(options.get("disable_caching", False))
            self.save_binary_mask_output = bool(
                options.get("save_binary_mask_output", False))

            self.output_images = Path(paths["images"])
            binary_masks_raw = paths.get("binary_masks")
            self.output_masks = Path(
                binary_masks_raw) if binary_masks_raw else None

            self.sensor_size_x = int(self.camera_cfg.get("sensor_size_x"))
            self.sensor_size_y = int(self.camera_cfg.get("sensor_size_y"))
            self.n_channels = int(self.camera_cfg.get("n_channels"))
            if self.n_channels not in (1, 3, 4):
                raise ValueError(
                    f"Unsupported number of channels: {self.n_channels}")

            self.num_img_array_channels = 4 if self.n_channels in (3, 4) else 1
            self.num_bodies = int(self.model_cfg.get("num_bodies"))

            self.file_format = str(self.render_cfg.get("file_format", "PNG"))
            self.file_ext = "png" if self.file_format.lower() == "png" else "exr"

            self._setup_scene()

            self.initialised = True
            return {"status": "ok"}

        def _setup_scene(self) -> None:
            print("Blender worker: configuring scene...")
            # Camera
            self.cam_obj = bpy.data.objects["Camera"]
            self.cam_obj.data.type = "PERSP"
            self.cam_obj.data.lens_unit = "FOV"
            self.cam_obj.data.angle = float(
                self.camera_cfg.get("FOV_x")) * np.pi / 180.0
            self.cam_obj.data.clip_start = 0.5
            self.cam_obj.data.clip_end = 1000.0

            # Render settings
            self.scene.render.engine = self.render_cfg.get(
                "render_engine", "CYCLES")
            if self.scene.render.engine == "CYCLES":
                self.scene.cycles.device = self.render_cfg.get("device", "CPU")
                self.scene.cycles.samples = int(
                    self.render_cfg.get("samples", 1))
                self.scene.cycles.diffuse_bounces = int(
                    self.render_cfg.get("diffuse_bounces", 0))
                if hasattr(self.scene.cycles, "tile_size"):
                    self.scene.cycles.tile_size = int(
                        self.render_cfg.get("tile_size", 256))

            self.scene.render.resolution_x = self.sensor_size_x
            self.scene.render.resolution_y = self.sensor_size_y
            self.scene.render.pixel_aspect_x = 1
            self.scene.render.pixel_aspect_y = 1

            file_format = self.render_cfg.get("file_format", "PNG")
            self.scene.render.image_settings.file_format = str(file_format)
            color_mode = {1: "BW", 3: "RGB", 4: "RGBA"}[self.n_channels]
            self.scene.render.image_settings.color_mode = color_mode
            self.scene.render.image_settings.color_depth = str(
                self.camera_cfg.get("bit_encoding", 8))
            self.scene.render.image_settings.compression = int(
                self.camera_cfg.get("compression", 15))

            # Light
            light_names = self.model_cfg.get("light_names", [])
            if len(light_names) != 1:
                raise NotImplementedError(
                    "Exactly one light object must be specified.")
            light_name = light_names[0]
            try:
                self.sun_obj = bpy.data.objects[light_name]
            except KeyError:
                alt = "Sun" if light_name == "Light" else "Light"
                print(
                    f"Primary light '{light_name}' missing. Trying '{alt}'...")
                self.sun_obj = bpy.data.objects[alt]

            self.sun_obj.data.type = "SUN"
            self.sun_obj.data.energy = float(
                self.model_cfg.get("sun_energy", 2.0))
            self.sun_obj.data.specular_factor = float(
                self.model_cfg.get("specular_factor", 0.0))

            # Bodies
            bodies_names = self.model_cfg.get("bodies_names", [])
            if len(bodies_names) < self.num_bodies:
                raise ValueError("Not enough bodies defined in configuration.")
            self.body_objects = [bpy.data.objects[name]
                                 for name in bodies_names[: self.num_bodies]]

            # Environment
            world = bpy.data.worlds.get("World")
            if world and world.node_tree:
                world.node_tree.nodes["Background"].inputs[0].default_value = (
                    0, 0, 0, 1)

            # Compositing node for mask (optional)
            self.mask_output_node = None
            if self.save_binary_mask_output and self.scene.use_nodes:
                node_tree = self.scene.node_tree
                if node_tree:
                    self.mask_output_node = node_tree.nodes.get(
                        "BinaryMaskOutput")

            # Initial poses
            self.cam_obj.location = (10, 0, 0)
            self.cam_obj.rotation_mode = "QUATERNION"
            self.cam_obj.rotation_quaternion = (1, 0, 0, 0)

            self.sun_obj.location = (0, 0, 0)
            self.sun_obj.rotation_mode = "QUATERNION"
            self.sun_obj.rotation_quaternion = (1, 0, 0, 0)

            for body in self.body_objects:
                body.location = (0, 0, 0)
                body.rotation_mode = "QUATERNION"
                body.rotation_quaternion = (1, 0, 0, 0)

            print("Blender worker: scene setup completed.")

        def handle_render_frame(self, message: Dict[str, Any]) -> Dict[str, Any]:
            if not self.initialised:
                raise RuntimeError("Worker not initialised.")

            frame_index = int(message["frame_index"])
            PQ_SC = np.array(message["spacecraft"], dtype=np.float64)
            PQ_Sun = np.array(message["sun"], dtype=np.float64)
            PQ_Bodies = np.array(message["bodies"], dtype=np.float64).reshape(
                self.num_bodies, 7)
            body_has_changed = bool(message.get("body_has_changed", True))

            if self.disable_caching:
                body_has_changed = True

            self._position_all(PQ_SC, PQ_Bodies, PQ_Sun, body_has_changed)
            if not bpy.app.background:
                bpy.context.view_layer.update()
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)

            self._render(frame_index)
            image_bytes = self._read_render_result(frame_index)
            return {"status": "ok", "frame": frame_index, "image_bytes": image_bytes}

        def _position_all(
            self,
            PQ_SC: np.ndarray,
            PQ_Bodies: np.ndarray,
            PQ_Sun: np.ndarray,
            body_has_changed: bool,
        ) -> None:
            self.sun_obj.location = (0.0, 0.0, 0.0)
            self.cam_obj.location = tuple(PQ_SC[0:3])

            if body_has_changed:
                for idx, body in enumerate(self.body_objects):
                    body.location = tuple(PQ_Bodies[idx, 0:3])
                    body.rotation_quaternion = tuple(PQ_Bodies[idx, 3:7])

            self.sun_obj.rotation_quaternion = tuple(PQ_Sun[3:7])
            self.cam_obj.rotation_quaternion = tuple(PQ_SC[3:7])

        def _render(self, frame_index: int) -> None:
            img_number = f"{frame_index:06d}"
            self.scene.frame_set(frame_index)
            self.scene.render.filepath = str(self.output_images / img_number)

            if self.save_binary_mask_output and self.mask_output_node and self.output_masks:
                self.mask_output_node.base_path = str(self.output_masks)
                self.mask_output_node.file_slots[0].path = ""

            bpy.ops.render.render(write_still=True)

            if self.save_binary_mask_output and self.mask_output_node and self.output_masks:
                default_mask = self.output_masks / f"{frame_index:04d}.png"
                desired_mask = self.output_masks / f"{frame_index:06d}.png"
                if default_mask.exists():
                    default_mask.rename(desired_mask)

        def _read_render_result(self, frame_index: int) -> bytes:
            image_path = self.output_images / \
                f"{frame_index:06d}.{self.file_ext}"
            img = bpy.data.images.load(filepath=str(image_path))
            try:
                if self.num_img_array_channels == 1:
                    width, height = img.size
                    pixels_flat = np.array(img.pixels[:], dtype=np.float32)
                    pixels_rgba = pixels_flat.reshape((height, width, 4))
                    grayscale = (
                        0.299 * pixels_rgba[:, :, 0]
                        + 0.587 * pixels_rgba[:, :, 1]
                        + 0.114 * pixels_rgba[:, :, 2]
                    )
                    img_vec = grayscale.flatten().astype(np.float64, copy=False)
                else:
                    img_vec = np.array(img.pixels[:], dtype=np.float64)
            finally:
                bpy.data.images.remove(img)
            return img_vec.tobytes()

    authkey = bytes.fromhex(args.authkey)
    conn = Client((args.ipc_host, args.ipc_port), authkey=authkey)
    runtime = BlenderWorkerRuntime(conn)
    runtime.loop()
    conn.close()


# -----------------------------------------------------------------------------
# Server entry point
# -----------------------------------------------------------------------------
def run_server(args: argparse.Namespace) -> None:
    config = load_yaml_config(args.config.resolve())
    camera_cfg = config.get("Camera_params", {})
    render_cfg = config.get("RenderingEngine_params", {})
    server_cfg = config.get("Server_params", {})

    if not camera_cfg or not render_cfg or not server_cfg:
        raise ValueError("Configuration file is missing required sections.")

    blend_exec, blend_file = resolve_blender_paths(args, config)

    save_binary_mask_output = bool(render_cfg.get(
        "bSaveGeomVisibilityBoolMask", False))
    output_root, output_images, output_masks = ensure_output_directories(
        Path(server_cfg.get("output_path")),
        save_binary_mask_output,
    )

    init_payload = {
        "camera": camera_cfg,
        "rendering": render_cfg,
        "model": config.get("BlenderModel_params", {}),
        "paths": {
            "output_root": str(output_root),
            "images": str(output_images),
            "binary_masks": str(output_masks) if output_masks else None,
        },
        "options": {
            "save_binary_mask_output": save_binary_mask_output,
            "disable_caching": bool(server_cfg.get("disable_caching", False)),
        },
    }

    bridge = BlenderBridge(blend_exec, blend_file, init_payload)
    server = StandaloneRenderServer(
        config, (output_root, output_images, output_masks), bridge)

    def handle_sigterm(signum, frame):
        print(f"Received signal {signum}. Stopping server.")
        bridge.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        server.run()
    finally:
        bridge.close()


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    if args.worker:
        run_worker(args)
    else:
        run_server(args)


if __name__ == "__main__":
    main()
