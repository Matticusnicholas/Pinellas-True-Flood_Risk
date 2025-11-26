"""
Elevation Risk Analyzer

Analyzes flood risk based on elevation and topography.
"""
import logging
from typing import Dict, Optional

from ..config import ANALYSIS_CONFIG

logger = logging.getLogger(__name__)


class ElevationRiskAnalyzer:
    """
    Analyzes flood risk based on elevation above sea level.

    Lower elevations have higher flood risk from:
    - Storm surge
    - Tidal flooding
    - Rainwater accumulation
    """

    def __init__(self):
        self.config = ANALYSIS_CONFIG

    def calculate_risk_score(self, elevation_m: float) -> Dict:
        """
        Calculate flood risk score based on elevation.

        Args:
            elevation_m: Elevation in meters above sea level

        Returns:
            Risk score (0-100) and breakdown
        """
        config = self.config

        # Determine risk category and score
        if elevation_m < 0:
            # Below sea level - extreme risk
            score = 100
            category = 'extreme'
            description = 'Below sea level - immediate flood risk'

        elif elevation_m < config.elevation_very_high_risk:
            # Below 2m - very high risk
            score = 100 - (elevation_m / config.elevation_very_high_risk * 15)
            category = 'very_high'
            description = f'Very low elevation ({elevation_m:.1f}m) - high storm surge risk'

        elif elevation_m < config.elevation_high_risk:
            # 2-5m - high risk
            relative_pos = (elevation_m - config.elevation_very_high_risk) / \
                           (config.elevation_high_risk - config.elevation_very_high_risk)
            score = 85 - (relative_pos * 20)
            category = 'high'
            description = f'Low elevation ({elevation_m:.1f}m) - vulnerable to major storms'

        elif elevation_m < config.elevation_moderate_risk:
            # 5-10m - moderate risk
            relative_pos = (elevation_m - config.elevation_high_risk) / \
                           (config.elevation_moderate_risk - config.elevation_high_risk)
            score = 65 - (relative_pos * 25)
            category = 'moderate'
            description = f'Moderate elevation ({elevation_m:.1f}m) - some flood risk in severe events'

        elif elevation_m < config.elevation_low_risk:
            # 10-20m - low risk
            relative_pos = (elevation_m - config.elevation_moderate_risk) / \
                           (config.elevation_low_risk - config.elevation_moderate_risk)
            score = 40 - (relative_pos * 25)
            category = 'low'
            description = f'Good elevation ({elevation_m:.1f}m) - minimal storm surge risk'

        else:
            # Above 20m - very low risk
            score = max(0, 15 - (elevation_m - config.elevation_low_risk))
            category = 'very_low'
            description = f'High elevation ({elevation_m:.1f}m) - protected from most flooding'

        # Storm surge exposure based on elevation
        surge_exposure = self._calculate_surge_exposure(elevation_m)

        return {
            'score': round(score, 1),
            'elevation_m': round(elevation_m, 2),
            'elevation_ft': round(elevation_m * 3.28084, 1),
            'risk_category': category,
            'description': description,
            'surge_exposure': surge_exposure,
            'thresholds': {
                'very_high_below_m': config.elevation_very_high_risk,
                'high_below_m': config.elevation_high_risk,
                'moderate_below_m': config.elevation_moderate_risk,
                'low_below_m': config.elevation_low_risk,
            }
        }

    def _calculate_surge_exposure(self, elevation_m: float) -> Dict:
        """
        Calculate exposure to different storm surge scenarios.
        """
        # Storm surge heights by hurricane category (typical Gulf Coast values)
        surge_heights_m = {
            'category_1': 1.5,   # 4-5 ft
            'category_2': 2.4,   # 6-8 ft
            'category_3': 3.7,   # 9-12 ft
            'category_4': 5.5,   # 13-18 ft
            'category_5': 7.6,   # 18+ ft
        }

        exposure = {}
        for category, surge_height in surge_heights_m.items():
            if elevation_m < surge_height:
                inundation_m = surge_height - elevation_m
                exposure[category] = {
                    'vulnerable': True,
                    'potential_inundation_m': round(inundation_m, 1),
                    'potential_inundation_ft': round(inundation_m * 3.28084, 1),
                }
            else:
                exposure[category] = {
                    'vulnerable': False,
                    'safety_margin_m': round(elevation_m - surge_height, 1),
                }

        return exposure

    def compare_to_fema(
        self,
        elevation_risk_score: float,
        fema_zone: Optional[str]
    ) -> Dict:
        """
        Compare elevation-based risk to FEMA flood zone designation.
        """
        if not fema_zone:
            return {
                'comparison': 'unknown',
                'fema_zone': None,
                'notes': 'FEMA flood zone data not available for this location'
            }

        # Map FEMA zones to approximate risk scores
        fema_risk_estimates = {
            'VE': 90,  # Coastal high hazard with waves
            'V': 85,
            'AE': 75,  # High risk with BFE
            'A': 70,
            'AH': 70,
            'AO': 65,
            'X': 30,   # Moderate to minimal
            'B': 35,
            'C': 20,
            'D': 50,   # Undetermined
        }

        base_zone = fema_zone.split('-')[0].upper() if fema_zone else 'Unknown'
        fema_score = fema_risk_estimates.get(base_zone, 50)

        diff = elevation_risk_score - fema_score

        if abs(diff) < 10:
            comparison = 'consistent'
            notes = 'Elevation analysis aligns with FEMA designation'
        elif diff > 0:
            comparison = 'higher_risk'
            notes = f'Elevation analysis suggests higher risk than FEMA zone {fema_zone} indicates'
        else:
            comparison = 'lower_risk'
            notes = f'Elevation analysis suggests lower risk than FEMA zone {fema_zone} indicates'

        return {
            'comparison': comparison,
            'elevation_score': round(elevation_risk_score, 1),
            'fema_equivalent_score': fema_score,
            'difference': round(diff, 1),
            'fema_zone': fema_zone,
            'notes': notes
        }


# Convenience function
def analyze_elevation_risk(elevation_m: float, fema_zone: Optional[str] = None) -> Dict:
    """Quick elevation risk analysis."""
    analyzer = ElevationRiskAnalyzer()
    risk = analyzer.calculate_risk_score(elevation_m)

    if fema_zone:
        risk['fema_comparison'] = analyzer.compare_to_fema(risk['score'], fema_zone)

    return risk
