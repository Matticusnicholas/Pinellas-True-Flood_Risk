"""
Data Manager - Handles automatic data initialization and caching

Supports two modes:
- QUICK_START: Uses demo data, starts instantly (set QUICK_START=1)
- FULL: Downloads 50 years of NOAA data on first run

All data is persisted to the filesystem and loaded on subsequent runs.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from ..config import PROCESSED_DATA_DIR, CACHE_DIR, ANALYSIS_CONFIG
from ..models.schemas import FloodEvent, Hurricane, AtmosphericAnalysis

logger = logging.getLogger(__name__)

# Check for quick start mode
QUICK_START = os.environ.get('QUICK_START', '').lower() in ('1', 'true', 'yes')


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
    is_demo_data: bool = False


class DataManager:
    """
    Manages all historical data with automatic initialization and caching.
    """

    FLOOD_EVENTS_FILE = "pinellas_flood_events.json"
    HURRICANES_FILE = "hurricane_tracks.json"
    ATMOSPHERIC_FILE = "atmospheric_analysis.json"
    STATUS_FILE = "data_status.json"
    DATA_REFRESH_DAYS = 30

    def __init__(self):
        self.data_dir = PROCESSED_DATA_DIR
        self.cache_dir = CACHE_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

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
                    needs_refresh=days_old > self.DATA_REFRESH_DAYS,
                    is_demo_data=data.get('is_demo_data', False)
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
                'is_demo_data': status.is_demo_data,
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

    def initialize(self, force_refresh: bool = False, quick_start: bool = None) -> DataStatus:
        """
        Initialize all data.

        Args:
            force_refresh: Re-fetch all data even if cached
            quick_start: Use demo data (overrides env var if set)
        """
        # Check for quick start mode
        use_quick_start = quick_start if quick_start is not None else QUICK_START

        status = self.check_status()

        # If already initialized with real data, load from cache
        if self.is_initialized() and not force_refresh and not status.is_demo_data:
            logger.info("Data already initialized, loading from cache...")
            self._load_all_from_cache()
            return status

        if use_quick_start:
            logger.info("=" * 60)
            logger.info("QUICK START MODE - Using demo data")
            logger.info("Set QUICK_START=0 to download real historical data")
            logger.info("=" * 60)
            return self._initialize_demo_data()

        logger.info("=" * 60)
        logger.info("INITIALIZING FLOOD RISK DATA")
        logger.info("Downloading historical data from NOAA...")
        logger.info("This will take 5-10 minutes on first run.")
        logger.info("=" * 60)

        # Fetch flood events
        if not status.flood_events_ready or force_refresh:
            logger.info("")
            logger.info("[1/3] Fetching flood events from NOAA Storm Database...")
            self._fetch_flood_events()
            status.flood_events_ready = True
            status.flood_events_count = len(self._flood_events) if self._flood_events else 0
            self.save_status(status)  # Save progress
        else:
            self._load_flood_events()

        # Fetch hurricane data
        if not status.hurricanes_ready or force_refresh:
            logger.info("")
            logger.info("[2/3] Fetching hurricane tracks from NOAA HURDAT2...")
            self._fetch_hurricanes()
            status.hurricanes_ready = True
            status.hurricanes_count = len(self._hurricanes) if self._hurricanes else 0
            self.save_status(status)  # Save progress
        else:
            self._load_hurricanes()

        # Generate atmospheric analysis
        if not status.atmospheric_ready or force_refresh:
            logger.info("")
            logger.info("[3/3] Generating atmospheric analysis...")
            self._generate_atmospheric()
            status.atmospheric_ready = True
            self.save_status(status)  # Save progress
        else:
            self._load_atmospheric()

        status.is_demo_data = False
        self.save_status(status)

        logger.info("")
        logger.info("=" * 60)
        logger.info("DATA INITIALIZATION COMPLETE")
        logger.info(f"  Flood events: {status.flood_events_count}")
        logger.info(f"  Hurricanes: {status.hurricanes_count}")
        logger.info("=" * 60)

        return status

    def _initialize_demo_data(self) -> DataStatus:
        """Initialize with demo data for quick testing."""
        self._flood_events = []
        self._hurricanes = []
        self._atmospheric = self._create_demo_atmospheric()

        status = DataStatus(
            flood_events_ready=True,
            flood_events_count=0,
            hurricanes_ready=True,
            hurricanes_count=0,
            atmospheric_ready=True,
            last_updated=datetime.now(),
            is_demo_data=True
        )

        self.save_status(status)
        logger.info("Demo data initialized - API will use default risk calculations")

        return status

    def _create_demo_atmospheric(self) -> AtmosphericAnalysis:
        """Create demo atmospheric analysis."""
        return AtmosphericAnalysis(
            analysis_period_start=datetime(1974, 1, 1),
            analysis_period_end=datetime.now(),
            avg_jet_stream_position=30.5,
            dominant_pattern="subtropical_ridge",
            gulf_thermal_gradient=1.5,
            wind_shear_index=15.0,
            protection_factor=0.25,
            findings=[
                "Demo mode - using estimated atmospheric patterns",
                "Run with QUICK_START=0 to analyze real historical data"
            ]
        )

    def _fetch_flood_events(self):
        """Fetch flood events from NOAA."""
        try:
            from .noaa_storm_events import NOAAStormEventsCollector

            collector = NOAAStormEventsCollector()

            # Fetch with progress logging - only recent 10 years for faster startup
            # Full 50 years can be fetched later via refresh endpoint
            logger.info("  Downloading recent flood event data (2014-2024)...")
            logger.info("  Use /api/v1/data/refresh to download full 50-year history")

            events = collector.collect_historical_floods(
                start_year=2014,  # Recent 10 years for faster first startup
                end_year=2024
            )
            collector.save_processed_data(events, self.FLOOD_EVENTS_FILE)

            self._flood_events = events
            logger.info(f"  Downloaded {len(events)} flood events")

        except Exception as e:
            logger.error(f"  Failed to fetch flood events: {e}")
            logger.info("  Continuing with empty flood history...")
            self._flood_events = []

    def _fetch_hurricanes(self):
        """Fetch hurricane data from NOAA."""
        try:
            from .hurricane_tracks import HurricaneTrackCollector

            collector = HurricaneTrackCollector()
            logger.info("  Downloading HURDAT2 hurricane database...")

            hurricanes = collector.collect_hurricane_data()
            collector.save_processed_data(hurricanes, self.HURRICANES_FILE)

            self._hurricanes = hurricanes
            logger.info(f"  Downloaded {len(hurricanes)} hurricane records")

        except Exception as e:
            logger.error(f"  Failed to fetch hurricanes: {e}")
            logger.info("  Continuing with empty hurricane history...")
            self._hurricanes = []

    def _generate_atmospheric(self):
        """Generate atmospheric analysis."""
        try:
            from .atmospheric_data import AtmosphericDataCollector

            collector = AtmosphericDataCollector()

            hurricane_stats = None
            if self._hurricanes:
                from .hurricane_tracks import HurricaneTrackCollector
                hc = HurricaneTrackCollector()
                stats = hc.get_statistics(self._hurricanes)
                hurricane_stats = stats.model_dump()

            analysis = collector.generate_atmospheric_analysis(hurricane_stats)
            collector.save_analysis(analysis, self.ATMOSPHERIC_FILE)

            self._atmospheric = analysis
            logger.info("  Generated atmospheric analysis")

        except Exception as e:
            logger.error(f"  Failed to generate atmospheric analysis: {e}")
            self._atmospheric = self._create_demo_atmospheric()

    def _load_flood_events(self):
        """Load flood events from cache."""
        file_path = self.data_dir / self.FLOOD_EVENTS_FILE

        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)

                self._flood_events = [FloodEvent(**event) for event in data]
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

                self._hurricanes = [Hurricane(**h) for h in data]
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
        if self._flood_events is None:
            self._load_flood_events()
        return self._flood_events or []

    @property
    def hurricanes(self) -> List[Hurricane]:
        if self._hurricanes is None:
            self._load_hurricanes()
        return self._hurricanes or []

    @property
    def atmospheric(self) -> Optional[AtmosphericAnalysis]:
        if self._atmospheric is None:
            self._load_atmospheric()
        return self._atmospheric


# Global singleton
_data_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """Get the global DataManager instance."""
    global _data_manager
    if _data_manager is None:
        _data_manager = DataManager()
    return _data_manager


def ensure_data_initialized(force_refresh: bool = False, quick_start: bool = None) -> DataStatus:
    """Ensure all data is initialized and ready."""
    manager = get_data_manager()
    return manager.initialize(force_refresh=force_refresh, quick_start=quick_start)
