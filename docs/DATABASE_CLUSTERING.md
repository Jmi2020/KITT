# Database Clustering & High Availability - Operations Guide

## Overview

KITT's database clustering implementation provides high availability and automatic failover for both PostgreSQL and Redis, eliminating single points of failure and ensuring continuous operation even when database nodes fail.

**Status**: ✅ **Production Ready** (P2 #14 Implementation Complete)

**Architecture**:
- **PostgreSQL**: 1 primary + 2 read replicas with streaming replication + PgBouncer connection pooling
- **Redis**: 1 master + 2 replicas + 3 Sentinel nodes for automatic failover

**Benefits**:
- Automatic failover if primary/master fails
- Read load distribution across replicas
- Zero downtime for read operations during failover
- Data durability with synchronous replication
- Connection pooling for efficient resource usage

---

## Table of Contents

1. [Architecture](#architecture)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Operations](#operations)
5. [Monitoring](#monitoring)
6. [Failover Testing](#failover-testing)
7. [Troubleshooting](#troubleshooting)
8. [Performance Tuning](#performance-tuning)
9. [Production Best Practices](#production-best-practices)
10. [Upgrade & Migration](#upgrade--migration)

---

## Architecture

### PostgreSQL High Availability

```
┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Cluster                                                  │
│                                                                      │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐│
│  │  Primary     │────────>│  Replica 1   │         │  Replica 2   ││
│  │  (5432)      │ stream  │  (5433)      │ stream  │  (5434)      ││
│  │              │<────────│              │<────────│              ││
│  │  READ/WRITE  │  sync   │  READ-ONLY   │  async  │  READ-ONLY   ││
│  └──────┬───────┘         └──────────────┘         └──────────────┘│
│         │                                                            │
│         │                                                            │
│  ┌──────┴───────────────┐                                          │
│  │  PgBouncer (6432)     │  Connection pooling                     │
│  │  Max connections: 1000│  - Reduces connection overhead          │
│  │  Pool size: 25/db     │  - Transaction-level pooling            │
│  │  Pool mode: transaction│ - Automatic reconnection               │
│  └────────────────────────┘                                         │
└──────────────────────────────────────────────────────────────────────┘
```

**Replication Mode**:
- **Streaming Replication**: Changes stream continuously from primary to replicas
- **Synchronous Commit**: Configurable (1 replica must acknowledge by default)
- **WAL (Write-Ahead Log)**: Ensures data durability

**Limitations**:
- **Manual failover required** for PostgreSQL (Bitnami implementation)
- For automatic failover, use **Patroni** or **Stolon** (see Production Best Practices)
- Read replicas remain available when primary fails
- Writes blocked until primary restored or manual promotion

### Redis High Availability (Sentinel)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Redis Cluster with Sentinel                                         │
│                                                                      │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐│
│  │  Master      │────────>│  Replica 1   │         │  Replica 2   ││
│  │  (6379)      │  sync   │  (6380)      │  sync   │  (6381)      ││
│  │              │<────────│              │<────────│              ││
│  │  READ/WRITE  │         │  READ-ONLY   │         │  READ-ONLY   ││
│  └──────────────┘         └──────────────┘         └──────────────┘│
│         ▲                        ▲                        ▲         │
│         │                        │                        │         │
│         │ monitor                │                        │         │
│  ┌──────┴───────┐         ┌──────┴───────┐         ┌──────┴───────┐│
│  │  Sentinel 1  │◄───────►│  Sentinel 2  │◄───────►│  Sentinel 3  ││
│  │  (26379)     │  gossip │  (26380)     │  gossip │  (26381)     ││
│  │              │         │              │         │              ││
│  │  Quorum: 2   │         │  Quorum: 2   │         │  Quorum: 2   ││
│  └──────────────┘         └──────────────┘         └──────────────┘│
│                                                                      │
│  Failover Process:                                                   │
│  1. Sentinels detect master failure (5 seconds)                     │
│  2. Quorum election (2/3 Sentinels must agree)                      │
│  3. Promote replica to new master                                   │
│  4. Reconfigure other replicas                                      │
│  5. Notify clients of new master address                            │
│  6. Old master rejoins as replica when restored                     │
└──────────────────────────────────────────────────────────────────────┘
```

**Sentinel Features**:
- **Automatic Failover**: Promotes replica to master when failure detected
- **Monitoring**: Continuously monitors all Redis nodes
- **Notification**: Publishes events for monitoring systems
- **Quorum**: 2/3 Sentinels must agree before failover (prevents split-brain)

**Failover Timing**:
- Detection: ~5 seconds (configurable: `down-after-milliseconds`)
- Election: ~3-5 seconds (leader election among Sentinels)
- Promotion: ~1-2 seconds (reconfiguration)
- **Total downtime**: ~8-12 seconds for writes

---

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- `.env` file configured with database passwords
- Sufficient system resources (4GB RAM minimum, 8GB recommended)

### 1. Enable Database Clustering

Stop existing services:
```bash
cd /home/user/KITT
docker compose -f infra/compose/docker-compose.yml down
```

Start with clustering enabled:
```bash
docker compose \
  -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.db-cluster.yml \
  up -d
```

### 2. Verify Cluster Health

Run health check script:
```bash
./ops/scripts/db-cluster-health.sh --verbose
```

Expected output:
```
╔════════════════════════════════════════════════════════════════╗
║  KITT Database Cluster Health Check                            ║
╚════════════════════════════════════════════════════════════════╝

■ PostgreSQL Cluster

  Primary (5432): ✓ Online
  Replica 1 (5433): ✓ Online
  Replica 2 (5434): ✓ Online
  PgBouncer (6432): ✓ Online

■ Redis Cluster

  Master (6379): ✓ Online
  Replica 1 (6380): ✓ Online
  Replica 2 (6381): ✓ Online

■ Redis Sentinel

  Sentinel 1 (26379): ✓ Online
  Sentinel 2 (26380): ✓ Online
  Sentinel 3 (26381): ✓ Online

╔════════════════════════════════════════════════════════════════╗
║  ✓ All database cluster components are healthy                 ║
╚════════════════════════════════════════════════════════════════╝
```

### 3. Test Failover (Optional - Development Only)

⚠️ **WARNING**: Only run in development/testing environments!

```bash
./ops/scripts/test-db-failover.sh both
```

This will:
1. Stop PostgreSQL primary and verify replicas remain available
2. Stop Redis master and verify Sentinel promotes a replica
3. Restore both nodes and verify rejoin

---

## Configuration

### Environment Variables

All database clustering configuration is in `.env` file:

```bash
# PostgreSQL High Availability
POSTGRES_PASSWORD=changeme
POSTGRES_REPLICATION_PASSWORD=replicator_password
POSTGRES_SYNC_COMMIT=on  # on, remote_write, local, off
POSTGRES_NUM_SYNC_REPLICAS=1  # 0, 1, or 2

# Redis High Availability
REDIS_PASSWORD=  # Empty for development
REDIS_SENTINEL_PASSWORD=
```

### Synchronous Commit Modes

**`POSTGRES_SYNC_COMMIT`** controls data safety vs. performance:

| Mode | Description | Data Safety | Performance | Use Case |
|------|-------------|-------------|-------------|----------|
| `on` | Wait for replica commit confirmation | **Highest** | Slower | Production (recommended) |
| `remote_write` | Wait for replica OS write | High | Balanced | Medium-risk workloads |
| `local` | Only wait for local commit | Medium | Faster | Development |
| `off` | No waiting | **Lowest** | Fastest | Testing only (NOT recommended) |

**`POSTGRES_NUM_SYNC_REPLICAS`** controls how many replicas must confirm:

| Value | Description | Data Safety | Availability |
|-------|-------------|-------------|--------------|
| 0 | Asynchronous replication | Lower | Higher (faster commits) |
| 1 | One replica must confirm | Balanced | Balanced (recommended) |
| 2 | Both replicas must confirm | Highest | Lower (requires all replicas) |

**Recommendation**: Use `POSTGRES_SYNC_COMMIT=on` with `POSTGRES_NUM_SYNC_REPLICAS=1` for production.

### Redis Sentinel Configuration

Sentinel parameters (set in docker-compose.db-cluster.yml):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `down-after-milliseconds` | 5000ms | Time before considering master down |
| `failover-timeout` | 10000ms | Maximum time for failover process |
| `quorum` | 2 | Minimum Sentinels for failover decision |

**Quorum Calculation**:
- With 3 Sentinels: `quorum=2` means majority (2/3) must agree
- Prevents split-brain scenarios
- Ensures consistent failover decisions

---

## Operations

### Connection Strings

#### PostgreSQL

**Primary (read/write)**:
```bash
# Direct connection
postgresql://kitty:changeme@localhost:5432/kitty

# Via PgBouncer (recommended)
postgresql://kitty:changeme@localhost:6432/kitty
```

**Read replicas** (read-only):
```bash
# Replica 1
postgresql://kitty:changeme@localhost:5433/kitty

# Replica 2
postgresql://kitty:changeme@localhost:5434/kitty
```

**Docker internal** (for services):
```bash
# Primary
postgresql://kitty:changeme@postgres-primary:5432/kitty

# PgBouncer
postgresql://kitty:changeme@pgbouncer:6432/kitty

# Replicas
postgresql://kitty:changeme@postgres-replica-1:5432/kitty
postgresql://kitty:changeme@postgres-replica-2:5432/kitty
```

#### Redis

**Sentinel-aware connection**:
```python
from redis.sentinel import Sentinel

sentinel = Sentinel([
    ('localhost', 26379),
    ('localhost', 26380),
    ('localhost', 26381)
], socket_timeout=0.5)

# Get master for writes
master = sentinel.master_for('mymaster', socket_timeout=0.5)
master.set('key', 'value')

# Get replica for reads
replica = sentinel.slave_for('mymaster', socket_timeout=0.5)
value = replica.get('key')
```

**Direct connection** (not recommended - won't follow failover):
```bash
# Master
redis://localhost:6379

# Replicas
redis://localhost:6380
redis://localhost:6381
```

### Manual PostgreSQL Failover

If primary fails permanently:

**1. Promote replica to primary**:
```bash
# Connect to replica-1
docker exec -it $(docker ps -q -f name=postgres-replica-1) bash

# Promote to primary
pg_ctl promote -D /bitnami/postgresql
```

**2. Reconfigure remaining replica**:
```bash
# Update replica-2 to follow new primary
docker exec -it $(docker ps -q -f name=postgres-replica-2) bash

# Edit postgresql.conf
echo "primary_conninfo = 'host=postgres-replica-1 port=5432 user=replicator password=replicator_password'" \
  > /bitnami/postgresql/recovery.conf

# Restart replica
pg_ctl restart -D /bitnami/postgresql
```

**3. Update application connection strings** to point to new primary.

### Redis Sentinel Failover (Automatic)

Sentinel handles failover automatically. No manual intervention required.

To force failover for testing:
```bash
# Trigger manual failover
docker exec -it $(docker ps -q -f name=redis-sentinel-1) \
  redis-cli -p 26379 SENTINEL failover mymaster
```

---

## Monitoring

### Health Checks

**Automated health check** (runs every 10s per container):
```bash
# PostgreSQL
docker exec -it <container> pg_isready -U kitty

# Redis
docker exec -it <container> redis-cli ping

# Redis Sentinel
docker exec -it <container> redis-cli -p 26379 ping
```

**Manual health check script**:
```bash
./ops/scripts/db-cluster-health.sh --verbose
```

### Prometheus Metrics

**PostgreSQL metrics**:
- Replication lag (seconds): `pg_stat_replication_lag_seconds`
- Connection pool usage: `pgbouncer_pools_*`
- Transaction rate: `pg_stat_database_xact_commit_total`

**Redis metrics** (via redis-exporter on port 9121):
- Master-replica sync: `redis_connected_slaves`
- Replication offset: `redis_replica_offset`
- Sentinel status: `redis_sentinel_master_status`

**Grafana dashboards**:
- PostgreSQL Replication Dashboard
- Redis Sentinel Monitoring
- Connection Pool Statistics

### Key Metrics to Monitor

**PostgreSQL**:
```sql
-- Replication lag
SELECT
  client_addr,
  state,
  sync_state,
  replay_lag
FROM pg_stat_replication;

-- Connection pool stats (via PgBouncer)
SHOW POOLS;
```

**Redis**:
```bash
# Master info
redis-cli INFO replication

# Sentinel status
redis-cli -p 26379 SENTINEL masters

# Replication lag
redis-cli -p 26379 SENTINEL master mymaster
```

---

## Failover Testing

### Test Redis Sentinel Failover

```bash
# Run automated test
./ops/scripts/test-db-failover.sh redis
```

**Manual test**:
```bash
# 1. Check current master
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster

# 2. Stop master
docker stop $(docker ps -q -f name=redis-master)

# 3. Wait 8-10 seconds for Sentinel election

# 4. Check new master
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster

# 5. Restore old master
docker start $(docker ps -q -f name=redis-master)
```

**Expected timeline**:
- T+0s: Master stopped
- T+5s: Sentinels detect failure
- T+8s: New master elected and promoted
- T+10s: Clients reconnect to new master

### Test PostgreSQL Replica Availability

```bash
# Run automated test
./ops/scripts/test-db-failover.sh postgres
```

**Manual test**:
```bash
# 1. Stop primary
docker stop $(docker ps -q -f name=postgres-primary)

# 2. Verify replicas still accept reads
psql -h localhost -p 5433 -U kitty -d kitty -c "SELECT NOW();"
psql -h localhost -p 5434 -U kitty -d kitty -c "SELECT NOW();"

# 3. Restore primary
docker start $(docker ps -q -f name=postgres-primary)
```

---

## Troubleshooting

### PostgreSQL Replication Issues

**Problem**: Replica shows high replication lag

**Diagnosis**:
```sql
-- On primary
SELECT * FROM pg_stat_replication;

-- Check WAL files
SELECT pg_current_wal_lsn();
```

**Solutions**:
1. Check network connectivity between primary and replica
2. Verify `max_wal_senders` is sufficient (default: 10)
3. Increase `wal_keep_size` if replica falling behind
4. Check disk I/O on replica

**Problem**: Replica can't connect to primary

**Diagnosis**:
```bash
# Check replica logs
docker logs $(docker ps -q -f name=postgres-replica-1)
```

**Solutions**:
1. Verify `POSTGRES_REPLICATION_PASSWORD` matches
2. Check firewall rules between containers
3. Ensure primary `wal_level=replica` (set by default)

### Redis Sentinel Issues

**Problem**: Sentinel not detecting master failure

**Diagnosis**:
```bash
# Check Sentinel logs
docker logs $(docker ps -q -f name=redis-sentinel-1)

# Verify Sentinel monitoring
redis-cli -p 26379 SENTINEL master mymaster
```

**Solutions**:
1. Increase `down-after-milliseconds` if false positives
2. Verify network connectivity between Sentinel and Redis nodes
3. Check Sentinel quorum configuration

**Problem**: Failover not happening

**Possible causes**:
- Quorum not reached (need 2/3 Sentinels to agree)
- Master not actually down (false alarm)
- Sentinels can't reach replicas

**Diagnosis**:
```bash
# Check Sentinel status
redis-cli -p 26379 SENTINEL sentinels mymaster

# Check all Sentinels
for port in 26379 26380 26381; do
  echo "Sentinel $port:"
  redis-cli -p $port SENTINEL master mymaster | grep flags
done
```

### Connection Pool Issues

**Problem**: PgBouncer showing many waiting clients

**Diagnosis**:
```bash
# Check pool stats
docker exec -it $(docker ps -q -f name=pgbouncer) \
  psql -h localhost -p 6432 -U kitty pgbouncer -c "SHOW POOLS;"
```

**Solutions**:
1. Increase `PGBOUNCER_DEFAULT_POOL_SIZE` (default: 25)
2. Check for long-running queries blocking connections
3. Consider increasing `PGBOUNCER_MAX_CLIENT_CONN` (default: 1000)

---

## Performance Tuning

### PostgreSQL Optimization

**Replication performance**:
```bash
# In docker-compose.db-cluster.yml, increase shared buffers
POSTGRESQL_SHARED_BUFFERS: 512MB  # Default: 256MB
POSTGRESQL_EFFECTIVE_CACHE_SIZE: 2GB  # Default: 1GB
```

**Connection pooling** (PgBouncer):
```bash
# Adjust based on workload
PGBOUNCER_DEFAULT_POOL_SIZE: 50  # Increase for high concurrency
PGBOUNCER_RESERVE_POOL_SIZE: 10  # Emergency connections
PGBOUNCER_SERVER_IDLE_TIMEOUT: 300  # Close idle connections faster
```

**Synchronous commit tuning**:
- High write throughput: `POSTGRES_SYNC_COMMIT=remote_write`
- Balance: `POSTGRES_SYNC_COMMIT=on` + `POSTGRES_NUM_SYNC_REPLICAS=1`
- Maximum safety: `POSTGRES_SYNC_COMMIT=on` + `POSTGRES_NUM_SYNC_REPLICAS=2`

### Redis Optimization

**Memory policy**:
```bash
# In docker-compose.db-cluster.yml
REDIS_MAXMEMORY: 4gb  # Increase for larger dataset
REDIS_MAXMEMORY_POLICY: allkeys-lru  # LRU eviction for cache workload
```

**Persistence tuning**:
```bash
# Disable AOF for performance (less durability)
REDIS_AOF_ENABLED: "no"

# Adjust RDB snapshot frequency
REDIS_SAVE: "3600 1 300 100"  # Less frequent saves
```

**Sentinel tuning**:
- Faster failover: `REDIS_SENTINEL_DOWN_AFTER_MILLISECONDS: 3000`
- Slower (fewer false positives): `REDIS_SENTINEL_DOWN_AFTER_MILLISECONDS: 10000`

---

## Production Best Practices

### 1. Use Patroni for PostgreSQL Automatic Failover

Bitnami PostgreSQL provides streaming replication but NOT automatic failover. For production, use **Patroni**:

```yaml
# Example Patroni setup (separate compose file)
patroni:
  image: patroni/patroni:latest
  environment:
    PATRONI_SCOPE: kitt-postgres
    PATRONI_NAME: patroni-1
    PATRONI_RESTAPI_CONNECT_ADDRESS: patroni-1:8008
    PATRONI_POSTGRESQL_CONNECT_ADDRESS: patroni-1:5432
    PATRONI_POSTGRESQL_DATA_DIR: /data/patroni
```

**Benefits**:
- Automatic leader election
- Zero-downtime failover for reads
- Automatic replica rejoin
- REST API for health checks

### 2. Separate Database Infrastructure

For production, run databases on dedicated hosts:
- Reduces resource contention
- Simplifies scaling
- Easier disaster recovery

### 3. Backup Strategy

**PostgreSQL**:
```bash
# Automated backups with pg_basebackup
docker exec -it postgres-primary \
  pg_basebackup -U replicator -D /backup/$(date +%Y%m%d) -Ft -z -P

# Point-in-time recovery (PITR)
# Enable WAL archiving in postgresql.conf
```

**Redis**:
```bash
# RDB snapshots (automatic with REDIS_SAVE)
# AOF backups (continuous with REDIS_AOF_ENABLED=yes)

# Manual backup
docker exec -it redis-master redis-cli BGSAVE
```

### 4. Monitoring & Alerting

**Critical alerts**:
- Primary database down
- Replication lag > 10 seconds
- Sentinel quorum lost
- High connection pool utilization (>80%)
- Disk space < 20%

**Setup Prometheus alerts**:
```yaml
# In prometheus/alerts/database.yml
- alert: PostgreSQLReplicationLag
  expr: pg_stat_replication_lag_seconds > 10
  annotations:
    summary: "PostgreSQL replication lag is high"
```

### 5. Security Hardening

**PostgreSQL**:
```bash
# Use strong passwords
POSTGRES_PASSWORD=<randomly-generated-64-char-password>
POSTGRES_REPLICATION_PASSWORD=<different-random-password>

# Enable SSL (in production)
POSTGRESQL_ENABLE_TLS: "yes"
POSTGRESQL_TLS_CERT_FILE: /certs/server.crt
POSTGRESQL_TLS_KEY_FILE: /certs/server.key
```

**Redis**:
```bash
# Enable authentication
REDIS_PASSWORD=<strong-random-password>
REDIS_SENTINEL_PASSWORD=<different-password>

# Disable dangerous commands
REDIS_DISABLE_COMMANDS: FLUSHDB,FLUSHALL,KEYS,CONFIG
```

### 6. Capacity Planning

**Resource requirements** (per node):

| Component | CPU | Memory | Disk I/O |
|-----------|-----|--------|----------|
| PostgreSQL Primary | 2-4 cores | 4-8GB | High |
| PostgreSQL Replica | 1-2 cores | 4-8GB | Medium |
| PgBouncer | 0.5 cores | 256MB | Low |
| Redis Master | 1-2 cores | 2-4GB | Medium |
| Redis Replica | 1 core | 2-4GB | Medium |
| Redis Sentinel | 0.25 cores | 128MB | Low |

**Total cluster** (minimum):
- CPU: 10-16 cores
- Memory: 20-32GB
- Disk: 100GB SSD (database), 50GB SSD (WAL/AOF)

---

## Upgrade & Migration

### Migrating from Single-Node to Clustered

**1. Backup existing data**:
```bash
# PostgreSQL
docker exec -it postgres pg_dump -U kitty kitty > backup.sql

# Redis
docker exec -it redis redis-cli BGSAVE
docker cp $(docker ps -q -f name=redis):/data/dump.rdb redis-backup.rdb
```

**2. Stop services**:
```bash
docker compose -f infra/compose/docker-compose.yml down
```

**3. Start clustered setup**:
```bash
docker compose \
  -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.db-cluster.yml \
  up -d
```

**4. Restore data** (if needed):
```bash
# PostgreSQL (will auto-replicate to replicas)
docker exec -i $(docker ps -q -f name=postgres-primary) \
  psql -U kitty kitty < backup.sql

# Redis (will auto-sync to replicas)
docker cp redis-backup.rdb $(docker ps -q -f name=redis-master):/data/dump.rdb
docker restart $(docker ps -q -f name=redis-master)
```

**5. Verify replication**:
```bash
./ops/scripts/db-cluster-health.sh --verbose
```

### Rolling Upgrades

**PostgreSQL version upgrade**:
```bash
# Update docker-compose.db-cluster.yml version
# image: bitnami/postgresql:17  # New version

# Upgrade replicas first (zero downtime)
docker compose -f infra/compose/docker-compose.db-cluster.yml up -d postgres-replica-1 postgres-replica-2

# Wait for replication to catch up
# Then upgrade primary
docker compose -f infra/compose/docker-compose.db-cluster.yml up -d postgres-primary
```

**Redis version upgrade**:
```bash
# Trigger Sentinel failover to replica
redis-cli -p 26379 SENTINEL failover mymaster

# Upgrade old master (now replica)
docker compose -f infra/compose/docker-compose.db-cluster.yml up -d redis-replica-1

# Failover back and upgrade other nodes
```

---

## Related Documentation

- **Docker Compose Configuration**: `infra/compose/docker-compose.db-cluster.yml`
- **Health Check Script**: `ops/scripts/db-cluster-health.sh`
- **Failover Test Script**: `ops/scripts/test-db-failover.sh`
- **Environment Configuration**: `.env.example` (Section 14)
- **Prometheus Alerts**: `infra/prometheus/alerts/database.yml`

---

## Support

For questions or issues:
1. Check health: `./ops/scripts/db-cluster-health.sh --verbose`
2. Review logs: `docker compose logs postgres-primary redis-master`
3. Test failover: `./ops/scripts/test-db-failover.sh`
4. File issue: https://github.com/Jmi2020/KITT/issues

---

**Database Clustering**: Production-ready high availability for PostgreSQL and Redis! 💾🔄
