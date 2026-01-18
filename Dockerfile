FROM mcr.microsoft.com/playwright:v1.49.0-jammy

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY src/ ./src/

# Create non-root user for security
RUN useradd -m -s /bin/bash scraper
RUN chown -R scraper:scraper /app
USER scraper

# Default command
CMD ["node", "src/index.js"]
