release: python manage.py migrate
web: gunicorn chatmonitor.wsgi --workers=1
worker: celery worker -A chatmonitor.celery.app --loglevel=info
