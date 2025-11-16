#!/bin/bash
# Database Cluster Health Check Script
#
# Checks health and replication status of PostgreSQL and Redis clusters
#
# Usage:
#   ./db-cluster-health.sh [--verbose]
#
# Exit codes:
#   0 = All systems healthy
#   1 = One or more systems unhealthy
#   2 = Script error

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

VERBOSE=false
if [[ "${1:-}" == "--verbose" ]]; then
    VERBOSE=true
fi

OVERALL_STATUS=0

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  KITT Database Cluster Health Check                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# PostgreSQL Cluster Health
# ============================================================================

echo -e "${BLUE}■ PostgreSQL Cluster${NC}"
echo ""

# Check primary
echo -n "  Primary (5432): "
if docker exec -it $(docker ps -q -f name=postgres-primary) pg_isready -U kitty > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Replication status:"
        docker exec -it $(docker ps -q -f name=postgres-primary) psql -U kitty -d kitty -c \
            "SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication;" \
            2>/dev/null | sed 's/^/    /' || echo "    No replicas connected"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check replica 1
echo -n "  Replica 1 (5433): "
if docker exec -it $(docker ps -q -f name=postgres-replica-1) pg_isready -U kitty > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Replication lag:"
        docker exec -it $(docker ps -q -f name=postgres-replica-1) psql -U kitty -c \
            "SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn()
             THEN 0
             ELSE EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp())
             END AS lag_seconds;" \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query lag"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check replica 2
echo -n "  Replica 2 (5434): "
if docker exec -it $(docker ps -q -f name=postgres-replica-2) pg_isready -U kitty > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Replication lag:"
        docker exec -it $(docker ps -q -f name=postgres-replica-2) psql -U kitty -c \
            "SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn()
             THEN 0
             ELSE EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp())
             END AS lag_seconds;" \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query lag"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check PgBouncer
echo -n "  PgBouncer (6432): "
if docker exec -it $(docker ps -q -f name=pgbouncer) pg_isready -h localhost -p 6432 -U kitty > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Connection pool stats:"
        docker exec -it $(docker ps -q -f name=pgbouncer) psql -h localhost -p 6432 -U kitty pgbouncer -c "SHOW POOLS;" \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query pool stats"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

echo ""

# ============================================================================
# Redis Cluster Health
# ============================================================================

echo -e "${BLUE}■ Redis Cluster${NC}"
echo ""

# Check master
echo -n "  Master (6379): "
if docker exec -it $(docker ps -q -f name=redis-master) redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Role:"
        docker exec -it $(docker ps -q -f name=redis-master) redis-cli ROLE \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query role"

        echo "    Connected replicas:"
        docker exec -it $(docker ps -q -f name=redis-master) redis-cli INFO replication | grep "connected_slaves" \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query replicas"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check replica 1
echo -n "  Replica 1 (6380): "
if docker exec -it $(docker ps -q -f name=redis-replica-1) redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Master sync status:"
        docker exec -it $(docker ps -q -f name=redis-replica-1) redis-cli INFO replication | grep "master_link_status" \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query sync status"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check replica 2
echo -n "  Replica 2 (6381): "
if docker exec -it $(docker ps -q -f name=redis-replica-2) redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Master sync status:"
        docker exec -it $(docker ps -q -f name=redis-replica-2) redis-cli INFO replication | grep "master_link_status" \
            2>/dev/null | sed 's/^/    /' || echo "    Unable to query sync status"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

echo ""

# ============================================================================
# Redis Sentinel Health
# ============================================================================

echo -e "${BLUE}■ Redis Sentinel${NC}"
echo ""

# Check sentinel 1
echo -n "  Sentinel 1 (26379): "
if docker exec -it $(docker ps -q -f name=redis-sentinel-1) redis-cli -p 26379 ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "    Master info:"
        docker exec -it $(docker ps -q -f name=redis-sentinel-1) redis-cli -p 26379 SENTINEL master mymaster \
            2>/dev/null | grep -E "ip|port|flags" | sed 's/^/    /' || echo "    Unable to query master info"
    fi
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check sentinel 2
echo -n "  Sentinel 2 (26380): "
if docker exec -it $(docker ps -q -f name=redis-sentinel-2) redis-cli -p 26379 ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

# Check sentinel 3
echo -n "  Sentinel 3 (26381): "
if docker exec -it $(docker ps -q -f name=redis-sentinel-3) redis-cli -p 26379 ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Online${NC}"
else
    echo -e "${RED}✗ Offline${NC}"
    OVERALL_STATUS=1
fi

echo ""

# ============================================================================
# Summary
# ============================================================================

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
if [[ $OVERALL_STATUS -eq 0 ]]; then
    echo -e "${BLUE}║${NC}  ${GREEN}✓ All database cluster components are healthy${NC}              ${BLUE}║${NC}"
else
    echo -e "${BLUE}║${NC}  ${RED}✗ One or more components are unhealthy${NC}                     ${BLUE}║${NC}"
fi
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"

exit $OVERALL_STATUS
