FROM python:3.12-slim

WORKDIR /app

COPY requirements /requirements
RUN pip install --no-cache-dir -r /requirements/base.txt -r /requirements/plot.txt

COPY plot /app

CMD ["python", "server.py"]
