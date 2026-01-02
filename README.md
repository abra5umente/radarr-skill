# Radarr Claude Skill

A Claude Skill that enables Claude to manage your Radarr movie library. Consists of a proxy server (to secure your Radarr API key) and skill scripts that Claude executes.

## Architecture

```
Claude Skill → HTTPS → Your Proxy URL → Proxy Container → Radarr API
                       (Cloudflare Tunnel or similar)
```

The proxy holds your Radarr API key server-side. Claude only knows a separate proxy token, never the actual API key.

## Prerequisites

- Docker and Docker Compose
- A running Radarr instance
- A way to expose the proxy to the internet (Cloudflare Tunnel, ngrok, reverse proxy, etc.)
- A Claude account with skills support

## Setup

### 1. Deploy the Proxy Server

```bash
cd proxy

# Create your environment file
cp .env.example .env
```

Edit `.env` with your values:

```env
# Your Radarr instance URL (accessible from the container)
RADARR_URL=http://your-radarr-host:7878

# Radarr API key from Settings -> General -> Security
RADARR_API_KEY=your-radarr-api-key

# Generate a proxy token for Claude authentication
# Run: python3 -c "import hashlib,secrets; print(hashlib.sha256(secrets.token_bytes(32)).hexdigest())"
PROXY_TOKEN=your-generated-sha256-token
```

Build and run:

```bash
docker compose up -d
```

### 2. Expose the Proxy

The proxy needs to be accessible via HTTPS from the internet. Options include:

**Cloudflare Tunnel (recommended):**
```bash
cloudflared tunnel --url http://localhost:5000
```

**Or add to an existing tunnel config:**
```yaml
ingress:
  - hostname: radarr-proxy.yourdomain.com
    service: http://localhost:5000
```

**Other options:** ngrok, Tailscale Funnel, or a reverse proxy with SSL.

Note your public URL (e.g., `https://radarr-proxy.yourdomain.com`).

### 3. Configure the Skill Scripts

Edit `skill/scripts/radarr.py` and update the configuration at the top:

```python
# Configuration
API_BASE = "https://radarr-proxy.yourdomain.com"  # Your proxy URL
PROXY_TOKEN = "your-generated-sha256-token"        # Same token from .env
```

### 4. Add the Skill to Claude

1. Copy the `skill/` directory to your Claude skills location:
   - The skill expects to be at `/mnt/skills/user/radarr/`
   - Scripts should be at `/mnt/skills/user/radarr/scripts/`
   - `SKILL.md` should be at `/mnt/skills/user/radarr/SKILL.md`

2. The skill will automatically activate when you mention Radarr, movie downloads, adding movies, or checking the download queue.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RADARR_URL` | Yes | Your Radarr instance URL (e.g., `http://localhost:7878`) |
| `RADARR_API_KEY` | Yes | Radarr API key from Settings → General → Security |
| `PROXY_TOKEN` | Yes | SHA256 token for Claude authentication |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `HOST` | No | Bind address (default: `0.0.0.0`) |
| `PORT` | No | Port (default: `5000`) |

## API Endpoints

All endpoints require `X-Proxy-Token` header.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth required) |
| `/search?query=...&year=...` | GET | Search movies by title |
| `/movies?monitored=...&status=...` | GET | List library |
| `/movie/<id>` | GET | Get movie details |
| `/movie/add` | POST | Add movie (body: `{tmdb_id, monitored, search_on_add}`) |
| `/releases/<movie_id>?sort=...` | GET | Search releases for a movie |
| `/download` | POST | Download release (body: `{guid, movie_id}`) |
| `/queue` | GET | Get download queue |
| `/wanted` | GET | Get missing/wanted movies |
| `/status` | GET | Get system status |

## Usage Examples

Once the skill is installed, you can ask Claude things like:

- "Search for The Matrix on Radarr"
- "Add Interstellar to my movie library"
- "What's in my download queue?"
- "Show me my wanted movies"
- "Check my Radarr status"

## Security Notes

- The proxy token is a SHA256 hash, separate from your Radarr API key
- Claude never sees your actual Radarr API key
- All traffic should go through HTTPS
- The proxy validates the token on every request

## Troubleshooting

**Proxy not responding:**
```bash
docker compose logs -f
curl http://localhost:5000/health
```

**Authentication errors:**
- Verify `PROXY_TOKEN` matches in both `.env` and `radarr.py`
- Check the proxy logs for token validation errors

**Can't reach Radarr:**
- Ensure `RADARR_URL` is accessible from inside the container
- If Radarr is on the host, use `host.docker.internal` or your LAN IP

## Development

```bash
# Rebuild after changes
docker compose up -d --build

# View logs
docker compose logs -f

# Test endpoints
curl -H "X-Proxy-Token: your-token" https://your-proxy-url/status
```
