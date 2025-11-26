import React, { useEffect, useRef } from 'react';
import L from 'leaflet';

// Pinellas County bounds
const PINELLAS_BOUNDS = {
  center: [27.8676, -82.7403],
  zoom: 11,
  minZoom: 10,
  maxZoom: 18,
  bounds: [
    [27.5706, -82.8473], // SW
    [28.1739, -82.5353], // NE
  ],
};

// Risk level colors
const RISK_COLORS = {
  very_low: '#22c55e',
  low: '#84cc16',
  moderate: '#eab308',
  high: '#f97316',
  very_high: '#ef4444',
};

function FloodRiskMap({ selectedLocation, onMapClick, riskResult }) {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);

  // Initialize map
  useEffect(() => {
    if (mapInstanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: PINELLAS_BOUNDS.center,
      zoom: PINELLAS_BOUNDS.zoom,
      minZoom: PINELLAS_BOUNDS.minZoom,
      maxZoom: PINELLAS_BOUNDS.maxZoom,
    });

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    // Add click handler
    map.on('click', (e) => {
      const { lat, lng } = e.latlng;

      // Check if within Pinellas bounds
      if (lat >= 27.5 && lat <= 28.2 && lng >= -82.9 && lng <= -82.5) {
        onMapClick(lat, lng);
      }
    });

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [onMapClick]);

  // Update marker when location changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Remove existing marker
    if (markerRef.current) {
      map.removeLayer(markerRef.current);
      markerRef.current = null;
    }

    // Add new marker if location selected
    if (selectedLocation) {
      const { lat, lng } = selectedLocation;

      // Determine marker color based on risk
      let color = '#0ea5e9'; // Default blue
      if (riskResult?.risk?.risk_level) {
        color = RISK_COLORS[riskResult.risk.risk_level] || color;
      }

      // Create custom marker icon
      const markerHtml = `
        <div style="
          width: 24px;
          height: 24px;
          background: ${color};
          border: 3px solid white;
          border-radius: 50%;
          box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        "></div>
      `;

      const icon = L.divIcon({
        html: markerHtml,
        className: 'custom-marker',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });

      const marker = L.marker([lat, lng], { icon }).addTo(map);

      // Add popup if we have risk data
      if (riskResult?.risk) {
        const risk = riskResult.risk;
        const popupContent = `
          <div class="map-popup">
            <h3>True Flood Risk: ${risk.true_risk_score}/100</h3>
            <p><strong>Risk Level:</strong> ${formatRiskLevel(risk.risk_level)}</p>
            ${risk.fema_flood_zone ? `<p><strong>FEMA Zone:</strong> ${risk.fema_flood_zone}</p>` : ''}
            <p><strong>Location:</strong> ${lat.toFixed(4)}, ${lng.toFixed(4)}</p>
          </div>
        `;
        marker.bindPopup(popupContent).openPopup();
      }

      markerRef.current = marker;

      // Pan to location
      map.panTo([lat, lng]);
    }
  }, [selectedLocation, riskResult]);

  return (
    <>
      <div ref={mapRef} style={{ height: '100%', width: '100%' }} />
      <MapLegend />
      <MapInstructions />
    </>
  );
}

function MapLegend() {
  return (
    <div className="map-legend">
      <h4>Risk Level</h4>
      {Object.entries(RISK_COLORS).map(([level, color]) => (
        <div key={level} className="legend-item">
          <div className="legend-color" style={{ backgroundColor: color }} />
          <span>{formatRiskLevel(level)}</span>
        </div>
      ))}
    </div>
  );
}

function MapInstructions() {
  return (
    <div style={{
      position: 'absolute',
      top: 10,
      left: '50%',
      transform: 'translateX(-50%)',
      background: 'white',
      padding: '8px 16px',
      borderRadius: '20px',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      fontSize: '14px',
      zIndex: 1000,
    }}>
      Click anywhere on the map to check flood risk
    </div>
  );
}

function formatRiskLevel(level) {
  return level
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export default FloodRiskMap;
