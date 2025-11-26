import React from 'react';

const RISK_COLORS = {
  very_low: '#22c55e',
  low: '#84cc16',
  moderate: '#eab308',
  high: '#f97316',
  very_high: '#ef4444',
};

function RiskDisplay({ risk, details }) {
  const riskLevel = risk.risk_level;
  const riskColor = RISK_COLORS[riskLevel] || '#64748b';

  return (
    <div className="risk-display">
      {/* Main Score */}
      <div className="risk-score-container">
        <div className={`risk-score-circle risk-${riskLevel}`}>
          <span className="risk-score-value">{Math.round(risk.true_risk_score)}</span>
          <span className="risk-score-label">out of 100</span>
        </div>
        <div className={`risk-level text-${riskLevel}`}>
          {formatRiskLevel(riskLevel)} Risk
        </div>
      </div>

      {/* Location */}
      {risk.address && (
        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          {risk.address}
        </p>
      )}

      {/* Risk Breakdown */}
      <div className="risk-breakdown">
        <h3>Risk Factors</h3>

        <RiskFactor
          label="Historical Floods"
          value={risk.factors.historical_flood_score}
          color={RISK_COLORS[getScoreLevel(risk.factors.historical_flood_score)]}
        />
        <RiskFactor
          label="Hurricane Probability"
          value={risk.factors.hurricane_probability_score}
          color={RISK_COLORS[getScoreLevel(risk.factors.hurricane_probability_score)]}
        />
        <RiskFactor
          label="Elevation Risk"
          value={risk.factors.elevation_risk_score}
          color={RISK_COLORS[getScoreLevel(risk.factors.elevation_risk_score)]}
        />
        <RiskFactor
          label="Storm Surge"
          value={risk.factors.storm_surge_score}
          color={RISK_COLORS[getScoreLevel(risk.factors.storm_surge_score)]}
        />
      </div>

      {/* Elevation & Details */}
      {details && (
        <div style={{
          background: 'var(--background)',
          borderRadius: '0.5rem',
          padding: '1rem',
          marginTop: '1rem',
          textAlign: 'left',
          fontSize: '0.8125rem'
        }}>
          {details.elevation_m && (
            <p>
              <strong>Elevation:</strong> {details.elevation_m.toFixed(1)}m ({details.elevation_ft.toFixed(1)}ft)
            </p>
          )}
          {details.storm_surge?.evacuation_zone && (
            <p>
              <strong>Evacuation Zone:</strong> Zone {details.storm_surge.evacuation_zone}
            </p>
          )}
        </div>
      )}

      {/* FEMA Comparison */}
      {risk.fema_flood_zone && (
        <div className="fema-comparison">
          <h4>FEMA Comparison</h4>
          <span className="fema-zone-badge">{risk.fema_flood_zone}</span>
          {risk.fema_comparison && (
            <div className={`comparison-indicator comparison-${risk.fema_comparison}`}>
              {risk.fema_comparison === 'higher' && (
                <>↑ Our analysis suggests <strong>higher risk</strong> than FEMA indicates</>
              )}
              {risk.fema_comparison === 'lower' && (
                <>↓ Our analysis suggests <strong>lower risk</strong> than FEMA indicates</>
              )}
              {risk.fema_comparison === 'same' && (
                <>≈ Our analysis is <strong>consistent</strong> with FEMA zone</>
              )}
            </div>
          )}
          {details?.fema_interpretation && (
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
              {details.fema_interpretation.description}
            </p>
          )}
        </div>
      )}

      {/* Recommendations */}
      <div className="recommendations">
        <h3>Recommendations</h3>
        {getRecommendations(risk, details).map((rec, idx) => (
          <div key={idx} className="recommendation-item">
            <span className="recommendation-icon">💡</span>
            <span>{rec}</span>
          </div>
        ))}
      </div>

      {/* Confidence */}
      <div style={{
        marginTop: '1rem',
        fontSize: '0.75rem',
        color: 'var(--text-secondary)',
        textAlign: 'center'
      }}>
        Confidence: {Math.round(risk.confidence * 100)}% •
        Methodology v{risk.methodology_version}
      </div>
    </div>
  );
}

function RiskFactor({ label, value, color }) {
  return (
    <div className="risk-factor">
      <span className="risk-factor-label">{label}</span>
      <div className="risk-factor-bar">
        <div
          className="risk-factor-fill"
          style={{
            width: `${value}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <span className="risk-factor-value">{Math.round(value)}</span>
    </div>
  );
}

function getScoreLevel(score) {
  if (score <= 20) return 'very_low';
  if (score <= 40) return 'low';
  if (score <= 60) return 'moderate';
  if (score <= 80) return 'high';
  return 'very_high';
}

function formatRiskLevel(level) {
  return level
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function getRecommendations(risk, details) {
  const recommendations = [];

  // Based on risk level
  if (risk.risk_level === 'very_high' || risk.risk_level === 'high') {
    recommendations.push(
      'Consider flood insurance even if not required by your lender'
    );
    recommendations.push(
      'Know your evacuation route and register for emergency alerts'
    );
  }

  if (risk.risk_level === 'very_high') {
    recommendations.push(
      'Strongly recommend elevating critical utilities above flood level'
    );
  }

  // Based on FEMA comparison
  if (risk.fema_comparison === 'higher') {
    recommendations.push(
      `Consider additional flood protection despite being in FEMA Zone ${risk.fema_flood_zone}`
    );
  } else if (risk.fema_comparison === 'lower') {
    recommendations.push(
      'You may want to review your flood insurance coverage - you might be overpaying'
    );
  }

  // Based on evacuation zone
  if (details?.storm_surge?.evacuation_zone === 'A') {
    recommendations.push(
      'Zone A: Evacuate for ANY tropical storm or hurricane threat'
    );
  } else if (details?.storm_surge?.evacuation_zone === 'B') {
    recommendations.push(
      'Zone B: Evacuate when ordered for Category 1+ hurricanes'
    );
  }

  // Default
  if (recommendations.length === 0) {
    recommendations.push(
      'Standard flood preparedness recommended - review FEMA flood preparedness guide'
    );
  }

  return recommendations;
}

export default RiskDisplay;
