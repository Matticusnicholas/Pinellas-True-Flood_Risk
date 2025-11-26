"""
Pydantic models for data schemas used throughout the application
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class FloodEventType(str, Enum):
    """Types of flood events from NOAA Storm Events"""
    FLASH_FLOOD = "Flash Flood"
    FLOOD = "Flood"
    COASTAL_FLOOD = "Coastal Flood"
    STORM_SURGE = "Storm Surge/Tide"
    HEAVY_RAIN = "Heavy Rain"
    TROPICAL_STORM = "Tropical Storm"
    HURRICANE = "Hurricane"


class HurricaneCategory(int, Enum):
    """Saffir-Simpson Hurricane Scale"""
    TROPICAL_DEPRESSION = -1
    TROPICAL_STORM = 0
    CATEGORY_1 = 1
    CATEGORY_2 = 2
    CATEGORY_3 = 3
    CATEGORY_4 = 4
    CATEGORY_5 = 5


class RiskLevel(str, Enum):
    """Risk level categories"""
    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


# ============ Historical Flood Events ============

class FloodEvent(BaseModel):
    """A historical flood event from NOAA Storm Events Database"""
    event_id: str
    event_type: str
    begin_date: datetime
    end_date: Optional[datetime] = None
    begin_lat: Optional[float] = None
    begin_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    episode_narrative: Optional[str] = None
    event_narrative: Optional[str] = None
    deaths_direct: int = 0
    deaths_indirect: int = 0
    injuries_direct: int = 0
    injuries_indirect: int = 0
    damage_property: Optional[float] = None  # In dollars
    damage_crops: Optional[float] = None
    flood_cause: Optional[str] = None
    magnitude: Optional[float] = None
    magnitude_type: Optional[str] = None


class FloodEventSummary(BaseModel):
    """Summary statistics for flood events"""
    total_events: int
    events_by_type: dict[str, int]
    events_by_year: dict[int, int]
    total_property_damage: float
    total_deaths: int
    total_injuries: int
    avg_events_per_year: float


# ============ Hurricane Track Data ============

class HurricaneTrackPoint(BaseModel):
    """A single point in a hurricane's track"""
    timestamp: datetime
    lat: float
    lon: float
    max_wind_kt: Optional[float] = None
    min_pressure_mb: Optional[float] = None
    category: Optional[int] = None
    record_identifier: Optional[str] = None  # L=landfall, etc.


class Hurricane(BaseModel):
    """A hurricane record from HURDAT2/IBTrACS"""
    storm_id: str
    name: str
    year: int
    basin: str = "NA"  # North Atlantic
    track_points: List[HurricaneTrackPoint]
    max_category: int
    max_wind_kt: Optional[float] = None
    min_pressure_mb: Optional[float] = None
    landfall_florida: bool = False
    closest_approach_to_pinellas_km: Optional[float] = None
    affected_pinellas: bool = False


class HurricaneStatistics(BaseModel):
    """Statistics about hurricanes affecting the region"""
    total_storms_analyzed: int
    storms_within_radius: int
    direct_hits_pinellas: int
    near_misses: int  # Passed within 100km
    storms_by_category: dict[int, int]
    avg_storms_per_decade: float
    deflection_analysis: Optional[dict] = None


# ============ Elevation/Topography ============

class ElevationPoint(BaseModel):
    """Elevation at a specific point"""
    lat: float
    lon: float
    elevation_m: float
    elevation_ft: float
    data_source: str = "USGS 3DEP"


class ElevationGrid(BaseModel):
    """Grid of elevation data for an area"""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    resolution_m: float
    grid_data: List[List[float]]  # 2D array of elevations
    stats: dict


# ============ Property Data ============

class Property(BaseModel):
    """A property record from Pinellas County"""
    parcel_id: str
    address: str
    city: str
    zip_code: str
    lat: float
    lon: float
    elevation_m: Optional[float] = None
    fema_flood_zone: Optional[str] = None
    year_built: Optional[int] = None
    property_type: Optional[str] = None
    assessed_value: Optional[float] = None


class PropertyRiskAssessment(BaseModel):
    """Complete risk assessment for a property"""
    property: Property
    true_risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    fema_risk_level: Optional[RiskLevel] = None
    risk_components: dict[str, float]
    historical_events_nearby: int
    nearest_flood_event_km: Optional[float] = None
    storm_surge_exposure: float
    recommendations: List[str]


# ============ Atmospheric Analysis ============

class JetStreamPattern(BaseModel):
    """Jet stream pattern data"""
    date: datetime
    avg_position_lat: float
    avg_speed_ms: float
    pattern_type: str  # "blocking", "zonal", "meridional"


class AtmosphericAnalysis(BaseModel):
    """Analysis of atmospheric patterns that may protect Pinellas"""
    analysis_period_start: datetime
    analysis_period_end: datetime
    avg_jet_stream_position: float
    dominant_pattern: str
    gulf_thermal_gradient: Optional[float] = None
    wind_shear_index: Optional[float] = None
    protection_factor: float = Field(ge=0, le=1)  # 0=no protection, 1=full protection
    findings: List[str]


# ============ Risk Calculation ============

class FloodRiskFactors(BaseModel):
    """All factors contributing to flood risk"""
    historical_flood_score: float = Field(ge=0, le=100)
    hurricane_probability_score: float = Field(ge=0, le=100)
    elevation_risk_score: float = Field(ge=0, le=100)
    storm_surge_score: float = Field(ge=0, le=100)
    atmospheric_protection_factor: float = Field(ge=0, le=1)


class TrueFloodRisk(BaseModel):
    """The computed true flood risk for a location"""
    lat: float
    lon: float
    address: Optional[str] = None
    true_risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    fema_flood_zone: Optional[str] = None
    fema_comparison: Optional[str] = None  # "lower", "same", "higher"
    factors: FloodRiskFactors
    confidence: float = Field(ge=0, le=1)
    methodology_version: str = "1.0"
    computed_at: datetime


# ============ API Request/Response Models ============

class LocationQuery(BaseModel):
    """Query for a specific location"""
    lat: float = Field(ge=24, le=32)  # Florida latitude range
    lon: float = Field(ge=-88, le=-79)  # Florida longitude range


class AddressQuery(BaseModel):
    """Query by address"""
    address: str
    city: str = "St Petersburg"
    state: str = "FL"
    zip_code: Optional[str] = None


class RiskMapRequest(BaseModel):
    """Request for risk map data"""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    resolution: str = "medium"  # low, medium, high
