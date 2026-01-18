FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Copy requirements file
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy source code
COPY src/ ./src/

# Create output directory
RUN mkdir -p /app/output

# Create non-root user for security
RUN useradd -m -s /bin/bash scraper
RUN chown -R scraper:scraper /app
USER scraper

# Set working directory to src for imports
WORKDIR /app/src

# Default command
CMD ["python", "main.py"]
