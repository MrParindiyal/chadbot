#!/bin/bash
python -m pip install --upgrade pip
pip install -r requirements.txt

gunicorn --workers 1 --bind 0.0.0.0:8080 main:app