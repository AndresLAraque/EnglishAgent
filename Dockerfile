FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY setup.py .
RUN pip install --no-cache-dir -e .

CMD ["english-bot"]
