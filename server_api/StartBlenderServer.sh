#!/bin/bash
# Bash script used to run CORTO_interfaces
# Function to display an error message and usage
usage() {
    echo "Usage: $0 -m <model_path> -p <python_script>"
    echo "  -m    Path to the Blender model file (.blend)"
    echo "  -p    Path to the Python script file (.py)"
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

# Parse command-line arguments
while getopts "m:p:" opt; do
    case $opt in
        m) MODEL_PATH="$OPTARG" ;;
        p) PYTHON_SCRIPT="$OPTARG" ;;
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

# Execute Blender with the provided paths
blender --log-level 3 -b $MODEL_PATH -P $PYTHON_SCRIPT
