# Use a lightweight Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling some packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Hugging Face Spaces expects the app to listen on port 7860
EXPOSE 7860

# Run the Flask app with Gunicorn listening on port 7860
CMD ["gunicorn", "-b", "0.0.0.0:7860", "--workers=1", "--threads=4", "app:app"]
