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
from typing import List, Dict, Tuple, Optional


# Distance threshold in kilometers to consider chapters as "nearby"
DISTANCE_THRESHOLD_KM = 100


def extract_location_from_issue(issue_body: str) -> Optional[str]:
    """
    Extract the city/location from the GitHub issue body.

    Args:
        issue_body: The full body text of the GitHub issue

    Returns:
        The city/location name or None if not found
    """
    # Look for the "City or location name for your CNCG" field
    pattern = r'###\s*City or location name for your CNCG\s*\n\s*(.+?)(?:\n|$)'
    match = re.search(pattern, issue_body, re.IGNORECASE | re.MULTILINE)

    if match:
        location = match.group(1).strip()
        # Remove common prefixes like "Cloud Native" from the location
        location = re.sub(r'^Cloud Native\s+', '', location, flags=re.IGNORECASE)
        return location

    return None


def extract_country_from_issue(issue_body: str) -> Optional[str]:
    """
    Extract the country from the GitHub issue body.

    Args:
        issue_body: The full body text of the GitHub issue

    Returns:
        The country name or None if not found
    """
    # Look for the "What country do you want to start your community group in?" field
    pattern = r'###\s*What country do you want to start your community group in\?\s*\n\s*(.+?)(?:\n|$)'
    match = re.search(pattern, issue_body, re.IGNORECASE | re.MULTILINE)

    if match:
        return match.group(1).strip()

    return None


def get_coordinates(location: str, country: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """
    Get latitude and longitude coordinates for a location.

    Args:
        location: City or location name
        country: Optional country name to help with disambiguation

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    geolocator = Nominatim(user_agent="cncf-community-groups-checker")

    # Try with country first if provided
    if country:
        query = f"{location}, {country}"
    else:
        query = location

    try:
        location_data = geolocator.geocode(query, timeout=10)
        if location_data:
            return (location_data.latitude, location_data.longitude)
    except Exception as e:
        print(f"Error geocoding {query}: {e}", file=sys.stderr)

    # If country search failed, try without country
    if country:
        try:
            location_data = geolocator.geocode(location, timeout=10)
            if location_data:
                return (location_data.latitude, location_data.longitude)
        except Exception as e:
            print(f"Error geocoding {location}: {e}", file=sys.stderr)

    return None


def fetch_existing_chapters() -> List[Dict[str, any]]:
    """
    Fetch the list of existing CNCF chapters from community.cncf.io.

    Returns:
        List of chapter dictionaries with location and coordinate information
    """
    # The community.cncf.io website loads chapters dynamically
    # We'll need to scrape the page or use an API if available

    url = "https://community.cncf.io/api/chapter/"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        chapters = []
        for chapter in data.get('results', []):
            if chapter.get('status') == 'active':
                chapters.append({
                    'title': chapter.get('title', ''),
                    'slug': chapter.get('slug', ''),
                    'city': chapter.get('city', ''),
                    'region': chapter.get('region', ''),
                    'country': chapter.get('country', ''),
                    'latitude': chapter.get('latitude'),
                    'longitude': chapter.get('longitude'),
                    'url': f"https://community.cncf.io/{chapter.get('slug', '')}"
                })

        return chapters

    except Exception as e:
        print(f"Error fetching chapters from API: {e}", file=sys.stderr)
        print("Falling back to web scraping...", file=sys.stderr)
        return fetch_chapters_from_webpage()


def fetch_chapters_from_webpage() -> List[Dict[str, any]]:
    """
    Fallback method to fetch chapters by scraping the webpage.

    Returns:
        List of chapter dictionaries
    """
    url = "https://community.cncf.io/chapters/"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Extract chapter data from the page
        # This is a simplified version - the actual implementation would need
        # to parse the HTML or JSON embedded in the page
        chapters = []

        # Look for JSON data in the page
        json_pattern = r'var\s+chapters\s*=\s*(\[.*?\]);'
        match = re.search(json_pattern, response.text, re.DOTALL)

        if match:
            import json
            chapters_data = json.loads(match.group(1))
            for chapter in chapters_data:
                chapters.append({
                    'title': chapter.get('title', ''),
                    'city': chapter.get('city', ''),
                    'country': chapter.get('country', ''),
                    'latitude': chapter.get('lat'),
                    'longitude': chapter.get('lng'),
                    'url': chapter.get('url', '')
                })

        return chapters

    except Exception as e:
        print(f"Error fetching chapters from webpage: {e}", file=sys.stderr)
        return []


def find_nearby_chapters(
    requested_coords: Tuple[float, float],
    existing_chapters: List[Dict[str, any]],
    threshold_km: float = DISTANCE_THRESHOLD_KM
) -> List[Dict[str, any]]:
    """
    Find existing chapters within the distance threshold.

    Args:
        requested_coords: (latitude, longitude) of the requested location
        existing_chapters: List of existing chapter data
        threshold_km: Distance threshold in kilometers

    Returns:
        List of nearby chapters with distance information
    """
    nearby = []

    for chapter in existing_chapters:
        if chapter.get('latitude') and chapter.get('longitude'):
            chapter_coords = (chapter['latitude'], chapter['longitude'])
            distance = geodesic(requested_coords, chapter_coords).kilometers

            if distance <= threshold_km:
                chapter_with_distance = chapter.copy()
                chapter_with_distance['distance_km'] = round(distance, 1)
                nearby.append(chapter_with_distance)

    # Sort by distance
    nearby.sort(key=lambda x: x['distance_km'])

    return nearby


def format_nearby_chapters(nearby_chapters: List[Dict[str, any]]) -> str:
    """
    Format the list of nearby chapters for the GitHub comment.

    Args:
        nearby_chapters: List of nearby chapter dictionaries

    Returns:
        Formatted markdown string
    """
    if not nearby_chapters:
        return ""

    lines = []
    for chapter in nearby_chapters:
        city = chapter.get('city', '')
        region = chapter.get('region', '')
        country = chapter.get('country', '')
        distance = chapter.get('distance_km', 0)
        url = chapter.get('url', '')
        title = chapter.get('title', '')

        # Build location string
        location_parts = [p for p in [city, region, country] if p]
        location = ', '.join(location_parts)
        if not location:
            location = title

        lines.append(f"- **{title}** ({location}) - ~{distance} km away")
        if url:
            lines.append(f"  - {url}")

    return '\n'.join(lines)


def set_output(name: str, value: str):
    """Set GitHub Actions output."""
    github_output = os.getenv('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            # Escape newlines and special characters for multiline output
            value_escaped = value.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D')
            f.write(f"{name}={value_escaped}\n")
    else:
        print(f"::set-output name={name}::{value}")


def main():
    """Main function to check for nearby chapters."""

    # Get the issue body from environment variable
    issue_body = os.getenv('ISSUE_BODY', '')

    if not issue_body:
        print("Error: No issue body provided", file=sys.stderr)
        set_output('nearby_chapters', '')
        sys.exit(0)

    # Extract location from issue
    location = extract_location_from_issue(issue_body)
    country = extract_country_from_issue(issue_body)

    if not location:
        print("Could not find location in issue body", file=sys.stderr)
        set_output('nearby_chapters', '')
        sys.exit(0)

    print(f"Requested location: {location}", file=sys.stderr)
    if country:
        print(f"Requested country: {country}", file=sys.stderr)

    # Get coordinates for the requested location
    coords = get_coordinates(location, country)

    if not coords:
        print(f"Could not geocode location: {location}", file=sys.stderr)
        set_output('nearby_chapters', '')
        sys.exit(0)

    print(f"Coordinates: {coords}", file=sys.stderr)

    # Fetch existing chapters
    print("Fetching existing chapters...", file=sys.stderr)
    existing_chapters = fetch_existing_chapters()
    print(f"Found {len(existing_chapters)} existing chapters", file=sys.stderr)

    # Find nearby chapters
    nearby = find_nearby_chapters(coords, existing_chapters)

    if nearby:
        print(f"Found {len(nearby)} nearby chapters:", file=sys.stderr)
        for chapter in nearby:
            print(f"  - {chapter.get('title', 'Unknown')} ({chapter.get('distance_km', 0)} km)", file=sys.stderr)

        formatted_output = format_nearby_chapters(nearby)
        set_output('nearby_chapters', formatted_output)
    else:
        print("No nearby chapters found", file=sys.stderr)
        set_output('nearby_chapters', '')


if __name__ == '__main__':
    main()
