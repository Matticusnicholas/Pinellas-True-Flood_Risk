"""
Hurricane Track Data Collector

Fetches and processes hurricane track data from NOAA HURDAT2 and IBTrACS
to analyze storm patterns affecting Pinellas County and the Tampa Bay area.

Data Sources:
- HURDAT2: https://www.nhc.noaa.gov/data/hurdat/
- IBTrACS: https://www.ncei.noaa.gov/products/international-best-track-archive
"""
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import requests
import pandas as pd

from ..config import (
    PINELLAS_BOUNDS,
    DATA_URLS,
    ANALYSIS_CONFIG,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    CACHE_DIR
)
from ..models.schemas import Hurricane, HurricaneTrackPoint, HurricaneStatistics

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees).
    """
    R = 6371  # Radius of earth in kilometers

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def wind_to_category(max_wind_kt: float) -> int:
    """Convert maximum sustained wind (knots) to Saffir-Simpson category."""
    if max_wind_kt < 34:
        return -1  # Tropical Depression
    elif max_wind_kt < 64:
        return 0   # Tropical Storm
    elif max_wind_kt < 83:
        return 1   # Category 1
    elif max_wind_kt < 96:
        return 2   # Category 2
    elif max_wind_kt < 113:
        return 3   # Category 3
    elif max_wind_kt < 137:
        return 4   # Category 4
    else:
        return 5   # Category 5


class HurricaneTrackCollector:
    """
    Collects and processes hurricane track data from HURDAT2 and IBTrACS.

    Analyzes hurricane paths to determine:
    - How many storms have come near Pinellas County
    - Track deflection patterns (storms that "veered away")
    - Storm surge risk from Tampa Bay entry
    """

    def __init__(self):
        self.bounds = PINELLAS_BOUNDS
        self.cache_dir = CACHE_DIR / "hurricane_tracks"
        self.cache_dir.mkdir(exist_ok=True)
        self.analysis_radius_km = ANALYSIS_CONFIG.hurricane_analysis_radius_km

    def _download_hurdat2(self) -> Optional[str]:
        """Download HURDAT2 data from NOAA NHC."""
        cache_file = self.cache_dir / "hurdat2_atlantic.txt"

        if cache_file.exists():
            logger.info("Loading cached HURDAT2 data")
            return cache_file.read_text()

        try:
            logger.info("Downloading HURDAT2 data from NOAA...")
            response = requests.get(DATA_URLS.hurdat2_atlantic, timeout=60)
            response.raise_for_status()

            cache_file.write_text(response.text)
            logger.info(f"Cached HURDAT2 data ({len(response.text)} bytes)")
            return response.text

        except requests.RequestException as e:
            logger.error(f"Failed to download HURDAT2: {e}")
            return None

    def _parse_hurdat2(self, data: str) -> List[Hurricane]:
        """
        Parse HURDAT2 format data into Hurricane objects.

        HURDAT2 format:
        Header: AL092023,IDALIA,34,
        Track:  20230826, 0600,  , TD, 16.1N,  80.5W,  30,   1007, ...
        """
        hurricanes = []
        current_storm = None
        track_points = []

        lines = data.strip().split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            # Header line detection (starts with basin code like AL, EP)
            if line[:2] in ['AL', 'EP', 'CP'] and ',' in line:
                # Save previous storm if exists
                if current_storm and track_points:
                    max_wind = max((p.max_wind_kt or 0) for p in track_points)
                    current_storm['track_points'] = track_points
                    current_storm['max_wind_kt'] = max_wind
                    current_storm['max_category'] = wind_to_category(max_wind)

                    hurricane = self._create_hurricane(current_storm)
                    if hurricane:
                        hurricanes.append(hurricane)

                # Parse header
                parts = line.split(',')
                storm_id = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else "UNNAMED"

                try:
                    year = int(storm_id[4:8])
                except (ValueError, IndexError):
                    year = 2000

                current_storm = {
                    'storm_id': storm_id,
                    'name': name,
                    'year': year,
                    'basin': storm_id[:2]
                }
                track_points = []

            else:
                # Track point line
                if current_storm:
                    point = self._parse_hurdat2_track_point(line)
                    if point:
                        track_points.append(point)

            i += 1

        # Don't forget the last storm
        if current_storm and track_points:
            max_wind = max((p.max_wind_kt or 0) for p in track_points)
            current_storm['track_points'] = track_points
            current_storm['max_wind_kt'] = max_wind
            current_storm['max_category'] = wind_to_category(max_wind)

            hurricane = self._create_hurricane(current_storm)
            if hurricane:
                hurricanes.append(hurricane)

        logger.info(f"Parsed {len(hurricanes)} storms from HURDAT2")
        return hurricanes

    def _parse_hurdat2_track_point(self, line: str) -> Optional[HurricaneTrackPoint]:
        """Parse a single HURDAT2 track point line."""
        try:
            parts = [p.strip() for p in line.split(',')]

            if len(parts) < 7:
                return None

            # Parse date and time
            date_str = parts[0]
            time_str = parts[1].zfill(4)
            timestamp = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M")

            # Parse record identifier (L = landfall, etc.)
            record_id = parts[2] if parts[2] else None

            # Parse status (HU, TS, TD, etc.)
            # status = parts[3]

            # Parse latitude (e.g., "27.5N" or "27.5S")
            lat_str = parts[4]
            lat = float(lat_str[:-1])
            if lat_str[-1] == 'S':
                lat = -lat

            # Parse longitude (e.g., "82.5W" or "82.5E")
            lon_str = parts[5]
            lon = float(lon_str[:-1])
            if lon_str[-1] == 'W':
                lon = -lon

            # Parse wind and pressure
            max_wind = float(parts[6]) if parts[6] and parts[6] != '-999' else None
            min_pressure = float(parts[7]) if len(parts) > 7 and parts[7] and parts[7] != '-999' else None

            return HurricaneTrackPoint(
                timestamp=timestamp,
                lat=lat,
                lon=lon,
                max_wind_kt=max_wind,
                min_pressure_mb=min_pressure,
                category=wind_to_category(max_wind) if max_wind else None,
                record_identifier=record_id
            )

        except (ValueError, IndexError) as e:
            return None

    def _create_hurricane(self, storm_data: dict) -> Optional[Hurricane]:
        """Create a Hurricane object with computed metadata."""
        track_points = storm_data.get('track_points', [])
        if not track_points:
            return None

        # Calculate closest approach to Pinellas
        closest_distance = float('inf')
        for point in track_points:
            dist = haversine_distance(
                point.lat, point.lon,
                self.bounds.center_lat, self.bounds.center_lon
            )
            closest_distance = min(closest_distance, dist)

        # Check if storm made landfall in Florida
        landfall_florida = any(
            p.record_identifier == 'L' and
            24 <= p.lat <= 31 and
            -88 <= p.lon <= -79
            for p in track_points
        )

        # Determine if storm affected Pinellas (within 150km)
        affected_pinellas = closest_distance < 150

        return Hurricane(
            storm_id=storm_data['storm_id'],
            name=storm_data['name'],
            year=storm_data['year'],
            basin=storm_data['basin'],
            track_points=track_points,
            max_category=storm_data.get('max_category', 0),
            max_wind_kt=storm_data.get('max_wind_kt'),
            min_pressure_mb=min((p.min_pressure_mb for p in track_points if p.min_pressure_mb), default=None),
            landfall_florida=landfall_florida,
            closest_approach_to_pinellas_km=closest_distance if closest_distance != float('inf') else None,
            affected_pinellas=affected_pinellas
        )

    def _download_ibtracs(self) -> Optional[pd.DataFrame]:
        """Download IBTrACS data as alternative/supplementary source."""
        cache_file = self.cache_dir / "ibtracs_na.parquet"

        if cache_file.exists():
            logger.info("Loading cached IBTrACS data")
            return pd.read_parquet(cache_file)

        try:
            logger.info("Downloading IBTrACS data...")
            df = pd.read_csv(DATA_URLS.ibtracs_csv, low_memory=False, skiprows=[1])

            df.to_parquet(cache_file)
            logger.info(f"Cached IBTrACS data ({len(df)} records)")
            return df

        except Exception as e:
            logger.error(f"Failed to download IBTrACS: {e}")
            return None

    def collect_hurricane_data(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None
    ) -> List[Hurricane]:
        """
        Collect hurricane data for analysis period.

        Args:
            start_year: Starting year (default: from config)
            end_year: Ending year (default: current year)

        Returns:
            List of Hurricane objects
        """
        start_year = start_year or ANALYSIS_CONFIG.start_year
        end_year = end_year or ANALYSIS_CONFIG.end_year

        # Try HURDAT2 first
        hurdat2_data = self._download_hurdat2()
        if hurdat2_data:
            hurricanes = self._parse_hurdat2(hurdat2_data)
        else:
            logger.warning("HURDAT2 unavailable, trying IBTrACS...")
            hurricanes = []  # Would need IBTrACS parser

        # Filter by year range
        hurricanes = [h for h in hurricanes if start_year <= h.year <= end_year]

        logger.info(f"Collected {len(hurricanes)} storms for {start_year}-{end_year}")
        return hurricanes

    def filter_storms_near_pinellas(
        self,
        hurricanes: List[Hurricane],
        max_distance_km: Optional[float] = None
    ) -> List[Hurricane]:
        """Filter to only storms that came within specified distance of Pinellas."""
        max_distance_km = max_distance_km or self.analysis_radius_km

        return [
            h for h in hurricanes
            if h.closest_approach_to_pinellas_km and
               h.closest_approach_to_pinellas_km <= max_distance_km
        ]

    def analyze_deflection_patterns(self, hurricanes: List[Hurricane]) -> dict:
        """
        Analyze storms that appeared to "deflect" away from Pinellas.

        A deflection is detected when:
        1. Storm was heading toward Pinellas (distance decreasing)
        2. Storm then turned away (distance started increasing)
        3. Storm never made direct landfall on Pinellas
        """
        deflections = []
        direct_approaches = []

        for hurricane in hurricanes:
            if not hurricane.track_points or len(hurricane.track_points) < 3:
                continue

            distances = []
            for point in hurricane.track_points:
                dist = haversine_distance(
                    point.lat, point.lon,
                    self.bounds.center_lat, self.bounds.center_lon
                )
                distances.append((point.timestamp, dist, point.lat, point.lon))

            # Find minimum distance point
            min_idx = min(range(len(distances)), key=lambda i: distances[i][1])
            min_distance = distances[min_idx][1]

            # Only analyze storms that got within 300km
            if min_distance > 300:
                continue

            # Check if storm was approaching (distances decreasing) then retreating
            approaching = all(
                distances[i][1] > distances[i+1][1]
                for i in range(max(0, min_idx - 3), min_idx)
            ) if min_idx > 0 else False

            retreating = all(
                distances[i][1] < distances[i+1][1]
                for i in range(min_idx, min(len(distances) - 1, min_idx + 3))
            ) if min_idx < len(distances) - 1 else False

            if approaching and retreating and min_distance > 50:
                # Calculate deflection angle
                if min_idx > 0 and min_idx < len(distances) - 1:
                    before = distances[min_idx - 1]
                    after = distances[min_idx + 1]

                    # Direction change
                    heading_before = math.atan2(
                        distances[min_idx][3] - before[3],
                        distances[min_idx][2] - before[2]
                    )
                    heading_after = math.atan2(
                        after[3] - distances[min_idx][3],
                        after[2] - distances[min_idx][2]
                    )
                    deflection_angle = math.degrees(heading_after - heading_before)

                    deflections.append({
                        'storm_id': hurricane.storm_id,
                        'name': hurricane.name,
                        'year': hurricane.year,
                        'min_distance_km': min_distance,
                        'deflection_angle': deflection_angle,
                        'category_at_closest': hurricane.track_points[min_idx].category
                    })
            elif min_distance < 50:
                direct_approaches.append({
                    'storm_id': hurricane.storm_id,
                    'name': hurricane.name,
                    'year': hurricane.year,
                    'min_distance_km': min_distance
                })

        return {
            'total_analyzed': len(hurricanes),
            'deflections': deflections,
            'direct_approaches': direct_approaches,
            'deflection_rate': len(deflections) / max(len(deflections) + len(direct_approaches), 1),
            'avg_deflection_distance_km': (
                sum(d['min_distance_km'] for d in deflections) / len(deflections)
                if deflections else 0
            )
        }

    def get_statistics(self, hurricanes: List[Hurricane]) -> HurricaneStatistics:
        """Generate comprehensive hurricane statistics for the region."""
        near_storms = self.filter_storms_near_pinellas(hurricanes)

        storms_by_category = {}
        for h in near_storms:
            cat = h.max_category
            storms_by_category[cat] = storms_by_category.get(cat, 0) + 1

        # Direct hits (within 50km)
        direct_hits = [h for h in near_storms if
                       h.closest_approach_to_pinellas_km and
                       h.closest_approach_to_pinellas_km < 50]

        # Near misses (50-100km)
        near_misses = [h for h in near_storms if
                       h.closest_approach_to_pinellas_km and
                       50 <= h.closest_approach_to_pinellas_km < 100]

        # Calculate storms per decade
        if hurricanes:
            years = [h.year for h in hurricanes]
            year_span = max(years) - min(years) + 1
            avg_per_decade = len(near_storms) / (year_span / 10)
        else:
            avg_per_decade = 0

        deflection_analysis = self.analyze_deflection_patterns(hurricanes)

        return HurricaneStatistics(
            total_storms_analyzed=len(hurricanes),
            storms_within_radius=len(near_storms),
            direct_hits_pinellas=len(direct_hits),
            near_misses=len(near_misses),
            storms_by_category=storms_by_category,
            avg_storms_per_decade=avg_per_decade,
            deflection_analysis=deflection_analysis
        )

    def save_processed_data(self, hurricanes: List[Hurricane], filename: str = "hurricane_tracks.json"):
        """Save processed hurricane data to JSON."""
        output_path = PROCESSED_DATA_DIR / filename

        import json
        data = [h.model_dump(mode='json') for h in hurricanes]

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Saved {len(hurricanes)} hurricane records to {output_path}")
        return output_path


# Convenience function
def fetch_hurricane_history() -> Tuple[List[Hurricane], HurricaneStatistics]:
    """
    Fetch hurricane data and generate statistics.
    Returns tuple of (hurricanes, statistics).
    """
    collector = HurricaneTrackCollector()
    hurricanes = collector.collect_hurricane_data()
    stats = collector.get_statistics(hurricanes)
    return hurricanes, stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hurricanes, stats = fetch_hurricane_history()

    print(f"\nHurricane Statistics for Pinellas County Region:")
    print(f"Total storms analyzed: {stats.total_storms_analyzed}")
    print(f"Storms within {ANALYSIS_CONFIG.hurricane_analysis_radius_km}km: {stats.storms_within_radius}")
    print(f"Direct hits (<50km): {stats.direct_hits_pinellas}")
    print(f"Near misses (50-100km): {stats.near_misses}")
    print(f"Average storms per decade: {stats.avg_storms_per_decade:.1f}")
    print(f"\nDeflection Analysis:")
    if stats.deflection_analysis:
        print(f"  Deflections detected: {len(stats.deflection_analysis.get('deflections', []))}")
        print(f"  Deflection rate: {stats.deflection_analysis.get('deflection_rate', 0):.1%}")
