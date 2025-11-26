"""
FastAPI Application for Pinellas True Flood Risk

Starts instantly with no data fetching.
Historical data can be downloaded via /api/v1/data/download endpoint.
"""
import os
import logging
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..config import PINELLAS_BOUNDS, ANALYSIS_CONFIG
from ..models.schemas import TrueFloodRisk
from ..risk_engine.calculator import TrueFloodRiskCalculator
from ..data_collection.elevation_data import ElevationDataCollector
from ..data_collection.property_data import PropertyDataCollector
from ..data_collection.address_database import get_address_database

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global instances
risk_calculator: Optional[TrueFloodRiskCalculator] = None
elevation_collector: Optional[ElevationDataCollector] = None
property_collector: Optional[PropertyDataCollector] = None
data_download_status = {"downloading": False, "progress": "", "complete": False}
address_download_status = {"downloading": False, "progress": "", "complete": False, "count": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fast startup - no data fetching."""
    global risk_calculator, elevation_collector, property_collector

    logger.info("=" * 60)
    logger.info("PINELLAS TRUE FLOOD RISK API - STARTING")
    logger.info("=" * 60)

    # Initialize collectors (no network calls)
    elevation_collector = ElevationDataCollector()
    property_collector = PropertyDataCollector()

    # Check if we have cached data
    from ..data_collection.data_manager import get_data_manager
    dm = get_data_manager()

    if dm.is_initialized():
        logger.info("Loading cached historical data...")
        dm._load_all_from_cache()
        risk_calculator = TrueFloodRiskCalculator(
            flood_events=dm.flood_events,
            hurricanes=dm.hurricanes,
            atmospheric_analysis=dm.atmospheric
        )
        logger.info(f"  Flood events: {len(dm.flood_events)}")
        logger.info(f"  Hurricanes: {len(dm.hurricanes)}")
    else:
        # Start with empty calculator (still works, just no historical data)
        logger.info("No cached data found - starting with base calculations")
        logger.info("Visit /api/v1/data/download to fetch historical data")
        risk_calculator = TrueFloodRiskCalculator()

    logger.info("=" * 60)
    logger.info("API READY")
    logger.info("=" * 60)

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Pinellas True Flood Risk API",
    description="Flood risk API - starts instantly, historical data can be downloaded separately",
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
        "has_historical_data": data_download_status["complete"],
        "endpoints": {
            "risk": "/api/v1/risk/location",
            "address": "/api/v1/risk/address",
            "download_data": "/api/v1/data/download",
            "status": "/api/v1/status",
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "ready": True}


@app.get("/api/v1/status")
async def status():
    """Get system status."""
    from ..data_collection.data_manager import get_data_manager
    dm = get_data_manager()

    return {
        "api_ready": True,
        "has_historical_data": dm.is_initialized(),
        "flood_events": len(dm.flood_events) if dm._flood_events else 0,
        "hurricanes": len(dm.hurricanes) if dm._hurricanes else 0,
        "data_download": data_download_status
    }


def _download_data_background():
    """Background task to download historical data."""
    global risk_calculator, data_download_status

    try:
        data_download_status["downloading"] = True
        data_download_status["progress"] = "Starting download..."

        from ..data_collection.data_manager import get_data_manager
        dm = get_data_manager()

        # Download with progress updates
        data_download_status["progress"] = "Downloading flood events from NOAA..."
        dm._fetch_flood_events()

        data_download_status["progress"] = "Downloading hurricane data..."
        dm._fetch_hurricanes()

        data_download_status["progress"] = "Generating atmospheric analysis..."
        dm._generate_atmospheric()

        # Save status
        from ..data_collection.data_manager import DataStatus
        status = DataStatus(
            flood_events_ready=True,
            flood_events_count=len(dm._flood_events or []),
            hurricanes_ready=True,
            hurricanes_count=len(dm._hurricanes or []),
            atmospheric_ready=True,
            last_updated=datetime.now(),
            is_demo_data=False
        )
        dm.save_status(status)

        # Update calculator
        risk_calculator = TrueFloodRiskCalculator(
            flood_events=dm.flood_events,
            hurricanes=dm.hurricanes,
            atmospheric_analysis=dm.atmospheric
        )

        data_download_status["downloading"] = False
        data_download_status["complete"] = True
        data_download_status["progress"] = f"Complete! {len(dm.flood_events)} flood events, {len(dm.hurricanes)} hurricanes"

    except Exception as e:
        logger.error(f"Download failed: {e}")
        data_download_status["downloading"] = False
        data_download_status["progress"] = f"Error: {str(e)}"


@app.post("/api/v1/data/download")
async def download_data(background_tasks: BackgroundTasks):
    """Start downloading historical data in background."""
    if data_download_status["downloading"]:
        return {"message": "Download already in progress", "status": data_download_status}

    background_tasks.add_task(_download_data_background)
    return {"message": "Download started in background", "status": data_download_status}


@app.get("/api/v1/data/download/status")
async def download_status():
    """Check data download progress."""
    return data_download_status


@app.post("/api/v1/risk/location", response_model=RiskResponse)
async def calculate_risk_by_location(request: RiskRequest):
    """Calculate flood risk for a lat/lon location."""
    if not risk_calculator:
        raise HTTPException(503, "Not initialized")

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
    from ..data_collection.data_manager import get_data_manager
    dm = get_data_manager()
    events = dm.flood_events
    if not events:
        return {"message": "No data - use /api/v1/data/download to fetch", "count": 0}

    by_type = {}
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

    return {"total": len(events), "by_type": by_type}


@app.get("/api/v1/stats/hurricanes")
async def hurricane_stats():
    from ..data_collection.data_manager import get_data_manager
    dm = get_data_manager()
    hurricanes = dm.hurricanes
    if not hurricanes:
        return {"message": "No data - use /api/v1/data/download to fetch", "count": 0}

    near = [h for h in hurricanes if h.closest_approach_to_pinellas_km and h.closest_approach_to_pinellas_km < 200]
    return {"total": len(hurricanes), "near_pinellas": len(near), "direct_hits": len([h for h in near if h.closest_approach_to_pinellas_km < 50])}


@app.get("/api/v1/analysis/atmospheric")
async def atmospheric_analysis():
    """
    Get the atmospheric analysis including jet stream patterns,
    steering flow, and the 'protection factor' hypothesis.

    This investigates why hurricanes seem to avoid Pinellas County.
    """
    from ..data_collection.data_manager import get_data_manager
    dm = get_data_manager()

    atmospheric = dm.atmospheric
    if not atmospheric:
        return {
            "message": "Atmospheric analysis not available. Use /api/v1/data/download to generate.",
            "hypothesis_summary": {
                "question": "Why do hurricanes seem to avoid Pinellas County?",
                "status": "Analysis not yet run - download historical data first"
            }
        }

    # Also get hurricane stats for context
    hurricanes = dm.hurricanes
    total_hurricanes = len(hurricanes) if hurricanes else 0
    near_misses = len([h for h in (hurricanes or []) if h.closest_approach_to_pinellas_km and 50 < h.closest_approach_to_pinellas_km < 200])
    direct_hits = len([h for h in (hurricanes or []) if h.closest_approach_to_pinellas_km and h.closest_approach_to_pinellas_km < 50])

    return {
        "hypothesis": {
            "question": "Why do hurricanes seem to avoid Pinellas County?",
            "investigated_factors": [
                "Jet stream position and patterns",
                "Bermuda High steering influence",
                "Tampa Bay thermal effects",
                "Gulf current patterns",
                "Geographic channeling effects"
            ]
        },
        "analysis_period": {
            "start": atmospheric.analysis_period_start.isoformat(),
            "end": atmospheric.analysis_period_end.isoformat()
        },
        "jet_stream_analysis": {
            "average_position": f"{atmospheric.avg_jet_stream_position}°N latitude",
            "dominant_pattern": atmospheric.dominant_pattern,
            "interpretation": "The subtropical jet stream typically positions at 28-32°N during hurricane season, creating steering currents that guide storms away from direct Tampa Bay approach."
        },
        "steering_flow_findings": {
            "primary_factor": "Bermuda High",
            "effect": "The Bermuda High's western extension creates southerly steering flow that guides Gulf hurricanes toward the Florida Panhandle or Big Bend region rather than Tampa Bay.",
            "significance": "This is the PRIMARY reason for the observed hurricane avoidance pattern."
        },
        "tampa_bay_local_effects": {
            "thermal_effects": "Tampa Bay creates a localized heat island effect generating weak onshore/offshore breezes, but these are TOO WEAK to alter major hurricane tracks.",
            "gulf_thermal_gradient": f"{atmospheric.gulf_thermal_gradient}°C cooler near coast (insufficient to weaken hurricanes)",
            "wind_shear": f"{atmospheric.wind_shear_index} knots typical (moderate)",
            "conclusion": "Local bay effects are MINIMAL - large-scale atmospheric patterns dominate hurricane steering."
        },
        "protection_factor": {
            "value": atmospheric.protection_factor,
            "interpretation": f"{atmospheric.protection_factor:.0%} estimated 'protection' based on historical deflection patterns",
            "caveat": "This is a SPECULATIVE metric for analysis purposes, not a guarantee of safety."
        },
        "key_findings": atmospheric.findings,
        "hurricane_statistics": {
            "total_analyzed": total_hurricanes,
            "near_misses_50_200km": near_misses,
            "direct_hits_under_50km": direct_hits,
            "hit_rate": f"{(direct_hits / total_hurricanes * 100):.1f}%" if total_hurricanes > 0 else "N/A"
        },
        "conclusion": {
            "primary_cause": "Large-scale atmospheric steering patterns (Bermuda High)",
            "secondary_cause": "Jet stream positioning during hurricane season",
            "local_effects": "Minimal - Tampa Bay thermals cannot deflect major storms",
            "warning": "Past patterns do NOT guarantee future protection. Tampa Bay remains highly vulnerable to the 'right' storm track."
        }
    }


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


# ============ Address Autocomplete ============

@app.get("/api/v1/addresses/autocomplete")
async def autocomplete_address(q: str = Query(..., min_length=2, description="Search query")):
    """
    Autocomplete address search.

    Returns matching addresses from Pinellas County database with exact coordinates.
    Download the address database first via /api/v1/addresses/download
    """
    addr_db = get_address_database()

    if not addr_db.is_loaded():
        return {
            "results": [],
            "message": "Address database not loaded. Use /api/v1/addresses/download to fetch addresses."
        }

    results = addr_db.autocomplete(q, limit=10)
    return {"results": results, "count": len(results)}


@app.get("/api/v1/addresses/lookup")
async def lookup_address(address: str = Query(..., description="Full address to look up")):
    """
    Look up exact address and get coordinates.

    Use autocomplete to find the correct address format first.
    """
    addr_db = get_address_database()

    if not addr_db.is_loaded():
        raise HTTPException(400, "Address database not loaded. Use /api/v1/addresses/download first.")

    result = addr_db.get_address(address)

    if not result:
        raise HTTPException(404, f"Address not found: {address}")

    return result


def _download_addresses_background():
    """Background task to download address database."""
    global address_download_status

    try:
        address_download_status["downloading"] = True
        address_download_status["progress"] = "Downloading Pinellas County addresses..."

        addr_db = get_address_database()
        count = addr_db.download_addresses(limit=100000)

        address_download_status["downloading"] = False
        address_download_status["complete"] = True
        address_download_status["count"] = count
        address_download_status["progress"] = f"Complete! {count} addresses loaded"

    except Exception as e:
        logger.error(f"Address download failed: {e}")
        address_download_status["downloading"] = False
        address_download_status["progress"] = f"Error: {str(e)}"


@app.post("/api/v1/addresses/download")
async def download_addresses(background_tasks: BackgroundTasks):
    """
    Download Pinellas County address database for autocomplete.

    This downloads ~50,000+ addresses from Pinellas County's open data.
    Runs in background - check status at /api/v1/addresses/download/status
    """
    if address_download_status["downloading"]:
        return {"message": "Download already in progress", "status": address_download_status}

    background_tasks.add_task(_download_addresses_background)
    return {"message": "Address download started in background", "status": address_download_status}


@app.get("/api/v1/addresses/download/status")
async def address_download_progress():
    """Check address database download progress."""
    addr_db = get_address_database()
    return {
        **address_download_status,
        "addresses_loaded": len(addr_db.addresses) if addr_db.is_loaded() else 0
    }


@app.post("/api/v1/risk/address-lookup")
async def calculate_risk_by_address_lookup(address: str = Query(..., description="Full address from autocomplete")):
    """
    Calculate flood risk using address from the database (most accurate).

    Use /api/v1/addresses/autocomplete to find the correct address first.
    """
    addr_db = get_address_database()

    if not addr_db.is_loaded():
        raise HTTPException(400, "Address database not loaded. Use /api/v1/addresses/download first.")

    addr_data = addr_db.get_address(address)

    if not addr_data:
        raise HTTPException(404, f"Address not found in database: {address}")

    return await calculate_risk_by_location(RiskRequest(
        lat=addr_data['lat'],
        lon=addr_data['lon'],
        address=addr_data['full_address']
    ))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
