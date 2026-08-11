# Dockerfile for Carim Store backend (Flask)
# Builds a production-ready image using gunicorn to serve the Flask app

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps (if needed)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Expose the port the app runs on
EXPOSE 5000

# Use an environment variable $PORT if provided by the hosting platform
ENV PORT=5000

# Run the application with gunicorn
CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:5000", "--workers", "4"]
