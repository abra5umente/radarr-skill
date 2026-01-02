# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Skill for managing a Radarr movie library. It consists of two components:

1. **Proxy Server** (`proxy/`) - Flask-based proxy that secures access to a local Radarr instance via Cloudflare Tunnel
2. **Skill Scripts** (`skill/`) - Python CLI tools that Claude uses to interact with the proxy

## Architecture

```
Claude Skill → HTTPS → your.container.url → Docker Container → Radarr API
                              (Cloudflare Tunnel)
```

The proxy holds the Radarr API key server-side. Claude authenticates with a separate proxy token via `X-Proxy-Token` header, never seeing the actual API key.

## Development Commands

### Proxy Server

```bash
# Build and run the proxy container
cd proxy
docker compose up -d

# View logs
docker compose logs -f

# Rebuild after changes
docker compose up -d --build
```

### Skill Scripts

Scripts are meant to run on the Claude skill environment at `/mnt/skills/user/radarr/scripts/`:

```bash
# Search for movies
python3 radarr.py search "Movie Title" [year]

# List library
python3 radarr.py movies [monitored] [status]

# Add movie by TMDB ID
python3 radarr.py add <tmdb_id>

# Check download queue
python3 radarr.py queue

# Manage cached results
python3 storage.py list
python3 storage.py get <filename>
python3 storage.py clear
```

## Key Files

- `proxy/server.py` - Flask proxy with all API endpoints
- `skill/scripts/radarr.py` - Main CLI interface for Radarr operations
- `skill/scripts/storage.py` - Local cache management for API results
- `skill/SKILL.md` - Skill definition that tells Claude when to invoke this skill

## Environment Variables (Proxy)

Required in `proxy/.env`:
- `RADARR_API_KEY` - From Radarr Settings → General → Security
- `PROXY_TOKEN` - SHA256 token for Claude authentication

## Result Caching

All API results are automatically saved to `/home/claude/radarr/` with a manifest tracking queries. This preserves context across interactions.
