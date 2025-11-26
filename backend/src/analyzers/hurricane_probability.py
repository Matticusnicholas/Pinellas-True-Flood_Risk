"""
Hurricane Probability Analyzer

Calculates hurricane impact probability for locations in Pinellas County
based on historical hurricane tracks and climatological patterns.
"""
import math
import logging
from datetime import datetime
from typing import List, Optional, Dict, Tuple

from ..models.schemas import Hurricane, HurricaneStatistics
from ..config import PINELLAS_BOUNDS, ANALYSIS_CONFIG

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two points."""
    R = 6371
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


class HurricaneProbabilityAnalyzer:
    """
    Analyzes hurricane probability for Pinellas County locations.

    Methodology:
    1. Calculate historical frequency of hurricanes passing near a location
    2. Consider storm intensity (category)
    3. Factor in approach direction and Tampa Bay storm surge risk
    4. Apply climatological adjustments
    """

    # Risk distance thresholds (km)
    DIRECT_HIT_RADIUS = 50
    HIGH_IMPACT_RADIUS = 100
    MODERATE_IMPACT_RADIUS = 150
    LOW_IMPACT_RADIUS = 200

    # Category weights for impact calculation
    CATEGORY_WEIGHTS = {
        -1: 0.3,   # Tropical Depression
        0: 0.5,    # Tropical Storm
        1: 1.0,    # Category 1
        2: 1.5,    # Category 2
        3: 2.5,    # Category 3
        4: 4.0,    # Category 4
        5: 6.0,    # Category 5
    }

    def __init__(self, hurricanes: List[Hurricane]):
        """
        Initialize analyzer with historical hurricane data.

        Args:
            hurricanes: List of Hurricane objects with track data
        """
        self.hurricanes = hurricanes
        self.bounds = PINELLAS_BOUNDS

    def get_closest_approach(
        self,
        hurricane: Hurricane,
        lat: float,
        lon: float
    ) -> Tuple[float, Optional[int], Optional[datetime]]:
        """
        Get the closest approach of a hurricane to a location.

        Returns:
            Tuple of (distance_km, category_at_closest, timestamp)
        """
        min_distance = float('inf')
        category_at_closest = None
        timestamp_at_closest = None

        for point in hurricane.track_points:
            dist = haversine_distance(lat, lon, point.lat, point.lon)
            if dist < min_distance:
                min_distance = dist
                category_at_closest = point.category
                timestamp_at_closest = point.timestamp

        return (min_distance, category_at_closest, timestamp_at_closest)

    def calculate_location_probability(
        self,
        lat: float,
        lon: float,
        time_period_years: Optional[int] = None
    ) -> Dict:
        """
        Calculate hurricane impact probability for a specific location.

        Returns probability scores and historical analysis.
        """
        time_period_years = time_period_years or (ANALYSIS_CONFIG.end_year - ANALYSIS_CONFIG.start_year)

        # Track storms by impact level
        direct_hits = []      # < 50km
        high_impact = []      # 50-100km
        moderate_impact = []  # 100-150km
        low_impact = []       # 150-200km

        for hurricane in self.hurricanes:
            dist, category, timestamp = self.get_closest_approach(hurricane, lat, lon)

            storm_info = {
                'storm_id': hurricane.storm_id,
                'name': hurricane.name,
                'year': hurricane.year,
                'closest_km': round(dist, 1),
                'category_at_closest': category,
                'max_category': hurricane.max_category,
                'timestamp': timestamp.isoformat() if timestamp else None
            }

            if dist < self.DIRECT_HIT_RADIUS:
                direct_hits.append(storm_info)
            elif dist < self.HIGH_IMPACT_RADIUS:
                high_impact.append(storm_info)
            elif dist < self.MODERATE_IMPACT_RADIUS:
                moderate_impact.append(storm_info)
            elif dist < self.LOW_IMPACT_RADIUS:
                low_impact.append(storm_info)

        # Calculate annual probabilities
        direct_hit_annual = len(direct_hits) / time_period_years
        high_impact_annual = len(high_impact) / time_period_years
        moderate_impact_annual = len(moderate_impact) / time_period_years

        # Calculate weighted impact score
        # Considers both frequency and intensity
        weighted_score = 0.0

        for storm in direct_hits:
            cat_weight = self.CATEGORY_WEIGHTS.get(storm['category_at_closest'], 1.0)
            weighted_score += cat_weight * 3.0  # Triple weight for direct hits

        for storm in high_impact:
            cat_weight = self.CATEGORY_WEIGHTS.get(storm['category_at_closest'], 1.0)
            weighted_score += cat_weight * 2.0

        for storm in moderate_impact:
            cat_weight = self.CATEGORY_WEIGHTS.get(storm['category_at_closest'], 1.0)
            weighted_score += cat_weight * 1.0

        for storm in low_impact:
            cat_weight = self.CATEGORY_WEIGHTS.get(storm['category_at_closest'], 1.0)
            weighted_score += cat_weight * 0.5

        # Normalize to 0-100 score
        # Calibrated based on Gulf Coast climatology
        raw_score = weighted_score / time_period_years * 10
        normalized_score = min(100, raw_score * 5)

        # Calculate return periods
        direct_hit_return_years = (
            time_period_years / len(direct_hits) if direct_hits
            else float('inf')
        )
        any_impact_return_years = (
            time_period_years / (len(direct_hits) + len(high_impact)) if (direct_hits or high_impact)
            else float('inf')
        )

        return {
            'score': round(normalized_score, 1),
            'annual_probabilities': {
                'direct_hit': round(direct_hit_annual * 100, 2),  # Percentage
                'high_impact': round(high_impact_annual * 100, 2),
                'moderate_impact': round(moderate_impact_annual * 100, 2),
            },
            'return_periods_years': {
                'direct_hit': round(direct_hit_return_years, 1) if direct_hit_return_years != float('inf') else None,
                'any_significant_impact': round(any_impact_return_years, 1) if any_impact_return_years != float('inf') else None,
            },
            'historical_counts': {
                'direct_hits': len(direct_hits),
                'high_impact': len(high_impact),
                'moderate_impact': len(moderate_impact),
                'low_impact': len(low_impact),
            },
            'analysis_period_years': time_period_years,
            'notable_storms': {
                'direct_hits': direct_hits[:5],  # Top 5 most recent
                'high_impact': high_impact[:5],
            }
        }

    def analyze_storm_surge_risk(
        self,
        lat: float,
        lon: float
    ) -> Dict:
        """
        Analyze storm surge risk based on location relative to Tampa Bay.

        Storm surge is particularly dangerous for:
        - Areas on the east side of Pinellas (Tampa Bay shoreline)
        - Low-lying areas near the bay mouth
        - Areas where a storm tracking NE would push water into the bay
        """
        # Calculate distance to Tampa Bay mouth
        dist_to_bay_mouth = haversine_distance(
            lat, lon,
            self.bounds.tampa_bay_mouth_lat,
            self.bounds.tampa_bay_mouth_lon
        )

        # Check if location is on Tampa Bay side (east side of peninsula)
        # Tampa Bay is roughly east of -82.75
        is_bayside = lon > -82.75

        # Calculate distance to bay center
        bay_center_lat = 27.85
        bay_center_lon = -82.55
        dist_to_bay_center = haversine_distance(lat, lon, bay_center_lat, bay_center_lon)

        # Storm surge risk factors
        surge_risk_score = 0.0

        # Bayside locations have higher surge risk
        if is_bayside:
            surge_risk_score += 30

            # Closer to bay center = higher risk
            if dist_to_bay_center < 10:
                surge_risk_score += 25
            elif dist_to_bay_center < 20:
                surge_risk_score += 15
            elif dist_to_bay_center < 30:
                surge_risk_score += 5

        # Close to bay mouth = high risk from direct surge
        if dist_to_bay_mouth < 15:
            surge_risk_score += 30
        elif dist_to_bay_mouth < 30:
            surge_risk_score += 15

        # Gulf side still has surge risk, but different pattern
        if not is_bayside:
            surge_risk_score += 15  # Gulf side baseline

        # Normalize and cap
        surge_risk_score = min(100, surge_risk_score)

        return {
            'score': round(surge_risk_score, 1),
            'is_bayside': is_bayside,
            'distance_to_bay_mouth_km': round(dist_to_bay_mouth, 2),
            'distance_to_bay_center_km': round(dist_to_bay_center, 2),
            'risk_factors': {
                'tampa_bay_exposure': 'high' if is_bayside and dist_to_bay_center < 20 else 'moderate' if is_bayside else 'low',
                'bay_mouth_proximity': 'high' if dist_to_bay_mouth < 15 else 'moderate' if dist_to_bay_mouth < 30 else 'low',
            },
            'surge_scenarios': {
                'category_1_2_ft': '3-5' if is_bayside else '2-4',
                'category_3_ft': '6-10' if is_bayside else '4-7',
                'category_4_ft': '10-15' if is_bayside and dist_to_bay_center < 20 else '7-12',
                'worst_case_ft': '15-20+' if is_bayside else '10-15',
            }
        }

    def get_regional_statistics(self) -> HurricaneStatistics:
        """Generate regional hurricane statistics."""
        # Filter storms within analysis radius
        near_pinellas = []
        by_category = {}

        for hurricane in self.hurricanes:
            dist, category, _ = self.get_closest_approach(
                hurricane,
                self.bounds.center_lat,
                self.bounds.center_lon
            )

            if dist < ANALYSIS_CONFIG.hurricane_analysis_radius_km:
                near_pinellas.append(hurricane)

                cat = hurricane.max_category
                by_category[cat] = by_category.get(cat, 0) + 1

        # Direct hits (< 50km)
        direct_hits = [
            h for h in near_pinellas
            if h.closest_approach_to_pinellas_km and h.closest_approach_to_pinellas_km < 50
        ]

        # Near misses (50-100km)
        near_misses = [
            h for h in near_pinellas
            if h.closest_approach_to_pinellas_km and 50 <= h.closest_approach_to_pinellas_km < 100
        ]

        years = ANALYSIS_CONFIG.end_year - ANALYSIS_CONFIG.start_year
        avg_per_decade = len(near_pinellas) / (years / 10)

        return HurricaneStatistics(
            total_storms_analyzed=len(self.hurricanes),
            storms_within_radius=len(near_pinellas),
            direct_hits_pinellas=len(direct_hits),
            near_misses=len(near_misses),
            storms_by_category=by_category,
            avg_storms_per_decade=round(avg_per_decade, 1)
        )


# Convenience function
def analyze_hurricane_risk(
    hurricanes: List[Hurricane],
    lat: float,
    lon: float
) -> Dict:
    """Quick hurricane risk analysis for a location."""
    analyzer = HurricaneProbabilityAnalyzer(hurricanes)
    probability = analyzer.calculate_location_probability(lat, lon)
    storm_surge = analyzer.analyze_storm_surge_risk(lat, lon)

    return {
        'hurricane_probability': probability,
        'storm_surge_risk': storm_surge
    }
