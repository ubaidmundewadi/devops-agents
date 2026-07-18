# Use official python slim image
FROM python:3.11-slim

# Install system dependencies and HashiCorp Terraform CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    git \
    unzip \
    && curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(. /etc/os-release && echo "$VERSION_CODENAME") main" | tee /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    terraform \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy python dependencies list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application directories
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY terraform/ ./terraform/

# Expose port 8000 for FastAPI / WebSockets
EXPOSE 8000

# Run the FastAPI server using Uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
