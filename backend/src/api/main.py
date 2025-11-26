"""
FastAPI Application for Pinellas True Flood Risk

REST API endpoints for:
- Location-based flood risk calculation
- Property lookup and assessment
- Historical data queries
- Risk map generation
"""
import logging
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..config import PINELLAS_BOUNDS, ANALYSIS_CONFIG
from ..models.schemas import (
    TrueFloodRisk, PropertyRiskAssessment, RiskLevel,
    LocationQuery, AddressQuery, FloodEventSummary, HurricaneStatistics
)
from ..risk_engine.calculator import TrueFloodRiskCalculator
from ..data_collection.noaa_storm_events import NOAAStormEventsCollector
from ..data_collection.hurricane_tracks import HurricaneTrackCollector
from ..data_collection.elevation_data import ElevationDataCollector
from ..data_collection.property_data import PropertyDataCollector
from ..data_collection.atmospheric_data import AtmosphericDataCollector

logger = logging.getLogger(__name__)

# Global calculator instance (loaded with data at startup)
risk_calculator: Optional[TrueFloodRiskCalculator] = None
elevation_collector: Optional[ElevationDataCollector] = None
property_collector: Optional[PropertyDataCollector] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data and initialize calculators on startup."""
    global risk_calculator, elevation_collector, property_collector

    logger.info("Initializing Pinellas Flood Risk API...")

    # Initialize collectors
    elevation_collector = ElevationDataCollector()
    property_collector = PropertyDataCollector()

    # For full initialization, uncomment to load historical data:
    # flood_collector = NOAAStormEventsCollector()
    # hurricane_collector = HurricaneTrackCollector()
    # atmospheric_collector = AtmosphericDataCollector()
    #
    # flood_events = flood_collector.collect_historical_floods()
    # hurricanes = hurricane_collector.collect_hurricane_data()
    # atmospheric = atmospheric_collector.generate_atmospheric_analysis()

    # Initialize calculator (without pre-loaded data for now)
    risk_calculator = TrueFloodRiskCalculator()

    logger.info("API initialized successfully")

    yield

    # Cleanup
    logger.info("Shutting down API...")


app = FastAPI(
    title="Pinellas True Flood Risk API",
    description="""
    Calculate accurate flood risk for any location in Pinellas County, FL.

    This API provides:
    - **True Flood Risk Scores** based on 50 years of historical data
    - **Property-level risk assessments**
    - **Comparison with FEMA flood zones**
    - **Storm surge exposure analysis**
    - **Hurricane probability calculations**

    The True Flood Risk Score considers:
    - Historical flood events (30% weight)
    - Hurricane probability (25% weight)
    - Elevation (25% weight)
    - Storm surge exposure (15% weight)
    - Atmospheric patterns (5% weight)
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Request/Response Models ============

class RiskRequest(BaseModel):
    """Request for flood risk calculation."""
    lat: float = Field(..., ge=27.5, le=28.2, description="Latitude (Pinellas range)")
    lon: float = Field(..., ge=-82.9, le=-82.5, description="Longitude (Pinellas range)")
    elevation_m: Optional[float] = Field(None, description="Elevation in meters (auto-fetched if not provided)")
    address: Optional[str] = Field(None, description="Optional address for reference")
    include_details: bool = Field(True, description="Include detailed breakdown")


class RiskResponse(BaseModel):
    """Response with flood risk assessment."""
    success: bool
    risk: Optional[TrueFloodRisk]
    details: Optional[dict] = None
    error: Optional[str] = None


class AddressRiskRequest(BaseModel):
    """Request for address-based risk lookup."""
    address: str
    city: str = "St Petersburg"
    state: str = "FL"
    zip_code: Optional[str] = None


class MapGridRequest(BaseModel):
    """Request for risk map grid data."""
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None
    resolution: str = Field("medium", description="low, medium, or high")


class MapGridResponse(BaseModel):
    """Response with grid data for mapping."""
    success: bool
    grid_points: List[dict]
    bounds: dict
    resolution_deg: float
    total_points: int


# ============ API Endpoints ============

@app.get("/")
async def root():
    """API root - basic info."""
    return {
        "name": "Pinellas True Flood Risk API",
        "version": "1.0.0",
        "status": "operational",
        "coverage": "Pinellas County, FL",
        "endpoints": {
            "risk_by_location": "/api/v1/risk/location",
            "risk_by_address": "/api/v1/risk/address",
            "elevation": "/api/v1/elevation",
            "fema_zone": "/api/v1/fema-zone",
            "map_grid": "/api/v1/map/grid",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "calculator_ready": risk_calculator is not None,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/risk/location", response_model=RiskResponse)
async def calculate_risk_by_location(request: RiskRequest):
    """
    Calculate flood risk for a specific lat/lon location.

    Returns comprehensive risk assessment including:
    - True Flood Risk Score (0-100)
    - Risk level category
    - Component scores breakdown
    - FEMA zone comparison (if available)
    - Recommendations
    """
    global risk_calculator, elevation_collector, property_collector

    if not risk_calculator:
        raise HTTPException(status_code=503, detail="Risk calculator not initialized")

    try:
        # Get elevation if not provided
        elevation_m = request.elevation_m
        if elevation_m is None and elevation_collector:
            point = elevation_collector.get_elevation_point(request.lat, request.lon)
            if point:
                elevation_m = point.elevation_m

        # Get FEMA zone
        fema_zone = None
        if property_collector:
            fema_zone = property_collector.get_fema_flood_zone(request.lat, request.lon)

        # Calculate risk
        risk = risk_calculator.calculate_risk(
            lat=request.lat,
            lon=request.lon,
            elevation_m=elevation_m,
            address=request.address,
            fema_flood_zone=fema_zone
        )

        # Build response
        details = None
        if request.include_details:
            # Get storm surge details
            surge_details = risk_calculator.surge_analyzer.calculate_surge_risk(
                request.lat, request.lon, elevation_m
            )

            details = {
                'elevation_m': elevation_m,
                'elevation_ft': elevation_m * 3.28084 if elevation_m else None,
                'fema_zone': fema_zone,
                'fema_interpretation': property_collector.interpret_fema_zone(fema_zone) if fema_zone and property_collector else None,
                'storm_surge': surge_details,
                'weights_used': risk_calculator.weights,
            }

        return RiskResponse(
            success=True,
            risk=risk,
            details=details
        )

    except Exception as e:
        logger.error(f"Error calculating risk: {e}", exc_info=True)
        return RiskResponse(
            success=False,
            risk=None,
            error=str(e)
        )


@app.post("/api/v1/risk/address")
async def calculate_risk_by_address(request: AddressRiskRequest):
    """
    Calculate flood risk for a street address.

    The address is geocoded to coordinates, then risk is calculated.
    """
    global property_collector

    if not property_collector:
        raise HTTPException(status_code=503, detail="Property collector not initialized")

    try:
        # Geocode address
        coords = property_collector.geocode_address(
            request.address,
            request.city,
            request.state,
            request.zip_code
        )

        if not coords:
            raise HTTPException(
                status_code=404,
                detail=f"Could not geocode address: {request.address}, {request.city}"
            )

        lat, lon = coords

        # Use location endpoint logic
        risk_request = RiskRequest(
            lat=lat,
            lon=lon,
            address=f"{request.address}, {request.city}, {request.state}",
            include_details=True
        )

        return await calculate_risk_by_location(risk_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing address: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/elevation")
async def get_elevation(
    lat: float = Query(..., ge=27.5, le=28.2),
    lon: float = Query(..., ge=-82.9, le=-82.5)
):
    """
    Get elevation for a specific location.

    Returns elevation in meters and feet from USGS 3DEP data.
    """
    global elevation_collector

    if not elevation_collector:
        raise HTTPException(status_code=503, detail="Elevation service not initialized")

    point = elevation_collector.get_elevation_point(lat, lon)

    if not point:
        raise HTTPException(status_code=404, detail="Could not fetch elevation for this location")

    return {
        "lat": lat,
        "lon": lon,
        "elevation_m": point.elevation_m,
        "elevation_ft": point.elevation_ft,
        "source": point.data_source
    }


@app.get("/api/v1/fema-zone")
async def get_fema_zone(
    lat: float = Query(..., ge=27.5, le=28.2),
    lon: float = Query(..., ge=-82.9, le=-82.5)
):
    """
    Get FEMA flood zone for a location.

    Returns the official FEMA flood zone designation and interpretation.
    """
    global property_collector

    if not property_collector:
        raise HTTPException(status_code=503, detail="Property service not initialized")

    zone = property_collector.get_fema_flood_zone(lat, lon)

    if not zone:
        return {
            "lat": lat,
            "lon": lon,
            "fema_zone": None,
            "note": "Could not determine FEMA flood zone for this location"
        }

    interpretation = property_collector.interpret_fema_zone(zone)

    return {
        "lat": lat,
        "lon": lon,
        "fema_zone": zone,
        "interpretation": interpretation
    }


@app.post("/api/v1/map/grid", response_model=MapGridResponse)
async def get_risk_map_grid(request: MapGridRequest):
    """
    Generate a grid of risk scores for map visualization.

    Resolution options:
    - low: ~5km grid (fast)
    - medium: ~1km grid (balanced)
    - high: ~500m grid (detailed, slower)
    """
    global risk_calculator

    if not risk_calculator:
        raise HTTPException(status_code=503, detail="Risk calculator not initialized")

    # Set resolution
    resolution_map = {
        'low': 0.05,      # ~5km
        'medium': 0.01,   # ~1km
        'high': 0.005,    # ~500m
    }
    resolution_deg = resolution_map.get(request.resolution, 0.01)

    # Use bounds from request or defaults
    min_lat = request.min_lat or PINELLAS_BOUNDS.min_lat
    max_lat = request.max_lat or PINELLAS_BOUNDS.max_lat
    min_lon = request.min_lon or PINELLAS_BOUNDS.min_lon
    max_lon = request.max_lon or PINELLAS_BOUNDS.max_lon

    try:
        grid_points = risk_calculator.generate_risk_grid(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            resolution_deg=resolution_deg
        )

        return MapGridResponse(
            success=True,
            grid_points=grid_points,
            bounds={
                'min_lat': min_lat,
                'max_lat': max_lat,
                'min_lon': min_lon,
                'max_lon': max_lon,
            },
            resolution_deg=resolution_deg,
            total_points=len(grid_points)
        )

    except Exception as e:
        logger.error(f"Error generating grid: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats/floods")
async def get_flood_statistics():
    """
    Get summary statistics for historical flood events in Pinellas County.
    """
    # This would return pre-computed statistics
    return {
        "coverage": "Pinellas County, FL",
        "period": f"{ANALYSIS_CONFIG.start_year}-{ANALYSIS_CONFIG.end_year}",
        "note": "Full statistics available after data collection is run",
        "methodology": {
            "source": "NOAA Storm Events Database",
            "event_types": [
                "Flash Flood", "Flood", "Coastal Flood",
                "Storm Surge/Tide", "Heavy Rain",
                "Tropical Storm", "Hurricane"
            ]
        }
    }


@app.get("/api/v1/stats/hurricanes")
async def get_hurricane_statistics():
    """
    Get statistics about hurricanes affecting the Pinellas region.
    """
    return {
        "coverage": f"{ANALYSIS_CONFIG.hurricane_analysis_radius_km}km radius around Pinellas",
        "period": f"{ANALYSIS_CONFIG.start_year}-{ANALYSIS_CONFIG.end_year}",
        "note": "Full statistics available after data collection is run",
        "methodology": {
            "source": "NOAA HURDAT2 / IBTrACS",
            "analysis": "Track-based closest approach calculation"
        }
    }


@app.get("/api/v1/methodology")
async def get_methodology():
    """
    Get detailed methodology information for the risk calculations.
    """
    return {
        "version": "1.0",
        "true_flood_risk_score": {
            "description": "Composite score 0-100 representing actual flood risk",
            "components": {
                "historical_flood_events": {
                    "weight": ANALYSIS_CONFIG.weight_historical_floods,
                    "source": "NOAA Storm Events Database",
                    "methodology": "Density and severity of events within 15km radius"
                },
                "hurricane_probability": {
                    "weight": ANALYSIS_CONFIG.weight_hurricane_probability,
                    "source": "NOAA HURDAT2",
                    "methodology": "Historical storm tracks and closest approach analysis"
                },
                "elevation_risk": {
                    "weight": ANALYSIS_CONFIG.weight_elevation_risk,
                    "source": "USGS 3DEP",
                    "methodology": "Risk increases exponentially below 5m elevation"
                },
                "storm_surge": {
                    "weight": ANALYSIS_CONFIG.weight_storm_surge,
                    "source": "Tampa Bay geographic analysis",
                    "methodology": "Bay funneling and amplification factors"
                },
                "atmospheric_protection": {
                    "weight": ANALYSIS_CONFIG.weight_atmospheric_protection,
                    "source": "NOAA NCEP Reanalysis (historical)",
                    "methodology": "Steering pattern analysis and deflection rates"
                }
            }
        },
        "risk_levels": {
            "very_low": "0-20",
            "low": "21-40",
            "moderate": "41-60",
            "high": "61-80",
            "very_high": "81-100"
        },
        "elevation_thresholds": {
            "very_high_risk_below_m": ANALYSIS_CONFIG.elevation_very_high_risk,
            "high_risk_below_m": ANALYSIS_CONFIG.elevation_high_risk,
            "moderate_risk_below_m": ANALYSIS_CONFIG.elevation_moderate_risk,
            "low_risk_below_m": ANALYSIS_CONFIG.elevation_low_risk
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
