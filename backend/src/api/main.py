"""
FastAPI Application for Pinellas True Flood Risk

REST API that auto-initializes on startup:
- First run: Fetches 50 years of historical data from NOAA (takes a few minutes)
- Subsequent runs: Loads from cache (fast startup)

All data is persisted to backend/data/processed/ for reuse.
"""
import logging
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..config import PINELLAS_BOUNDS, ANALYSIS_CONFIG
from ..models.schemas import TrueFloodRisk, RiskLevel
from ..risk_engine.calculator import TrueFloodRiskCalculator
from ..data_collection.data_manager import get_data_manager, ensure_data_initialized, DataStatus
from ..data_collection.elevation_data import ElevationDataCollector
from ..data_collection.property_data import PropertyDataCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
risk_calculator: Optional[TrueFloodRiskCalculator] = None
elevation_collector: Optional[ElevationDataCollector] = None
property_collector: Optional[PropertyDataCollector] = None
data_status: Optional[DataStatus] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-initialize data and calculator on startup."""
    global risk_calculator, elevation_collector, property_collector, data_status

    logger.info("=" * 60)
    logger.info("PINELLAS TRUE FLOOD RISK API")
    logger.info("=" * 60)

    # Auto-initialize data (fetches on first run, loads from cache after)
    data_manager = get_data_manager()
    data_status = ensure_data_initialized()

    # Initialize collectors
    elevation_collector = ElevationDataCollector()
    property_collector = PropertyDataCollector()

    # Initialize risk calculator with historical data
    risk_calculator = TrueFloodRiskCalculator(
        flood_events=data_manager.flood_events,
        hurricanes=data_manager.hurricanes,
        atmospheric_analysis=data_manager.atmospheric
    )

    logger.info("=" * 60)
    logger.info("API READY")
    logger.info(f"  Flood events: {len(data_manager.flood_events)}")
    logger.info(f"  Hurricanes: {len(data_manager.hurricanes)}")
    logger.info(f"  Atmospheric: {'Ready' if data_manager.atmospheric else 'N/A'}")
    logger.info("=" * 60)

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Pinellas True Flood Risk API",
    description="Auto-initializing flood risk API with 50 years of historical data",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Models ============

class RiskRequest(BaseModel):
    lat: float = Field(..., ge=27.5, le=28.2)
    lon: float = Field(..., ge=-82.9, le=-82.5)
    elevation_m: Optional[float] = None
    address: Optional[str] = None
    include_details: bool = True


class RiskResponse(BaseModel):
    success: bool
    risk: Optional[TrueFloodRisk] = None
    details: Optional[dict] = None
    error: Optional[str] = None


class AddressRiskRequest(BaseModel):
    address: str
    city: str = "St Petersburg"
    state: str = "FL"
    zip_code: Optional[str] = None


# ============ Endpoints ============

@app.get("/")
async def root():
    return {
        "name": "Pinellas True Flood Risk API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "risk": "/api/v1/risk/location",
            "address": "/api/v1/risk/address",
            "status": "/api/v1/status",
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "ready": risk_calculator is not None}


@app.get("/api/v1/status")
async def status():
    """Get system status including data initialization state."""
    dm = get_data_manager()
    return {
        "initialized": dm.is_initialized(),
        "flood_events": len(dm.flood_events),
        "hurricanes": len(dm.hurricanes),
        "atmospheric": dm.atmospheric is not None,
        "last_updated": data_status.last_updated.isoformat() if data_status and data_status.last_updated else None
    }


@app.post("/api/v1/data/refresh")
async def refresh_data():
    """Force refresh all cached data."""
    global risk_calculator, data_status

    dm = get_data_manager()
    data_status = dm.initialize(force_refresh=True)

    risk_calculator = TrueFloodRiskCalculator(
        flood_events=dm.flood_events,
        hurricanes=dm.hurricanes,
        atmospheric_analysis=dm.atmospheric
    )

    return {"success": True, "flood_events": len(dm.flood_events), "hurricanes": len(dm.hurricanes)}


@app.post("/api/v1/risk/location", response_model=RiskResponse)
async def calculate_risk_by_location(request: RiskRequest):
    """Calculate flood risk for a lat/lon location."""
    if not risk_calculator:
        raise HTTPException(503, "Not initialized yet")

    try:
        elevation_m = request.elevation_m
        if elevation_m is None and elevation_collector:
            point = elevation_collector.get_elevation_point(request.lat, request.lon)
            if point:
                elevation_m = point.elevation_m

        fema_zone = None
        if property_collector:
            fema_zone = property_collector.get_fema_flood_zone(request.lat, request.lon)

        risk = risk_calculator.calculate_risk(
            lat=request.lat,
            lon=request.lon,
            elevation_m=elevation_m,
            address=request.address,
            fema_flood_zone=fema_zone
        )

        details = None
        if request.include_details:
            surge = risk_calculator.surge_analyzer.calculate_surge_risk(request.lat, request.lon, elevation_m)
            details = {
                'elevation_m': elevation_m,
                'elevation_ft': elevation_m * 3.28084 if elevation_m else None,
                'fema_zone': fema_zone,
                'fema_interpretation': property_collector.interpret_fema_zone(fema_zone) if fema_zone else None,
                'storm_surge': surge,
            }

        return RiskResponse(success=True, risk=risk, details=details)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return RiskResponse(success=False, error=str(e))


@app.post("/api/v1/risk/address")
async def calculate_risk_by_address(request: AddressRiskRequest):
    """Calculate flood risk for a street address."""
    if not property_collector:
        raise HTTPException(503, "Not initialized")

    coords = property_collector.geocode_address(request.address, request.city, request.state, request.zip_code)
    if not coords:
        raise HTTPException(404, f"Could not find: {request.address}, {request.city}")

    lat, lon = coords
    return await calculate_risk_by_location(RiskRequest(
        lat=lat, lon=lon,
        address=f"{request.address}, {request.city}, {request.state}"
    ))


@app.get("/api/v1/elevation")
async def get_elevation(lat: float = Query(..., ge=27.5, le=28.2), lon: float = Query(..., ge=-82.9, le=-82.5)):
    if not elevation_collector:
        raise HTTPException(503, "Not initialized")
    point = elevation_collector.get_elevation_point(lat, lon)
    if not point:
        raise HTTPException(404, "Could not fetch elevation")
    return {"lat": lat, "lon": lon, "elevation_m": point.elevation_m, "elevation_ft": point.elevation_ft}


@app.get("/api/v1/fema-zone")
async def get_fema_zone(lat: float = Query(..., ge=27.5, le=28.2), lon: float = Query(..., ge=-82.9, le=-82.5)):
    if not property_collector:
        raise HTTPException(503, "Not initialized")
    zone = property_collector.get_fema_flood_zone(lat, lon)
    return {"lat": lat, "lon": lon, "fema_zone": zone, "interpretation": property_collector.interpret_fema_zone(zone) if zone else None}


@app.get("/api/v1/stats/floods")
async def flood_stats():
    dm = get_data_manager()
    events = dm.flood_events
    if not events:
        return {"message": "No data", "count": 0}

    by_type = {}
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

    return {"total": len(events), "by_type": by_type}


@app.get("/api/v1/stats/hurricanes")
async def hurricane_stats():
    dm = get_data_manager()
    hurricanes = dm.hurricanes
    if not hurricanes:
        return {"message": "No data", "count": 0}

    near = [h for h in hurricanes if h.closest_approach_to_pinellas_km and h.closest_approach_to_pinellas_km < 200]
    return {"total": len(hurricanes), "near_pinellas": len(near), "direct_hits": len([h for h in near if h.closest_approach_to_pinellas_km < 50])}


@app.get("/api/v1/methodology")
async def methodology():
    return {
        "weights": {
            "historical_floods": ANALYSIS_CONFIG.weight_historical_floods,
            "hurricane_probability": ANALYSIS_CONFIG.weight_hurricane_probability,
            "elevation_risk": ANALYSIS_CONFIG.weight_elevation_risk,
            "storm_surge": ANALYSIS_CONFIG.weight_storm_surge,
            "atmospheric": ANALYSIS_CONFIG.weight_atmospheric_protection,
        },
        "risk_levels": {"very_low": "0-20", "low": "21-40", "moderate": "41-60", "high": "61-80", "very_high": "81-100"}
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
