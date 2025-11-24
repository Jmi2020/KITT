import React, { useState } from 'react';
import { Card, Select, Input, Button, Spin, Badge, Divider } from 'antd';
import { RobotOutlined, TeamOutlined, MessageOutlined } from '@ant-design/icons';

const { TextArea } = Input;

interface Proposal {
  role: string;
  text: string;
  label?: string;
  model?: string;
}

interface CollectiveResponse {
  pattern: string;
  proposals: Proposal[];
  verdict: string;
  logs?: string;
  peer_reviews?: any[];
  aggregate_rankings?: { label: string; model?: string; average_rank: number }[];
}

export const CollectivePanel: React.FC = () => {
  const [pattern, setPattern] = useState<'council' | 'debate' | 'pipeline'>('council');
  const [k, setK] = useState(3);
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CollectiveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runCollective = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/collective/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, pattern, k })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Unknown error');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const getPatternIcon = (pattern: string) => {
    switch (pattern) {
      case 'council': return <TeamOutlined />;
      case 'debate': return <MessageOutlined />;
      case 'pipeline': return <RobotOutlined />;
      default: return <RobotOutlined />;
    }
  };

  const getPatternColor = (pattern: string) => {
    switch (pattern) {
      case 'council': return 'blue';
      case 'debate': return 'orange';
      case 'pipeline': return 'purple';
      default: return 'default';
    }
  };

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <RobotOutlined style={{ fontSize: 20 }} />
          <span>Collective Meta-Agent</span>
          <Badge
            count="Multi-Agent"
            style={{ backgroundColor: '#52c41a', marginLeft: 8 }}
          />
        </div>
      }
      style={{ maxWidth: 1200, margin: '0 auto' }}
    >
      {/* Configuration Section */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
            Pattern
          </label>
          <Select
            value={pattern}
            onChange={setPattern}
            style={{ width: '100%', maxWidth: 300 }}
            disabled={loading}
          >
            <Select.Option value="council">
              <TeamOutlined /> Council (K specialists propose solutions)
            </Select.Option>
            <Select.Option value="debate">
              <MessageOutlined /> Debate (PRO vs CON arguments)
            </Select.Option>
            <Select.Option value="pipeline">
              <RobotOutlined /> Pipeline (Sequential workflow)
            </Select.Option>
          </Select>
        </div>

        {pattern === 'council' && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
              Number of Specialists (k)
            </label>
            <Select
              value={k}
              onChange={setK}
              style={{ width: 200 }}
              disabled={loading}
            >
              {[2, 3, 4, 5, 6, 7].map(n => (
                <Select.Option key={n} value={n}>k = {n}</Select.Option>
              ))}
            </Select>
          </div>
        )}

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
            Task Description
          </label>
          <TextArea
            placeholder="Enter your question or task for multi-agent analysis...

Examples:
• Compare PETG vs ABS vs ASA for outdoor furniture
• Should I use tree supports for this overhang?
• Recommend optimal print settings for a tall vase"
            value={task}
            onChange={e => setTask(e.target.value)}
            rows={4}
            disabled={loading}
          />
        </div>

        <Button
          type="primary"
          onClick={runCollective}
          loading={loading}
          disabled={!task.trim()}
          icon={getPatternIcon(pattern)}
          size="large"
        >
          {loading ? 'Generating Proposals...' : `Run ${pattern.charAt(0).toUpperCase() + pattern.slice(1)}`}
        </Button>

        {loading && (
          <div style={{ marginTop: 16, color: '#888' }}>
            <Spin /> Estimated time: {pattern === 'council' ? `${k * 20}-${k * 30}s` : '50-120s'}
            {pattern === 'council' && ' (specialists working in parallel)'}
          </div>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <Card type="inner" style={{ marginBottom: 16, borderColor: '#ff4d4f' }}>
          <div style={{ color: '#ff4d4f' }}>
            <strong>Error:</strong> {error}
          </div>
        </Card>
      )}

      {/* Results Display */}
      {result && (
        <div>
          <Divider />
          <h3 style={{ marginBottom: 16 }}>
            <Badge color={getPatternColor(result.pattern)} />
            Results ({result.pattern})
          </h3>

          {/* Proposals */}
          <div style={{ marginBottom: 24 }}>
            <h4>Proposals ({result.proposals.length})</h4>
            {result.proposals.map((prop, i) => (
              <Card
                key={i}
                type="inner"
                size="small"
                style={{ marginBottom: 12 }}
                title={
                  <span>
                    <Badge
                      count={i + 1}
                      style={{ backgroundColor: '#1890ff', marginRight: 8 }}
                    />
                    {prop.label || `Response ${String.fromCharCode(65 + i)}`} [{prop.role}{prop.model ? ` • ${prop.model}` : ''}]
                  </span>
                }
              >
                <div style={{ whiteSpace: 'pre-wrap' }}>{prop.text}</div>
              </Card>
            ))}

            {result.aggregate_rankings && result.aggregate_rankings.length > 0 && (
              <Card type="inner" size="small" title="Aggregate Ranking" style={{ marginTop: 12 }}>
                <ul style={{ paddingLeft: 16 }}>
                  {result.aggregate_rankings.map((r, idx) => (
                    <li key={idx}>
                      {r.label} {r.model ? `(${r.model})` : ''} — avg_rank={r.average_rank}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>

          {/* Verdict */}
          <div>
            <h4 style={{ color: '#52c41a' }}>⚖️ Judge Verdict</h4>
            <Card
              style={{
                backgroundColor: '#f6ffed',
                borderColor: '#b7eb8f'
              }}
            >
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 15 }}>
                {result.verdict}
              </div>
            </Card>
          </div>

          {/* Peer Reviews */}
          {result.peer_reviews && result.peer_reviews.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h4>Peer Reviews</h4>
              {result.peer_reviews.map((pr, i) => (
                <Card key={i} type="inner" size="small" style={{ marginBottom: 12 }}>
                  <strong>Reviewer:</strong> {pr.reviewer_model || 'anonymous'}<br />
                  <div style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{pr.critiques || pr.raw_ranking}</div>
                </Card>
              ))}
            </div>
          )}

          {/* Logs (collapsible) */}
          {result.logs && (
            <details style={{ marginTop: 16 }}>
              <summary style={{ cursor: 'pointer', color: '#888' }}>
                View Execution Logs
              </summary>
              <pre style={{
                marginTop: 8,
                padding: 12,
                backgroundColor: '#f5f5f5',
                borderRadius: 4,
                fontSize: 12,
                overflow: 'auto'
              }}>
                {result.logs}
              </pre>
            </details>
          )}
        </div>
      )}
    </Card>
  );
};
