const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');

// Parse issue body to extract location information
function parseIssueBody(issueBody) {
  const lines = issueBody.split('\n');
  let location = '';
  let country = '';

  // Look for the city/location name field
  const locationIndex = lines.findIndex(line =>
    line.includes('City or location name for your CNCG')
  );

  if (locationIndex !== -1 && locationIndex + 2 < lines.length) {
    location = lines[locationIndex + 2].trim();
  }

  // Look for the country field
  const countryIndex = lines.findIndex(line =>
    line.includes('What country do you want to start your community group in?')
  );

  if (countryIndex !== -1 && countryIndex + 2 < lines.length) {
    country = lines[countryIndex + 2].trim();
  }

  return { location, country };
}

// Fetch all chapters from CNCF community page
async function fetchExistingChapters() {
  try {
    const response = await axios.get('https://community.cncf.io/chapters/');
    const $ = cheerio.load(response.data);

    const chapters = [];

    // Parse chapter information from the page
    // The chapters are in anchor tags with class 'gtmChapterCard'
    $('a.gtmChapterCard').each((i, element) => {
      const chapterName = $(element).find('.card-title').text().trim();

      // Extract location from chapter name (typically "Cloud Native CityName" or just "CityName")
      const locationMatch = chapterName.replace('Cloud Native', '').trim();

      if (locationMatch) {
        chapters.push({
          name: chapterName,
          location: locationMatch,
          url: $(element).attr('href')
        });
      }
    });

    return chapters;
  } catch (error) {
    console.error('Error fetching chapters:', error.message);
    return [];
  }
}

// Simple distance calculation based on location similarity
function findNearbyChapters(requestedLocation, requestedCountry, existingChapters) {
  const nearbyChapters = [];
  const locationLower = requestedLocation.toLowerCase();
  const countryLower = requestedCountry.toLowerCase();

  for (const chapter of existingChapters) {
    const chapterLocationLower = chapter.location.toLowerCase();

    // Check if the chapter is in the same country or has similar location name
    if (chapterLocationLower.includes(countryLower) ||
        chapterLocationLower.includes(locationLower) ||
        locationLower.includes(chapterLocationLower)) {

      // Check for exact or close matches
      const isSameCity = chapterLocationLower.includes(locationLower) ||
                         locationLower.includes(chapterLocationLower);
      const isSameCountry = chapterLocationLower.includes(countryLower);

      nearbyChapters.push({
        ...chapter,
        matchType: isSameCity ? 'same_city' : (isSameCountry ? 'same_country' : 'similar')
      });
    }
  }

  return nearbyChapters;
}

// Format nearby chapters for GitHub comment
function formatNearbyChapters(nearbyChapters) {
  if (nearbyChapters.length === 0) {
    return '';
  }

  let formatted = '';

  // Group by match type
  const sameCityChapters = nearbyChapters.filter(c => c.matchType === 'same_city');
  const sameCountryChapters = nearbyChapters.filter(c => c.matchType === 'same_country');
  const similarChapters = nearbyChapters.filter(c => c.matchType === 'similar');

  if (sameCityChapters.length > 0) {
    formatted += '### ⚠️ Chapters in the Same City:\n\n';
    sameCityChapters.forEach(chapter => {
      formatted += `- [${chapter.name}](https://community.cncf.io${chapter.url})\n`;
    });
    formatted += '\n';
  }

  if (sameCountryChapters.length > 0) {
    formatted += '### 🌍 Chapters in the Same Country:\n\n';
    sameCountryChapters.forEach(chapter => {
      formatted += `- [${chapter.name}](https://community.cncf.io${chapter.url})\n`;
    });
    formatted += '\n';
  }

  if (similarChapters.length > 0) {
    formatted += '### 📌 Other Potentially Related Chapters:\n\n';
    similarChapters.forEach(chapter => {
      formatted += `- [${chapter.name}](https://community.cncf.io${chapter.url})\n`;
    });
    formatted += '\n';
  }

  return formatted;
}

// Main execution
async function main() {
  const issueBody = process.env.ISSUE_BODY || '';

  if (!issueBody) {
    console.log('No issue body found');
    process.exit(0);
  }

  // Parse the issue body
  const { location, country } = parseIssueBody(issueBody);

  if (!location || !country) {
    console.log('Could not extract location information from issue');
    process.exit(0);
  }

  console.log(`Requested location: ${location}, ${country}`);

  // Fetch existing chapters
  const existingChapters = await fetchExistingChapters();
  console.log(`Found ${existingChapters.length} existing chapters`);

  // Find nearby chapters
  const nearbyChapters = findNearbyChapters(location, country, existingChapters);
  console.log(`Found ${nearbyChapters.length} nearby chapters`);

  // Format output for GitHub Actions
  const formattedChapters = formatNearbyChapters(nearbyChapters);

  // Set GitHub Actions outputs
  if (formattedChapters) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT || '', `nearby_chapters<<EOF\n${formattedChapters}EOF\n`);
    fs.appendFileSync(process.env.GITHUB_OUTPUT || '', `requested_location=${location}, ${country}\n`);
  }
}

main().catch(error => {
  console.error('Error:', error);
  process.exit(1);
});
