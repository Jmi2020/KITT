# LangGraph Routing Service Level Objectives (SLOs)

## Overview

This document defines the Service Level Objectives (SLOs) for the LangGraph-enhanced routing system in KITTY Brain. These SLOs establish quantifiable targets for system performance, reliability, and quality.

## SLO Framework

**SLI (Service Level Indicator)**: Quantitative measure of service behavior
**SLO (Service Level Objective)**: Target value or range for an SLI
**SLA (Service Level Agreement)**: Contract with consequences for missing SLOs

## Critical SLOs

### 1. Q4 Routing Latency

**SLI**: P95 latency of router_graph execution
**SLO**: P95 < 2 seconds
**Measurement Window**: 5 minutes
**Target Availability**: 99.0%

**Rationale**: Q4 handles 80% of queries and must provide fast responses for acceptable user experience.

**Alert Thresholds**:
- **Warning**: P95 > 2s for 3 minutes
- **Critical**: P95 > 5s for 2 minutes

**Prometheus Query**:
```promql
histogram_quantile(0.95,
  sum by (le) (rate(brain_graph_node_duration_seconds_bucket{graph="router_graph"}[5m]))
)
```

---

### 2. F16 Deep Reasoner Latency

**SLI**: P95 latency of deep_reasoner_graph execution
**SLO**: P95 < 10 seconds
**Measurement Window**: 5 minutes
**Target Availability**: 95.0%

**Rationale**: F16 handles complex queries requiring deeper reasoning; users expect longer latency but still bounded.

**Alert Thresholds**:
- **Warning**: P95 > 10s for 3 minutes
- **Critical**: P95 > 20s for 2 minutes

**Prometheus Query**:
```promql
histogram_quantile(0.95,
  sum by (le) (rate(brain_graph_node_duration_seconds_bucket{graph="deep_reasoner_graph"}[5m]))
)
```

---

### 3. Escalation Success Rate

**SLI**: Percentage of F16 escalations that succeed (don't fallback to Q4)
**SLO**: Success rate > 90%
**Measurement Window**: 5 minutes
**Target Availability**: 99.5%

**Rationale**: F16 escalation should reliably provide higher-quality responses; frequent fallbacks indicate F16 service issues.

**Alert Thresholds**:
- **Warning**: Failure rate > 10% for 5 minutes
- **Critical**: Failure rate > 25% for 3 minutes

**Prometheus Query**:
```promql
100 * (
  sum(rate(brain_escalation_status_total{status="success"}[5m]))
  /
  sum(rate(brain_escalation_status_total[5m]))
)
```

---

### 4. Tool Execution Success Rate

**SLI**: Percentage of tool executions that complete successfully
**SLO**: Success rate > 80%
**Measurement Window**: 5 minutes
**Target Availability**: 98.0%

**Rationale**: Tools are critical for CAD generation, fabrication, and other capabilities; high failure rates degrade user experience.

**Alert Thresholds**:
- **Warning**: Failure rate > 20% for 5 minutes
- **Critical**: Failure rate > 40% for 3 minutes

**Prometheus Query**:
```promql
100 * (
  sum(rate(brain_tool_execution_total{status="completed"}[5m]))
  /
  sum(rate(brain_tool_execution_total[5m]))
)
```

---

### 5. Response Confidence Quality

**SLI**: Percentage of queries with confidence ≥ 0.6
**SLO**: ≥ 70% of queries achieve confidence ≥ 0.6
**Measurement Window**: 5 minutes
**Target Availability**: 95.0%

**Rationale**: Low-confidence responses indicate the system is struggling; excessive low-confidence queries suggest degraded service quality.

**Alert Thresholds**:
- **Warning**: > 30% of queries with confidence ≤ 0.6 for 10 minutes

**Prometheus Query**:
```promql
100 * (
  1 - (
    sum(rate(brain_confidence_distribution_bucket{le="0.6"}[5m]))
    /
    sum(rate(brain_confidence_distribution_count[5m]))
  )
)
```

---

### 6. Memory Retrieval Latency

**SLI**: P95 latency of memory retrieval operations
**SLO**: P95 < 1 second
**Measurement Window**: 5 minutes
**Target Availability**: 98.0%

**Rationale**: Memory retrieval is synchronous and blocks query processing; slow retrieval degrades overall latency.

**Alert Thresholds**:
- **Warning**: P95 > 1s for 5 minutes

**Prometheus Query**:
```promql
histogram_quantile(0.95,
  sum by (le) (rate(brain_memory_retrieval_duration_seconds_bucket[5m]))
)
```

---

### 7. Graph Execution Success Rate

**SLI**: Percentage of graph executions that complete without errors
**SLO**: Success rate > 95%
**Measurement Window**: 5 minutes
**Target Availability**: 99.0%

**Rationale**: Graph execution failures result in error responses to users; system should gracefully handle edge cases.

**Alert Thresholds**:
- **Warning**: Failure rate > 5% for 5 minutes

**Prometheus Query**:
```promql
100 * (
  sum(rate(brain_graph_execution_total{status="completed"}[5m]))
  /
  sum(rate(brain_graph_execution_total[5m]))
)
```

---

## Secondary SLOs

### 8. F16 Self-Evaluation Quality

**SLI**: Median F16 self-evaluation score
**SLO**: P50 ≥ 0.7
**Measurement Window**: 5 minutes
**Target Availability**: 90.0%

**Alert Thresholds**:
- **Warning**: P50 < 0.5 for 10 minutes

---

### 9. Memory Sufficiency

**SLI**: Median memory sufficiency score
**SLO**: P50 ≥ 0.6
**Measurement Window**: 5 minutes
**Target Availability**: 90.0%

**Alert Thresholds**:
- **Warning**: P50 < 0.5 for 15 minutes

---

### 10. Critical Tool Availability

**SLI**: Per-tool success rate for critical tools (CAD, fabrication, coding)
**SLO**: Success rate > 90% per tool
**Measurement Window**: 5 minutes
**Target Availability**: 99.0%

**Alert Thresholds**:
- **Critical**: Specific tool failure rate > 80% for 3 minutes

---

## SLO Compliance Tracking

### Monthly SLO Review

Track SLO compliance monthly using error budget methodology:

**Error Budget Formula**:
```
Error Budget = (1 - SLO Target) × Total Requests
```

**Example** (Q4 Latency SLO of 99.0%):
- Total requests in month: 1,000,000
- SLO target: 99.0%
- Error budget: (1 - 0.99) × 1,000,000 = 10,000 slow requests allowed

**Tracking Queries**:

```promql
# Q4 Latency Error Budget Consumption
sum(
  rate(brain_graph_node_duration_seconds_bucket{graph="router_graph", le="2"}[30d])
)
/
sum(
  rate(brain_graph_node_duration_seconds_count{graph="router_graph"}[30d])
) * 100
```

---

## SLO Dashboard Links

- **Routing Overview**: `langgraph-routing-overview` dashboard
- **Quality Metrics**: `langgraph-quality-metrics` dashboard
- **Tool Performance**: `langgraph-tool-performance` dashboard
- **Memory Performance**: `langgraph-memory-performance` dashboard

---

## SLO Escalation Policy

### Severity Levels

**Info**: SLO degradation < 10% below target
- Response: Monitor, no immediate action

**Warning**: SLO degradation 10-25% below target
- Response: Investigate within 1 hour
- Notify: On-call engineer via PagerDuty/Slack

**Critical**: SLO degradation > 25% below target OR critical tool down
- Response: Immediate investigation
- Notify: On-call engineer + team lead
- Action: Incident response playbook

---

## SLO Review Cadence

**Daily**: Review critical SLO compliance (automated)
**Weekly**: Review secondary SLO trends
**Monthly**: SLO compliance report + error budget analysis
**Quarterly**: SLO target adjustment based on capacity and user needs

---

## Related Documentation

- **Alerting Rules**: `/infra/prometheus/alerts/langgraph-alerts.yml`
- **Runbook**: `/ops/runbooks/langgraph-troubleshooting.md`
- **Capacity Planning**: `/services/brain/src/brain/agents/graphs/CAPACITY_PLANNING.md`
- **Testing Guide**: `/services/brain/src/brain/agents/graphs/TESTING_GUIDE.md`

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-01-XX | 1.0 | Initial SLO definitions for Phase 4 |
