#!/bin/bash

python -m venv venv
source venv/bin/activate
sudo pip install python3-gobject gtk3
pip install --upgrade pip
pip install -r requirements.txt
deactivate
