# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt and update yt-dlp
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --upgrade yt-dlp

# Copy the rest of the application's code to the working directory
COPY . .

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "main:app"]
