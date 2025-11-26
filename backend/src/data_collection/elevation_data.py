"""
Elevation Data Collector

Fetches high-resolution elevation data from USGS 3DEP (3D Elevation Program)
to create detailed flood zone maps based on actual topography.

Data Source: USGS 3DEP via National Map API
https://apps.nationalmap.gov/epqs/
"""
import logging
import asyncio
import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import (
    PINELLAS_BOUNDS,
    DATA_URLS,
    ANALYSIS_CONFIG,
    CACHE_DIR,
    PROCESSED_DATA_DIR
)
from ..models.schemas import ElevationPoint, ElevationGrid

logger = logging.getLogger(__name__)


class ElevationDataCollector:
    """
    Collects elevation data from USGS 3DEP for flood risk analysis.

    The 3DEP program provides high-resolution elevation data (1-10m)
    for the entire United States, which is critical for determining
    flood risk at the property level.
    """

    def __init__(self):
        self.bounds = PINELLAS_BOUNDS
        self.api_url = DATA_URLS.usgs_elevation_api
        self.cache_dir = CACHE_DIR / "elevation"
        self.cache_dir.mkdir(exist_ok=True)

    def get_elevation_point(self, lat: float, lon: float) -> Optional[ElevationPoint]:
        """
        Get elevation for a single point.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            ElevationPoint with elevation in meters and feet
        """
        # Check cache first
        cache_key = f"{lat:.6f}_{lon:.6f}"
        cache_file = self.cache_dir / f"point_{cache_key}.json"

        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
                return ElevationPoint(**data)

        try:
            # USGS EPQS API
            params = {
                'x': lon,
                'y': lat,
                'units': 'Meters',
                'output': 'json'
            }

            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Parse response - format varies slightly
            if 'value' in data:
                elevation_m = float(data['value'])
            elif 'USGS_Elevation_Point_Query_Service' in data:
                elevation_m = float(
                    data['USGS_Elevation_Point_Query_Service']
                    ['Elevation_Query']['Elevation']
                )
            else:
                logger.warning(f"Unexpected API response format: {data}")
                return None

            # Handle "no data" values
            if elevation_m < -1000:
                elevation_m = 0.0  # Assume sea level for water/missing data

            point = ElevationPoint(
                lat=lat,
                lon=lon,
                elevation_m=elevation_m,
                elevation_ft=elevation_m * 3.28084,
                data_source="USGS 3DEP"
            )

            # Cache the result
            with open(cache_file, 'w') as f:
                json.dump(point.model_dump(), f)

            return point

        except requests.RequestException as e:
            logger.error(f"Failed to fetch elevation for ({lat}, {lon}): {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse elevation data: {e}")
            return None

    def get_elevation_batch(
        self,
        points: List[Tuple[float, float]],
        max_workers: int = 5
    ) -> List[Optional[ElevationPoint]]:
        """
        Get elevation for multiple points in parallel.

        Args:
            points: List of (lat, lon) tuples
            max_workers: Number of parallel requests

        Returns:
            List of ElevationPoint objects (None for failed requests)
        """
        results = [None] * len(points)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.get_elevation_point, lat, lon): idx
                for idx, (lat, lon) in enumerate(points)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Error fetching elevation for point {idx}: {e}")
                    results[idx] = None

        return results

    def create_elevation_grid(
        self,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        resolution_m: Optional[float] = None,
        use_cache: bool = True
    ) -> ElevationGrid:
        """
        Create a grid of elevation data for the specified area.

        Args:
            min_lat, max_lat, min_lon, max_lon: Bounding box (defaults to Pinellas)
            resolution_m: Grid resolution in meters (default: from config)
            use_cache: Whether to use/update cache

        Returns:
            ElevationGrid with 2D array of elevations
        """
        # Use defaults from config/bounds
        min_lat = min_lat or self.bounds.min_lat
        max_lat = max_lat or self.bounds.max_lat
        min_lon = min_lon or self.bounds.min_lon
        max_lon = max_lon or self.bounds.max_lon
        resolution_m = resolution_m or ANALYSIS_CONFIG.elevation_grid_resolution_m

        # Convert resolution from meters to degrees (approximate)
        # 1 degree latitude ≈ 111km
        # 1 degree longitude ≈ 111km * cos(lat) ≈ 97km at 28°N
        lat_step = resolution_m / 111000
        lon_step = resolution_m / 97000  # Approximate for Pinellas latitude

        # Check for cached grid
        cache_key = f"grid_{min_lat:.4f}_{max_lat:.4f}_{min_lon:.4f}_{max_lon:.4f}_{resolution_m:.0f}"
        cache_file = self.cache_dir / f"{cache_key}.json"

        if use_cache and cache_file.exists():
            logger.info("Loading cached elevation grid")
            with open(cache_file) as f:
                data = json.load(f)
                return ElevationGrid(**data)

        # Generate grid points
        lats = []
        lat = min_lat
        while lat <= max_lat:
            lats.append(lat)
            lat += lat_step

        lons = []
        lon = min_lon
        while lon <= max_lon:
            lons.append(lon)
            lon += lon_step

        logger.info(f"Creating elevation grid: {len(lats)} x {len(lons)} = {len(lats) * len(lons)} points")

        # Collect all points
        all_points = [(lat, lon) for lat in lats for lon in lons]

        # Fetch elevations (this may take a while for large grids)
        # Using batching to avoid overwhelming the API
        batch_size = 100
        all_elevations = []

        for i in range(0, len(all_points), batch_size):
            batch = all_points[i:i + batch_size]
            logger.info(f"Fetching batch {i // batch_size + 1}/{(len(all_points) - 1) // batch_size + 1}")

            elevations = self.get_elevation_batch(batch, max_workers=5)
            all_elevations.extend(elevations)

            # Small delay to be nice to the API
            import time
            time.sleep(0.5)

        # Reshape into grid
        grid_data = []
        idx = 0
        for lat in lats:
            row = []
            for lon in lons:
                elev = all_elevations[idx]
                row.append(elev.elevation_m if elev else 0.0)
                idx += 1
            grid_data.append(row)

        # Calculate statistics
        all_elevations_m = [e for row in grid_data for e in row if e is not None]
        stats = {
            'min_elevation_m': min(all_elevations_m) if all_elevations_m else 0,
            'max_elevation_m': max(all_elevations_m) if all_elevations_m else 0,
            'mean_elevation_m': sum(all_elevations_m) / len(all_elevations_m) if all_elevations_m else 0,
            'total_points': len(all_elevations_m),
            'below_2m_pct': len([e for e in all_elevations_m if e < 2]) / len(all_elevations_m) * 100 if all_elevations_m else 0,
            'below_5m_pct': len([e for e in all_elevations_m if e < 5]) / len(all_elevations_m) * 100 if all_elevations_m else 0,
        }

        grid = ElevationGrid(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            resolution_m=resolution_m,
            grid_data=grid_data,
            stats=stats
        )

        # Cache the result
        if use_cache:
            with open(cache_file, 'w') as f:
                json.dump(grid.model_dump(), f)
            logger.info(f"Cached elevation grid to {cache_file}")

        return grid

    def get_elevation_risk_score(self, elevation_m: float) -> float:
        """
        Calculate risk score based on elevation.

        Returns score from 0 (no risk) to 100 (extreme risk).
        """
        config = ANALYSIS_CONFIG

        if elevation_m < config.elevation_very_high_risk:
            # Below 2m: very high risk (80-100)
            return 100 - (elevation_m / config.elevation_very_high_risk * 20)
        elif elevation_m < config.elevation_high_risk:
            # 2-5m: high risk (60-80)
            return 80 - ((elevation_m - config.elevation_very_high_risk) /
                         (config.elevation_high_risk - config.elevation_very_high_risk) * 20)
        elif elevation_m < config.elevation_moderate_risk:
            # 5-10m: moderate risk (40-60)
            return 60 - ((elevation_m - config.elevation_high_risk) /
                         (config.elevation_moderate_risk - config.elevation_high_risk) * 20)
        elif elevation_m < config.elevation_low_risk:
            # 10-20m: low risk (20-40)
            return 40 - ((elevation_m - config.elevation_moderate_risk) /
                         (config.elevation_low_risk - config.elevation_moderate_risk) * 20)
        else:
            # Above 20m: very low risk (0-20)
            return max(0, 20 - (elevation_m - config.elevation_low_risk))

    def analyze_flood_zones_by_elevation(
        self,
        grid: ElevationGrid
    ) -> Dict[str, any]:
        """
        Analyze flood risk zones based on elevation grid.

        Returns breakdown of land area by flood risk category.
        """
        zones = {
            'very_high_risk': [],   # < 2m
            'high_risk': [],        # 2-5m
            'moderate_risk': [],    # 5-10m
            'low_risk': [],         # 10-20m
            'very_low_risk': []     # > 20m
        }

        config = ANALYSIS_CONFIG
        lat_step = (grid.max_lat - grid.min_lat) / (len(grid.grid_data) - 1) if len(grid.grid_data) > 1 else 0
        lon_step = (grid.max_lon - grid.min_lon) / (len(grid.grid_data[0]) - 1) if grid.grid_data and len(grid.grid_data[0]) > 1 else 0

        for i, row in enumerate(grid.grid_data):
            lat = grid.min_lat + i * lat_step
            for j, elev in enumerate(row):
                lon = grid.min_lon + j * lon_step
                point = {'lat': lat, 'lon': lon, 'elevation_m': elev}

                if elev < config.elevation_very_high_risk:
                    zones['very_high_risk'].append(point)
                elif elev < config.elevation_high_risk:
                    zones['high_risk'].append(point)
                elif elev < config.elevation_moderate_risk:
                    zones['moderate_risk'].append(point)
                elif elev < config.elevation_low_risk:
                    zones['low_risk'].append(point)
                else:
                    zones['very_low_risk'].append(point)

        total_points = sum(len(z) for z in zones.values())

        return {
            'zones': {k: len(v) for k, v in zones.items()},
            'percentages': {k: len(v) / total_points * 100 for k, v in zones.items()} if total_points > 0 else {},
            'detailed_zones': zones,
            'grid_stats': grid.stats
        }

    def export_to_geojson(
        self,
        grid: ElevationGrid,
        output_path: Optional[Path] = None
    ) -> Path:
        """Export elevation grid as GeoJSON for mapping."""
        output_path = output_path or (PROCESSED_DATA_DIR / "elevation_grid.geojson")

        features = []
        lat_step = (grid.max_lat - grid.min_lat) / (len(grid.grid_data) - 1) if len(grid.grid_data) > 1 else 0
        lon_step = (grid.max_lon - grid.min_lon) / (len(grid.grid_data[0]) - 1) if grid.grid_data and len(grid.grid_data[0]) > 1 else 0

        for i, row in enumerate(grid.grid_data):
            lat = grid.min_lat + i * lat_step
            for j, elev in enumerate(row):
                lon = grid.min_lon + j * lon_step

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": {
                        "elevation_m": elev,
                        "elevation_ft": elev * 3.28084,
                        "risk_score": self.get_elevation_risk_score(elev)
                    }
                }
                features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        with open(output_path, 'w') as f:
            json.dump(geojson, f)

        logger.info(f"Exported elevation grid to {output_path}")
        return output_path


# Convenience function
def get_pinellas_elevation_data(
    resolution_m: float = 100  # 100m resolution for faster initial analysis
) -> Tuple[ElevationGrid, Dict]:
    """
    Get elevation grid and analysis for Pinellas County.

    Args:
        resolution_m: Grid resolution in meters (smaller = more detailed but slower)

    Returns:
        Tuple of (ElevationGrid, zone_analysis)
    """
    collector = ElevationDataCollector()
    grid = collector.create_elevation_grid(resolution_m=resolution_m)
    analysis = collector.analyze_flood_zones_by_elevation(grid)
    return grid, analysis


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with a single point (St. Petersburg downtown)
    collector = ElevationDataCollector()
    point = collector.get_elevation_point(27.7676, -82.6403)

    if point:
        print(f"\nElevation at St. Petersburg downtown:")
        print(f"  {point.elevation_m:.2f} meters ({point.elevation_ft:.2f} feet)")
        print(f"  Risk score: {collector.get_elevation_risk_score(point.elevation_m):.1f}/100")

    # Create a small test grid (use larger resolution for quick test)
    print("\nCreating test elevation grid (500m resolution)...")
    grid, analysis = get_pinellas_elevation_data(resolution_m=500)

    print(f"\nElevation Analysis:")
    print(f"  Grid size: {len(grid.grid_data)} x {len(grid.grid_data[0]) if grid.grid_data else 0}")
    print(f"  Elevation range: {grid.stats['min_elevation_m']:.1f}m - {grid.stats['max_elevation_m']:.1f}m")
    print(f"  Mean elevation: {grid.stats['mean_elevation_m']:.1f}m")
    print(f"\nFlood Risk Zones:")
    for zone, pct in analysis['percentages'].items():
        print(f"  {zone}: {pct:.1f}%")
