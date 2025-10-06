#!/usr/bin/env python3
"""
Check for nearby CNCF Community Group chapters when a new chapter request is opened.
"""

import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Distance threshold in kilometers
DISTANCE_THRESHOLD_KM = 100

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

def fetch_existing_chapters():
    """
    Fetch the list of existing chapters from community.cncf.io/chapters/
    """
    url = "https://community.cncf.io/chapters/"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all chapter links - they typically follow a pattern
        chapters = []

        # Look for links that point to chapter pages
        # Pattern: /cloud-native-{city}/ or /{city}/
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text(strip=True)

            # Filter for chapter links
            if href and '/community.cncf.io/' in href or (href and href.startswith('/') and text):
                # Extract chapter name from text or URL
                chapter_name = text if text else href

                # Skip navigation links, headers, etc.
                if chapter_name and len(chapter_name) > 3 and not chapter_name.lower() in ['chapters', 'events', 'home', 'about']:
                    # Clean up chapter name
                    chapter_name = re.sub(r'^Cloud Native\s*', '', chapter_name, flags=re.IGNORECASE)
                    chapter_name = chapter_name.strip()

                    if chapter_name and chapter_name not in chapters:
                        chapters.append({
                            'name': chapter_name,
                            'url': href if href.startswith('http') else f"https://community.cncf.io{href}"
                        })

        # Alternative approach: look for specific HTML structure
        # This may need to be adjusted based on the actual page structure
        chapter_cards = soup.find_all(['div', 'article', 'section'], class_=re.compile(r'chapter|community|group', re.I))

        for card in chapter_cards:
            name_elem = card.find(['h2', 'h3', 'h4', 'a'])
            if name_elem:
                chapter_name = name_elem.get_text(strip=True)
                chapter_name = re.sub(r'^Cloud Native\s*', '', chapter_name, flags=re.IGNORECASE)

                link_elem = card.find('a', href=True)
                chapter_url = link_elem.get('href') if link_elem else ''

                if chapter_url and not chapter_url.startswith('http'):
                    chapter_url = f"https://community.cncf.io{chapter_url}"

                if chapter_name and chapter_name not in [c['name'] for c in chapters]:
                    chapters.append({
                        'name': chapter_name,
                        'url': chapter_url
                    })

        return chapters if chapters else get_fallback_chapters()

    except requests.RequestException as e:
        print(f"Error fetching chapters: {e}", file=sys.stderr)
        return get_fallback_chapters()

def get_fallback_chapters():
    """
    Fallback list of major CNCF chapters in case web scraping fails.
    This should be updated periodically.
    """
    return [
        {'name': 'San Francisco', 'url': 'https://community.cncf.io/cloud-native-san-francisco/'},
        {'name': 'New York City', 'url': 'https://community.cncf.io/cloud-native-new-york-city/'},
        {'name': 'London', 'url': 'https://community.cncf.io/cloud-native-london/'},
        {'name': 'Berlin', 'url': 'https://community.cncf.io/cloud-native-berlin/'},
        {'name': 'Amsterdam', 'url': 'https://community.cncf.io/cloud-native-amsterdam/'},
        {'name': 'Paris', 'url': 'https://community.cncf.io/cloud-native-paris/'},
        {'name': 'Tokyo', 'url': 'https://community.cncf.io/cloud-native-community-japan/'},
        {'name': 'Bangalore', 'url': 'https://community.cncf.io/cloud-native-bangalore/'},
        {'name': 'Sydney', 'url': 'https://community.cncf.io/cloud-native-sydney/'},
        {'name': 'Singapore', 'url': 'https://community.cncf.io/cloud-native-singapore/'},
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
        chapter_coords = get_coordinates(chapter['name'])

        if chapter_coords:
            distance = geodesic(requested_coords, chapter_coords).kilometers
            print(f"Distance to {chapter['name']}: {distance:.2f} km", file=sys.stderr)

            if distance < DISTANCE_THRESHOLD_KM:
                nearby_chapters.append({
                    'name': chapter['name'],
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
        output.append(f"- **{chapter['name']}** (~{chapter['distance_km']} km away) - {chapter['url']}")

    return '\n'.join(output)

def set_github_output(name, value):
    """
    Set GitHub Actions output variable.
    """
    github_output = os.getenv('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            # Escape newlines and special characters for multiline output
            value_escaped = value.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D')
            f.write(f"{name}={value_escaped}\n")
    else:
        print(f"::set-output name={name}::{value}")

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
