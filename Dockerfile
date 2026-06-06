FROM python:3.12-slim

LABEL maintainer="Domenick Waldvogel <domenick.waldvogel@domekologe.eu>"
LABEL description="JellyLogin — Central media hub with Jellyfin SSO"
LABEL version="1.0.0"

WORKDIR /app

# Install dependencies first — separate layer so Docker cache skips this
# on source-only changes
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY jellylogin/ ./jellylogin/

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

CMD ["python", "-c", "from jellylogin.app import main; main()"]
