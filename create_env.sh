python3.11 -m venv .venvCORTOpy
source .venvCORTOpy/bin/activate
pip install -r requirements.txt --require-virtualenv
pip install -e . --require-virtualenv
pip install pyyaml types-PyYAML --require-virtualenv