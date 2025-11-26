"""
Property Data Collector

Fetches property data from Pinellas County Property Appraiser
and related public records for flood risk assessment.

Data Sources:
- Pinellas County Property Appraiser GIS
- Pinellas County Open Data Portal
- FEMA National Flood Hazard Layer (for comparison)
"""
import logging
import json
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import requests

from ..config import (
    PINELLAS_BOUNDS,
    DATA_URLS,
    CACHE_DIR,
    PROCESSED_DATA_DIR
)
from ..models.schemas import Property

logger = logging.getLogger(__name__)


class PropertyDataCollector:
    """
    Collects property data from Pinellas County public records.

    Integrates with:
    - Pinellas County Property Appraiser GIS services
    - FEMA flood zone data for comparison
    - Geocoding services for address lookup
    """

    def __init__(self):
        self.bounds = PINELLAS_BOUNDS
        self.pa_gis_url = DATA_URLS.pinellas_pa_gis
        self.fema_nfhl_url = DATA_URLS.fema_nfhl_base
        self.cache_dir = CACHE_DIR / "properties"
        self.cache_dir.mkdir(exist_ok=True)

    def geocode_address(
        self,
        address: str,
        city: str = "St Petersburg",
        state: str = "FL",
        zip_code: Optional[str] = None
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode an address to lat/lon coordinates.

        Uses free Nominatim (OpenStreetMap) API.
        For production, consider using Pinellas County's geocoding service.
        """
        # Build full address string
        full_address = f"{address}, {city}, {state}"
        if zip_code:
            full_address += f" {zip_code}"

        # Check cache
        cache_key = full_address.replace(" ", "_").replace(",", "")[:100]
        cache_file = self.cache_dir / f"geocode_{cache_key}.json"

        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
                return (data['lat'], data['lon'])

        try:
            # Use Nominatim (OpenStreetMap) for geocoding
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': full_address,
                'format': 'json',
                'limit': 1,
                'countrycodes': 'us'
            }
            headers = {
                'User-Agent': 'PinellasFloodRisk/1.0'
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()

            results = response.json()

            if results:
                lat = float(results[0]['lat'])
                lon = float(results[0]['lon'])

                # Cache result
                with open(cache_file, 'w') as f:
                    json.dump({'lat': lat, 'lon': lon, 'address': full_address}, f)

                return (lat, lon)
            else:
                logger.warning(f"No geocoding results for: {full_address}")
                return None

        except requests.RequestException as e:
            logger.error(f"Geocoding failed for {full_address}: {e}")
            return None

    def get_fema_flood_zone(self, lat: float, lon: float) -> Optional[str]:
        """
        Query FEMA NFHL for the flood zone at a given location.

        Returns zone designation (e.g., "AE", "X", "VE")
        """
        cache_key = f"fema_{lat:.6f}_{lon:.6f}"
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f).get('zone')

        try:
            # FEMA NFHL ArcGIS REST API
            # Layer 28 is typically the flood hazard zones layer
            url = f"{self.fema_nfhl_url}/28/query"

            params = {
                'geometry': f'{lon},{lat}',
                'geometryType': 'esriGeometryPoint',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': 'FLD_ZONE,ZONE_SUBTY,STATIC_BFE',
                'returnGeometry': 'false',
                'f': 'json'
            }

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if 'features' in data and data['features']:
                attrs = data['features'][0].get('attributes', {})
                zone = attrs.get('FLD_ZONE', 'Unknown')

                # Cache result
                with open(cache_file, 'w') as f:
                    json.dump({'zone': zone, 'attributes': attrs}, f)

                return zone
            else:
                return None

        except requests.RequestException as e:
            logger.error(f"FEMA query failed for ({lat}, {lon}): {e}")
            return None

    def query_pinellas_parcels(
        self,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Query Pinellas County parcel data within a bounding box.

        Note: This queries the county's ArcGIS REST services.
        Results are cached to minimize API calls.
        """
        min_lat = min_lat or self.bounds.min_lat
        max_lat = max_lat or self.bounds.max_lat
        min_lon = min_lon or self.bounds.min_lon
        max_lon = max_lon or self.bounds.max_lon

        # Check cache
        cache_key = f"parcels_{min_lat:.4f}_{max_lat:.4f}_{min_lon:.4f}_{max_lon:.4f}"
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            logger.info("Loading cached parcel data")
            with open(cache_file) as f:
                return json.load(f)

        try:
            # Pinellas County Parcel layer
            # Note: The actual service URL may need adjustment based on
            # Pinellas County's current ArcGIS service configuration
            url = f"{self.pa_gis_url}/Property/Parcels/MapServer/0/query"

            # Build envelope geometry
            envelope = f'{min_lon},{min_lat},{max_lon},{max_lat}'

            params = {
                'geometry': envelope,
                'geometryType': 'esriGeometryEnvelope',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': '*',
                'returnGeometry': 'true',
                'resultRecordCount': limit,
                'f': 'json'
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            parcels = []
            if 'features' in data:
                for feature in data['features']:
                    attrs = feature.get('attributes', {})
                    geom = feature.get('geometry', {})

                    # Extract centroid for properties with polygon geometry
                    if 'rings' in geom and geom['rings']:
                        ring = geom['rings'][0]
                        lon = sum(p[0] for p in ring) / len(ring)
                        lat = sum(p[1] for p in ring) / len(ring)
                    else:
                        lat = attrs.get('LATITUDE', 0)
                        lon = attrs.get('LONGITUDE', 0)

                    parcels.append({
                        'parcel_id': attrs.get('PARCEL_ID', ''),
                        'address': attrs.get('SITE_ADDR', ''),
                        'city': attrs.get('SITE_CITY', ''),
                        'zip_code': attrs.get('SITE_ZIP', ''),
                        'lat': lat,
                        'lon': lon,
                        'year_built': attrs.get('YEAR_BUILT'),
                        'property_type': attrs.get('PROPERTY_USE', ''),
                        'assessed_value': attrs.get('ASSESSED_VALUE'),
                        'raw_attributes': attrs
                    })

            # Cache results
            with open(cache_file, 'w') as f:
                json.dump(parcels, f)

            logger.info(f"Retrieved {len(parcels)} parcels from Pinellas County")
            return parcels

        except requests.RequestException as e:
            logger.error(f"Parcel query failed: {e}")
            return []

    def search_property_by_address(
        self,
        address: str,
        city: str = "St Petersburg"
    ) -> Optional[Property]:
        """
        Search for a property by address.

        Returns Property object with all available data.
        """
        # First geocode the address
        coords = self.geocode_address(address, city)

        if not coords:
            logger.warning(f"Could not geocode address: {address}, {city}")
            return None

        lat, lon = coords

        # Get FEMA flood zone
        fema_zone = self.get_fema_flood_zone(lat, lon)

        # Create property object
        property_obj = Property(
            parcel_id="",  # Would need parcel query to get this
            address=address,
            city=city,
            zip_code="",
            lat=lat,
            lon=lon,
            fema_flood_zone=fema_zone
        )

        return property_obj

    def get_property_with_flood_data(
        self,
        lat: float,
        lon: float,
        address: Optional[str] = None
    ) -> Property:
        """
        Get property information with flood zone data for a specific location.
        """
        fema_zone = self.get_fema_flood_zone(lat, lon)

        return Property(
            parcel_id="",
            address=address or f"{lat:.6f}, {lon:.6f}",
            city="Pinellas County",
            zip_code="",
            lat=lat,
            lon=lon,
            fema_flood_zone=fema_zone
        )

    def interpret_fema_zone(self, zone: str) -> Dict[str, any]:
        """
        Interpret FEMA flood zone designation.

        Returns human-readable explanation and risk level.
        """
        zone_info = {
            'A': {
                'risk_level': 'high',
                'description': 'High-risk flood area with 1% annual chance of flooding',
                'insurance_required': True,
                'base_flood_elevation': 'Not determined'
            },
            'AE': {
                'risk_level': 'high',
                'description': 'High-risk area with determined Base Flood Elevations',
                'insurance_required': True,
                'base_flood_elevation': 'Determined'
            },
            'AH': {
                'risk_level': 'high',
                'description': 'High-risk shallow flooding area (1-3 feet)',
                'insurance_required': True,
                'base_flood_elevation': 'Determined'
            },
            'AO': {
                'risk_level': 'high',
                'description': 'High-risk sheet flow flooding area',
                'insurance_required': True,
                'base_flood_elevation': 'Depth specified'
            },
            'VE': {
                'risk_level': 'very_high',
                'description': 'High-risk coastal area with wave action',
                'insurance_required': True,
                'base_flood_elevation': 'Determined'
            },
            'V': {
                'risk_level': 'very_high',
                'description': 'High-risk coastal area with wave action',
                'insurance_required': True,
                'base_flood_elevation': 'Not determined'
            },
            'X': {
                'risk_level': 'low_to_moderate',
                'description': 'Area of minimal to moderate flood risk',
                'insurance_required': False,
                'base_flood_elevation': 'N/A'
            },
            'B': {
                'risk_level': 'moderate',
                'description': 'Moderate flood risk area (0.2% annual chance)',
                'insurance_required': False,
                'base_flood_elevation': 'N/A'
            },
            'C': {
                'risk_level': 'low',
                'description': 'Minimal flood risk area',
                'insurance_required': False,
                'base_flood_elevation': 'N/A'
            },
            'D': {
                'risk_level': 'unknown',
                'description': 'Undetermined flood risk - no analysis performed',
                'insurance_required': False,
                'base_flood_elevation': 'Unknown'
            }
        }

        # Handle zone variations (e.g., "AE" vs "AE-FW")
        base_zone = zone.split('-')[0].upper() if zone else 'Unknown'

        if base_zone in zone_info:
            return zone_info[base_zone]
        else:
            return {
                'risk_level': 'unknown',
                'description': f'Unknown flood zone: {zone}',
                'insurance_required': None,
                'base_flood_elevation': 'Unknown'
            }

    def export_sample_properties(
        self,
        sample_size: int = 100,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Export a sample of properties with flood zone data for testing.
        """
        output_path = output_path or (PROCESSED_DATA_DIR / "sample_properties.json")

        # Query parcels
        parcels = self.query_pinellas_parcels(limit=sample_size)

        properties = []
        for parcel in parcels[:sample_size]:
            if parcel['lat'] and parcel['lon']:
                fema_zone = self.get_fema_flood_zone(parcel['lat'], parcel['lon'])

                prop = Property(
                    parcel_id=parcel['parcel_id'],
                    address=parcel['address'],
                    city=parcel['city'],
                    zip_code=parcel['zip_code'],
                    lat=parcel['lat'],
                    lon=parcel['lon'],
                    fema_flood_zone=fema_zone,
                    year_built=parcel.get('year_built'),
                    property_type=parcel.get('property_type'),
                    assessed_value=parcel.get('assessed_value')
                )
                properties.append(prop.model_dump())

        with open(output_path, 'w') as f:
            json.dump(properties, f, indent=2)

        logger.info(f"Exported {len(properties)} sample properties to {output_path}")
        return output_path


# Convenience functions
def lookup_property(address: str, city: str = "St Petersburg") -> Optional[Property]:
    """Quick property lookup by address."""
    collector = PropertyDataCollector()
    return collector.search_property_by_address(address, city)


def get_fema_zone(lat: float, lon: float) -> Tuple[Optional[str], Dict]:
    """Get FEMA flood zone and interpretation for a location."""
    collector = PropertyDataCollector()
    zone = collector.get_fema_flood_zone(lat, lon)
    interpretation = collector.interpret_fema_zone(zone) if zone else {}
    return zone, interpretation


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test geocoding and FEMA lookup
    collector = PropertyDataCollector()

    # Test address
    test_address = "100 Central Ave"
    test_city = "St Petersburg"

    print(f"\nLooking up: {test_address}, {test_city}, FL")

    coords = collector.geocode_address(test_address, test_city)
    if coords:
        lat, lon = coords
        print(f"Coordinates: {lat:.6f}, {lon:.6f}")

        zone = collector.get_fema_flood_zone(lat, lon)
        if zone:
            print(f"FEMA Flood Zone: {zone}")
            interp = collector.interpret_fema_zone(zone)
            print(f"Risk Level: {interp['risk_level']}")
            print(f"Description: {interp['description']}")
            print(f"Insurance Required: {interp['insurance_required']}")
