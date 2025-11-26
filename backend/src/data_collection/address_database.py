"""
Address Database for Pinellas County

Provides autocomplete functionality with accurate coordinates
from Pinellas County's official address point dataset.
"""
import json
import logging
import requests
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from ..config import CACHE_DIR, PROCESSED_DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class AddressRecord:
    """A single address with coordinates."""
    full_address: str
    street_number: str
    street_name: str
    city: str
    zip_code: str
    lat: float
    lon: float
    parcel_id: Optional[str] = None


class AddressDatabase:
    """
    Local database of Pinellas County addresses for fast autocomplete.

    Data source: Pinellas County Address Points (Open Data)
    """

    ADDRESS_FILE = "pinellas_addresses.json"
    # Pinellas County Open Data - Address Points
    DATA_URL = "https://opendata.arcgis.com/api/v3/datasets/5093d947a6a848f49ebb3d9077447ee7_0/downloads/data?format=geojson&spatialRefId=4326"
    # Backup: Direct ArcGIS REST API
    ARCGIS_URL = "https://egis.pinellascounty.org/arcgis/rest/services/Address/AddressPoints/MapServer/0/query"

    def __init__(self):
        self.data_dir = PROCESSED_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._addresses: Optional[List[AddressRecord]] = None
        self._search_index: Optional[Dict[str, List[int]]] = None

    @property
    def addresses(self) -> List[AddressRecord]:
        """Get all addresses, loading from cache if needed."""
        if self._addresses is None:
            self._load_addresses()
        return self._addresses or []

    def is_loaded(self) -> bool:
        """Check if address database is loaded."""
        return self._addresses is not None and len(self._addresses) > 0

    def _get_file_path(self) -> Path:
        return self.data_dir / self.ADDRESS_FILE

    def _load_addresses(self):
        """Load addresses from cache file."""
        file_path = self._get_file_path()

        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)

                self._addresses = [
                    AddressRecord(**addr) for addr in data
                ]
                self._build_search_index()
                logger.info(f"Loaded {len(self._addresses)} addresses from cache")

            except Exception as e:
                logger.error(f"Failed to load address cache: {e}")
                self._addresses = []
        else:
            self._addresses = []

    def _build_search_index(self):
        """Build search index for fast autocomplete."""
        if not self._addresses:
            self._search_index = {}
            return

        self._search_index = {}

        for idx, addr in enumerate(self._addresses):
            # Index by street name words
            words = addr.street_name.upper().split()
            for word in words:
                if len(word) >= 2:
                    key = word[:3]  # First 3 chars
                    if key not in self._search_index:
                        self._search_index[key] = []
                    self._search_index[key].append(idx)

            # Index by street number prefix
            if addr.street_number:
                num_key = f"#{addr.street_number[:3]}"
                if num_key not in self._search_index:
                    self._search_index[num_key] = []
                self._search_index[num_key].append(idx)

        logger.info(f"Built search index with {len(self._search_index)} keys")

    def download_addresses(self, limit: int = 50000) -> int:
        """
        Download address database from Pinellas County.

        Returns number of addresses downloaded.
        """
        logger.info("Downloading Pinellas County address database...")

        addresses = []

        try:
            # Try ArcGIS REST API (more reliable, supports pagination)
            addresses = self._fetch_from_arcgis(limit)
        except Exception as e:
            logger.warning(f"ArcGIS fetch failed: {e}")
            try:
                # Fallback to GeoJSON download
                addresses = self._fetch_from_geojson(limit)
            except Exception as e2:
                logger.error(f"GeoJSON fetch also failed: {e2}")

        if addresses:
            self._addresses = addresses
            self._save_addresses()
            self._build_search_index()
            logger.info(f"Downloaded {len(addresses)} addresses")
            return len(addresses)

        return 0

    def _fetch_from_arcgis(self, limit: int) -> List[AddressRecord]:
        """Fetch addresses from ArcGIS REST API with pagination."""
        addresses = []
        offset = 0
        batch_size = 2000

        while len(addresses) < limit:
            params = {
                'where': '1=1',
                'outFields': 'FULLADDR,ADDNUM,STREET,CITY,ZIP,LATITUDE,LONGITUDE,PARCELID',
                'returnGeometry': 'false',
                'resultOffset': offset,
                'resultRecordCount': batch_size,
                'f': 'json'
            }

            response = requests.get(self.ARCGIS_URL, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()

            features = data.get('features', [])
            if not features:
                break

            for feature in features:
                attrs = feature.get('attributes', {})

                lat = attrs.get('LATITUDE')
                lon = attrs.get('LONGITUDE')

                if lat and lon and attrs.get('FULLADDR'):
                    addresses.append(AddressRecord(
                        full_address=attrs.get('FULLADDR', ''),
                        street_number=str(attrs.get('ADDNUM', '')),
                        street_name=attrs.get('STREET', ''),
                        city=attrs.get('CITY', 'PINELLAS'),
                        zip_code=str(attrs.get('ZIP', '')),
                        lat=float(lat),
                        lon=float(lon),
                        parcel_id=attrs.get('PARCELID')
                    ))

            offset += batch_size
            logger.info(f"  Downloaded {len(addresses)} addresses...")

            if len(features) < batch_size:
                break

        return addresses[:limit]

    def _fetch_from_geojson(self, limit: int) -> List[AddressRecord]:
        """Fetch addresses from GeoJSON endpoint."""
        response = requests.get(self.DATA_URL, timeout=120)
        response.raise_for_status()
        data = response.json()

        addresses = []

        for feature in data.get('features', [])[:limit]:
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            coords = geom.get('coordinates', [])

            if len(coords) >= 2 and props.get('FULLADDR'):
                addresses.append(AddressRecord(
                    full_address=props.get('FULLADDR', ''),
                    street_number=str(props.get('ADDNUM', '')),
                    street_name=props.get('STREET', ''),
                    city=props.get('CITY', 'PINELLAS'),
                    zip_code=str(props.get('ZIP', '')),
                    lat=float(coords[1]),
                    lon=float(coords[0]),
                    parcel_id=props.get('PARCELID')
                ))

        return addresses

    def _save_addresses(self):
        """Save addresses to cache file."""
        file_path = self._get_file_path()

        data = [
            {
                'full_address': addr.full_address,
                'street_number': addr.street_number,
                'street_name': addr.street_name,
                'city': addr.city,
                'zip_code': addr.zip_code,
                'lat': addr.lat,
                'lon': addr.lon,
                'parcel_id': addr.parcel_id
            }
            for addr in self._addresses
        ]

        with open(file_path, 'w') as f:
            json.dump(data, f)

        logger.info(f"Saved {len(data)} addresses to {file_path}")

    def autocomplete(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for addresses matching the query.

        Returns list of matching addresses with coordinates.
        """
        if not query or len(query) < 2:
            return []

        if not self._addresses:
            self._load_addresses()

        if not self._addresses:
            return []

        query_upper = query.upper().strip()
        query_parts = query_upper.split()

        # Find candidate indices using search index
        candidate_indices = set()

        # Check if query starts with a number (street number search)
        if query_parts and query_parts[0].isdigit():
            num_key = f"#{query_parts[0][:3]}"
            if num_key in self._search_index:
                candidate_indices.update(self._search_index[num_key])

        # Search by street name
        for part in query_parts:
            if len(part) >= 3 and not part.isdigit():
                key = part[:3]
                if key in self._search_index:
                    if not candidate_indices:
                        candidate_indices.update(self._search_index[key])
                    else:
                        # Intersect for multiple words
                        candidate_indices &= set(self._search_index[key])

        # If no index matches, do full scan (slower but catches everything)
        if not candidate_indices:
            candidate_indices = set(range(min(5000, len(self._addresses))))

        # Score and filter candidates
        results = []

        for idx in candidate_indices:
            addr = self._addresses[idx]

            # Check if query matches
            if query_upper in addr.full_address.upper():
                # Score based on match position (earlier = better)
                pos = addr.full_address.upper().find(query_upper)
                score = 100 - pos

                # Boost exact street number match
                if query_parts and query_parts[0] == addr.street_number:
                    score += 50

                results.append({
                    'full_address': addr.full_address,
                    'city': addr.city,
                    'zip_code': addr.zip_code,
                    'lat': addr.lat,
                    'lon': addr.lon,
                    'score': score
                })

        # Sort by score and return top matches
        results.sort(key=lambda x: x['score'], reverse=True)

        # Remove score from output
        for r in results:
            del r['score']

        return results[:limit]

    def get_address(self, full_address: str) -> Optional[Dict]:
        """Get exact address match with coordinates."""
        if not self._addresses:
            self._load_addresses()

        search = full_address.upper().strip()

        for addr in self._addresses:
            if addr.full_address.upper() == search:
                return {
                    'full_address': addr.full_address,
                    'city': addr.city,
                    'zip_code': addr.zip_code,
                    'lat': addr.lat,
                    'lon': addr.lon
                }

        return None


# Global singleton
_address_db: Optional[AddressDatabase] = None


def get_address_database() -> AddressDatabase:
    """Get the global AddressDatabase instance."""
    global _address_db
    if _address_db is None:
        _address_db = AddressDatabase()
    return _address_db
