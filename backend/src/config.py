"""
Configuration settings for Pinellas Flood Risk Assessment Tool
"""
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Base paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"

# Ensure directories exist
for dir_path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


@dataclass
class PinellasCountyBounds:
    """Geographic bounds for Pinellas County, FL"""
    # Bounding box (approximate)
    min_lat: float = 27.5706
    max_lat: float = 28.1739
    min_lon: float = -82.8473
    max_lon: float = -82.5353

    # County center (approximately St. Petersburg)
    center_lat: float = 27.7676
    center_lon: float = -82.6403

    # Tampa Bay entry point (relevant for storm surge)
    tampa_bay_mouth_lat: float = 27.5833
    tampa_bay_mouth_lon: float = -82.7333

    # FIPS code for Pinellas County
    state_fips: str = "12"  # Florida
    county_fips: str = "103"  # Pinellas

    @property
    def fips(self) -> str:
        return f"{self.state_fips}{self.county_fips}"


@dataclass
class DataSourceURLs:
    """URLs for data sources"""
    # NOAA Storm Events Database (CSV bulk download)
    noaa_storm_events_base: str = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"

    # NOAA HURDAT2 (Atlantic Hurricane Database)
    hurdat2_atlantic: str = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2023-051124.txt"

    # IBTrACS (International Best Track Archive) - alternative hurricane data
    ibtracs_csv: str = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r00/access/csv/ibtracs.NA.list.v04r00.csv"

    # USGS 3DEP Elevation (REST API)
    usgs_elevation_api: str = "https://epqs.nationalmap.gov/v1/json"

    # FEMA National Flood Hazard Layer (ArcGIS)
    fema_nfhl_base: str = "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer"

    # NOAA NCEP/NCAR Reanalysis (for jet stream data)
    ncep_reanalysis_base: str = "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis"

    # Pinellas County Property Appraiser
    pinellas_pa_gis: str = "https://egis.pinellascounty.org/arcgis/rest/services"


@dataclass
class AnalysisConfig:
    """Configuration for analysis parameters"""
    # Historical analysis period (years)
    historical_years: int = 50
    start_year: int = 1974
    end_year: int = 2024

    # Hurricane analysis radius from county center (km)
    hurricane_analysis_radius_km: float = 200.0

    # Elevation grid resolution (meters)
    elevation_grid_resolution_m: float = 30.0

    # Risk score weights (must sum to 1.0)
    weight_historical_floods: float = 0.30
    weight_hurricane_probability: float = 0.25
    weight_elevation_risk: float = 0.25
    weight_storm_surge: float = 0.15
    weight_atmospheric_protection: float = 0.05

    # Elevation thresholds for risk (meters above sea level)
    elevation_very_high_risk: float = 2.0   # Below 2m = very high risk
    elevation_high_risk: float = 5.0        # 2-5m = high risk
    elevation_moderate_risk: float = 10.0   # 5-10m = moderate risk
    elevation_low_risk: float = 20.0        # 10-20m = low risk
    # Above 20m = very low risk


# Singleton instances
PINELLAS_BOUNDS = PinellasCountyBounds()
DATA_URLS = DataSourceURLs()
ANALYSIS_CONFIG = AnalysisConfig()


# Environment variable overrides
def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with optional default"""
    return os.environ.get(key, default)


# API Keys (if needed for premium services)
CENSUS_API_KEY = get_env("CENSUS_API_KEY")
MAPBOX_TOKEN = get_env("MAPBOX_TOKEN")
