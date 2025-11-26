"""
NOAA Storm Events Database Collector

Fetches and processes historical flood events for Pinellas County, FL
from the NOAA Storm Events Database (1950-present).

Data Source: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
"""
import os
import gzip
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Generator
import requests
import pandas as pd
from io import BytesIO, StringIO

from ..config import (
    PINELLAS_BOUNDS,
    DATA_URLS,
    ANALYSIS_CONFIG,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    CACHE_DIR
)
from ..models.schemas import FloodEvent, FloodEventSummary

logger = logging.getLogger(__name__)


class NOAAStormEventsCollector:
    """
    Collects and processes storm events from NOAA Storm Events Database.

    The Storm Events Database contains records of significant weather phenomena
    including floods, flash floods, coastal floods, and storm surge events.
    """

    # Event types we're interested in for flood analysis
    FLOOD_EVENT_TYPES = [
        "Flash Flood",
        "Flood",
        "Coastal Flood",
        "Storm Surge/Tide",
        "Heavy Rain",
        "Tropical Storm",
        "Hurricane",
        "Hurricane (Typhoon)",
        "Tropical Depression",
    ]

    def __init__(self):
        self.base_url = DATA_URLS.noaa_storm_events_base
        self.bounds = PINELLAS_BOUNDS
        self.cache_dir = CACHE_DIR / "storm_events"
        self.cache_dir.mkdir(exist_ok=True)

    def _get_year_files(self, start_year: int, end_year: int) -> List[str]:
        """Generate list of storm events files to download by year."""
        files = []
        for year in range(start_year, end_year + 1):
            # NOAA uses format: StormEvents_details-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz
            # The exact filename varies, so we'll search for the pattern
            files.append(f"StormEvents_details-ftp_v1.0_d{year}")
        return files

    def _download_year_data(self, year: int) -> Optional[pd.DataFrame]:
        """Download storm events data for a specific year."""
        cache_file = self.cache_dir / f"storm_events_{year}.parquet"

        # Check cache first
        if cache_file.exists():
            logger.info(f"Loading cached data for {year}")
            return pd.read_parquet(cache_file)

        # List available files from NOAA
        try:
            logger.info(f"Fetching storm events index from NOAA...")
            response = requests.get(self.base_url, timeout=30)
            response.raise_for_status()

            # Find the file for this year
            import re
            pattern = rf'StormEvents_details-ftp_v1\.0_d{year}_c\d+\.csv\.gz'
            matches = re.findall(pattern, response.text)

            if not matches:
                logger.warning(f"No storm events file found for {year}")
                return None

            # Use the most recent file (last in sorted list)
            filename = sorted(matches)[-1]
            file_url = f"{self.base_url}{filename}"

            logger.info(f"Downloading {filename}...")
            response = requests.get(file_url, timeout=120)
            response.raise_for_status()

            # Decompress and read CSV
            with gzip.GzipFile(fileobj=BytesIO(response.content)) as gz:
                df = pd.read_csv(gz, low_memory=False)

            # Cache for future use
            df.to_parquet(cache_file)
            logger.info(f"Cached {len(df)} records for {year}")

            return df

        except requests.RequestException as e:
            logger.error(f"Failed to download data for {year}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing data for {year}: {e}")
            return None

    def _filter_pinellas_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter dataframe to only Pinellas County flood-related events."""
        if df is None or df.empty:
            return pd.DataFrame()

        # Filter by state and county FIPS
        df_filtered = df[
            (df['STATE_FIPS'].astype(str).str.zfill(2) == self.bounds.state_fips) &
            (df['CZ_FIPS'].astype(str).str.zfill(3) == self.bounds.county_fips)
        ].copy()

        # Also filter by event type
        df_filtered = df_filtered[
            df_filtered['EVENT_TYPE'].isin(self.FLOOD_EVENT_TYPES)
        ]

        return df_filtered

    def _parse_damage(self, damage_str: str) -> float:
        """Parse damage string (e.g., '50K', '1.5M') to numeric value."""
        if pd.isna(damage_str) or damage_str == '' or damage_str == '0':
            return 0.0

        damage_str = str(damage_str).upper().strip()

        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'B': 1_000_000_000,
            'T': 1_000,  # Sometimes 'T' means thousand
        }

        for suffix, mult in multipliers.items():
            if damage_str.endswith(suffix):
                try:
                    return float(damage_str[:-1]) * mult
                except ValueError:
                    return 0.0

        try:
            return float(damage_str)
        except ValueError:
            return 0.0

    def _convert_to_flood_event(self, row: pd.Series) -> FloodEvent:
        """Convert a DataFrame row to a FloodEvent object."""
        # Parse dates
        begin_date = None
        end_date = None

        try:
            if 'BEGIN_DATE_TIME' in row and pd.notna(row['BEGIN_DATE_TIME']):
                begin_date = pd.to_datetime(row['BEGIN_DATE_TIME'])
            elif 'BEGIN_YEARMONTH' in row:
                year = int(str(row['BEGIN_YEARMONTH'])[:4])
                month = int(str(row['BEGIN_YEARMONTH'])[4:6])
                day = int(row.get('BEGIN_DAY', 1)) if pd.notna(row.get('BEGIN_DAY')) else 1
                begin_date = datetime(year, month, day)
        except Exception:
            begin_date = datetime(2000, 1, 1)  # Fallback

        try:
            if 'END_DATE_TIME' in row and pd.notna(row['END_DATE_TIME']):
                end_date = pd.to_datetime(row['END_DATE_TIME'])
        except Exception:
            pass

        return FloodEvent(
            event_id=str(row.get('EVENT_ID', '')),
            event_type=str(row.get('EVENT_TYPE', 'Unknown')),
            begin_date=begin_date,
            end_date=end_date,
            begin_lat=float(row['BEGIN_LAT']) if pd.notna(row.get('BEGIN_LAT')) else None,
            begin_lon=float(row['BEGIN_LON']) if pd.notna(row.get('BEGIN_LON')) else None,
            end_lat=float(row['END_LAT']) if pd.notna(row.get('END_LAT')) else None,
            end_lon=float(row['END_LON']) if pd.notna(row.get('END_LON')) else None,
            episode_narrative=str(row.get('EPISODE_NARRATIVE', ''))[:5000] if pd.notna(row.get('EPISODE_NARRATIVE')) else None,
            event_narrative=str(row.get('EVENT_NARRATIVE', ''))[:5000] if pd.notna(row.get('EVENT_NARRATIVE')) else None,
            deaths_direct=int(row.get('DEATHS_DIRECT', 0)) if pd.notna(row.get('DEATHS_DIRECT')) else 0,
            deaths_indirect=int(row.get('DEATHS_INDIRECT', 0)) if pd.notna(row.get('DEATHS_INDIRECT')) else 0,
            injuries_direct=int(row.get('INJURIES_DIRECT', 0)) if pd.notna(row.get('INJURIES_DIRECT')) else 0,
            injuries_indirect=int(row.get('INJURIES_INDIRECT', 0)) if pd.notna(row.get('INJURIES_INDIRECT')) else 0,
            damage_property=self._parse_damage(row.get('DAMAGE_PROPERTY', 0)),
            damage_crops=self._parse_damage(row.get('DAMAGE_CROPS', 0)),
            flood_cause=str(row.get('FLOOD_CAUSE', '')) if pd.notna(row.get('FLOOD_CAUSE')) else None,
            magnitude=float(row['MAGNITUDE']) if pd.notna(row.get('MAGNITUDE')) else None,
            magnitude_type=str(row.get('MAGNITUDE_TYPE', '')) if pd.notna(row.get('MAGNITUDE_TYPE')) else None,
        )

    def collect_historical_floods(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        force_refresh: bool = False
    ) -> List[FloodEvent]:
        """
        Collect all historical flood events for Pinellas County.

        Args:
            start_year: Starting year (default: from config, 1974)
            end_year: Ending year (default: current year)
            force_refresh: If True, ignore cache and re-download

        Returns:
            List of FloodEvent objects
        """
        start_year = start_year or ANALYSIS_CONFIG.start_year
        end_year = end_year or ANALYSIS_CONFIG.end_year

        all_events = []

        for year in range(start_year, end_year + 1):
            logger.info(f"Processing year {year}...")

            if force_refresh:
                cache_file = self.cache_dir / f"storm_events_{year}.parquet"
                if cache_file.exists():
                    cache_file.unlink()

            df = self._download_year_data(year)
            if df is None:
                continue

            df_pinellas = self._filter_pinellas_events(df)

            for _, row in df_pinellas.iterrows():
                try:
                    event = self._convert_to_flood_event(row)
                    all_events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse event: {e}")
                    continue

        logger.info(f"Collected {len(all_events)} flood events for Pinellas County ({start_year}-{end_year})")
        return all_events

    def get_event_summary(self, events: List[FloodEvent]) -> FloodEventSummary:
        """Generate summary statistics for flood events."""
        if not events:
            return FloodEventSummary(
                total_events=0,
                events_by_type={},
                events_by_year={},
                total_property_damage=0.0,
                total_deaths=0,
                total_injuries=0,
                avg_events_per_year=0.0
            )

        events_by_type = {}
        events_by_year = {}
        total_damage = 0.0
        total_deaths = 0
        total_injuries = 0

        for event in events:
            # Count by type
            events_by_type[event.event_type] = events_by_type.get(event.event_type, 0) + 1

            # Count by year
            year = event.begin_date.year
            events_by_year[year] = events_by_year.get(year, 0) + 1

            # Sum damages and casualties
            total_damage += event.damage_property or 0
            total_deaths += event.deaths_direct + event.deaths_indirect
            total_injuries += event.injuries_direct + event.injuries_indirect

        years_span = max(events_by_year.keys()) - min(events_by_year.keys()) + 1 if events_by_year else 1

        return FloodEventSummary(
            total_events=len(events),
            events_by_type=events_by_type,
            events_by_year=events_by_year,
            total_property_damage=total_damage,
            total_deaths=total_deaths,
            total_injuries=total_injuries,
            avg_events_per_year=len(events) / years_span
        )

    def save_processed_data(self, events: List[FloodEvent], filename: str = "pinellas_flood_events.json"):
        """Save processed flood events to JSON file."""
        output_path = PROCESSED_DATA_DIR / filename

        import json
        events_data = [event.model_dump(mode='json') for event in events]

        with open(output_path, 'w') as f:
            json.dump(events_data, f, indent=2, default=str)

        logger.info(f"Saved {len(events)} events to {output_path}")
        return output_path


# Convenience function
def fetch_pinellas_flood_history() -> tuple[List[FloodEvent], FloodEventSummary]:
    """
    Fetch all historical flood events for Pinellas County.
    Returns tuple of (events, summary).
    """
    collector = NOAAStormEventsCollector()
    events = collector.collect_historical_floods()
    summary = collector.get_event_summary(events)
    return events, summary


if __name__ == "__main__":
    # Test the collector
    logging.basicConfig(level=logging.INFO)
    events, summary = fetch_pinellas_flood_history()
    print(f"\nSummary for Pinellas County:")
    print(f"Total flood events: {summary.total_events}")
    print(f"Events by type: {summary.events_by_type}")
    print(f"Total property damage: ${summary.total_property_damage:,.2f}")
    print(f"Average events per year: {summary.avg_events_per_year:.1f}")
