FROM python:3.6

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD [ "python", "manage.py", "migrate", "&&", "gunicorn", "chatmonitor.wsgi", "--workers=1" ]
