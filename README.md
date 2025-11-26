# Pinellas County True Flood Risk Assessment Tool

A data-driven flood risk assessment system that challenges traditional FEMA flood maps by combining:
- **50 years of historical flood events** from NOAA Storm Events Database
- **Hurricane track analysis** and Tampa Bay storm surge probability
- **High-resolution elevation data** from USGS for granular flood zone mapping
- **Property database integration** from Pinellas County Property Appraiser
- **Atmospheric pattern analysis** including jet streams and Gulf currents

## Hypothesis

Pinellas County may have natural meteorological protection from hurricanes due to:
- Jet stream patterns over the Tampa Bay/Gulf region
- Thermal currents from Tampa Bay flowing into the Gulf
- Wind shear phenomena that deflect storm tracks

This tool analyzes 50+ years of data to test this hypothesis and provide property-level flood risk scores.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Application                          │
│  (React + Mapbox/Leaflet for interactive property lookup)       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         REST API                                │
│              (FastAPI - /api/v1/*)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Risk Calculation Engine                       │
│  Combines all data sources into composite flood risk score      │
└─────────────────────────────────────────────────────────────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Historical  │ │  Hurricane   │ │  Elevation   │ │  Atmospheric │
│    Floods    │ │    Tracks    │ │    Data      │ │   Patterns   │
│   Analyzer   │ │   Analyzer   │ │   Processor  │ │   Analyzer   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ NOAA Storm   │ │ NOAA HURDAT2 │ │ USGS 3DEP    │ │ NCEP/NCAR    │
│ Events DB    │ │ Database     │ │ Elevation    │ │ Reanalysis   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

## Data Sources (All Free/Public)

| Data Type | Source | API/Access |
|-----------|--------|------------|
| Historical Floods | NOAA Storm Events | CSV/API |
| Hurricane Tracks | NOAA HURDAT2 | CSV (IBTrACS) |
| Elevation | USGS 3DEP | REST API |
| Property Data | Pinellas County PA | Public Records |
| Jet Streams | NOAA NCEP Reanalysis | OpenDAP |
| Current Flood Zones | FEMA NFHL | ArcGIS API |

## Installation

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m src.data_collection.fetch_all

# Frontend
cd frontend
npm install
npm run dev
```

## Usage

```bash
# Start the API server
cd backend
uvicorn src.api.main:app --reload

# Start the web app
cd frontend
npm run dev
```

## Risk Score Methodology

The True Flood Risk Score (0-100) is calculated as:

```
TrueRiskScore = (
    HistoricalFloodScore × 0.30 +
    HurricaneProbabilityScore × 0.25 +
    ElevationRiskScore × 0.25 +
    StormSurgeExposure × 0.15 +
    AtmosphericProtectionFactor × 0.05
)
```

Each component is normalized to 0-100 scale.
