"""
Data Manager - Handles automatic data initialization and caching

Checks if historical data has been collected. If not, fetches it automatically.
All data is persisted to the filesystem and loaded on subsequent runs.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass

from ..config import PROCESSED_DATA_DIR, CACHE_DIR, ANALYSIS_CONFIG
from ..models.schemas import FloodEvent, Hurricane, AtmosphericAnalysis

logger = logging.getLogger(__name__)


@dataclass
class DataStatus:
    """Status of collected data"""
    flood_events_ready: bool = False
    flood_events_count: int = 0
    hurricanes_ready: bool = False
    hurricanes_count: int = 0
    atmospheric_ready: bool = False
    last_updated: Optional[datetime] = None
    needs_refresh: bool = False


class DataManager:
    """
    Manages all historical data with automatic initialization and caching.

    On first run: Fetches all data from APIs and saves to filesystem
    On subsequent runs: Loads from filesystem (fast startup)
    """

    # Data file paths
    FLOOD_EVENTS_FILE = "pinellas_flood_events.json"
    HURRICANES_FILE = "hurricane_tracks.json"
    ATMOSPHERIC_FILE = "atmospheric_analysis.json"
    STATUS_FILE = "data_status.json"

    # Refresh data if older than this (days)
    DATA_REFRESH_DAYS = 30

    def __init__(self):
        self.data_dir = PROCESSED_DATA_DIR
        self.cache_dir = CACHE_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Loaded data
        self._flood_events: Optional[List[FloodEvent]] = None
        self._hurricanes: Optional[List[Hurricane]] = None
        self._atmospheric: Optional[AtmosphericAnalysis] = None
        self._status: Optional[DataStatus] = None

    def get_status_file_path(self) -> Path:
        return self.data_dir / self.STATUS_FILE

    def check_status(self) -> DataStatus:
        """Check current status of collected data."""
        status_file = self.get_status_file_path()

        if status_file.exists():
            try:
                with open(status_file) as f:
                    data = json.load(f)

                last_updated = datetime.fromisoformat(data.get('last_updated', '2000-01-01'))
                days_old = (datetime.now() - last_updated).days

                return DataStatus(
                    flood_events_ready=data.get('flood_events_ready', False),
                    flood_events_count=data.get('flood_events_count', 0),
                    hurricanes_ready=data.get('hurricanes_ready', False),
                    hurricanes_count=data.get('hurricanes_count', 0),
                    atmospheric_ready=data.get('atmospheric_ready', False),
                    last_updated=last_updated,
                    needs_refresh=days_old > self.DATA_REFRESH_DAYS
                )
            except Exception as e:
                logger.warning(f"Could not read status file: {e}")

        return DataStatus()

    def save_status(self, status: DataStatus):
        """Save current data status."""
        status_file = self.get_status_file_path()

        with open(status_file, 'w') as f:
            json.dump({
                'flood_events_ready': status.flood_events_ready,
                'flood_events_count': status.flood_events_count,
                'hurricanes_ready': status.hurricanes_ready,
                'hurricanes_count': status.hurricanes_count,
                'atmospheric_ready': status.atmospheric_ready,
                'last_updated': datetime.now().isoformat(),
            }, f, indent=2)

    def is_initialized(self) -> bool:
        """Check if all data has been collected."""
        status = self.check_status()
        return (
            status.flood_events_ready and
            status.hurricanes_ready and
            status.atmospheric_ready and
            not status.needs_refresh
        )

    def initialize(self, force_refresh: bool = False) -> DataStatus:
        """
        Initialize all data - fetch if needed, load from cache if available.

        Args:
            force_refresh: If True, re-fetch all data even if cached

        Returns:
            DataStatus indicating what was loaded/fetched
        """
        status = self.check_status()

        if self.is_initialized() and not force_refresh:
            logger.info("Data already initialized, loading from cache...")
            self._load_all_from_cache()
            return status

        logger.info("=" * 60)
        logger.info("INITIALIZING FLOOD RISK DATA")
        logger.info("This may take a few minutes on first run...")
        logger.info("=" * 60)

        # Fetch flood events
        if not status.flood_events_ready or force_refresh:
            logger.info("Fetching historical flood events...")
            self._fetch_flood_events()
            status.flood_events_ready = True
            status.flood_events_count = len(self._flood_events) if self._flood_events else 0
        else:
            self._load_flood_events()

        # Fetch hurricane data
        if not status.hurricanes_ready or force_refresh:
            logger.info("Fetching hurricane track data...")
            self._fetch_hurricanes()
            status.hurricanes_ready = True
            status.hurricanes_count = len(self._hurricanes) if self._hurricanes else 0
        else:
            self._load_hurricanes()

        # Generate atmospheric analysis
        if not status.atmospheric_ready or force_refresh:
            logger.info("Generating atmospheric analysis...")
            self._generate_atmospheric()
            status.atmospheric_ready = True
        else:
            self._load_atmospheric()

        # Save status
        self.save_status(status)

        logger.info("=" * 60)
        logger.info("DATA INITIALIZATION COMPLETE")
        logger.info(f"Flood events: {status.flood_events_count}")
        logger.info(f"Hurricanes: {status.hurricanes_count}")
        logger.info("=" * 60)

        return status

    def _fetch_flood_events(self):
        """Fetch flood events from NOAA."""
        try:
            from .noaa_storm_events import NOAAStormEventsCollector

            collector = NOAAStormEventsCollector()
            events = collector.collect_historical_floods()
            collector.save_processed_data(events, self.FLOOD_EVENTS_FILE)

            self._flood_events = events
            logger.info(f"Fetched {len(events)} flood events")

        except Exception as e:
            logger.error(f"Failed to fetch flood events: {e}")
            self._flood_events = []

    def _fetch_hurricanes(self):
        """Fetch hurricane data from NOAA."""
        try:
            from .hurricane_tracks import HurricaneTrackCollector

            collector = HurricaneTrackCollector()
            hurricanes = collector.collect_hurricane_data()
            collector.save_processed_data(hurricanes, self.HURRICANES_FILE)

            self._hurricanes = hurricanes
            logger.info(f"Fetched {len(hurricanes)} hurricane records")

        except Exception as e:
            logger.error(f"Failed to fetch hurricanes: {e}")
            self._hurricanes = []

    def _generate_atmospheric(self):
        """Generate atmospheric analysis."""
        try:
            from .atmospheric_data import AtmosphericDataCollector

            collector = AtmosphericDataCollector()

            # Get hurricane stats if available
            hurricane_stats = None
            if self._hurricanes:
                from .hurricane_tracks import HurricaneTrackCollector
                hc = HurricaneTrackCollector()
                stats = hc.get_statistics(self._hurricanes)
                hurricane_stats = stats.model_dump()

            analysis = collector.generate_atmospheric_analysis(hurricane_stats)
            collector.save_analysis(analysis, self.ATMOSPHERIC_FILE)

            self._atmospheric = analysis
            logger.info("Generated atmospheric analysis")

        except Exception as e:
            logger.error(f"Failed to generate atmospheric analysis: {e}")
            self._atmospheric = None

    def _load_flood_events(self):
        """Load flood events from cache."""
        file_path = self.data_dir / self.FLOOD_EVENTS_FILE

        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)

                self._flood_events = [
                    FloodEvent(**event) for event in data
                ]
                logger.info(f"Loaded {len(self._flood_events)} flood events from cache")

            except Exception as e:
                logger.error(f"Failed to load flood events: {e}")
                self._flood_events = []
        else:
            self._flood_events = []

    def _load_hurricanes(self):
        """Load hurricanes from cache."""
        file_path = self.data_dir / self.HURRICANES_FILE

        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)

                self._hurricanes = [
                    Hurricane(**h) for h in data
                ]
                logger.info(f"Loaded {len(self._hurricanes)} hurricanes from cache")

            except Exception as e:
                logger.error(f"Failed to load hurricanes: {e}")
                self._hurricanes = []
        else:
            self._hurricanes = []

    def _load_atmospheric(self):
        """Load atmospheric analysis from cache."""
        file_path = self.data_dir / self.ATMOSPHERIC_FILE

        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)

                self._atmospheric = AtmosphericAnalysis(**data)
                logger.info("Loaded atmospheric analysis from cache")

            except Exception as e:
                logger.error(f"Failed to load atmospheric analysis: {e}")
                self._atmospheric = None
        else:
            self._atmospheric = None

    def _load_all_from_cache(self):
        """Load all data from cache files."""
        self._load_flood_events()
        self._load_hurricanes()
        self._load_atmospheric()

    @property
    def flood_events(self) -> List[FloodEvent]:
        """Get flood events, loading from cache if needed."""
        if self._flood_events is None:
            self._load_flood_events()
        return self._flood_events or []

    @property
    def hurricanes(self) -> List[Hurricane]:
        """Get hurricanes, loading from cache if needed."""
        if self._hurricanes is None:
            self._load_hurricanes()
        return self._hurricanes or []

    @property
    def atmospheric(self) -> Optional[AtmosphericAnalysis]:
        """Get atmospheric analysis, loading from cache if needed."""
        if self._atmospheric is None:
            self._load_atmospheric()
        return self._atmospheric


# Global singleton instance
_data_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """Get the global DataManager instance."""
    global _data_manager
    if _data_manager is None:
        _data_manager = DataManager()
    return _data_manager


def ensure_data_initialized(force_refresh: bool = False) -> DataStatus:
    """
    Ensure all data is initialized and ready.
    Call this at application startup.
    """
    manager = get_data_manager()
    return manager.initialize(force_refresh=force_refresh)
