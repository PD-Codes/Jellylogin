FROM python:3.12-slim

LABEL maintainer="Domenick Waldvogel <domenick.waldvogel@domekologe.eu>"
LABEL description="JellyLogin — Central media hub with Jellyfin SSO"
LABEL version="1.0.0"

WORKDIR /app

# Install build dependencies (only needed for hatchling build backend)
RUN pip install --no-cache-dir hatchling

# Copy project files
COPY pyproject.toml MANIFEST.in ./
COPY jellylogin/ ./jellylogin/

# Install the app
RUN pip install --no-cache-dir .

# Runtime environment
ENV JELLYLOGIN_DATA=/data
ENV JELLYLOGIN_HTTPS=0
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Persistent data volume
VOLUME ["/data"]

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" \
  || exit 1

CMD ["jellylogin", "--host", "0.0.0.0", "--port", "5000"]
