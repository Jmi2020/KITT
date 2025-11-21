import { useEffect, useState } from 'react';
import { getWebUserId } from '../utils/user';
import './AutonomyCalendar.css';

interface Schedule {
  id: string;
  user_id: string;
  job_type: string;
  job_name: string;
  description?: string;
  natural_language_schedule?: string;
  cron_expression: string;
  timezone: string;
  enabled: boolean;
  budget_limit_usd?: number;
  priority: number;
  tags?: string[];
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  last_execution_at?: string;
  next_execution_at?: string;
}

const AutonomyCalendar = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobTypeFilter, setJobTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [jobName, setJobName] = useState('');
  const [jobType, setJobType] = useState('research');
  const [nlSchedule, setNlSchedule] = useState('every monday at 5');
  const [cronExpression, setCronExpression] = useState('');
  const [budgetLimit, setBudgetLimit] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [priority, setPriority] = useState(5);
  const userId = getWebUserId();

  useEffect(() => {
    loadSchedules();
    loadHistory();
  }, []);

  const loadSchedules = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/autonomy/calendar/schedules?user_id=${encodeURIComponent(userId)}`);
      if (!res.ok) throw new Error(`Failed to load schedules (${res.status})`);
      const data: Schedule[] = await res.json();
      setSchedules(data);
    } catch (e: any) {
      setError(e.message || 'Failed to load schedules');
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    try {
      const res = await fetch('/api/autonomy/calendar/history?limit=50');
      if (!res.ok) throw new Error(`Failed to load history (${res.status})`);
      const data: any[] = await res.json();
      setHistory(data);
    } catch (e: any) {
      setError((prev) => prev || e.message || 'Failed to load history');
    }
  };

  const createSchedule = async () => {
    if (!jobName.trim()) {
      setError('Job name is required');
      return;
    }
    setError(null);
    try {
      const payload: any = {
        job_type: jobType,
        job_name: jobName,
        natural_language_schedule: nlSchedule || undefined,
        cron_expression: cronExpression || undefined,
        budget_limit_usd: budgetLimit ? parseFloat(budgetLimit) : undefined,
        priority,
        enabled,
        user_id: userId,
      };
      const res = await fetch('/api/autonomy/calendar/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Failed to create schedule (${res.status})`);
      setJobName('');
      setNlSchedule('');
      setCronExpression('');
      setBudgetLimit('');
      await loadSchedules();
    } catch (e: any) {
      setError(e.message || 'Failed to create schedule');
    }
  };

  const toggleEnabled = async (id: string, current: boolean) => {
    try {
      const res = await fetch(`/api/autonomy/calendar/schedules/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !current }),
      });
      if (!res.ok) throw new Error(`Failed to update schedule (${res.status})`);
      await loadSchedules();
    } catch (e: any) {
      setError(e.message || 'Failed to update schedule');
    }
  };

  const deleteSchedule = async (id: string) => {
    if (!confirm('Delete this schedule?')) return;
    try {
      const res = await fetch(`/api/autonomy/calendar/schedules/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Failed to delete schedule (${res.status})`);
      await loadSchedules();
    } catch (e: any) {
      setError(e.message || 'Failed to delete schedule');
    }
  };

  const formatDate = (value?: string) => {
    if (!value) return '—';
    const d = new Date(value);
    return isNaN(d.getTime()) ? '—' : d.toLocaleString();
  };

  const filteredSchedules = schedules
    .filter((s) => (jobTypeFilter === 'all' ? true : s.job_type === jobTypeFilter))
    .filter((s) => (search ? s.job_name.toLowerCase().includes(search.toLowerCase()) : true))
    .sort((a, b) => {
      const aNext = a.next_execution_at ? new Date(a.next_execution_at).getTime() : Infinity;
      const bNext = b.next_execution_at ? new Date(b.next_execution_at).getTime() : Infinity;
      return aNext - bNext;
    });

  const filteredHistory = history
    .filter((h) => (statusFilter === 'all' ? true : h.status === statusFilter))
    .slice(0, 50);

  return (
    <section className="autonomy-calendar">
      <header>
        <div>
          <h2>Autonomy Calendar</h2>
          <p className="muted">Create and manage autonomous schedules (research, checks, etc.).</p>
        </div>
        <div className="header-actions">
          <button onClick={loadSchedules} className="btn-refresh">{loading ? 'Loading…' : 'Refresh'}</button>
          <button onClick={loadHistory} className="btn-refresh">Reload History</button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

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
      </div>

      <div className="create-card">
        <h3>New Schedule</h3>
        <div className="form-grid">
          <label>
            Job name
            <input value={jobName} onChange={(e) => setJobName(e.target.value)} placeholder="Weekly research" />
          </label>
          <label>
            Job type
            <select value={jobType} onChange={(e) => setJobType(e.target.value)}>
              <option value="research">Research</option>
              <option value="health_check">Health Check</option>
              <option value="project_generation">Project Generation</option>
              <option value="knowledge_update">Knowledge Update</option>
              <option value="task_execution">Task Execution</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label>
            Natural language (optional)
            <input value={nlSchedule} onChange={(e) => setNlSchedule(e.target.value)} placeholder="every monday at 5" />
          </label>
          <label>
            Cron (optional)
            <input value={cronExpression} onChange={(e) => setCronExpression(e.target.value)} placeholder="0 5 * * 1" />
          </label>
          <label>
            Budget limit ($)
            <input value={budgetLimit} onChange={(e) => setBudgetLimit(e.target.value)} placeholder="0.50" />
          </label>
          <label>
            Priority (1-10)
            <input type="number" min={1} max={10} value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Enabled
          </label>
        </div>
        <button onClick={createSchedule} className="btn-primary">Create</button>
      </div>

      <div className="list-header">
        <h3>Schedules</h3>
        <span className="count">{filteredSchedules.length}</span>
      </div>
      <div className="schedule-list">
        {filteredSchedules.map((s) => (
          <div key={s.id} className="schedule-card">
            <div className="schedule-row">
              <div>
                <div className="name">{s.job_name}</div>
                <div className="meta">
                  <span className="pill">{s.job_type}</span>
                  <span className="pill">{s.cron_expression}</span>
                  {s.natural_language_schedule && <span className="pill pill-muted">{s.natural_language_schedule}</span>}
                  {s.priority && <span className="pill pill-muted">P{String(s.priority)}</span>}
                  {s.enabled ? <span className="pill">enabled</span> : <span className="pill pill-muted">disabled</span>}
                </div>
              </div>
              <div className="actions">
                <label className="toggle">
                  <input type="checkbox" checked={s.enabled} onChange={() => toggleEnabled(s.id, s.enabled)} />
                  <span>Enabled</span>
                </label>
                <button onClick={() => deleteSchedule(s.id)} className="btn-text danger">Delete</button>
              </div>
            </div>
            <div className="times">
              <span>Next: {formatDate(s.next_execution_at)}</span>
              <span>Last: {formatDate(s.last_execution_at)}</span>
              {s.budget_limit_usd != null && <span>Budget: ${s.budget_limit_usd.toFixed(2)}</span>}
            </div>
          </div>
        ))}
        {schedules.length === 0 && <div className="empty">No schedules yet.</div>}
      </div>

      <div className="list-header">
        <h3>Recent Executions</h3>
        <span className="count">{filteredHistory.length}</span>
      </div>
      <div className="history-list">
        {filteredHistory.map((h) => (
          <div key={h.id} className="history-row">
            <div className="name">{h.job_name}</div>
            <div className="meta">
              <span className="pill">{h.status}</span>
              {h.budget_spent_usd != null && <span className="pill pill-muted">Cost: ${Number(h.budget_spent_usd).toFixed(2)}</span>}
              <span className="pill pill-muted">{formatDate(h.execution_time)}</span>
            </div>
            {h.error_message && <div className="error-text">{h.error_message}</div>}
          </div>
        ))}
        {history.length === 0 && <div className="empty">No executions yet.</div>}
      </div>
    </section>
  );
};

export default AutonomyCalendar;
