#!/usr/bin/env python3
"""
Check for nearby CNCF Community Group chapters when a new chapter request is opened.
"""

import os
import re
import sys
import requests
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Distance threshold in kilometers
DISTANCE_THRESHOLD_KM = 100

# Open Community Groups JSON search API. The CNCF program migrated from
# community.cncf.io to ocgroups.dev; this endpoint returns groups (with
# coordinates) as JSON, replacing the old community.cncf.io HTML scrape.
# See https://github.com/cncf/open-community-groups (handler: /explore/groups/search).
CHAPTERS_API_URL = "https://ocgroups.dev/explore/groups/search"
CHAPTERS_COMMUNITY = "cncf"
# Max page size accepted by the API (MAX_PAGINATION_LIMIT in the server).
CHAPTERS_PAGE_SIZE = 100
# Safety cap on pages fetched, in case `total` is unreliable.
CHAPTERS_MAX_PAGES = 50

def extract_location_from_issue(issue_body):
    """
    Extract the city/location from the GitHub issue body.
    The location is in the field labeled "City or location name for your CNCG"
    """
    if not issue_body:
        return None

    # Pattern to match the location field in the issue template
    # Looking for "City or location name for your CNCG" section
    pattern = r'###\s*City or location name for your CNCG\s*\n\s*(.+?)(?:\n\n|\n###|$)'
    match = re.search(pattern, issue_body, re.IGNORECASE | re.DOTALL)

    if match:
        location = match.group(1).strip()
        # Remove common prefixes like "e.g." or "Cloud Native"
        location = re.sub(r'^(e\.g\.\s*|Cloud Native\s*)', '', location, flags=re.IGNORECASE)
        return location.strip()

    # Fallback: try to find any location-like text after the first heading
    lines = issue_body.split('\n')
    for i, line in enumerate(lines):
        if 'City or location name' in line or 'location name for your CNCG' in line.lower():
            # Get the next non-empty line
            for j in range(i + 1, len(lines)):
                potential_location = lines[j].strip()
                if potential_location and not potential_location.startswith('#'):
                    potential_location = re.sub(r'^(e\.g\.\s*|Cloud Native\s*)', '', potential_location, flags=re.IGNORECASE)
                    return potential_location.strip()

    return None

def get_coordinates(location):
    """
    Get latitude and longitude for a given location using geopy.
    """
    try:
        geolocator = Nominatim(user_agent="cncf-chapter-checker/1.0")
        location_data = geolocator.geocode(location, timeout=10)

        if location_data:
            return (location_data.latitude, location_data.longitude)
        return None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"Geocoding error for '{location}': {e}", file=sys.stderr)
        return None

def normalize_chapter(group):
    """
    Map an Open Community Groups search result to the chapter shape used
    downstream: {name, location, geocode_hint, url, latitude, longitude}.
    Returns None if the group has no usable name or URL.
    """
    name = group.get('name', '')
    city = group.get('city')
    country = group.get('country_name')
    latitude = group.get('latitude')
    longitude = group.get('longitude')

    # Human-readable location used as context in the posted comment.
    if city and country:
        location = f"{city}, {country}"
    else:
        location = city or country or ''

    # String to geocode only when the API does not supply coordinates. Prefer
    # the physical location so it resolves cleanly; fall back to the group name.
    geocode_hint = location or name

    # Public group URL: /{community}/group/{slug}. The admin-managed
    # "pretty" slug takes precedence when present (matches public_slug() server-side).
    community = group.get('community_name') or CHAPTERS_COMMUNITY
    slug = group.get('slug_pretty') or group.get('slug')
    url = f"https://ocgroups.dev/{community}/group/{slug}" if slug else ''

    if not (name and url):
        return None

    return {
        'name': name,
        'location': location,
        'geocode_hint': geocode_hint,
        'url': url,
        'latitude': latitude,
        'longitude': longitude,
    }


def fetch_existing_chapters():
    """
    Fetch the list of existing CNCF chapters from the Open Community Groups
    JSON search API (ocgroups.dev), paging through all results.
    """
    chapters = []

    try:
        for page in range(CHAPTERS_MAX_PAGES):
            offset = page * CHAPTERS_PAGE_SIZE
            # community is an array filter; serde_qs expects community[0]=...
            params = [
                ('community[0]', CHAPTERS_COMMUNITY),
                ('limit', CHAPTERS_PAGE_SIZE),
                ('offset', offset),
                ('sort_by', 'name'),
            ]
            response = requests.get(CHAPTERS_API_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()

            groups = payload.get('groups', [])
            for group in groups:
                chapter = normalize_chapter(group)
                if chapter:
                    chapters.append(chapter)

            total = payload.get('total', 0)
            # Stop once we've fetched everything (or the page came back short).
            if len(groups) < CHAPTERS_PAGE_SIZE or offset + CHAPTERS_PAGE_SIZE >= total:
                break

        if not chapters:
            print("No chapters returned by the API", file=sys.stderr)
            return get_fallback_chapters()

        print(f"Successfully fetched {len(chapters)} chapters from the API", file=sys.stderr)
        return chapters

    except requests.RequestException as e:
        print(f"Error fetching chapters: {e}", file=sys.stderr)
        return get_fallback_chapters()
    except (ValueError, KeyError) as e:
        print(f"Error parsing chapters data: {e}", file=sys.stderr)
        return get_fallback_chapters()

def get_fallback_chapters():
    """
    Fallback list of major CNCF chapters in case the API call fails.
    Coordinates are embedded so this path does not depend on geocoding.
    This should be updated periodically.
    """
    return [
        {'name': 'San Francisco, USA', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 37.7749, 'longitude': -122.4194},
        {'name': 'New York City, USA', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 40.7128, 'longitude': -74.0060},
        {'name': 'London, UK', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 51.5074, 'longitude': -0.1278},
        {'name': 'Berlin, Germany', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 52.5200, 'longitude': 13.4050},
        {'name': 'Amsterdam, Netherlands', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 52.3676, 'longitude': 4.9041},
        {'name': 'Paris, France', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 48.8566, 'longitude': 2.3522},
        {'name': 'Tokyo, Japan', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 35.6762, 'longitude': 139.6503},
        {'name': 'Bangalore, India', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 12.9716, 'longitude': 77.5946},
        {'name': 'Sydney, Australia', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': -33.8688, 'longitude': 151.2093},
        {'name': 'Singapore', 'url': 'https://ocgroups.dev/explore?community[0]=cncf&entity=groups', 'latitude': 1.3521, 'longitude': 103.8198},
    ]

def find_nearby_chapters(requested_location, existing_chapters):
    """
    Find chapters that are within DISTANCE_THRESHOLD_KM of the requested location.
    """
    requested_coords = get_coordinates(requested_location)

    if not requested_coords:
        print(f"Could not geocode requested location: {requested_location}", file=sys.stderr)
        return []

    print(f"Requested location coordinates: {requested_coords}", file=sys.stderr)

    nearby_chapters = []

    for chapter in existing_chapters:
        # Use coordinates from the chapter data if available, otherwise geocode
        if chapter.get('latitude') is not None and chapter.get('longitude') is not None:
            chapter_coords = (chapter['latitude'], chapter['longitude'])
        else:
            chapter_coords = get_coordinates(chapter.get('geocode_hint') or chapter['name'])

        if chapter_coords:
            distance = geodesic(requested_coords, chapter_coords).kilometers
            print(f"Distance to {chapter['name']}: {distance:.2f} km", file=sys.stderr)

            if distance < DISTANCE_THRESHOLD_KM:
                nearby_chapters.append({
                    'name': chapter['name'],
                    'location': chapter.get('location', ''),
                    'url': chapter['url'],
                    'distance_km': round(distance, 2)
                })

    # Sort by distance
    nearby_chapters.sort(key=lambda x: x['distance_km'])

    return nearby_chapters

def format_output(nearby_chapters):
    """
    Format the nearby chapters as markdown for GitHub comment.
    """
    if not nearby_chapters:
        return ""

    output = []
    for chapter in nearby_chapters:
        location = f" — {chapter['location']}" if chapter.get('location') else ""
        output.append(
            f"- **{chapter['name']}**{location} (~{chapter['distance_km']} km away) - {chapter['url']}"
        )

    return '\n'.join(output)

def set_github_output(name, value):
    """
    Set a GitHub Actions output variable.

    Uses the heredoc form required by the $GITHUB_OUTPUT file for multi-line
    values; the older `%0A` percent-encoding is NOT decoded from that file and
    would surface literal `%0A` in the posted comment.
    """
    github_output = os.getenv('GITHUB_OUTPUT')
    if github_output:
        # A delimiter that cannot appear in the value (per Actions guidance).
        delimiter = 'EOF_NEARBY_CHAPTERS'
        with open(github_output, 'a') as f:
            f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"{name}={value}")

def main():
    """
    Main function to check for nearby chapters.
    """
    issue_body = os.getenv('ISSUE_BODY', '')
    issue_title = os.getenv('ISSUE_TITLE', '')

    print(f"Issue title: {issue_title}", file=sys.stderr)

    # Extract location from issue
    requested_location = extract_location_from_issue(issue_body)

    if not requested_location:
        print("Could not extract location from issue body", file=sys.stderr)
        set_github_output('nearby_chapters', '')
        return

    print(f"Requested location: {requested_location}", file=sys.stderr)

    # Fetch existing chapters
    existing_chapters = fetch_existing_chapters()
    print(f"Found {len(existing_chapters)} existing chapters", file=sys.stderr)

    # Find nearby chapters
    nearby_chapters = find_nearby_chapters(requested_location, existing_chapters)

    if nearby_chapters:
        print(f"Found {len(nearby_chapters)} nearby chapters", file=sys.stderr)
        output = format_output(nearby_chapters)
        set_github_output('nearby_chapters', output)
    else:
        print("No nearby chapters found", file=sys.stderr)
        set_github_output('nearby_chapters', '')

if __name__ == '__main__':
    main()
