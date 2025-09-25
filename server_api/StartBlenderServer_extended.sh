#!/bin/bash
# Bash script used to run CORTO_interfaces
# Function to display an error message and usage
usage() {
    echo "Usage: $0 -m <model_path> -p <python_script>"
    echo "  -m    Path to the Blender model file (.blend)"
    echo "  -p    Path to the Python script file (.py)"
    echo "  -k    Flag to keep process in shell (default is false)"
    exit 1
}

# NAVCAM_HF_1_a
# -------------
# blender -b ../milani-input/Blender/Didymos_AB_crater.blend -P script/CORTO_interfaces/CORTO_interface_HF_1_a.py
# -------------

# NAVCAM_HF_1_b
# -------------
# blender ../milani-input/Blender/Didymos_AB_crater.blend -P script/CORTO_interfaces/CORTO_interface_HF_1_b.py
# -------------

# NAVCAM_HF_1_c
# -------------
# blender -b ../milani-input/Blender/Didymos_AB_crater.blend -P script/CORTO_interfaces/CORTO_interface_HF_1_c.py
# -------------

# NAVCAM_HF_1_d
# -------------
#blender -b ../milani-input/Blender/Didymos_AB_crater_RGB.blend -P script/CORTO_interfaces/CORTO_interface_HF_1_d.py
# -------------

KEEP_SHELL_BUSY=0
LOG_FILE_OUT=""
# Parse command-line arguments
while getopts "m:p:k" opt; do
    case $opt in
        m) MODEL_PATH="$OPTARG" ;;
        p) PYTHON_SCRIPT="$OPTARG" ;;
        k) KEEP_SHELL_BUSY=1;;
        l) LOG_FILE_OUT="$OPTARG" ;;
        *) usage ;;
    esac
done

# Check if both arguments are provided
if [[ -z "$MODEL_PATH" || -z "$PYTHON_SCRIPT" ]]; then
    echo "Error: Both Blender model path and Python script path must be specified."
    usage
fi

# Check if the provided files exist
if [[ ! -f "$MODEL_PATH" ]]; then
    echo "Error: Blender model file '$MODEL_PATH' does not exist."
    exit 1
fi

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "Error: Python script file '$PYTHON_SCRIPT' does not exist."
    exit 1
fi


if [[ $KEEP_SHELL_BUSY -eq 1 ]]; then
    # Execute Blender with the provided paths
    blender --log-level 3 -b $MODEL_PATH -P $PYTHON_SCRIPT
    exit 0
else
    blender_path=$(which blender)
    clear
    # TODO extend to log to file
    #exec > >(tee -a "$LOG_FILE_OUT") 2>&1 # DEVNOTE: all outs are written to file. MATLAB won't get anything back this way.

    # Execute Blender with the provided paths in the background and return PID
    blender --log-level 3 -b $MODEL_PATH -P $PYTHON_SCRIPT > /dev/null 2>&1 &

    if [[ $blender_path == *"snap"* ]]; then
        # If exec is under snap, return bpy_pid of child process
        bpy_wrapper_pid=$!
        sleep 1.0 # Give it a second to start
        bpy_pid=$(pgrep -P $bpy_wrapper_pid);
        # Echo all PIDS
        echo "$bpy_pid"
    else
        # If exec is not under snap, return bpy_pid of parent process
        bpy_pid=$!
        echo "$bpy_pid"
    fi
    exit 0
fi

