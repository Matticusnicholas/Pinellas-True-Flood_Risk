import React, { useState, useCallback } from 'react';
import FloodRiskMap from './components/FloodRiskMap';
import Sidebar from './components/Sidebar';
import { calculateRisk, calculateRiskByAddress } from './services/api';

function App() {
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [riskResult, setRiskResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleMapClick = useCallback(async (lat, lng) => {
    setSelectedLocation({ lat, lng });
    setLoading(true);
    setError(null);

    try {
      const result = await calculateRisk(lat, lng);
      if (result.success) {
        setRiskResult(result);
      } else {
        setError(result.error || 'Failed to calculate risk');
      }
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle address selected from autocomplete (uses exact coordinates from database)
  const handleAddressSelect = useCallback(async (addressData) => {
    const { lat, lon, full_address } = addressData;

    setSelectedLocation({ lat, lng: lon });
    setLoading(true);
    setError(null);

    try {
      // Use the exact coordinates from the address database
      const result = await calculateRisk(lat, lon, { address: full_address });
      if (result.success) {
        setRiskResult(result);
      } else {
        setError(result.error || 'Failed to calculate risk');
      }
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fallback for manual address entry (uses geocoding)
  const handleAddressSearch = useCallback(async (address, city) => {
    setLoading(true);
    setError(null);

    try {
      const result = await calculateRiskByAddress(address, city);
      if (result.success && result.risk) {
        setSelectedLocation({
          lat: result.risk.lat,
          lng: result.risk.lon
        });
        setRiskResult(result);
      } else {
        setError(result.error || 'Address not found. Try selecting from the autocomplete suggestions.');
      }
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleClear = useCallback(() => {
    setSelectedLocation(null);
    setRiskResult(null);
    setError(null);
  }, []);

  return (
    <div className="app-container">
      <header className="header">
        <h1>Pinellas True Flood Risk</h1>
        <p className="header-subtitle">
          Data-driven flood risk assessment based on 50 years of historical data
        </p>
      </header>

      <main className="main-content">
        <div className="map-container">
          <FloodRiskMap
            selectedLocation={selectedLocation}
            onMapClick={handleMapClick}
            riskResult={riskResult}
          />
        </div>

        <Sidebar
          selectedLocation={selectedLocation}
          riskResult={riskResult}
          loading={loading}
          error={error}
          onAddressSearch={handleAddressSearch}
          onAddressSelect={handleAddressSelect}
          onClear={handleClear}
        />
      </main>
    </div>
  );
}

export default App;
