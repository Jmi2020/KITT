/**
 * Schedule Tab - Autonomy Calendar
 * Create and manage autonomous research schedules
 */

import { useState, useEffect } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';

interface ScheduleProps {
  api: UseResearchApiReturn;
}

const Schedule = ({ api }: ScheduleProps) => {
  // Form state
  const [jobName, setJobName] = useState('');
  const [jobType, setJobType] = useState('research');
  const [nlSchedule, setNlSchedule] = useState('every monday at 5');
  const [cronExpression, setCronExpression] = useState('');
  const [budgetLimit, setBudgetLimit] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [priority, setPriority] = useState(5);

  // Filters
  const [search, setSearch] = useState('');
  const [jobTypeFilter, setJobTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  // Load data on mount
  useEffect(() => {
    api.loadSchedules();
    api.loadScheduleHistory();
  }, []);

  const handleCreateSchedule = async () => {
    const schedule = await api.createSchedule({
      jobName,
      jobType,
      naturalLanguageSchedule: nlSchedule || undefined,
      cronExpression: cronExpression || undefined,
      budgetLimit: budgetLimit ? parseFloat(budgetLimit) : undefined,
      priority,
      enabled,
    });

    if (schedule) {
      setJobName('');
      setNlSchedule('');
      setCronExpression('');
      setBudgetLimit('');
    }
  };

  const handleToggleEnabled = async (id: string, currentEnabled: boolean) => {
    await api.updateSchedule(id, { enabled: !currentEnabled });
  };

  const handleDeleteSchedule = async (id: string) => {
    if (!confirm('Delete this schedule?')) return;
    await api.deleteSchedule(id);
  };

  const formatDate = (value?: string) => {
    if (!value) return '—';
    const d = new Date(value);
    return isNaN(d.getTime()) ? '—' : d.toLocaleString();
  };

  const filteredSchedules = api.schedules
    .filter((s) => (jobTypeFilter === 'all' ? true : s.job_type === jobTypeFilter))
    .filter((s) => (search ? s.job_name.toLowerCase().includes(search.toLowerCase()) : true))
    .sort((a, b) => {
      const aNext = a.next_execution_at ? new Date(a.next_execution_at).getTime() : Infinity;
      const bNext = b.next_execution_at ? new Date(b.next_execution_at).getTime() : Infinity;
      return aNext - bNext;
    });

  const filteredHistory = api.scheduleHistory
    .filter((h) => (statusFilter === 'all' ? true : h.status === statusFilter))
    .slice(0, 50);

  return (
    <div className="schedule-tab">
      <h2>Autonomy Calendar</h2>
      <p className="subtitle">Create and manage autonomous schedules (research, checks, etc.)</p>

      {/* Filters */}
      <div className="filters-row">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by job name"
        />
        <select value={jobTypeFilter} onChange={(e) => setJobTypeFilter(e.target.value)}>
          <option value="all">All types</option>
          <option value="research">Research</option>
          <option value="health_check">Health Check</option>
          <option value="project_generation">Project Generation</option>
          <option value="knowledge_update">Knowledge Update</option>
          <option value="task_execution">Task Execution</option>
          <option value="custom">Custom</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All history statuses</option>
          <option value="success">success</option>
          <option value="failed">failed</option>
        </select>
        <button className="btn-small" onClick={() => api.loadSchedules()}>
          {api.loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Create Form */}
      <div className="create-card">
        <h3>New Schedule</h3>
        <div className="form-grid">
          <div className="form-group">
            <label htmlFor="jobName">Job name</label>
            <input
              id="jobName"
              value={jobName}
              onChange={(e) => setJobName(e.target.value)}
              placeholder="Weekly research"
            />
          </div>
          <div className="form-group">
            <label htmlFor="jobType">Job type</label>
            <select id="jobType" value={jobType} onChange={(e) => setJobType(e.target.value)}>
              <option value="research">Research</option>
              <option value="health_check">Health Check</option>
              <option value="project_generation">Project Generation</option>
              <option value="knowledge_update">Knowledge Update</option>
              <option value="task_execution">Task Execution</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="nlSchedule">Natural language (optional)</label>
            <input
              id="nlSchedule"
              value={nlSchedule}
              onChange={(e) => setNlSchedule(e.target.value)}
              placeholder="every monday at 5"
            />
          </div>
          <div className="form-group">
            <label htmlFor="cronExpr">Cron (optional)</label>
            <input
              id="cronExpr"
              value={cronExpression}
              onChange={(e) => setCronExpression(e.target.value)}
              placeholder="0 5 * * 1"
            />
          </div>
          <div className="form-group">
            <label htmlFor="budgetLimit">Budget limit ($)</label>
            <input
              id="budgetLimit"
              value={budgetLimit}
              onChange={(e) => setBudgetLimit(e.target.value)}
              placeholder="0.50"
            />
          </div>
          <div className="form-group">
            <label htmlFor="priority">Priority (1-10)</label>
            <input
              id="priority"
              type="number"
              min={1}
              max={10}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            />
          </div>
          <div className="form-group checkbox-row">
            <label>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Enabled
            </label>
          </div>
        </div>
        <button className="btn-primary" onClick={handleCreateSchedule}>
          Create Schedule
        </button>
      </div>

      {/* Schedules List */}
      <div className="list-section">
        <div className="list-header">
          <h3>Schedules</h3>
          <span className="count">{filteredSchedules.length}</span>
        </div>
        <div className="schedule-list">
          {filteredSchedules.map((s) => (
            <div key={s.id} className="schedule-card">
              <div className="schedule-row">
                <div className="schedule-info">
                  <div className="schedule-name">{s.job_name}</div>
                  <div className="schedule-meta">
                    <span className="pill">{s.job_type}</span>
                    <span className="pill">{s.cron_expression}</span>
                    {s.natural_language_schedule && (
                      <span className="pill pill-muted">{s.natural_language_schedule}</span>
                    )}
                    {s.priority && <span className="pill pill-muted">P{String(s.priority)}</span>}
                    <span className={`pill ${s.enabled ? '' : 'pill-muted'}`}>
                      {s.enabled ? 'enabled' : 'disabled'}
                    </span>
                  </div>
                </div>
                <div className="schedule-actions">
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={s.enabled}
                      onChange={() => handleToggleEnabled(s.id, s.enabled)}
                    />
                    <span>Enabled</span>
                  </label>
                  <button
                    className="btn-text danger"
                    onClick={() => handleDeleteSchedule(s.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
              <div className="schedule-times">
                <span>Next: {formatDate(s.next_execution_at)}</span>
                <span>Last: {formatDate(s.last_execution_at)}</span>
                {s.budget_limit_usd != null && (
                  <span>Budget: ${s.budget_limit_usd.toFixed(2)}</span>
                )}
              </div>
            </div>
          ))}
          {api.schedules.length === 0 && <div className="empty-state">No schedules yet.</div>}
        </div>
      </div>

      {/* Execution History */}
      <div className="list-section">
        <div className="list-header">
          <h3>Recent Executions</h3>
          <span className="count">{filteredHistory.length}</span>
        </div>
        <div className="history-list">
          {filteredHistory.map((h) => (
            <div key={h.id} className="history-row">
              <div className="history-name">{h.job_name}</div>
              <div className="history-meta">
                <span className={`pill ${h.status === 'success' ? 'pill-success' : 'pill-error'}`}>
                  {h.status}
                </span>
                {h.budget_spent_usd != null && (
                  <span className="pill pill-muted">
                    Cost: ${Number(h.budget_spent_usd).toFixed(2)}
                  </span>
                )}
                <span className="pill pill-muted">{formatDate(h.execution_time)}</span>
              </div>
              {h.error_message && <div className="history-error">{h.error_message}</div>}
            </div>
          ))}
          {api.scheduleHistory.length === 0 && (
            <div className="empty-state">No executions yet.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Schedule;
