#!/usr/bin/env python3
"""
Radarr skill for Claude - movie management via proxy.
All results are saved to disk to preserve context.
"""

import json
import sys
import os
import ssl
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# SSL context for Cloudflare tunnel compatibility
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Add script directory to path for storage import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from storage import save_result

# Configuration
API_BASE = "https://your.container.url"
PROXY_TOKEN = "sha256 token"


def api_request(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Make authenticated request to Radarr proxy."""
    url = f"{API_BASE}/{endpoint.lstrip('/')}"
    
    headers = {
        "X-Proxy-Token": PROXY_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        if method == "GET":
            req = urllib.request.Request(url, headers=headers)
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode() if data else None,
                headers=headers,
                method=method
            )
        
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode())
    
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            return json.loads(body)
        except:
            return {"error": f"HTTP {e.code}: {e.reason}", "body": body[:200]}
    except urllib.error.URLError as e:
        return {"error": f"Connection error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def search_movies(query: str, year: str = None) -> dict:
    """Search for movies by title."""
    params = f"query={urllib.parse.quote(query)}"
    if year:
        params += f"&year={year}"
    
    result = api_request(f"search?{params}")
    
    if "error" not in result:
        path = save_result("search", result, query)
        result["_saved_to"] = path
    
    return result


def get_movies(monitored: str = None, status: str = None) -> dict:
    """Get movies in library. Returns metadata only - full data saved to file."""
    params = []
    if monitored:
        params.append(f"monitored={monitored}")
    if status:
        params.append(f"status={status}")
    
    endpoint = "movies"
    if params:
        endpoint += "?" + "&".join(params)
    
    result = api_request(endpoint)
    
    if "error" not in result:
        path = save_result("movies", result)
        # Return metadata only, not full movie list
        return {
            "count": result.get("count", len(result.get("movies", []))),
            "saved_to": path,
            "hint": f"Full data saved. Use: grep -i 'pattern' {path}"
        }
    
    return result


def get_movie_details(movie_id: int) -> dict:
    """Get detailed info for a specific movie."""
    result = api_request(f"movie/{movie_id}")
    
    if "error" not in result:
        path = save_result("movie_details", result, str(movie_id))
        result["_saved_to"] = path
    
    return result


def add_movie(tmdb_id: str, monitored: bool = True, search_on_add: bool = True) -> dict:
    """Add a movie to Radarr by TMDB ID."""
    data = {
        "tmdb_id": tmdb_id,
        "monitored": monitored,
        "search_on_add": search_on_add
    }
    
    result = api_request("movie/add", "POST", data)
    
    if "error" not in result:
        path = save_result("add_movie", result, tmdb_id)
        result["_saved_to"] = path
    
    return result


def search_releases(movie_id: int, sort: str = "seeders") -> dict:
    """Search for available releases of a movie. Returns metadata only."""
    result = api_request(f"releases/{movie_id}?sort={sort}")
    
    if "error" not in result:
        path = save_result("releases", result, str(movie_id))
        return {
            "count": result.get("count", len(result.get("releases", []))),
            "movie_id": movie_id,
            "saved_to": path,
            "hint": f"Full data saved. Use: grep -i 'pattern' {path}"
        }
    
    return result


def download_release(guid: str, movie_id: int) -> dict:
    """Download a specific release."""
    data = {
        "guid": guid,
        "movie_id": movie_id
    }
    
    result = api_request("download", "POST", data)
    
    if "error" not in result:
        path = save_result("download", result, guid[:20])
        result["_saved_to"] = path
    
    return result


def get_queue() -> dict:
    """Get download queue. Returns metadata only."""
    result = api_request("queue")
    
    if "error" not in result:
        path = save_result("queue", result)
        return {
            "count": result.get("count", len(result.get("items", []))),
            "total": result.get("total", 0),
            "saved_to": path,
            "hint": f"Full data saved. Use: grep -i 'pattern' {path}"
        }
    
    return result


def get_wanted() -> dict:
    """Get wanted/missing movies. Returns metadata only."""
    result = api_request("wanted")
    
    if "error" not in result:
        path = save_result("wanted", result)
        return {
            "count": result.get("count", len(result.get("movies", []))),
            "total": result.get("total", 0),
            "saved_to": path,
            "hint": f"Full data saved. Use: grep -i 'pattern' {path}"
        }
    
    return result


def get_status() -> dict:
    """Get system status."""
    result = api_request("status")
    
    if "error" not in result:
        path = save_result("status", result)
        result["_saved_to"] = path
    
    return result


def print_help():
    """Print usage information."""
    print(json.dumps({
        "usage": "radarr.py <command> [args]",
        "commands": {
            "search <query> [year]": "Search for movies by title",
            "movies [monitored] [status]": "List movies in library",
            "movie <id>": "Get details for a specific movie",
            "add <tmdb_id>": "Add movie by TMDB ID",
            "releases <movie_id> [sort]": "Search releases for a movie",
            "download <guid> <movie_id>": "Download a specific release",
            "queue": "Get download queue",
            "wanted": "Get wanted/missing movies",
            "status": "Get system status"
        },
        "notes": [
            "Large results (movies, releases, queue, wanted) return metadata only",
            "Full data saved to /home/claude/radarr/ - grep the files directly"
        ]
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    args = sys.argv[2:]
    
    try:
        if cmd == "search" and args:
            year = args[1] if len(args) > 1 else None
            result = search_movies(args[0], year)
        
        elif cmd == "movies":
            monitored = args[0] if len(args) > 0 else None
            status = args[1] if len(args) > 1 else None
            result = get_movies(monitored, status)
        
        elif cmd == "movie" and args:
            result = get_movie_details(int(args[0]))
        
        elif cmd == "add" and args:
            result = add_movie(args[0])
        
        elif cmd == "releases" and args:
            sort = args[1] if len(args) > 1 else "seeders"
            result = search_releases(int(args[0]), sort)
        
        elif cmd == "download" and len(args) >= 2:
            result = download_release(args[0], int(args[1]))
        
        elif cmd == "queue":
            result = get_queue()
        
        elif cmd == "wanted":
            result = get_wanted()
        
        elif cmd == "status":
            result = get_status()
        
        elif cmd == "help":
            print_help()
            sys.exit(0)
        
        else:
            result = {"error": f"Unknown command: {cmd}. Use 'help' for usage."}
        
        print(json.dumps(result, indent=2))
    
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
