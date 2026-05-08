# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
# Ensure you have a requirements.txt file in your project root.
RUN pip install --no-cache-dir -r requirements.txt

# The entry point for FastAPI is assumed to be main.py. 
# Adjust 'main:app' if your entry point file or FastAPI instance name differs.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

# Note for React Integration:
# If serving a React frontend via FastAPI StaticFiles, ensure your 'build' 
# directory is included in the 'COPY . ./' or use a multi-stage build.

EXPOSE 8080