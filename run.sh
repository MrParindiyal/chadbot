#!/bin/bash
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

gunicorn --workers 1 --bind 0.0.0.0:8080 main:app