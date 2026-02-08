FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# git is often needed for installing dependencies from git repos
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port for the API
EXPOSE 8000

# Default command (can be overridden)
CMD ["uvicorn", "pr_merge_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
