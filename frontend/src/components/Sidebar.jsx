import React, { useState, useEffect, useCallback, useRef } from 'react';
import RiskDisplay from './RiskDisplay';
import { autocompleteAddress, getAddressDownloadStatus, downloadAddresses } from '../services/api';

function Sidebar({ selectedLocation, riskResult, loading, error, onAddressSearch, onAddressSelect, onClear }) {
  const [activeTab, setActiveTab] = useState('search');
  const [address, setAddress] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [addressDbStatus, setAddressDbStatus] = useState({ addresses_loaded: 0 });
  const [downloadingAddresses, setDownloadingAddresses] = useState(false);
  const [atmosphericAnalysis, setAtmosphericAnalysis] = useState(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const suggestionsRef = useRef(null);
  const inputRef = useRef(null);

  // Check address database status on mount
  useEffect(() => {
    const checkStatus = async () => {
      const status = await getAddressDownloadStatus();
      setAddressDbStatus(status);
    };
    checkStatus();
    // Check periodically if downloading
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Debounced autocomplete
  useEffect(() => {
    if (address.length < 2 || !addressDbStatus.addresses_loaded) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(async () => {
      const result = await autocompleteAddress(address);
      setSuggestions(result.results || []);
      setShowSuggestions(true);
    }, 200);

    return () => clearTimeout(timer);
  }, [address, addressDbStatus.addresses_loaded]);

  // Close suggestions when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target) &&
          inputRef.current && !inputRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSuggestionClick = (suggestion) => {
    setAddress(suggestion.full_address);
    setSuggestions([]);
    setShowSuggestions(false);
    // Use the coordinates directly from the database
    if (onAddressSelect) {
      onAddressSelect(suggestion);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (address.trim()) {
      // If we have a matching suggestion, use it
      const match = suggestions.find(s => s.full_address.toUpperCase() === address.toUpperCase());
      if (match && onAddressSelect) {
        onAddressSelect(match);
      } else {
        // Fall back to geocoding
        onAddressSearch(address.trim(), 'Pinellas County');
      }
    }
  };

  const handleDownloadAddresses = async () => {
    setDownloadingAddresses(true);
    await downloadAddresses();
    // Status will update via the interval
  };

  const hasAddressDb = addressDbStatus.addresses_loaded > 0;

  return (
    <aside className="sidebar">
      {/* Tabs */}
      <div className="tabs">
        <button
          className={`tab ${activeTab === 'search' ? 'active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          Search
        </button>
        <button
          className={`tab ${activeTab === 'results' ? 'active' : ''}`}
          onClick={() => setActiveTab('results')}
          disabled={!riskResult}
        >
          Results
        </button>
        <button
          className={`tab ${activeTab === 'analysis' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('analysis');
            if (!atmosphericAnalysis && !loadingAnalysis) {
              setLoadingAnalysis(true);
              fetch('/api/v1/analysis/atmospheric')
                .then(res => res.json())
                .then(data => setAtmosphericAnalysis(data))
                .catch(err => console.error(err))
                .finally(() => setLoadingAnalysis(false));
            }
          }}
        >
          Analysis
        </button>
        <button
          className={`tab ${activeTab === 'info' ? 'active' : ''}`}
          onClick={() => setActiveTab('info')}
        >
          Info
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'search' && (
        <div className="sidebar-section">
          <h2>Search by Address</h2>

          {/* Address Database Status */}
          {!hasAddressDb && (
            <div style={{
              marginBottom: '1rem',
              padding: '0.75rem',
              background: '#fef3c7',
              border: '1px solid #fcd34d',
              borderRadius: '0.375rem',
              fontSize: '0.8125rem'
            }}>
              <strong>Address Database Not Loaded</strong>
              <p style={{ margin: '0.5rem 0', color: '#92400e' }}>
                Download the Pinellas County address database for accurate autocomplete.
              </p>
              <button
                className="btn btn-secondary"
                onClick={handleDownloadAddresses}
                disabled={downloadingAddresses || addressDbStatus.downloading}
                style={{ fontSize: '0.75rem', padding: '0.375rem 0.75rem' }}
              >
                {addressDbStatus.downloading ? 'Downloading...' : 'Download Addresses'}
              </button>
              {addressDbStatus.progress && (
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.75rem', color: '#78716c' }}>
                  {addressDbStatus.progress}
                </p>
              )}
            </div>
          )}

          {hasAddressDb && (
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              {addressDbStatus.addresses_loaded.toLocaleString()} addresses loaded
            </p>
          )}

          <form onSubmit={handleSubmit} className="search-form">
            <div className="form-group" style={{ position: 'relative' }}>
              <label htmlFor="address">Street Address</label>
              <input
                ref={inputRef}
                type="text"
                id="address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                placeholder={hasAddressDb ? "Start typing an address..." : "e.g., 100 Central Ave"}
                autoComplete="off"
              />

              {/* Autocomplete Suggestions */}
              {showSuggestions && suggestions.length > 0 && (
                <div
                  ref={suggestionsRef}
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    background: 'white',
                    border: '1px solid #e5e7eb',
                    borderRadius: '0.375rem',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                    maxHeight: '200px',
                    overflowY: 'auto',
                    zIndex: 1000
                  }}
                >
                  {suggestions.map((suggestion, idx) => (
                    <div
                      key={idx}
                      onClick={() => handleSuggestionClick(suggestion)}
                      style={{
                        padding: '0.625rem 0.75rem',
                        cursor: 'pointer',
                        borderBottom: idx < suggestions.length - 1 ? '1px solid #f3f4f6' : 'none',
                        fontSize: '0.8125rem'
                      }}
                      onMouseEnter={(e) => e.target.style.background = '#f3f4f6'}
                      onMouseLeave={(e) => e.target.style.background = 'white'}
                    >
                      <div style={{ fontWeight: 500 }}>{suggestion.full_address}</div>
                      <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                        {suggestion.city}, FL {suggestion.zip_code}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !address.trim()}
            >
              {loading ? 'Searching...' : 'Check Flood Risk'}
            </button>
          </form>

          {selectedLocation && (
            <div style={{ marginTop: '1rem' }}>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                <strong>Selected Location:</strong><br />
                {selectedLocation.lat.toFixed(4)}, {selectedLocation.lng.toFixed(4)}
              </p>
              <button
                className="btn btn-secondary"
                onClick={onClear}
                style={{ marginTop: '0.5rem' }}
              >
                Clear Selection
              </button>
            </div>
          )}

          {error && (
            <div style={{
              marginTop: '1rem',
              padding: '0.75rem',
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '0.375rem',
              color: '#dc2626',
              fontSize: '0.875rem'
            }}>
              {error}
            </div>
          )}
        </div>
      )}

      {activeTab === 'results' && (
        <div className="sidebar-section">
          {loading ? (
            <div className="loading-spinner">
              <div className="spinner"></div>
            </div>
          ) : riskResult?.risk ? (
            <RiskDisplay risk={riskResult.risk} details={riskResult.details} />
          ) : (
            <div className="info-panel">
              <p>Click on the map or search an address to see flood risk results.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'analysis' && (
        <div className="sidebar-section">
          <h2>Hurricane Avoidance Analysis</h2>
          <div className="info-panel">
            {loadingAnalysis ? (
              <div className="loading-spinner">
                <div className="spinner"></div>
                <p>Loading atmospheric analysis...</p>
              </div>
            ) : atmosphericAnalysis?.message ? (
              <div>
                <p style={{ color: '#92400e' }}>{atmosphericAnalysis.message}</p>
                <p style={{ marginTop: '0.5rem' }}>Download historical data to run the analysis.</p>
              </div>
            ) : atmosphericAnalysis ? (
              <div style={{ fontSize: '0.8125rem' }}>
                <h3 style={{ fontSize: '1rem', marginBottom: '0.75rem', color: '#1e40af' }}>
                  {atmosphericAnalysis.hypothesis?.question}
                </h3>

                <div style={{ background: '#dbeafe', padding: '0.75rem', borderRadius: '0.375rem', marginBottom: '1rem' }}>
                  <strong>Primary Finding:</strong>
                  <p style={{ margin: '0.25rem 0 0' }}>
                    {atmosphericAnalysis.steering_flow_findings?.effect}
                  </p>
                </div>

                <h4 style={{ fontSize: '0.875rem', marginTop: '1rem', marginBottom: '0.5rem' }}>Jet Stream Analysis</h4>
                <p><strong>Position:</strong> {atmosphericAnalysis.jet_stream_analysis?.average_position}</p>
                <p><strong>Pattern:</strong> {atmosphericAnalysis.jet_stream_analysis?.dominant_pattern}</p>

                <h4 style={{ fontSize: '0.875rem', marginTop: '1rem', marginBottom: '0.5rem' }}>Tampa Bay Local Effects</h4>
                <p>{atmosphericAnalysis.tampa_bay_local_effects?.thermal_effects}</p>
                <p style={{ marginTop: '0.5rem' }}>
                  <strong>Conclusion:</strong> {atmosphericAnalysis.tampa_bay_local_effects?.conclusion}
                </p>

                <h4 style={{ fontSize: '0.875rem', marginTop: '1rem', marginBottom: '0.5rem' }}>Hurricane Statistics</h4>
                <ul style={{ paddingLeft: '1.25rem' }}>
                  <li>Total analyzed: {atmosphericAnalysis.hurricane_statistics?.total_analyzed}</li>
                  <li>Near misses (50-200km): {atmosphericAnalysis.hurricane_statistics?.near_misses_50_200km}</li>
                  <li>Direct hits (&lt;50km): {atmosphericAnalysis.hurricane_statistics?.direct_hits_under_50km}</li>
                  <li>Hit rate: {atmosphericAnalysis.hurricane_statistics?.hit_rate}</li>
                </ul>

                <h4 style={{ fontSize: '0.875rem', marginTop: '1rem', marginBottom: '0.5rem' }}>Protection Factor</h4>
                <div style={{ background: '#fef3c7', padding: '0.75rem', borderRadius: '0.375rem' }}>
                  <p><strong>{atmosphericAnalysis.protection_factor?.interpretation}</strong></p>
                  <p style={{ fontSize: '0.75rem', color: '#92400e', marginTop: '0.25rem' }}>
                    {atmosphericAnalysis.protection_factor?.caveat}
                  </p>
                </div>

                <h4 style={{ fontSize: '0.875rem', marginTop: '1rem', marginBottom: '0.5rem' }}>Key Findings</h4>
                <ul style={{ paddingLeft: '1.25rem' }}>
                  {atmosphericAnalysis.key_findings?.map((finding, idx) => (
                    <li key={idx} style={{ marginBottom: '0.25rem' }}>{finding}</li>
                  ))}
                </ul>

                <div style={{ background: '#fee2e2', padding: '0.75rem', borderRadius: '0.375rem', marginTop: '1rem' }}>
                  <strong style={{ color: '#dc2626' }}>Warning:</strong>
                  <p style={{ margin: '0.25rem 0 0', color: '#991b1b' }}>
                    {atmosphericAnalysis.conclusion?.warning}
                  </p>
                </div>
              </div>
            ) : (
              <p>Click to load atmospheric analysis</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'info' && (
        <div className="sidebar-section">
          <h2>About This Tool</h2>
          <div className="info-panel">
            <p>
              The <strong>True Flood Risk Score</strong> is calculated using 50 years
              of historical data, providing a more accurate picture of flood risk than
              FEMA flood zones alone.
            </p>

            <h3 style={{ fontSize: '0.9375rem', marginTop: '1rem', marginBottom: '0.5rem' }}>
              Data Sources
            </h3>
            <ul style={{ paddingLeft: '1.25rem', fontSize: '0.8125rem' }}>
              <li>NOAA Storm Events Database (1974-present)</li>
              <li>NOAA HURDAT2 Hurricane Database</li>
              <li>USGS 3DEP Elevation Data</li>
              <li>FEMA National Flood Hazard Layer</li>
              <li>Pinellas County Address Database</li>
            </ul>

            <h3 style={{ fontSize: '0.9375rem', marginTop: '1rem', marginBottom: '0.5rem' }}>
              Risk Score Components
            </h3>
            <ul style={{ paddingLeft: '1.25rem', fontSize: '0.8125rem' }}>
              <li><strong>Historical Floods (30%)</strong> - Past flood events nearby</li>
              <li><strong>Hurricane Probability (25%)</strong> - Storm track analysis</li>
              <li><strong>Elevation Risk (25%)</strong> - Height above sea level</li>
              <li><strong>Storm Surge (15%)</strong> - Tampa Bay exposure</li>
              <li><strong>Atmospheric Protection (5%)</strong> - Pattern analysis</li>
            </ul>

            <h3 style={{ fontSize: '0.9375rem', marginTop: '1rem', marginBottom: '0.5rem' }}>
              Risk Levels
            </h3>
            <div style={{ fontSize: '0.8125rem' }}>
              <p><span className="text-very-low">●</span> Very Low: 0-20</p>
              <p><span className="text-low">●</span> Low: 21-40</p>
              <p><span className="text-moderate">●</span> Moderate: 41-60</p>
              <p><span className="text-high">●</span> High: 61-80</p>
              <p><span className="text-very-high">●</span> Very High: 81-100</p>
            </div>

            <p style={{ marginTop: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              This tool is for informational purposes only. Always consult official
              sources and insurance professionals for flood insurance decisions.
            </p>
          </div>
        </div>
      )}
    </aside>
  );
}

export default Sidebar;
