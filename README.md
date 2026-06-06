# JellyLogin

**A self-hosted media dashboard with Jellyfin authentication.**  
Manage all your media services — Jellyfin, Overseerr, Sonarr, Radarr, Prowlarr and more — from one central, beautiful launch page.

---

## Features

### Dashboard
- **Link cards** for any web service — name, URL, icon (emoji, image URL or Font Awesome class), background colour/image, and three card styles: *Glass*, *Solid*, *Minimal*
- **Categories** to group related services
- **Status indicators** — live online/offline dot on every card, results cached server-side
- **Quick search** — filter cards instantly by name or description (`/` keyboard shortcut)
- **Drag-and-drop** sorting for both cards and categories (admin)
- **Announcements** — admin can broadcast an info / warning / success banner to all users

### Authentication
- **Local master account** — the first account (created during setup) is independent of Jellyfin
- **Jellyfin login** — other users authenticate with their existing Jellyfin credentials; optional auto-creation of accounts on first login
- **Two roles** — `admin` (full settings access) and `user` (dashboard only)
- **Rate limiting** — 5 failed attempts lock an IP for 15 minutes
- **CSRF protection** on every form and AJAX call

### Customisation
- **Login-page designer** — live WYSIWYG editor for the login screen
  - Logo: Font Awesome icon (quick-pick grid) or uploaded image
  - Title override, subtitle text
  - Accent colour (picker + 8 presets)
  - Card style: Glassmorphism / Solid Dark / Frosted Light
  - Separate login background (colour, gradient preset, or image URL)
- **Site background** — sticky behind all content; choose a solid colour, one of six gradient presets, an image URL, or upload a file
- **Favicon upload** — replace the default icon with any ICO, PNG, SVG, or JPG
- **Custom site name and description**

### Jellyfin SSO Plugin
A companion C# plugin (included in `jellyfin-plugin/`) lets Jellyfin users log in to Jellyfin **using their JellyLogin credentials** — single sign-on in both directions.

### Deployment
- `pip install jellylogin` — works like any Python package
- **Docker** ready with a single `docker-compose up`
- Default port **5000**, configurable via CLI
- SQLite database, no external dependencies

---

## Requirements

- Python 3.9 or newer  
- pip  
*(Docker users: nothing else needed)*

---

## Installation

### pip (recommended)

```bash
pip install jellylogin
jellylogin
```

Open **http://localhost:5000** and complete the first-run setup.

---

### From source

```bash
git clone https://github.com/domekologe/jellylogin
cd jellylogin
pip install -e .
jellylogin
```

---

### Docker

```bash
docker run -d \
  --name jellylogin \
  --restart unless-stopped \
  -p 5000:5000 \
  -v jellylogin_data:/data \
  jellylogin:latest
```

---

### Docker Compose

```yaml
services:
  jellylogin:
    image: jellylogin:latest
    container_name: jellylogin
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - jellylogin_data:/data
    environment:
      JELLYLOGIN_DATA: /data
      # JELLYLOGIN_HTTPS: "1"   # enable when behind an HTTPS reverse proxy

volumes:
  jellylogin_data:
```

Build the image locally if you haven't published it yet:

```bash
docker compose up --build -d
```

---

## Configuration

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `JELLYLOGIN_DATA` | Directory for the SQLite database, secret key, and uploaded files | `./data` |
| `JELLYLOGIN_HTTPS` | Set to `1` to mark session cookies as Secure (use behind HTTPS) | `0` |

### CLI options

```
jellylogin [--host HOST] [--port PORT] [--data DIR]

  --host   Bind address   (default: 0.0.0.0)
  --port   TCP port       (default: 5000)
  --data   Data directory (overrides JELLYLOGIN_DATA)
```

---

## First run

1. Navigate to **http://localhost:5000**
2. You will be redirected to the **setup page** — create your master admin account
3. Log in and head to **Admin → Links** to add your first services

---

## Jellyfin integration

1. In Jellyfin: **Dashboard → API Keys → Create new key**
2. In JellyLogin: **Admin → Jellyfin** — enter your server URL and the API key
3. Click **Test connection**
4. Enable **Jellyfin login** so Jellyfin users can sign in
5. Optionally click **Sync users** to import all existing Jellyfin accounts at once

---

## Jellyfin SSO Plugin

The plugin in `jellyfin-plugin/` implements `IAuthenticationProvider` for Jellyfin.  
It forwards login attempts to JellyLogin's `/api/plugin/auth` endpoint, so Jellyfin users can authenticate **with their JellyLogin password**.

### Setup

1. Build the plugin (`dotnet publish`) and copy the DLL into Jellyfin's plugin directory
2. Restart Jellyfin
3. In Jellyfin: **Admin → Plugins → JellyLogin SSO** — enter the JellyLogin server URL and the **Plugin Secret**
4. The Plugin Secret is shown (masked) under **Admin → Settings → Jellyfin SSO Plugin** in JellyLogin

---

## Reverse proxy

Set `JELLYLOGIN_HTTPS=1` when running behind nginx, Traefik, or Caddy so the session cookie gets the `Secure` flag.

### nginx example

```nginx
server {
    listen 443 ssl;
    server_name jellylogin.example.com;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

---

## Development

```bash
git clone https://github.com/domekologe/jellylogin
cd jellylogin
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run in development mode (Flask reloader):

```bash
flask --app jellylogin.app:create_app run --debug --port 5000
```

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for the full text.

© Domenick Waldvogel
