"""
True Flood Risk Calculator

The core engine that combines all data sources and analyses to calculate
a comprehensive "True Flood Risk" score for any location in Pinellas County.

This score differs from FEMA flood zones by incorporating:
1. 50 years of actual historical flood events
2. Hurricane track analysis and probability
3. Granular elevation data
4. Storm surge modeling specific to Tampa Bay
5. Atmospheric pattern analysis
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Tuple

from ..models.schemas import (
    FloodEvent, Hurricane, Property,
    TrueFloodRisk, FloodRiskFactors, RiskLevel,
    PropertyRiskAssessment, AtmosphericAnalysis
)
from ..config import ANALYSIS_CONFIG, PINELLAS_BOUNDS
from ..analyzers.flood_history_analyzer import FloodHistoryAnalyzer
from ..analyzers.hurricane_probability import HurricaneProbabilityAnalyzer
from ..analyzers.elevation_analyzer import ElevationRiskAnalyzer
from ..analyzers.storm_surge_analyzer import StormSurgeAnalyzer

logger = logging.getLogger(__name__)


class TrueFloodRiskCalculator:
    """
    Main calculator that combines all flood risk factors into a single score.

    The True Flood Risk Score (0-100) represents the actual flood risk
    based on historical data, geography, and meteorological patterns.

    Score interpretation:
    - 0-20:  Very Low Risk
    - 21-40: Low Risk
    - 41-60: Moderate Risk
    - 61-80: High Risk
    - 81-100: Very High Risk
    """

    def __init__(
        self,
        flood_events: Optional[List[FloodEvent]] = None,
        hurricanes: Optional[List[Hurricane]] = None,
        atmospheric_analysis: Optional[AtmosphericAnalysis] = None
    ):
        """
        Initialize calculator with historical data.

        Args:
            flood_events: Historical flood events (from NOAA Storm Events)
            hurricanes: Historical hurricane tracks (from HURDAT2)
            atmospheric_analysis: Pre-computed atmospheric analysis
        """
        self.flood_events = flood_events or []
        self.hurricanes = hurricanes or []
        self.atmospheric_analysis = atmospheric_analysis

        # Initialize analyzers
        self.flood_analyzer = FloodHistoryAnalyzer(self.flood_events) if self.flood_events else None
        self.hurricane_analyzer = HurricaneProbabilityAnalyzer(self.hurricanes) if self.hurricanes else None
        self.elevation_analyzer = ElevationRiskAnalyzer()
        self.surge_analyzer = StormSurgeAnalyzer()

        # Risk weights from config
        self.weights = {
            'historical_floods': ANALYSIS_CONFIG.weight_historical_floods,
            'hurricane_probability': ANALYSIS_CONFIG.weight_hurricane_probability,
            'elevation_risk': ANALYSIS_CONFIG.weight_elevation_risk,
            'storm_surge': ANALYSIS_CONFIG.weight_storm_surge,
            'atmospheric_protection': ANALYSIS_CONFIG.weight_atmospheric_protection,
        }

    def calculate_risk(
        self,
        lat: float,
        lon: float,
        elevation_m: Optional[float] = None,
        address: Optional[str] = None,
        fema_flood_zone: Optional[str] = None
    ) -> TrueFloodRisk:
        """
        Calculate the True Flood Risk for a specific location.

        Args:
            lat: Latitude
            lon: Longitude
            elevation_m: Elevation in meters (will be fetched if not provided)
            address: Optional address string
            fema_flood_zone: FEMA flood zone for comparison

        Returns:
            TrueFloodRisk object with comprehensive risk assessment
        """
        # Calculate individual risk components

        # 1. Historical Flood Score
        if self.flood_analyzer:
            flood_analysis = self.flood_analyzer.calculate_location_score(lat, lon)
            historical_flood_score = flood_analysis['score']
        else:
            historical_flood_score = 50.0  # Default moderate if no data

        # 2. Hurricane Probability Score
        if self.hurricane_analyzer:
            hurricane_analysis = self.hurricane_analyzer.calculate_location_probability(lat, lon)
            hurricane_probability_score = hurricane_analysis['score']
        else:
            hurricane_probability_score = 50.0  # Default moderate

        # 3. Elevation Risk Score
        if elevation_m is not None:
            elevation_analysis = self.elevation_analyzer.calculate_risk_score(elevation_m)
            elevation_risk_score = elevation_analysis['score']
        else:
            # Use county average elevation as default
            elevation_risk_score = 50.0

        # 4. Storm Surge Score
        surge_analysis = self.surge_analyzer.calculate_surge_risk(lat, lon, elevation_m)
        storm_surge_score = surge_analysis['score']

        # 5. Atmospheric Protection Factor (Bermuda High steering effect)
        if self.atmospheric_analysis:
            protection_factor = self.atmospheric_analysis.protection_factor
        else:
            # Default protection factor for Tampa Bay based on historical patterns
            # Even without full analysis, we know steering patterns typically guide storms away
            protection_factor = 0.25

        # Apply Bermuda High protection to hurricane-related scores
        # This reflects the statistical reality that Tampa Bay has fewer direct hits
        # than other Gulf Coast regions due to typical steering patterns
        protection_multiplier = 1.0 - (protection_factor * self.weights['atmospheric_protection'])

        # Reduce hurricane and storm surge scores by the protection factor
        # Historical floods and elevation are NOT affected (those are physical facts)
        adjusted_hurricane_score = hurricane_probability_score * protection_multiplier
        adjusted_surge_score = storm_surge_score * protection_multiplier

        # Create factors object (store original scores for transparency)
        factors = FloodRiskFactors(
            historical_flood_score=historical_flood_score,
            hurricane_probability_score=hurricane_probability_score,  # Original score
            elevation_risk_score=elevation_risk_score,
            storm_surge_score=storm_surge_score,  # Original score
            atmospheric_protection_factor=protection_factor
        )

        # Calculate weighted composite score with protected hurricane scores
        raw_score = (
            factors.historical_flood_score * self.weights['historical_floods'] +
            adjusted_hurricane_score * self.weights['hurricane_probability'] +
            factors.elevation_risk_score * self.weights['elevation_risk'] +
            adjusted_surge_score * self.weights['storm_surge']
        )

        # The protection is now baked into the adjusted scores
        final_score = raw_score

        # Clamp to 0-100
        final_score = max(0, min(100, final_score))

        # Determine risk level
        risk_level = self._score_to_risk_level(final_score)

        # Compare with FEMA
        fema_comparison = None
        if fema_flood_zone:
            fema_comparison = self._compare_to_fema(final_score, fema_flood_zone)

        # Calculate confidence based on data availability
        confidence = self._calculate_confidence()

        return TrueFloodRisk(
            lat=lat,
            lon=lon,
            address=address,
            true_risk_score=round(final_score, 1),
            risk_level=risk_level,
            fema_flood_zone=fema_flood_zone,
            fema_comparison=fema_comparison,
            factors=factors,
            confidence=confidence,
            methodology_version="1.0",
            computed_at=datetime.now()
        )

    def _score_to_risk_level(self, score: float) -> RiskLevel:
        """Convert numeric score to risk level category."""
        if score <= 20:
            return RiskLevel.VERY_LOW
        elif score <= 40:
            return RiskLevel.LOW
        elif score <= 60:
            return RiskLevel.MODERATE
        elif score <= 80:
            return RiskLevel.HIGH
        else:
            return RiskLevel.VERY_HIGH

    def _compare_to_fema(self, score: float, fema_zone: str) -> str:
        """Compare calculated risk to FEMA flood zone."""
        # Map FEMA zones to approximate risk scores
        fema_scores = {
            'VE': 90, 'V': 85,
            'AE': 75, 'A': 70, 'AH': 70, 'AO': 65,
            'X': 30, 'B': 35, 'C': 20, 'D': 50,
        }

        base_zone = fema_zone.split('-')[0].upper()
        fema_score = fema_scores.get(base_zone, 50)

        diff = score - fema_score

        if abs(diff) < 10:
            return "same"
        elif diff > 0:
            return "higher"
        else:
            return "lower"

    def _calculate_confidence(self) -> float:
        """Calculate confidence in the risk assessment."""
        confidence = 0.5  # Base confidence

        # More data = higher confidence
        if self.flood_events:
            event_count = len(self.flood_events)
            if event_count > 100:
                confidence += 0.2
            elif event_count > 50:
                confidence += 0.15
            elif event_count > 20:
                confidence += 0.1

        if self.hurricanes:
            hurricane_count = len(self.hurricanes)
            if hurricane_count > 100:
                confidence += 0.15
            elif hurricane_count > 50:
                confidence += 0.1

        if self.atmospheric_analysis:
            confidence += 0.05

        return min(1.0, confidence)

    def assess_property(
        self,
        property_obj: Property,
        elevation_m: Optional[float] = None
    ) -> PropertyRiskAssessment:
        """
        Generate a complete risk assessment for a property.

        Args:
            property_obj: Property object with location info
            elevation_m: Elevation (uses property's if available)

        Returns:
            Complete PropertyRiskAssessment
        """
        # Use provided elevation or property's elevation
        elev = elevation_m or property_obj.elevation_m

        # Calculate true risk
        risk = self.calculate_risk(
            lat=property_obj.lat,
            lon=property_obj.lon,
            elevation_m=elev,
            address=property_obj.address,
            fema_flood_zone=property_obj.fema_flood_zone
        )

        # Get detailed analysis for nearby events
        nearby_events = 0
        nearest_event_km = None
        if self.flood_analyzer:
            flood_details = self.flood_analyzer.calculate_location_score(
                property_obj.lat, property_obj.lon
            )
            nearby_events = flood_details['events_count']
            nearest_event_km = flood_details.get('nearest_event_km')

        # Storm surge details
        surge_analysis = self.surge_analyzer.calculate_surge_risk(
            property_obj.lat, property_obj.lon, elev
        )

        # FEMA risk level
        fema_risk_level = None
        if property_obj.fema_flood_zone:
            fema_risk_level = self._fema_zone_to_risk_level(property_obj.fema_flood_zone)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            risk, surge_analysis, property_obj.fema_flood_zone
        )

        return PropertyRiskAssessment(
            property=property_obj,
            true_risk_score=risk.true_risk_score,
            risk_level=risk.risk_level,
            fema_risk_level=fema_risk_level,
            risk_components={
                'historical_floods': risk.factors.historical_flood_score,
                'hurricane_probability': risk.factors.hurricane_probability_score,
                'elevation_risk': risk.factors.elevation_risk_score,
                'storm_surge': risk.factors.storm_surge_score,
                'atmospheric_protection': risk.factors.atmospheric_protection_factor,
            },
            historical_events_nearby=nearby_events,
            nearest_flood_event_km=nearest_event_km,
            storm_surge_exposure=surge_analysis['score'],
            recommendations=recommendations
        )

    def _fema_zone_to_risk_level(self, fema_zone: str) -> RiskLevel:
        """Convert FEMA flood zone to risk level."""
        base_zone = fema_zone.split('-')[0].upper()

        high_risk_zones = ['V', 'VE', 'A', 'AE', 'AH', 'AO', 'AR']
        moderate_zones = ['X', 'B']
        low_zones = ['C']

        if base_zone in ['VE', 'V']:
            return RiskLevel.VERY_HIGH
        elif base_zone in high_risk_zones:
            return RiskLevel.HIGH
        elif base_zone in moderate_zones:
            return RiskLevel.MODERATE
        elif base_zone in low_zones:
            return RiskLevel.LOW
        else:
            return RiskLevel.MODERATE

    def _generate_recommendations(
        self,
        risk: TrueFloodRisk,
        surge_analysis: Dict,
        fema_zone: Optional[str]
    ) -> List[str]:
        """Generate actionable recommendations based on risk assessment."""
        recommendations = []

        # Based on overall risk level
        if risk.risk_level in [RiskLevel.VERY_HIGH, RiskLevel.HIGH]:
            recommendations.append(
                "Consider flood insurance even if not required by mortgage lender"
            )
            recommendations.append(
                "Know your evacuation route and zone - register for emergency alerts"
            )

        if risk.risk_level == RiskLevel.VERY_HIGH:
            recommendations.append(
                "Strongly recommend elevating critical utilities above flood level"
            )
            recommendations.append(
                "Create an emergency kit and evacuation plan"
            )

        # Based on storm surge
        evac_zone = surge_analysis.get('evacuation_zone', '')
        if evac_zone == 'A':
            recommendations.append(
                "Evacuation Zone A - evacuate for ANY tropical storm or hurricane threat"
            )
        elif evac_zone == 'B':
            recommendations.append(
                "Evacuation Zone B - evacuate when ordered for Category 1+ hurricanes"
            )

        # Based on elevation risk
        if risk.factors.elevation_risk_score > 70:
            recommendations.append(
                "Low elevation increases flood risk - consider flood barriers or landscaping"
            )

        # FEMA comparison
        if risk.fema_comparison == 'higher':
            recommendations.append(
                f"Our analysis suggests higher risk than FEMA zone {fema_zone} indicates - "
                "consider additional protection"
            )
        elif risk.fema_comparison == 'lower':
            recommendations.append(
                f"Historical data suggests potentially lower risk than FEMA zone {fema_zone} - "
                "you may be overpaying for flood insurance"
            )

        # Historical events nearby
        if risk.factors.historical_flood_score > 60:
            recommendations.append(
                "Multiple flood events recorded nearby - review historical flood maps"
            )

        # Default recommendation
        if not recommendations:
            recommendations.append(
                "Standard flood preparedness recommended - review FEMA flood preparedness guide"
            )

        return recommendations

    def generate_risk_grid(
        self,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        resolution_deg: float = 0.01
    ) -> List[Dict]:
        """
        Generate a grid of risk scores for mapping.

        Args:
            resolution_deg: Grid resolution in degrees (0.01 ≈ 1km)

        Returns:
            List of {lat, lon, risk_score, risk_level} dicts
        """
        min_lat = min_lat or PINELLAS_BOUNDS.min_lat
        max_lat = max_lat or PINELLAS_BOUNDS.max_lat
        min_lon = min_lon or PINELLAS_BOUNDS.min_lon
        max_lon = max_lon or PINELLAS_BOUNDS.max_lon

        grid_points = []

        lat = min_lat
        while lat <= max_lat:
            lon = min_lon
            while lon <= max_lon:
                # Calculate risk (without elevation for speed)
                risk = self.calculate_risk(lat, lon)

                grid_points.append({
                    'lat': round(lat, 4),
                    'lon': round(lon, 4),
                    'risk_score': risk.true_risk_score,
                    'risk_level': risk.risk_level.value,
                })

                lon += resolution_deg
            lat += resolution_deg

        logger.info(f"Generated risk grid with {len(grid_points)} points")
        return grid_points


# Convenience function for quick risk calculation
def calculate_true_flood_risk(
    lat: float,
    lon: float,
    flood_events: Optional[List[FloodEvent]] = None,
    hurricanes: Optional[List[Hurricane]] = None,
    elevation_m: Optional[float] = None,
    fema_zone: Optional[str] = None
) -> TrueFloodRisk:
    """
    Quick calculation of true flood risk for a location.

    For production use, create a TrueFloodRiskCalculator instance
    with pre-loaded data for better performance.
    """
    calculator = TrueFloodRiskCalculator(
        flood_events=flood_events,
        hurricanes=hurricanes
    )

    return calculator.calculate_risk(
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        fema_flood_zone=fema_zone
    )


if __name__ == "__main__":
    # Test calculation
    logging.basicConfig(level=logging.INFO)

    # Test without data (will use defaults)
    calculator = TrueFloodRiskCalculator()

    # Test location: Downtown St. Petersburg
    lat, lon = 27.7676, -82.6403

    print(f"\nCalculating True Flood Risk for ({lat}, {lon})...")
    print("(Downtown St. Petersburg, FL)")

    risk = calculator.calculate_risk(
        lat=lat,
        lon=lon,
        elevation_m=3.0,  # Assume 3 meters
        fema_flood_zone="AE"
    )

    print(f"\nTrue Flood Risk Score: {risk.true_risk_score}/100")
    print(f"Risk Level: {risk.risk_level.value}")
    print(f"FEMA Zone: {risk.fema_flood_zone}")
    print(f"Comparison to FEMA: {risk.fema_comparison}")
    print(f"\nRisk Factors:")
    print(f"  Historical Floods: {risk.factors.historical_flood_score:.1f}")
    print(f"  Hurricane Probability: {risk.factors.hurricane_probability_score:.1f}")
    print(f"  Elevation Risk: {risk.factors.elevation_risk_score:.1f}")
    print(f"  Storm Surge: {risk.factors.storm_surge_score:.1f}")
    print(f"  Atmospheric Protection: {risk.factors.atmospheric_protection_factor:.2f}")
    print(f"\nConfidence: {risk.confidence:.0%}")
