import React, { useState } from 'react';
import RiskDisplay from './RiskDisplay';

function Sidebar({ selectedLocation, riskResult, loading, error, onAddressSearch, onClear }) {
  const [activeTab, setActiveTab] = useState('search');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('St Petersburg');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (address.trim()) {
      onAddressSearch(address.trim(), city.trim());
    }
  };

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
          <form onSubmit={handleSubmit} className="search-form">
            <div className="form-group">
              <label htmlFor="address">Street Address</label>
              <input
                type="text"
                id="address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="e.g., 100 Central Ave"
              />
            </div>
            <div className="form-group">
              <label htmlFor="city">City</label>
              <input
                type="text"
                id="city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="St Petersburg"
              />
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
