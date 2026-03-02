---
name: goplaces
description: "Search for places and businesses using Google Places API"
command: "${command}"
args:
  - name: command
    description: "curl command for Google Places API"
    required: true
tags: [places, google, maps, search, api]
timeout: 15
---

# Go Places Skill

Search for places and businesses using the Google Places API via curl. Find restaurants, shops, landmarks, and more with detailed information.

Requires `$GOOGLE_PLACES_API_KEY` environment variable.

## Text Search

```bash
# Search for places by text query
curl -s "https://maps.googleapis.com/maps/api/place/textsearch/json?query=pizza+near+zurich&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for place in data['results'][:5]:
    rating = place.get('rating', 'N/A')
    print(f'{place[\"name\"]} ({rating}⭐) - {place[\"formatted_address\"]}')
"

# Search with location bias
curl -s "https://maps.googleapis.com/maps/api/place/textsearch/json?query=coffee+shop&location=47.3769,8.5417&radius=1000&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for place in data['results'][:5]:
    print(f'{place[\"name\"]} - {place.get(\"formatted_address\", \"\")}')
"
```

## Nearby Search

```bash
# Find nearby restaurants
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=500&type=restaurant&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for place in data['results'][:5]:
    rating = place.get('rating', 'N/A')
    status = place.get('business_status', 'UNKNOWN')
    print(f'{place[\"name\"]} ({rating}⭐) [{status}]')
"

# Find nearby with keyword
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=1000&keyword=sushi&key=$GOOGLE_PLACES_API_KEY"

# Find open-now places
curl -s "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=500&type=cafe&opennow=true&key=$GOOGLE_PLACES_API_KEY"
```

## Place Details

```bash
# Get detailed info about a place by place_id
curl -s "https://maps.googleapis.com/maps/api/place/details/json?place_id=ChIJN1t_tDeuEmsRUsoyG83frY4&fields=name,formatted_address,formatted_phone_number,rating,opening_hours,website,reviews&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)['result']
print(f'Name: {data[\"name\"]}')
print(f'Address: {data.get(\"formatted_address\", \"N/A\")}')
print(f'Phone: {data.get(\"formatted_phone_number\", \"N/A\")}')
print(f'Rating: {data.get(\"rating\", \"N/A\")}')
print(f'Website: {data.get(\"website\", \"N/A\")}')
"
```

## Autocomplete

```bash
# Place autocomplete for search suggestions
curl -s "https://maps.googleapis.com/maps/api/place/autocomplete/json?input=zurich+main+station&key=$GOOGLE_PLACES_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for pred in data['predictions']:
    print(f'{pred[\"description\"]} (place_id: {pred[\"place_id\"]})')
"
```

## Common Place Types

| Type | Description |
|------|-------------|
| `restaurant` | Restaurants |
| `cafe` | Coffee shops and cafes |
| `bar` | Bars and pubs |
| `hotel` | Hotels and lodging |
| `pharmacy` | Pharmacies |
| `hospital` | Hospitals |
| `gas_station` | Gas/petrol stations |
| `supermarket` | Grocery stores |
| `gym` | Fitness centers |
| `park` | Parks and recreation |

## Examples

**Find Italian restaurants near Zurich:**
```
command: "curl -s 'https://maps.googleapis.com/maps/api/place/textsearch/json?query=italian+restaurant+zurich&key=$GOOGLE_PLACES_API_KEY' | python3 -c \"import sys, json; [print(f'{p[\\\"name\\\"]} - {p.get(\\\"rating\\\", \\\"N/A\\\")}⭐') for p in json.load(sys.stdin)['results'][:5]]\""
```

**Find open cafes nearby:**
```
command: "curl -s 'https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=47.3769,8.5417&radius=500&type=cafe&opennow=true&key=$GOOGLE_PLACES_API_KEY' | python3 -c \"import sys, json; [print(p['name']) for p in json.load(sys.stdin)['results'][:5]]\""
```

**Get place details:**
```
command: "curl -s 'https://maps.googleapis.com/maps/api/place/details/json?place_id=PLACE_ID_HERE&fields=name,rating,formatted_phone_number,website&key=$GOOGLE_PLACES_API_KEY'"
```
