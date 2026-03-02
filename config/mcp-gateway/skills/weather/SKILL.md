---
name: weather
description: "Get weather forecasts using wttr.in"
command: "curl -s \"wttr.in/${location}?format=${format}\""
args:
  - name: location
    description: "City name, airport code, or coordinates (empty for auto-detect)"
    required: false
    default: ""
  - name: format
    description: "Output format: 1=one-line, 2=two-line, 3=three-line, 4=full, j1=JSON"
    required: false
    default: "3"
tags: [weather, utility, web]
timeout: 10
---

# Weather Skill

Get weather forecasts from [wttr.in](https://wttr.in), a console-oriented weather service.

## Overview

wttr.in is a free weather service that returns plain-text weather data. It supports multiple output formats, location types, and special weather pages. No API key is required.

## Format Options

| Format | Description |
|--------|-------------|
| `1` | One-line output: current conditions |
| `2` | Two-line output: current + today's forecast |
| `3` | Three-line output: current + today + tomorrow (default) |
| `4` | Full multi-day forecast with ASCII art |
| `v2` | Graphical output with wind/precipitation bars |
| `j1` | JSON format with structured weather data |

## Location Formats

| Type | Example | Description |
|------|---------|-------------|
| City name | `London` | City lookup |
| City + country | `London,UK` | Disambiguated city |
| Airport code | `ZRH` | IATA 3-letter code |
| Coordinates | `48.8566,2.3522` | Latitude,Longitude |
| Domain | `@github.com` | Geo-IP of the domain |
| Empty | *(none)* | Auto-detect from IP |

## Special Pages

| Query | Description |
|-------|-------------|
| `~Snowfall` | Snowfall forecast |
| `~Rainfall` | Rainfall forecast |
| `Moon` | Current moon phase |
| `Moon@2025-12-25` | Moon phase for a specific date |

## Examples

**Current weather (auto-detect location):**
```
location: ""
format: "3"
```

**Weather for a specific city:**
```
location: "Zurich"
format: "3"
```

**Full forecast with ASCII art:**
```
location: "Paris"
format: "4"
```

**JSON output for programmatic use:**
```
location: "Tokyo"
format: "j1"
```

**One-line summary:**
```
location: "New+York"
format: "1"
```
