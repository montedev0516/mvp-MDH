FROM python:3.12-slim-bookworm

# Set environment variables to reduce interaction and improve Docker build
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_CONFIG_FILE=/app/pip.conf

# Configure apt to retry and avoid hash mismatches
RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80retries && \
    echo 'Acquire::http::Pipeline-Depth "0";' > /etc/apt/apt.conf.d/99nopipelining && \
    echo 'APT::Get::Fix-Missing "true";' > /etc/apt/apt.conf.d/80fix-missing

# Install WeasyPrint dependencies with retry logic
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --fix-missing --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu \
    libpq-dev \
    postgresql-client \
    libmagic-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Download the latest UV installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"
WORKDIR /app

# Copy the project into the image
COPY . .

# Sync the project into a new environment, using the frozen lockfile
RUN uv sync --frozen

# Expose port 8000
EXPOSE 8000

# Start Gunicorn server
CMD ["uv", "run", "gunicorn", "mdh.wsgi", "-w", "2", "--bind", "0.0.0.0:8000"]