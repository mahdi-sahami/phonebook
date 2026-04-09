#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

if [ "$DEBUG" = "True" ]; then
    echo "Starting Django development server..."
    python manage.py runserver 0.0.0.0:8000 
else
    echo "Starting Gunicorn..."
    exec gunicorn contact.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 3
fi