FROM python:3.12-slim

# Install ffmpeg and OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better caching
COPY requirements-prod.txt ./
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install -r requirements-prod.txt

COPY . /app

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]
