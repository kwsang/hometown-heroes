# Use the official lightweight Python image.
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn and Uvicorn for production-grade serving
RUN pip install --no-cache-dir gunicorn uvicorn

# Run the web service on container startup.
# Cloud Run sets the PORT environment variable; we bind to 0.0.0.0
CMD exec gunicorn --bind 0.0.0.0:$PORT \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --threads 8 \
    --timeout 0 \
    main:app