"""
Historical Flood Event Analyzer

Analyzes historical flood events to calculate location-specific
flood risk scores based on past occurrences.
"""
import math
import logging
from datetime import datetime
from typing import List, Optional, Dict, Tuple

from ..models.schemas import FloodEvent, FloodEventSummary
from ..config import PINELLAS_BOUNDS, ANALYSIS_CONFIG

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two points."""
    R = 6371  # Earth radius in km
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


class FloodHistoryAnalyzer:
    """
    Analyzes historical flood events to generate location-based risk scores.

    Methodology:
    1. Calculate density of flood events near a location
    2. Weight recent events more heavily than older ones
    3. Factor in severity (damage, casualties)
    4. Consider event type (coastal flood vs flash flood)
    """

    # Weight factors for event types
    EVENT_TYPE_WEIGHTS = {
        "Storm Surge/Tide": 1.5,      # Most dangerous for coastal flooding
        "Hurricane": 1.4,
        "Tropical Storm": 1.2,
        "Coastal Flood": 1.3,
        "Flash Flood": 1.0,
        "Flood": 0.9,
        "Heavy Rain": 0.7,
        "Tropical Depression": 0.8,
    }

    # Decay factor for older events (half-life in years)
    TIME_DECAY_HALFLIFE = 15.0

    # Maximum radius to consider events (km)
    MAX_RADIUS_KM = 15.0

    def __init__(self, events: List[FloodEvent]):
        """
        Initialize analyzer with historical flood events.

        Args:
            events: List of historical flood events for the region
        """
        self.events = events
        self.events_with_coords = [
            e for e in events
            if e.begin_lat is not None and e.begin_lon is not None
        ]
        self.bounds = PINELLAS_BOUNDS
        self._build_spatial_index()

    def _build_spatial_index(self):
        """Build simple spatial index for faster queries."""
        # Grid-based index (0.1 degree cells ≈ 11km)
        self.grid = {}
        grid_size = 0.1

        for event in self.events_with_coords:
            grid_key = (
                int(event.begin_lat / grid_size),
                int(event.begin_lon / grid_size)
            )
            if grid_key not in self.grid:
                self.grid[grid_key] = []
            self.grid[grid_key].append(event)

    def _get_nearby_events(
        self,
        lat: float,
        lon: float,
        radius_km: float
    ) -> List[Tuple[FloodEvent, float]]:
        """
        Get events within radius of a point.

        Returns list of (event, distance_km) tuples.
        """
        nearby = []
        grid_size = 0.1
        search_cells = int(radius_km / 11) + 1  # 11km per 0.1 degree

        center_grid = (int(lat / grid_size), int(lon / grid_size))

        for di in range(-search_cells, search_cells + 1):
            for dj in range(-search_cells, search_cells + 1):
                grid_key = (center_grid[0] + di, center_grid[1] + dj)
                if grid_key in self.grid:
                    for event in self.grid[grid_key]:
                        dist = haversine_distance(lat, lon, event.begin_lat, event.begin_lon)
                        if dist <= radius_km:
                            nearby.append((event, dist))

        return nearby

    def _calculate_time_weight(self, event_date: datetime) -> float:
        """
        Calculate time-decay weight for an event.

        More recent events are weighted more heavily.
        """
        now = datetime.now()
        years_ago = (now - event_date).days / 365.25

        # Exponential decay with half-life
        decay = 0.5 ** (years_ago / self.TIME_DECAY_HALFLIFE)

        return decay

    def _calculate_severity_weight(self, event: FloodEvent) -> float:
        """
        Calculate severity weight based on damage and casualties.
        """
        base_weight = 1.0

        # Property damage factor
        if event.damage_property:
            if event.damage_property > 10_000_000:
                base_weight += 0.5
            elif event.damage_property > 1_000_000:
                base_weight += 0.3
            elif event.damage_property > 100_000:
                base_weight += 0.1

        # Casualty factor
        total_deaths = event.deaths_direct + event.deaths_indirect
        total_injuries = event.injuries_direct + event.injuries_indirect

        if total_deaths > 0:
            base_weight += min(0.5, total_deaths * 0.1)
        if total_injuries > 0:
            base_weight += min(0.3, total_injuries * 0.05)

        return base_weight

    def calculate_location_score(
        self,
        lat: float,
        lon: float,
        radius_km: Optional[float] = None
    ) -> Dict:
        """
        Calculate historical flood risk score for a specific location.

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Search radius (default: MAX_RADIUS_KM)

        Returns:
            Dictionary with score and breakdown
        """
        radius_km = radius_km or self.MAX_RADIUS_KM

        # Get nearby events
        nearby_events = self._get_nearby_events(lat, lon, radius_km)

        if not nearby_events:
            return {
                'score': 0.0,
                'events_count': 0,
                'nearest_event_km': None,
                'breakdown': {},
                'nearby_events': []
            }

        # Calculate weighted score
        total_weight = 0.0
        type_breakdown = {}
        event_details = []

        for event, distance in nearby_events:
            # Distance weight (inverse square, capped)
            dist_weight = 1.0 / (1.0 + (distance / 2.0) ** 2)

            # Time weight
            time_weight = self._calculate_time_weight(event.begin_date)

            # Severity weight
            severity_weight = self._calculate_severity_weight(event)

            # Event type weight
            type_weight = self.EVENT_TYPE_WEIGHTS.get(event.event_type, 1.0)

            # Combined weight
            combined_weight = dist_weight * time_weight * severity_weight * type_weight

            total_weight += combined_weight

            # Track by type
            if event.event_type not in type_breakdown:
                type_breakdown[event.event_type] = 0.0
            type_breakdown[event.event_type] += combined_weight

            # Store event detail
            event_details.append({
                'event_id': event.event_id,
                'type': event.event_type,
                'date': event.begin_date.isoformat(),
                'distance_km': round(distance, 2),
                'weight': round(combined_weight, 3)
            })

        # Normalize score to 0-100
        # Calibrated so that average risk location scores around 50
        # High-risk areas with many severe events score 80+
        raw_score = total_weight * 10  # Scale factor

        # Apply sigmoid to bound between 0 and 100
        normalized_score = 100 / (1 + math.exp(-0.1 * (raw_score - 50)))

        # Find nearest event
        nearest_distance = min(d for _, d in nearby_events)

        return {
            'score': round(normalized_score, 1),
            'raw_score': round(raw_score, 2),
            'events_count': len(nearby_events),
            'nearest_event_km': round(nearest_distance, 2),
            'breakdown': {k: round(v, 2) for k, v in type_breakdown.items()},
            'nearby_events': sorted(event_details, key=lambda x: x['distance_km'])[:10]
        }

    def get_county_wide_analysis(self) -> Dict:
        """
        Generate county-wide flood history analysis.
        """
        summary = FloodEventSummary(
            total_events=len(self.events),
            events_by_type={},
            events_by_year={},
            total_property_damage=0.0,
            total_deaths=0,
            total_injuries=0,
            avg_events_per_year=0.0
        )

        # Calculate statistics
        for event in self.events:
            # By type
            etype = event.event_type
            summary.events_by_type[etype] = summary.events_by_type.get(etype, 0) + 1

            # By year
            year = event.begin_date.year
            summary.events_by_year[year] = summary.events_by_year.get(year, 0) + 1

            # Totals
            summary.total_property_damage += event.damage_property or 0
            summary.total_deaths += event.deaths_direct + event.deaths_indirect
            summary.total_injuries += event.injuries_direct + event.injuries_indirect

        # Average per year
        if summary.events_by_year:
            years_span = max(summary.events_by_year.keys()) - min(summary.events_by_year.keys()) + 1
            summary.avg_events_per_year = len(self.events) / years_span

        # Identify hotspots (areas with highest event density)
        hotspots = self._identify_hotspots()

        return {
            'summary': summary.model_dump(),
            'hotspots': hotspots,
            'analysis_period': {
                'start': ANALYSIS_CONFIG.start_year,
                'end': ANALYSIS_CONFIG.end_year
            }
        }

    def _identify_hotspots(self, grid_size_km: float = 2.0) -> List[Dict]:
        """Identify flood hotspot areas."""
        # Simple grid-based density analysis
        grid_counts = {}
        grid_size_deg = grid_size_km / 111.0  # Approximate km to degrees

        for event in self.events_with_coords:
            grid_key = (
                round(event.begin_lat / grid_size_deg) * grid_size_deg,
                round(event.begin_lon / grid_size_deg) * grid_size_deg
            )
            if grid_key not in grid_counts:
                grid_counts[grid_key] = {'count': 0, 'damage': 0.0}
            grid_counts[grid_key]['count'] += 1
            grid_counts[grid_key]['damage'] += event.damage_property or 0

        # Sort by count and return top hotspots
        sorted_cells = sorted(
            grid_counts.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )

        hotspots = []
        for (lat, lon), data in sorted_cells[:10]:
            hotspots.append({
                'center_lat': lat,
                'center_lon': lon,
                'event_count': data['count'],
                'total_damage': data['damage'],
                'radius_km': grid_size_km
            })

        return hotspots


# Convenience function
def analyze_flood_history(events: List[FloodEvent], lat: float, lon: float) -> Dict:
    """Quick flood history analysis for a location."""
    analyzer = FloodHistoryAnalyzer(events)
    return analyzer.calculate_location_score(lat, lon)
