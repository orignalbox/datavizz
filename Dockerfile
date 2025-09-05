# Use a more complete official Python runtime as a parent image.
# 'bullseye' is a standard Debian release that has better package compatibility than 'slim'.
FROM python:3.10-bullseye

# Set the working directory in the container
WORKDIR /app

# Install system-level dependencies required by Manim
# This is the crucial step that makes Docker so powerful for this project.
# We are installing FFmpeg, a smaller set of essential LaTeX packages, and other libraries.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-science \
    tipa \
    libgl1-mesa-glx \
    libcairo2-dev \
    libjpeg-dev \
    libgif-dev \
    libpango1.0-dev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy the file with our Python dependencies
COPY requirements.txt .

# Install Python dependencies, including Manim and a production web server (Gunicorn)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Expose the port Gunicorn will run on
EXPOSE 8000

# The command to run your application in production using Gunicorn
# Gunicorn is a robust WSGI server, unlike Flask's built-in development server.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "300", "app:app"]


