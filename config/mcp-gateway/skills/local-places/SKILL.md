---
name: local-places
description: "Search for local businesses and places using Google Places API with location context"
command: "${command}"
args:
  - name: command
    description: "curl command for Google Places API with location parameters"
    required: true
tags: [places, google, local, search, api]
timeout: 15
---

# Local Places Skill

Search for local businesses and places using the Google Places API with user location context.

## Overview

Find nearby businesses, restaurants, services, and points of interest using the Google Places API with location-biased results. Builds on the Google Places API with emphasis on proximity-based search and location awareness. Requires `$GOOGLE_PLACES_API_KEY`.

## Nearby Search (Location-First)

```bash
# Find restaurants within 500m of a location
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=500&type=restaurant&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data['results'][:5]:
    r = p.get('rating', 'N/A')
    print(f'{p[\"name\"]} ({r}⭐) - {p.get(\"vicinity\", \"\")}')
"

# Find open pharmacies nearby
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=1000&type=pharmacy&opennow=true&key=$GOOGLE_PLACES_API_KEY"

# Find gas stations sorted by distance
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&rankby=distance&type=gas_station&key=$GOOGLE_PLACES_API_KEY"

# Find places with a keyword filter
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=2000&keyword=vegan&type=restaurant&key=$GOOGLE_PLACES_API_KEY"
```

## Text Search with Location Bias

```bash
# Search with location bias (results prioritize nearby)
curl -s "https://maps.googleapis.com/maps/api/place/textsearch/json?query=best+brunch&location=47.3769,8.5417&radius=2000&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data['results'][:5]:
    r = p.get('rating', 'N/A')
    total = p.get('user_ratings_total', 0)
    print(f'{p[\"name\"]} ({r}⭐, {total} reviews) - {p[\"formatted_address\"]}')
"

# Search for a specific service nearby
curl -s "https://maps.googleapis.com/maps/api/place/textsearch/json?query=dentist&location=47.3769,8.5417&radius=5000&key=$GOOGLE_PLACES_API_KEY"
```

## Place Details

```bash
# Get full details including hours and reviews
curl -s "https://maps.googleapis.com/maps/api/place/details/json?place_id=PLACE_ID&fields=name,formatted_address,formatted_phone_number,rating,opening_hours,website,reviews,price_level&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)['result']
print(f'Name: {d[\"name\"]}')
print(f'Address: {d.get(\"formatted_address\", \"N/A\")}')
print(f'Phone: {d.get(\"formatted_phone_number\", \"N/A\")}')
print(f'Rating: {d.get(\"rating\", \"N/A\")}')
print(f'Price: {\"$\" * d.get(\"price_level\", 0) or \"N/A\"}')
print(f'Website: {d.get(\"website\", \"N/A\")}')
hours = d.get('opening_hours', {}).get('weekday_text', [])
if hours:
    print('Hours:')
    for h in hours:
        print(f'  {h}')
"
```

## Place Photos

```bash
# Get photo reference from place details, then download
# Step 1: Get photo_reference from a place
curl -s "https://maps.googleapis.com/maps/api/place/details/json?place_id=PLACE_ID&fields=photos&key=$GOOGLE_PLACES_API_KEY"

# Step 2: Download photo using photo_reference
curl -sL -o place_photo.jpg "https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photo_reference=PHOTO_REFERENCE&key=$GOOGLE_PLACES_API_KEY"
```

## Common Place Types

| Type | Description |
|------|-------------|
| `restaurant` | Restaurants |
| `cafe` | Coffee shops |
| `bar` | Bars and pubs |
| `supermarket` | Grocery stores |
| `pharmacy` | Pharmacies |
| `hospital` | Hospitals |
| `gas_station` | Gas stations |
| `parking` | Parking lots |
| `atm` | ATMs |
| `bank` | Banks |
| `gym` | Fitness centers |
| `laundry` | Laundromats |
| `hair_care` | Hair salons |
| `dentist` | Dentists |
| `doctor` | Doctors |

## Examples

**Find nearby open restaurants:**
```
command: "curl -s 'https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=500&type=restaurant&opennow=true&key=$GOOGLE_PLACES_API_KEY' | python3 -c \"import sys, json; [print(f'{p[\\\"name\\\"]} ({p.get(\\\"rating\\\", \\\"N/A\\\")}⭐)') for p in json.load(sys.stdin)['results'][:5]]\""
```

**Search for best coffee near coordinates:**
```
command: "curl -s 'https://maps.googleapis.com/maps/api/place/textsearch/json?query=best+coffee&location=46.9480,7.4474&radius=1000&key=$GOOGLE_PLACES_API_KEY' | python3 -c \"import sys, json; [print(f'{p[\\\"name\\\"]} - {p[\\\"formatted_address\\\"]}') for p in json.load(sys.stdin)['results'][:5]]\""
```

**Get details for a specific place:**
```
command: "curl -s 'https://maps.googleapis.com/maps/api/place/details/json?place_id=PLACE_ID_HERE&fields=name,rating,formatted_phone_number,website,opening_hours&key=$GOOGLE_PLACES_API_KEY'"
```

## Notes

- `$GOOGLE_PLACES_API_KEY` must be set in the environment
- `radius` is in meters (max 50,000)
- Use `rankby=distance` instead of `radius` to sort by proximity (requires `type` or `keyword`)
- `opennow=true` filters to currently open businesses
- Location coordinates: latitude,longitude (e.g., 47.3769,8.5417 for Zurich)
- Results are limited to 20 per page — use `next_page_token` for pagination
