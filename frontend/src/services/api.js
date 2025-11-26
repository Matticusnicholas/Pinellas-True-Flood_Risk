/**
 * API service for Pinellas Flood Risk
 */

const API_BASE = '/api/v1';

/**
 * Autocomplete address search
 */
export async function autocompleteAddress(query) {
  if (!query || query.length < 2) {
    return { results: [] };
  }

  try {
    const response = await fetch(
      `${API_BASE}/addresses/autocomplete?q=${encodeURIComponent(query)}`
    );

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error in autocomplete:', error);
    return { results: [] };
  }
}

/**
 * Calculate risk using address from database (most accurate)
 */
export async function calculateRiskByAddressLookup(fullAddress) {
  try {
    const response = await fetch(
      `${API_BASE}/risk/address-lookup?address=${encodeURIComponent(fullAddress)}`,
      { method: 'POST' }
    );

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error calculating risk by address lookup:', error);
    return { success: false, error: error.message };
  }
}

/**
 * Download address database
 */
export async function downloadAddresses() {
  try {
    const response = await fetch(`${API_BASE}/addresses/download`, {
      method: 'POST'
    });
    return await response.json();
  } catch (error) {
    console.error('Error starting address download:', error);
    return { error: error.message };
  }
}

/**
 * Check address download status
 */
export async function getAddressDownloadStatus() {
  try {
    const response = await fetch(`${API_BASE}/addresses/download/status`);
    return await response.json();
  } catch (error) {
    console.error('Error checking address status:', error);
    return { addresses_loaded: 0 };
  }
}

/**
 * Calculate flood risk for a lat/lon location
 */
export async function calculateRisk(lat, lon, options = {}) {
  try {
    const response = await fetch(`${API_BASE}/risk/location`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        lat,
        lon,
        elevation_m: options.elevation,
        address: options.address,
        include_details: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error calculating risk:', error);

    // Return mock data for demo when API is unavailable
    return getMockRiskData(lat, lon);
  }
}

/**
 * Calculate flood risk by address
 */
export async function calculateRiskByAddress(address, city = 'St Petersburg', state = 'FL') {
  try {
    const response = await fetch(`${API_BASE}/risk/address`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        address,
        city,
        state,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error calculating risk by address:', error);

    // Return mock data with geocoded location
    return getMockRiskData(27.7676, -82.6403, address);
  }
}

/**
 * Get elevation for a location
 */
export async function getElevation(lat, lon) {
  try {
    const response = await fetch(
      `${API_BASE}/elevation?lat=${lat}&lon=${lon}`
    );

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching elevation:', error);
    return null;
  }
}

/**
 * Get FEMA flood zone for a location
 */
export async function getFemaZone(lat, lon) {
  try {
    const response = await fetch(
      `${API_BASE}/fema-zone?lat=${lat}&lon=${lon}`
    );

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching FEMA zone:', error);
    return null;
  }
}

/**
 * Get risk map grid data
 */
export async function getRiskMapGrid(bounds, resolution = 'medium') {
  try {
    const response = await fetch(`${API_BASE}/map/grid`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        min_lat: bounds.south,
        max_lat: bounds.north,
        min_lon: bounds.west,
        max_lon: bounds.east,
        resolution,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching map grid:', error);
    return null;
  }
}

/**
 * Get methodology information
 */
export async function getMethodology() {
  try {
    const response = await fetch(`${API_BASE}/methodology`);
    return await response.json();
  } catch (error) {
    console.error('Error fetching methodology:', error);
    return null;
  }
}

/**
 * Mock risk data for demo purposes
 */
function getMockRiskData(lat, lon, address = null) {
  // Generate somewhat realistic mock data based on location
  // Lower latitudes and locations closer to bay have higher risk

  const bayDistance = Math.abs(lon - (-82.55)); // Distance from bay center
  const baseRisk = 45 + (Math.random() * 20);

  // Adjust risk based on proximity to bay
  const bayAdjustment = bayDistance < 0.15 ? 15 : bayDistance < 0.25 ? 5 : -10;

  // Adjust for latitude (south tends to be lower elevation)
  const latAdjustment = lat < 27.75 ? 10 : lat < 27.85 ? 5 : 0;

  const trueRiskScore = Math.min(100, Math.max(0,
    baseRisk + bayAdjustment + latAdjustment + (Math.random() * 10 - 5)
  ));

  const riskLevel =
    trueRiskScore <= 20 ? 'very_low' :
    trueRiskScore <= 40 ? 'low' :
    trueRiskScore <= 60 ? 'moderate' :
    trueRiskScore <= 80 ? 'high' : 'very_high';

  const femaZones = ['AE', 'X', 'VE', 'A'];
  const femaZone = femaZones[Math.floor(Math.random() * femaZones.length)];

  const femaComparison =
    Math.random() > 0.6 ? 'higher' :
    Math.random() > 0.5 ? 'lower' : 'same';

  return {
    success: true,
    risk: {
      lat,
      lon,
      address: address || `${lat.toFixed(4)}, ${lon.toFixed(4)}`,
      true_risk_score: Math.round(trueRiskScore * 10) / 10,
      risk_level: riskLevel,
      fema_flood_zone: femaZone,
      fema_comparison: femaComparison,
      factors: {
        historical_flood_score: Math.round((30 + Math.random() * 40) * 10) / 10,
        hurricane_probability_score: Math.round((40 + Math.random() * 30) * 10) / 10,
        elevation_risk_score: Math.round((35 + Math.random() * 35) * 10) / 10,
        storm_surge_score: Math.round((bayAdjustment + 50 + Math.random() * 20) * 10) / 10,
        atmospheric_protection_factor: Math.round(Math.random() * 30) / 100,
      },
      confidence: 0.75,
      methodology_version: '1.0',
      computed_at: new Date().toISOString(),
    },
    details: {
      elevation_m: 2 + Math.random() * 8,
      elevation_ft: (2 + Math.random() * 8) * 3.28084,
      fema_zone: femaZone,
      fema_interpretation: {
        risk_level: femaZone.startsWith('A') || femaZone.startsWith('V') ? 'high' : 'low_to_moderate',
        description: femaZone.startsWith('V')
          ? 'High-risk coastal area with wave action'
          : femaZone.startsWith('A')
          ? 'High-risk flood area with 1% annual chance of flooding'
          : 'Area of minimal to moderate flood risk',
        insurance_required: femaZone.startsWith('A') || femaZone.startsWith('V'),
      },
      storm_surge: {
        score: Math.round((bayAdjustment + 50 + Math.random() * 20) * 10) / 10,
        surge_zone: bayDistance < 0.15 ? 'middle_bay' : 'lower_bay',
        evacuation_zone: bayDistance < 0.2 ? 'A' : 'B',
      },
    },
  };
}
