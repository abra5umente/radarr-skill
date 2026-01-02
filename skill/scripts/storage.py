#!/usr/bin/env python3
"""Local storage for Radarr results - save responses to disk to preserve context."""

import json
import os
from pathlib import Path
from datetime import datetime

RADARR_CACHE = Path("/home/claude/radarr")
MANIFEST_FILE = RADARR_CACHE / "manifest.json"


def ensure_dirs():
    """Create cache directories if needed."""
    RADARR_CACHE.mkdir(parents=True, exist_ok=True)


def load_manifest() -> dict:
    """Load the manifest tracking cached content."""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text())
    return {"queries": {}}


def save_manifest(manifest: dict):
    """Save the manifest."""
    ensure_dirs()
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))


def save_result(operation: str, result: dict, key: str = None) -> str:
    """Save an API result to local cache. Returns the cache path."""
    ensure_dirs()
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if key:
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(key))[:50]
        filename = f"{operation}_{safe_key}_{timestamp}.json"
    else:
        filename = f"{operation}_{timestamp}.json"
    
    cache_path = RADARR_CACHE / filename
    
    # Add metadata
    result["_meta"] = {
        "operation": operation,
        "key": key,
        "cached_at": datetime.now().isoformat(),
        "path": str(cache_path)
    }
    
    cache_path.write_text(json.dumps(result, indent=2))
    
    # Update manifest
    manifest = load_manifest()
    manifest["queries"][filename] = {
        "operation": operation,
        "key": key,
        "cached_at": datetime.now().isoformat(),
        "path": str(cache_path)
    }
    save_manifest(manifest)
    
    return str(cache_path)


def list_cached() -> dict:
    """List all cached results."""
    manifest = load_manifest()
    
    by_operation = {}
    for filename, meta in manifest.get("queries", {}).items():
        op = meta.get("operation", "unknown")
        if op not in by_operation:
            by_operation[op] = []
        by_operation[op].append({
            "filename": filename,
            "key": meta.get("key"),
            "cached_at": meta.get("cached_at")
        })
    
    return {
        "by_operation": by_operation,
        "total": len(manifest.get("queries", {}))
    }


def get_cached(filename: str) -> dict:
    """Load a specific cached result."""
    path = RADARR_CACHE / filename
    if path.exists():
        return json.loads(path.read_text())
    return {"error": f"Cache file {filename} not found"}


def clear_cache() -> dict:
    """Clear all cached results."""
    import shutil
    
    manifest = load_manifest()
    count = len(manifest.get("queries", {}))
    
    if RADARR_CACHE.exists():
        shutil.rmtree(RADARR_CACHE)
    
    return {"cleared": count}


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: storage.py <command> [args]",
            "commands": {
                "list": "List all cached results",
                "get <filename>": "Load a cached result",
                "clear": "Clear all cache"
            }
        }, indent=2))
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    args = sys.argv[2:]
    
    try:
        if cmd == "list":
            result = list_cached()
        elif cmd == "get" and args:
            result = get_cached(args[0])
        elif cmd == "clear":
            result = clear_cache()
        else:
            result = {"error": f"Unknown command: {cmd}"}
        
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
