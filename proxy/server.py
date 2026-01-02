#!/usr/bin/env python3
"""
Radarr Proxy Server for Claude Skills
Routes authenticated requests to local Radarr instance.
Keeps API key server-side, validates requests with proxy token.
"""

import os
import json
import logging
from typing import Any
from urllib.parse import quote_plus
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Configuration from environment
RADARR_URL = os.getenv('RADARR_URL', '').rstrip('/')
RADARR_API_KEY = os.getenv('RADARR_API_KEY', '')
PROXY_TOKEN = os.getenv('PROXY_TOKEN', '')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('RadarrProxy')

# Validate required config
if not all([RADARR_URL, RADARR_API_KEY, PROXY_TOKEN]):
    logger.error("Missing required environment variables: RADARR_URL, RADARR_API_KEY, PROXY_TOKEN")


def validate_token():
    """Validate the proxy token from request header."""
    token = request.headers.get('X-Proxy-Token', '')
    if token != PROXY_TOKEN:
        return False
    return True


def make_radarr_request(endpoint: str, method: str = 'GET', data: dict | None = None) -> tuple[Any, int]:
    """Forward request to Radarr API."""
    url = f"{RADARR_URL}/api/v3/{endpoint.lstrip('/')}"
    headers = {
        'X-Api-Key': RADARR_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == 'PUT':
            resp = requests.put(url, headers=headers, json=data, timeout=30)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return {'error': f'Unsupported method: {method}'}, 400
        
        resp.raise_for_status()
        return resp.json(), resp.status_code
    except requests.exceptions.HTTPError as e:
        logger.error(f"Radarr HTTP error: {e}")
        error_body = {'error': str(e)}
        if e.response is not None:
            try:
                error_body = e.response.json()
            except json.JSONDecodeError:
                error_body = {'error': e.response.text or str(e)}
        return error_body, e.response.status_code if e.response else 500
    except requests.exceptions.RequestException as e:
        logger.error(f"Radarr request error: {e}")
        return {'error': str(e)}, 500
    except json.JSONDecodeError:
        return {'success': True}, 200  # Some DELETE responses are empty


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


@app.route('/api/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_request(endpoint):
    """Generic proxy endpoint for Radarr API calls."""
    if not validate_token():
        return jsonify({'error': 'Invalid or missing proxy token'}), 401
    
    # Get query string for GET requests
    if request.method == 'GET' and request.query_string:
        endpoint = f"{endpoint}?{request.query_string.decode()}"
    
    data = request.get_json(silent=True)
    result, status = make_radarr_request(endpoint, request.method, data)
    
    return jsonify(result), status


# Convenience endpoints for common operations

@app.route('/search', methods=['GET'])
def search_movies():
    """Search for movies by title."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    query = request.args.get('query', '')
    year = request.args.get('year', '')
    
    search_term = f"{query} {year}".strip() if year else query
    result, status = make_radarr_request(f"movie/lookup?term={quote_plus(search_term)}")
    
    if status != 200:
        return jsonify(result), status
    
    # Process results
    movies = []
    for m in result[:10]:
        movies.append({
            'title': m.get('title', 'Unknown'),
            'year': m.get('year'),
            'overview': (m.get('overview', '') or '')[:200],
            'tmdb_id': m.get('tmdbId'),
            'imdb_id': m.get('imdbId'),
            'runtime': m.get('runtime'),
            'status': m.get('status'),
            'genres': [g if isinstance(g, str) else g.get('name') for g in m.get('genres', [])]
        })
    
    return jsonify({'movies': movies, 'count': len(movies)})


@app.route('/movies', methods=['GET'])
def get_movies():
    """Get movies in library with optional filters."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    monitored = request.args.get('monitored')
    status_filter = request.args.get('status')
    
    result, status = make_radarr_request('movie')
    if status != 200:
        return jsonify(result), status
    
    movies = result
    if monitored is not None:
        mon_bool = monitored.lower() == 'true'
        movies = [m for m in movies if m.get('monitored') == mon_bool]
    if status_filter:
        movies = [m for m in movies if m.get('status') == status_filter]
    
    processed = []
    for m in movies:
        processed.append({
            'id': m.get('id'),
            'title': m.get('title'),
            'year': m.get('year'),
            'status': m.get('status'),
            'monitored': m.get('monitored'),
            'has_file': m.get('hasFile', False),
            'size_on_disk': m.get('sizeOnDisk', 0),
            'quality_profile': m.get('qualityProfile', {}).get('name'),
            'tmdb_id': m.get('tmdbId')
        })
    
    return jsonify({'movies': processed, 'count': len(processed)})


@app.route('/qualityprofiles', methods=['GET'])
def get_quality_profiles():
    """Get available quality profiles."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    result, status = make_radarr_request('qualityprofile')
    if status != 200:
        return jsonify(result), status
    
    profiles = [
        {'id': p.get('id'), 'name': p.get('name')}
        for p in result
    ]
    
    return jsonify({'profiles': profiles, 'count': len(profiles)})


@app.route('/movie/<int:movie_id>', methods=['GET'])
def get_movie_details(movie_id):
    """Get detailed info for a specific movie."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    result, status = make_radarr_request(f'movie/{movie_id}')
    if status != 200:
        return jsonify(result), status
    
    movie = {
        'id': result.get('id'),
        'title': result.get('title'),
        'year': result.get('year'),
        'overview': result.get('overview'),
        'status': result.get('status'),
        'monitored': result.get('monitored'),
        'has_file': result.get('hasFile'),
        'runtime': result.get('runtime'),
        'genres': [g if isinstance(g, str) else g.get('name') for g in result.get('genres', [])],
        'quality_profile': result.get('qualityProfile', {}).get('name'),
        'root_folder': result.get('rootFolderPath'),
        'size_on_disk': result.get('sizeOnDisk'),
        'tmdb_id': result.get('tmdbId'),
        'imdb_id': result.get('imdbId')
    }
    
    # Include file details if present
    if result.get('movieFile'):
        mf = result['movieFile']
        movie['file'] = {
            'path': mf.get('relativePath'),
            'size': mf.get('size'),
            'quality': mf.get('quality', {}).get('quality', {}).get('name'),
            'date_added': mf.get('dateAdded')
        }
    
    return jsonify(movie)


@app.route('/movie/add', methods=['POST'])
def add_movie():
    """Add a movie to Radarr."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    data = request.get_json() or {}
    tmdb_id = data.get('tmdb_id')

    if not tmdb_id:
        return jsonify({'error': 'tmdb_id is required'}), 400
    
    # Lookup movie first
    lookup, status = make_radarr_request(f'movie/lookup/tmdb?tmdbId={tmdb_id}')
    if status != 200:
        return jsonify(lookup), status
    
    if not lookup:
        return jsonify({'error': f'Movie with TMDB ID {tmdb_id} not found'}), 404
    
    # Get defaults if not provided
    quality_profile_id = data.get('quality_profile_id')
    root_folder = data.get('root_folder')
    
    if not quality_profile_id:
        profiles, _ = make_radarr_request('qualityprofile')
        quality_profile_id = profiles[0]['id'] if profiles else 1
    
    if not root_folder:
        folders, _ = make_radarr_request('rootfolder')
        root_folder = folders[0]['path'] if folders else '/movies'
    
    movie_data = {
        'title': lookup.get('title'),
        'year': lookup.get('year'),
        'tmdbId': lookup.get('tmdbId'),
        'imdbId': lookup.get('imdbId'),
        'titleSlug': lookup.get('titleSlug'),
        'images': lookup.get('images', []),
        'runtime': lookup.get('runtime'),
        'overview': lookup.get('overview'),
        'genres': lookup.get('genres', []),
        'qualityProfileId': quality_profile_id,
        'rootFolderPath': root_folder,
        'monitored': data.get('monitored', True),
        'addOptions': {
            'searchForMovie': data.get('search_on_add', True)
        }
    }
    
    result, status = make_radarr_request('movie', 'POST', movie_data)
    
    if status not in [200, 201]:
        return jsonify(result), status
    
    return jsonify({
        'success': True,
        'id': result.get('id'),
        'title': result.get('title'),
        'year': result.get('year'),
        'monitored': result.get('monitored')
    })


@app.route('/releases/<int:movie_id>', methods=['GET'])
def search_releases(movie_id):
    """Search for available releases of a movie."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    sort_by = request.args.get('sort', 'seeders')
    
    result, status = make_radarr_request(f'release?movieId={movie_id}')
    if status != 200:
        return jsonify(result), status
    
    releases = result
    if sort_by == 'seeders':
        releases.sort(key=lambda x: x.get('seeders', 0), reverse=True)
    elif sort_by == 'size':
        releases.sort(key=lambda x: x.get('size', 0), reverse=True)
    
    processed = []
    for r in releases[:20]:
        processed.append({
            'guid': r.get('guid'),
            'title': r.get('title'),
            'size': r.get('size'),
            'seeders': r.get('seeders'),
            'leechers': r.get('leechers'),
            'quality': r.get('quality', {}).get('quality', {}).get('name'),
            'indexer': r.get('indexer'),
            'approved': r.get('approved', False),
            'rejections': r.get('rejections', [])
        })
    
    return jsonify({'releases': processed, 'count': len(processed)})


@app.route('/download', methods=['POST'])
def download_release():
    """Download a specific release."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    data = request.get_json() or {}
    guid = data.get('guid')
    movie_id = data.get('movie_id')

    if not guid or not movie_id:
        return jsonify({'error': 'guid and movie_id are required'}), 400
    
    result, status = make_radarr_request('release', 'POST', {
        'guid': guid,
        'movieId': movie_id
    })
    
    return jsonify({'success': status in [200, 201], 'result': result}), status


@app.route('/queue', methods=['GET'])
def get_queue():
    """Get download queue."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401

    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    result, status = make_radarr_request(f'queue?page={page}&pageSize={page_size}')
    if status != 200:
        return jsonify(result), status
    
    items = []
    for item in result.get('records', []):
        items.append({
            'id': item.get('id'),
            'movie_title': item.get('movie', {}).get('title'),
            'title': item.get('title'),
            'size': item.get('size'),
            'sizeleft': item.get('sizeleft'),
            'status': item.get('status'),
            'progress': round((1 - item.get('sizeleft', 0) / max(item.get('size', 1), 1)) * 100, 1),
            'eta': item.get('estimatedCompletionTime'),
            'quality': item.get('quality', {}).get('quality', {}).get('name'),
            'download_client': item.get('downloadClient')
        })
    
    return jsonify({
        'items': items,
        'count': len(items),
        'total': result.get('totalRecords', 0)
    })


@app.route('/wanted', methods=['GET'])
def get_wanted():
    """Get wanted/missing movies."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401

    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    result, status = make_radarr_request(f'wanted/missing?page={page}&pageSize={page_size}&sortKey=title')
    if status != 200:
        return jsonify(result), status
    
    movies = []
    for m in result.get('records', []):
        movies.append({
            'id': m.get('id'),
            'title': m.get('title'),
            'year': m.get('year'),
            'status': m.get('status'),
            'quality_profile': m.get('qualityProfile', {}).get('name'),
            'tmdb_id': m.get('tmdbId')
        })
    
    return jsonify({
        'movies': movies,
        'count': len(movies),
        'total': result.get('totalRecords', 0)
    })


@app.route('/status', methods=['GET'])
def get_status():
    """Get system status."""
    if not validate_token():
        return jsonify({'error': 'Invalid proxy token'}), 401
    
    status_result, s1 = make_radarr_request('system/status')
    health_result, s2 = make_radarr_request('health')
    disk_result, s3 = make_radarr_request('diskspace')
    
    if s1 != 200:
        return jsonify(status_result), s1
    
    return jsonify({
        'version': status_result.get('version'),
        'os': status_result.get('osName'),
        'branch': status_result.get('branch'),
        'health': [
            {'source': h.get('source'), 'type': h.get('type'), 'message': h.get('message')}
            for h in (health_result if isinstance(health_result, list) else [])
        ],
        'disk_space': [
            {
                'path': d.get('path'),
                'free': d.get('freeSpace'),
                'total': d.get('totalSpace')
            }
            for d in (disk_result if isinstance(disk_result, list) else [])
        ]
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting Radarr proxy on {host}:{port}")
    logger.info(f"Radarr URL: {RADARR_URL}")
    
    app.run(host=host, port=port, debug=debug)
