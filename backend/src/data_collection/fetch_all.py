"""
Master data collection script

Run this to fetch all historical data needed for the flood risk analysis.
This will download and cache data from:
- NOAA Storm Events Database
- NOAA HURDAT2 Hurricane Database
- Generate atmospheric analysis

Usage:
    python -m src.data_collection.fetch_all
"""
import logging
import json
from pathlib import Path
from datetime import datetime

from ..config import PROCESSED_DATA_DIR, ANALYSIS_CONFIG

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_flood_events():
    """Fetch historical flood events from NOAA."""
    logger.info("=" * 60)
    logger.info("Fetching NOAA Storm Events Data...")
    logger.info("=" * 60)

    from .noaa_storm_events import NOAAStormEventsCollector

    collector = NOAAStormEventsCollector()
    events = collector.collect_historical_floods()
    summary = collector.get_event_summary(events)

    # Save processed data
    collector.save_processed_data(events)

    logger.info(f"Collected {len(events)} flood events")
    logger.info(f"Events by type: {summary.events_by_type}")
    logger.info(f"Total property damage: ${summary.total_property_damage:,.2f}")

    return events, summary


def fetch_hurricane_tracks():
    """Fetch historical hurricane track data."""
    logger.info("=" * 60)
    logger.info("Fetching Hurricane Track Data...")
    logger.info("=" * 60)

    from .hurricane_tracks import HurricaneTrackCollector

    collector = HurricaneTrackCollector()
    hurricanes = collector.collect_hurricane_data()
    stats = collector.get_statistics(hurricanes)

    # Save processed data
    collector.save_processed_data(hurricanes)

    logger.info(f"Analyzed {stats.total_storms_analyzed} storms")
    logger.info(f"Storms within analysis radius: {stats.storms_within_radius}")
    logger.info(f"Direct hits on Pinellas: {stats.direct_hits_pinellas}")

    return hurricanes, stats


def generate_atmospheric_analysis(hurricane_stats):
    """Generate atmospheric pattern analysis."""
    logger.info("=" * 60)
    logger.info("Generating Atmospheric Analysis...")
    logger.info("=" * 60)

    from .atmospheric_data import AtmosphericDataCollector

    collector = AtmosphericDataCollector()

    # Convert stats to dict if needed
    stats_dict = hurricane_stats.model_dump() if hasattr(hurricane_stats, 'model_dump') else hurricane_stats

    analysis = collector.generate_atmospheric_analysis(stats_dict)

    # Save analysis
    collector.save_analysis(analysis)

    logger.info(f"Protection factor: {analysis.protection_factor:.2f}")
    logger.info("Key findings:")
    for finding in analysis.findings[:3]:
        logger.info(f"  - {finding}")

    return analysis


def generate_summary_report(flood_events, flood_summary, hurricanes, hurricane_stats, atmospheric):
    """Generate a summary report of all collected data."""
    logger.info("=" * 60)
    logger.info("Generating Summary Report...")
    logger.info("=" * 60)

    report = {
        'generated_at': datetime.now().isoformat(),
        'analysis_period': {
            'start_year': ANALYSIS_CONFIG.start_year,
            'end_year': ANALYSIS_CONFIG.end_year,
            'years_analyzed': ANALYSIS_CONFIG.end_year - ANALYSIS_CONFIG.start_year
        },
        'flood_events': {
            'total_events': len(flood_events),
            'events_by_type': flood_summary.events_by_type,
            'total_property_damage': flood_summary.total_property_damage,
            'avg_events_per_year': flood_summary.avg_events_per_year,
        },
        'hurricanes': {
            'total_analyzed': hurricane_stats.total_storms_analyzed,
            'storms_within_radius': hurricane_stats.storms_within_radius,
            'direct_hits': hurricane_stats.direct_hits_pinellas,
            'near_misses': hurricane_stats.near_misses,
            'storms_by_category': hurricane_stats.storms_by_category,
            'avg_per_decade': hurricane_stats.avg_storms_per_decade,
        },
        'atmospheric': {
            'protection_factor': atmospheric.protection_factor,
            'dominant_pattern': atmospheric.dominant_pattern,
            'findings': atmospheric.findings,
        },
        'data_quality': {
            'flood_events_with_coords': len([e for e in flood_events if e.begin_lat]),
            'hurricanes_analyzed': len(hurricanes),
        }
    }

    # Save report
    report_path = PROCESSED_DATA_DIR / 'data_collection_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Summary report saved to {report_path}")

    return report


def main():
    """Main data collection workflow."""
    logger.info("=" * 60)
    logger.info("PINELLAS FLOOD RISK - DATA COLLECTION")
    logger.info("=" * 60)
    logger.info(f"Analysis period: {ANALYSIS_CONFIG.start_year}-{ANALYSIS_CONFIG.end_year}")
    logger.info("")

    try:
        # 1. Fetch flood events
        flood_events, flood_summary = fetch_flood_events()

        # 2. Fetch hurricane tracks
        hurricanes, hurricane_stats = fetch_hurricane_tracks()

        # 3. Generate atmospheric analysis
        atmospheric = generate_atmospheric_analysis(hurricane_stats)

        # 4. Generate summary report
        report = generate_summary_report(
            flood_events, flood_summary,
            hurricanes, hurricane_stats,
            atmospheric
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info("DATA COLLECTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Flood events: {len(flood_events)}")
        logger.info(f"Hurricanes analyzed: {hurricane_stats.total_storms_analyzed}")
        logger.info(f"Data saved to: {PROCESSED_DATA_DIR}")

        return report

    except Exception as e:
        logger.error(f"Data collection failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
