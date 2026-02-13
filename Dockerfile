FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY flashscore_scraper/ ./flashscore_scraper/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Install Playwright browsers
RUN playwright install chromium

# Create output directory
RUN mkdir -p /app/output

# Create non-root user for security
RUN useradd -m -s /bin/bash scraper
RUN chown -R scraper:scraper /app
USER scraper

# Default command
CMD ["python", "-m", "flashscore_scraper"]
