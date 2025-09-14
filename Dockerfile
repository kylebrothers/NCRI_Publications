FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download SpaCy language model (for NLP features from NCRI_Timelines)
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p \
    templates \
    static \
    logs \
    uploads \
    server_files \
    server_files/shared-articles \
    server_files/pubmed-search \
    server_files/literature-review \
    server_files/research-assistant

# Set permissions for directories
RUN chmod -R 755 /app/server_files

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["python", "app.py"]
