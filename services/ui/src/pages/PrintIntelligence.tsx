import { useEffect, useState } from 'react';
import './PrintIntelligence.css';

interface PrintOutcome {
  id: string;
  job_id: string;
  printer_id: string;
  material_id: string;
  success: boolean;
  failure_reason: string | null;
  quality_score: number;
  actual_duration_hours: number;
  actual_cost_usd: number;
  material_used_grams: number;
  print_settings: Record<string, unknown>;
  quality_metrics: Record<string, unknown>;
  started_at: string;
  completed_at: string;
  measured_at: string;
  initial_snapshot_url: string | null;
  final_snapshot_url: string | null;
  snapshot_urls: string[];
  video_url: string | null;
  human_reviewed: boolean;
  review_requested_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
  goal_id: string | null;
}

interface OutcomeStatistics {
  total_outcomes: number;
  success_rate: number;
  avg_quality_score: number;
  avg_duration_hours: number;
  total_cost_usd: number;
}

const FAILURE_REASONS = [
  { value: 'first_layer_adhesion', label: 'First Layer Adhesion' },
  { value: 'warping', label: 'Warping' },
  { value: 'stringing', label: 'Stringing' },
  { value: 'spaghetti', label: 'Spaghetti' },
  { value: 'nozzle_clog', label: 'Nozzle Clog' },
  { value: 'filament_runout', label: 'Filament Runout' },
  { value: 'layer_shift', label: 'Layer Shift' },
  { value: 'overheating', label: 'Overheating' },
  { value: 'support_failure', label: 'Support Failure' },
  { value: 'user_cancelled', label: 'User Cancelled' },
  { value: 'power_failure', label: 'Power Failure' },
  { value: 'other', label: 'Other' },
];

const PrintIntelligence = () => {
  const [outcomes, setOutcomes] = useState<PrintOutcome[]>([]);
  const [statistics, setStatistics] = useState<OutcomeStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [printerFilter, setPrinterFilter] = useState<string>('');
  const [materialFilter, setMaterialFilter] = useState<string>('');
  const [successFilter, setSuccessFilter] = useState<string>(''); // 'true', 'false', ''
  const [showPendingReviewOnly, setShowPendingReviewOnly] = useState(false);

  // Detail modal
  const [selectedOutcome, setSelectedOutcome] = useState<PrintOutcome | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Review modal
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewForm, setReviewForm] = useState({
    reviewed_by: '',
    quality_score: 80,
    failure_reason: '',
    notes: '',
  });

  useEffect(() => {
    loadData();
  }, [printerFilter, materialFilter, successFilter]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Load statistics
      const statsParams = new URLSearchParams();
      if (printerFilter) statsParams.append('printer_id', printerFilter);
      if (materialFilter) statsParams.append('material_id', materialFilter);

      const statsResponse = await fetch(`/api/fabrication/outcomes/statistics?${statsParams}`);
      if (!statsResponse.ok) throw new Error('Failed to load statistics');
      const statsData = await statsResponse.json();
      setStatistics(statsData);

      // Load outcomes
      const outcomesParams = new URLSearchParams();
      if (printerFilter) outcomesParams.append('printer_id', printerFilter);
      if (materialFilter) outcomesParams.append('material_id', materialFilter);
      if (successFilter) outcomesParams.append('success', successFilter);
      outcomesParams.append('limit', '200');

      const outcomesResponse = await fetch(`/api/fabrication/outcomes?${outcomesParams}`);
      if (!outcomesResponse.ok) throw new Error('Failed to load outcomes');
      const outcomesData = await outcomesResponse.json();
      setOutcomes(outcomesData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetails = (outcome: PrintOutcome) => {
    setSelectedOutcome(outcome);
    setShowDetailModal(true);
  };

  const handleStartReview = (outcome: PrintOutcome) => {
    setSelectedOutcome(outcome);
    setReviewForm({
      reviewed_by: 'operator',
      quality_score: outcome.success ? 80 : 0,
      failure_reason: outcome.failure_reason || '',
      notes: '',
    });
    setShowReviewModal(true);
  };

  const handleSubmitReview = async () => {
    if (!selectedOutcome) return;

    try {
      const response = await fetch(`/api/fabrication/outcomes/${selectedOutcome.job_id}/review`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reviewForm),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to submit review');
      }

      // Reload data
      await loadData();
      setShowReviewModal(false);
      setSelectedOutcome(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to submit review');
    }
  };

  // Calculate failure breakdown
  const failureBreakdown = outcomes
    .filter((o) => !o.success && o.failure_reason)
    .reduce((acc, outcome) => {
      const reason = outcome.failure_reason || 'unknown';
      acc[reason] = (acc[reason] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

  // Filter for pending review
  const filteredOutcomes = showPendingReviewOnly
    ? outcomes.filter((o) => !o.human_reviewed)
    : outcomes;

  // Get unique printers and materials for filter dropdowns
  const uniquePrinters = Array.from(new Set(outcomes.map((o) => o.printer_id))).sort();
  const uniqueMaterials = Array.from(new Set(outcomes.map((o) => o.material_id))).sort();

  // Format date
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  // Get quality badge color
  const getQualityBadgeClass = (score: number) => {
    if (score >= 80) return 'quality-excellent';
    if (score >= 60) return 'quality-good';
    if (score >= 40) return 'quality-fair';
    return 'quality-poor';
  };

  if (loading) {
    return (
      <div className="print-intelligence">
        <div className="loading">Loading print intelligence data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="print-intelligence">
        <div className="error">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="print-intelligence">
      <div className="intelligence-header">
        <h1>📊 Print Intelligence</h1>
        <p className="subtitle">Historical print outcomes, success rates, and quality analytics</p>
      </div>

      {/* Statistics Overview */}
      {statistics && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Prints</div>
            <div className="stat-value">{statistics.total_outcomes}</div>
          </div>
          <div className="stat-card stat-success-rate">
            <div className="stat-label">Success Rate</div>
            <div className="stat-value">{(statistics.success_rate * 100).toFixed(1)}%</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Avg Quality Score</div>
            <div className="stat-value">{statistics.avg_quality_score.toFixed(1)}/100</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Avg Duration</div>
            <div className="stat-value">{statistics.avg_duration_hours.toFixed(1)}h</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Cost</div>
            <div className="stat-value">${statistics.total_cost_usd.toFixed(2)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Pending Review</div>
            <div className="stat-value">{outcomes.filter((o) => !o.human_reviewed).length}</div>
          </div>
        </div>
      )}

      {/* Failure Breakdown */}
      {Object.keys(failureBreakdown).length > 0 && (
        <div className="failure-breakdown">
          <h2>Failure Reasons</h2>
          <div className="failure-bars">
            {Object.entries(failureBreakdown)
              .sort(([, a], [, b]) => b - a)
              .map(([reason, count]) => {
                const label = FAILURE_REASONS.find((r) => r.value === reason)?.label || reason;
                const percentage = (count / outcomes.filter((o) => !o.success).length) * 100;
                return (
                  <div key={reason} className="failure-bar-item">
                    <div className="failure-label">
                      {label} ({count})
                    </div>
                    <div className="failure-bar">
                      <div className="failure-bar-fill" style={{ width: `${percentage}%` }} />
                    </div>
                    <div className="failure-percentage">{percentage.toFixed(0)}%</div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="filters">
        <div className="filter-group">
          <label>Printer:</label>
          <select value={printerFilter} onChange={(e) => setPrinterFilter(e.target.value)}>
            <option value="">All Printers</option>
            {uniquePrinters.map((printer) => (
              <option key={printer} value={printer}>
                {printer}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Material:</label>
          <select value={materialFilter} onChange={(e) => setMaterialFilter(e.target.value)}>
            <option value="">All Materials</option>
            {uniqueMaterials.map((material) => (
              <option key={material} value={material}>
                {material}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Status:</label>
          <select value={successFilter} onChange={(e) => setSuccessFilter(e.target.value)}>
            <option value="">All Outcomes</option>
            <option value="true">Successful Only</option>
            <option value="false">Failed Only</option>
          </select>
        </div>

        <div className="filter-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={showPendingReviewOnly}
              onChange={(e) => setShowPendingReviewOnly(e.target.checked)}
            />
            <span>Pending Review Only</span>
          </label>
        </div>
      </div>

      {/* Outcomes Table */}
      <div className="outcomes-table">
        <h2>Print History ({filteredOutcomes.length} records)</h2>
        {filteredOutcomes.length === 0 ? (
          <div className="empty-state">No print outcomes found.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Printer</th>
                <th>Material</th>
                <th>Status</th>
                <th>Quality</th>
                <th>Duration</th>
                <th>Cost</th>
                <th>Completed</th>
                <th>Review</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredOutcomes.map((outcome) => (
                <tr
                  key={outcome.id}
                  className={`${!outcome.success ? 'failed-row' : ''} ${
                    !outcome.human_reviewed ? 'unreviewed-row' : ''
                  }`}
                >
                  <td className="job-id">{outcome.job_id}</td>
                  <td>{outcome.printer_id}</td>
                  <td>{outcome.material_id}</td>
                  <td>
                    {outcome.success ? (
                      <span className="badge badge-success">Success</span>
                    ) : (
                      <span className="badge badge-failure">
                        Failed
                        {outcome.failure_reason && `: ${FAILURE_REASONS.find((r) => r.value === outcome.failure_reason)?.label || outcome.failure_reason}`}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`quality-badge ${getQualityBadgeClass(outcome.quality_score)}`}>
                      {outcome.quality_score.toFixed(0)}/100
                    </span>
                  </td>
                  <td>{outcome.actual_duration_hours.toFixed(1)}h</td>
                  <td>${outcome.actual_cost_usd.toFixed(2)}</td>
                  <td className="date-cell">{formatDate(outcome.completed_at)}</td>
                  <td>
                    {outcome.human_reviewed ? (
                      <span className="badge badge-reviewed">✓ Reviewed</span>
                    ) : (
                      <span className="badge badge-pending">Pending</span>
                    )}
                  </td>
                  <td className="actions-cell">
                    <button className="btn-small btn-view" onClick={() => handleViewDetails(outcome)}>
                      View
                    </button>
                    {!outcome.human_reviewed && (
                      <button className="btn-small btn-review" onClick={() => handleStartReview(outcome)}>
                        Review
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail Modal */}
      {showDetailModal && selectedOutcome && (
        <div className="modal-overlay" onClick={() => setShowDetailModal(false)}>
          <div className="modal-content detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Print Outcome Details</h2>
              <button className="modal-close" onClick={() => setShowDetailModal(false)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="detail-section">
                <h3>Job Information</h3>
                <div className="detail-grid">
                  <div>
                    <strong>Job ID:</strong> {selectedOutcome.job_id}
                  </div>
                  <div>
                    <strong>Printer:</strong> {selectedOutcome.printer_id}
                  </div>
                  <div>
                    <strong>Material:</strong> {selectedOutcome.material_id}
                  </div>
                  <div>
                    <strong>Started:</strong> {formatDate(selectedOutcome.started_at)}
                  </div>
                  <div>
                    <strong>Completed:</strong> {formatDate(selectedOutcome.completed_at)}
                  </div>
                  <div>
                    <strong>Duration:</strong> {selectedOutcome.actual_duration_hours.toFixed(2)} hours
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <h3>Outcome</h3>
                <div className="detail-grid">
                  <div>
                    <strong>Status:</strong>{' '}
                    {selectedOutcome.success ? (
                      <span className="badge badge-success">Success</span>
                    ) : (
                      <span className="badge badge-failure">Failed</span>
                    )}
                  </div>
                  <div>
                    <strong>Quality Score:</strong>{' '}
                    <span className={`quality-badge ${getQualityBadgeClass(selectedOutcome.quality_score)}`}>
                      {selectedOutcome.quality_score.toFixed(0)}/100
                    </span>
                  </div>
                  {selectedOutcome.failure_reason && (
                    <div>
                      <strong>Failure Reason:</strong>{' '}
                      {FAILURE_REASONS.find((r) => r.value === selectedOutcome.failure_reason)?.label ||
                        selectedOutcome.failure_reason}
                    </div>
                  )}
                  <div>
                    <strong>Cost:</strong> ${selectedOutcome.actual_cost_usd.toFixed(2)}
                  </div>
                  <div>
                    <strong>Material Used:</strong> {selectedOutcome.material_used_grams.toFixed(0)}g
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <h3>Print Settings</h3>
                <pre className="settings-json">{JSON.stringify(selectedOutcome.print_settings, null, 2)}</pre>
              </div>

              {selectedOutcome.quality_metrics && Object.keys(selectedOutcome.quality_metrics).length > 0 && (
                <div className="detail-section">
                  <h3>Quality Metrics</h3>
                  <pre className="settings-json">{JSON.stringify(selectedOutcome.quality_metrics, null, 2)}</pre>
                </div>
              )}

              {/* Snapshots */}
              {(selectedOutcome.initial_snapshot_url ||
                selectedOutcome.final_snapshot_url ||
                selectedOutcome.snapshot_urls.length > 0) && (
                <div className="detail-section">
                  <h3>Visual Evidence</h3>
                  <div className="snapshots-grid">
                    {selectedOutcome.initial_snapshot_url && (
                      <div className="snapshot-item">
                        <label>First Layer</label>
                        <img src={selectedOutcome.initial_snapshot_url} alt="First layer" />
                      </div>
                    )}
                    {selectedOutcome.final_snapshot_url && (
                      <div className="snapshot-item">
                        <label>Final Result</label>
                        <img src={selectedOutcome.final_snapshot_url} alt="Final result" />
                      </div>
                    )}
                    {selectedOutcome.snapshot_urls.map((url, idx) => (
                      <div key={idx} className="snapshot-item">
                        <label>Progress {idx + 1}</label>
                        <img src={url} alt={`Progress ${idx + 1}`} />
                      </div>
                    ))}
                  </div>
                  {selectedOutcome.video_url && (
                    <div className="video-container">
                      <label>Timelapse Video</label>
                      <video src={selectedOutcome.video_url} controls />
                    </div>
                  )}
                </div>
              )}

              {/* Review Info */}
              {selectedOutcome.human_reviewed && (
                <div className="detail-section">
                  <h3>Human Review</h3>
                  <div className="detail-grid">
                    <div>
                      <strong>Reviewed By:</strong> {selectedOutcome.reviewed_by || 'Unknown'}
                    </div>
                    <div>
                      <strong>Reviewed At:</strong>{' '}
                      {selectedOutcome.reviewed_at ? formatDate(selectedOutcome.reviewed_at) : 'N/A'}
                    </div>
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              {!selectedOutcome.human_reviewed && (
                <button
                  className="btn-primary"
                  onClick={() => {
                    setShowDetailModal(false);
                    handleStartReview(selectedOutcome);
                  }}
                >
                  Review This Print
                </button>
              )}
              <button className="btn-secondary" onClick={() => setShowDetailModal(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Review Modal */}
      {showReviewModal && selectedOutcome && (
        <div className="modal-overlay" onClick={() => setShowReviewModal(false)}>
          <div className="modal-content review-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Review Print Outcome</h2>
              <button className="modal-close" onClick={() => setShowReviewModal(false)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <p className="review-subtitle">
                Reviewing job: <strong>{selectedOutcome.job_id}</strong>
              </p>

              <div className="form-group">
                <label>Reviewer Name *</label>
                <input
                  type="text"
                  value={reviewForm.reviewed_by}
                  onChange={(e) => setReviewForm({ ...reviewForm, reviewed_by: e.target.value })}
                  placeholder="Your name or ID"
                  required
                />
              </div>

              <div className="form-group">
                <label>Quality Score (0-100) *</label>
                <input
                  type="number"
                  value={reviewForm.quality_score}
                  onChange={(e) =>
                    setReviewForm({ ...reviewForm, quality_score: parseFloat(e.target.value) })
                  }
                  min="0"
                  max="100"
                  step="5"
                  required
                />
                <div className="quality-hint">
                  0 = Complete failure, 50 = Usable but flawed, 80 = Good, 100 = Perfect
                </div>
              </div>

              <div className="form-group">
                <label>Failure Reason (if applicable)</label>
                <select
                  value={reviewForm.failure_reason}
                  onChange={(e) => setReviewForm({ ...reviewForm, failure_reason: e.target.value })}
                >
                  <option value="">None (successful print)</option>
                  {FAILURE_REASONS.map((reason) => (
                    <option key={reason.value} value={reason.value}>
                      {reason.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={reviewForm.notes}
                  onChange={(e) => setReviewForm({ ...reviewForm, notes: e.target.value })}
                  placeholder="Optional notes about print quality, issues, or observations..."
                  rows={4}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowReviewModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSubmitReview}
                disabled={!reviewForm.reviewed_by}
              >
                Submit Review
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PrintIntelligence;
