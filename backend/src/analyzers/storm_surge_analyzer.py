"""
Storm Surge Analyzer

Specialized analysis of storm surge risk for Tampa Bay / Pinellas County.
"""
import math
import logging
from typing import Dict, Optional

from ..config import PINELLAS_BOUNDS

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


class StormSurgeAnalyzer:
    """
    Analyzes storm surge risk specific to Tampa Bay geography.

    Tampa Bay is particularly vulnerable to storm surge because:
    1. The bay funnels water inward during certain storm approaches
    2. A storm tracking NE up the bay could push massive surge
    3. The bay is relatively shallow, amplifying surge
    4. The worst-case scenario is a slow-moving major hurricane
       crossing just south of the bay mouth
    """

    # Tampa Bay key geographic points
    BAY_MOUTH = (27.5833, -82.7333)  # Between Egmont Key and Anna Maria
    BAY_CENTER = (27.85, -82.55)     # Central Tampa Bay
    INNER_BAY = (27.92, -82.45)      # Upper Tampa Bay

    # Storm surge amplification factors for different areas
    SURGE_AMPLIFICATION = {
        'gulf_beach': 1.0,      # Gulf beaches - direct surge
        'bay_mouth': 1.2,       # Bay mouth area - funneling begins
        'lower_bay': 1.4,       # Lower Tampa Bay - funneling effect
        'middle_bay': 1.6,      # Middle bay - amplified surge
        'upper_bay': 1.8,       # Upper bay - maximum amplification
        'old_tampa_bay': 1.7,   # Old Tampa Bay (west of Howard Frankland)
        'hillsborough_bay': 1.9 # Hillsborough Bay - maximum funneling
    }

    def __init__(self):
        self.bounds = PINELLAS_BOUNDS

    def determine_surge_zone(self, lat: float, lon: float) -> str:
        """
        Determine which storm surge zone a location falls into.
        """
        # Distance to various bay features
        dist_to_mouth = haversine_distance(lat, lon, *self.BAY_MOUTH)
        dist_to_center = haversine_distance(lat, lon, *self.BAY_CENTER)
        dist_to_inner = haversine_distance(lat, lon, *self.INNER_BAY)

        # Check if on Gulf side (west of certain longitude)
        is_gulf_side = lon < -82.78

        # Check if in Old Tampa Bay (north of Gandy, west of bay center)
        is_old_tampa_bay = lat > 27.87 and lon < -82.55

        # Check if in Hillsborough Bay (east of bay center, north of bay mouth)
        is_hillsborough_bay = lat > 27.85 and lon > -82.50

        if is_gulf_side:
            return 'gulf_beach'
        elif is_old_tampa_bay:
            return 'old_tampa_bay'
        elif is_hillsborough_bay:
            return 'hillsborough_bay'
        elif dist_to_mouth < 10:
            return 'bay_mouth'
        elif dist_to_center < 15:
            return 'middle_bay'
        elif lat < 27.7:
            return 'lower_bay'
        else:
            return 'upper_bay'

    def calculate_surge_risk(
        self,
        lat: float,
        lon: float,
        elevation_m: Optional[float] = None
    ) -> Dict:
        """
        Calculate comprehensive storm surge risk for a location.
        """
        # Determine geographic zone
        surge_zone = self.determine_surge_zone(lat, lon)
        amplification = self.SURGE_AMPLIFICATION.get(surge_zone, 1.0)

        # Distance metrics
        dist_to_bay_mouth = haversine_distance(lat, lon, *self.BAY_MOUTH)
        dist_to_bay_center = haversine_distance(lat, lon, *self.BAY_CENTER)

        # Base surge estimates by category (meters at bay mouth)
        base_surge_m = {
            'category_1': 1.2,
            'category_2': 2.1,
            'category_3': 3.4,
            'category_4': 4.9,
            'category_5': 6.7,
        }

        # Apply amplification for this zone
        local_surge_estimates = {}
        for cat, base in base_surge_m.items():
            local_surge = base * amplification
            local_surge_estimates[cat] = {
                'surge_m': round(local_surge, 1),
                'surge_ft': round(local_surge * 3.28084, 1),
            }

            # Add inundation depth if elevation provided
            if elevation_m is not None:
                if local_surge > elevation_m:
                    local_surge_estimates[cat]['inundation_m'] = round(local_surge - elevation_m, 1)
                    local_surge_estimates[cat]['inundation_ft'] = round((local_surge - elevation_m) * 3.28084, 1)
                    local_surge_estimates[cat]['vulnerable'] = True
                else:
                    local_surge_estimates[cat]['safety_margin_m'] = round(elevation_m - local_surge, 1)
                    local_surge_estimates[cat]['vulnerable'] = False

        # Calculate overall score (0-100)
        base_score = 50  # Start at moderate

        # Zone-based adjustment
        zone_scores = {
            'gulf_beach': 55,
            'bay_mouth': 65,
            'lower_bay': 70,
            'middle_bay': 75,
            'upper_bay': 80,
            'old_tampa_bay': 78,
            'hillsborough_bay': 85,
        }
        base_score = zone_scores.get(surge_zone, 50)

        # Elevation adjustment
        if elevation_m is not None:
            if elevation_m < 2:
                base_score += 15
            elif elevation_m < 4:
                base_score += 10
            elif elevation_m < 6:
                base_score += 5
            elif elevation_m > 10:
                base_score -= 15
            elif elevation_m > 6:
                base_score -= 5

        # Cap at 0-100
        score = max(0, min(100, base_score))

        # Worst-case scenario description
        worst_case = self._describe_worst_case(surge_zone, elevation_m)

        return {
            'score': round(score, 1),
            'surge_zone': surge_zone,
            'surge_zone_description': self._get_zone_description(surge_zone),
            'amplification_factor': amplification,
            'distance_to_bay_mouth_km': round(dist_to_bay_mouth, 2),
            'distance_to_bay_center_km': round(dist_to_bay_center, 2),
            'elevation_m': elevation_m,
            'surge_estimates': local_surge_estimates,
            'worst_case_scenario': worst_case,
            'evacuation_zone': self._estimate_evacuation_zone(surge_zone, elevation_m)
        }

    def _get_zone_description(self, zone: str) -> str:
        """Get human-readable description of surge zone."""
        descriptions = {
            'gulf_beach': 'Gulf of Mexico beachfront - direct ocean surge exposure',
            'bay_mouth': 'Tampa Bay entrance - transition zone with initial surge funneling',
            'lower_bay': 'Lower Tampa Bay - moderate surge amplification',
            'middle_bay': 'Central Tampa Bay - significant surge amplification due to bay shape',
            'upper_bay': 'Upper Tampa Bay - high surge amplification, water piles up',
            'old_tampa_bay': 'Old Tampa Bay - enclosed area with significant surge risk',
            'hillsborough_bay': 'Hillsborough Bay - maximum surge amplification, most vulnerable',
        }
        return descriptions.get(zone, 'Unknown zone')

    def _describe_worst_case(self, zone: str, elevation_m: Optional[float]) -> Dict:
        """Describe worst-case storm surge scenario."""
        base_worst = {
            'gulf_beach': 'Category 4-5 hurricane making direct landfall',
            'bay_mouth': 'Major hurricane tracking northeast across bay entrance',
            'lower_bay': 'Slow-moving major hurricane pushing water into the bay',
            'middle_bay': 'Category 3+ hurricane with worst-track approach',
            'upper_bay': 'Any major hurricane approaching from the southwest',
            'old_tampa_bay': 'Major hurricane with prolonged onshore winds',
            'hillsborough_bay': 'Even moderate hurricanes can cause significant surge',
        }

        # Estimate worst-case surge
        worst_surge_m = {
            'gulf_beach': 6.0,
            'bay_mouth': 7.5,
            'lower_bay': 8.5,
            'middle_bay': 9.5,
            'upper_bay': 10.5,
            'old_tampa_bay': 10.0,
            'hillsborough_bay': 12.0,
        }

        surge = worst_surge_m.get(zone, 8.0)

        result = {
            'scenario': base_worst.get(zone, 'Major hurricane approach'),
            'estimated_surge_m': surge,
            'estimated_surge_ft': round(surge * 3.28084, 0),
        }

        if elevation_m is not None:
            if surge > elevation_m:
                result['potential_inundation_m'] = round(surge - elevation_m, 1)
                result['potential_inundation_ft'] = round((surge - elevation_m) * 3.28084, 0)
                result['survival_note'] = 'Evacuation absolutely critical in this scenario'
            else:
                result['survival_note'] = f'Location may remain above worst-case surge by {elevation_m - surge:.1f}m'

        return result

    def _estimate_evacuation_zone(
        self,
        surge_zone: str,
        elevation_m: Optional[float]
    ) -> str:
        """
        Estimate evacuation zone (A, B, C, D, E or Non-Evac).

        Note: This is an estimate. Official evacuation zones should be
        consulted from Pinellas County Emergency Management.

        Pinellas County zones are based on storm surge vulnerability:
        - Zone A: Mobile homes + most vulnerable areas (barrier islands, low-lying coast)
        - Zone B: Slightly higher areas still at risk from Cat 1+
        - Zone C: Areas at risk from Cat 2+
        - Zone D: Areas at risk from Cat 3+
        - Zone E: Areas at risk from Cat 4+
        """
        # Zone baseline - more nuanced based on actual geography
        zone_baseline = {
            'hillsborough_bay': 'A',  # Very low-lying
            'upper_bay': 'B',
            'old_tampa_bay': 'B',
            'middle_bay': 'B',
            'lower_bay': 'C',
            'bay_mouth': 'B',
            'gulf_beach': 'A',  # Barrier islands always Zone A
        }

        base = zone_baseline.get(surge_zone, 'C')
        zone_order = ['A', 'B', 'C', 'D', 'E', 'Non-Evac']

        # Adjust by elevation - this is the key factor
        if elevation_m is not None:
            if elevation_m < 2:
                # Very low - stay at base or move to A
                idx = zone_order.index(base) if base in zone_order else 0
                idx = max(0, idx - 1)  # Move towards A
                return zone_order[idx]
            elif elevation_m < 4:
                # Low - use baseline
                return base
            elif elevation_m > 15:
                # Very high elevation - unlikely to need evacuation for surge
                return 'Non-Evac'
            elif elevation_m > 10:
                # High elevation - reduce by 2 zones
                idx = zone_order.index(base) if base in zone_order else 0
                idx = min(idx + 2, len(zone_order) - 1)
                return zone_order[idx]
            elif elevation_m > 6:
                # Moderate-high elevation - reduce by 1 zone
                idx = zone_order.index(base) if base in zone_order else 0
                idx = min(idx + 1, len(zone_order) - 1)
                return zone_order[idx]

        return base


# Convenience function
def analyze_storm_surge(
    lat: float,
    lon: float,
    elevation_m: Optional[float] = None
) -> Dict:
    """Quick storm surge analysis for a location."""
    analyzer = StormSurgeAnalyzer()
    return analyzer.calculate_surge_risk(lat, lon, elevation_m)
