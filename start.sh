#!/bin/bash
gunicorn app:app --workers 1 --threads 1 --bind 0.0.0.0:8080 --timeout 86400 & python3 bot.py