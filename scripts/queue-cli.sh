#!/bin/bash
# KITT Print Queue CLI Helper
# Provides command-line access to print queue management

set -e

FABRICATION_URL="${FABRICATION_URL:-http://localhost:8300}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

success() {
    echo -e "${GREEN}$1${NC}"
}

info() {
    echo -e "${BLUE}$1${NC}"
}

warn() {
    echo -e "${YELLOW}$1${NC}"
}

# Check if jq is available for JSON formatting
if command -v jq &> /dev/null; then
    JQ_AVAILABLE=true
else
    JQ_AVAILABLE=false
    warn "Note: Install 'jq' for better JSON formatting"
fi

format_json() {
    if [ "$JQ_AVAILABLE" = true ]; then
        jq '.'
    else
        cat
    fi
}

# Commands

cmd_list() {
    info "Fetching print queue..."
    curl -s "$FABRICATION_URL/api/fabrication/queue" | format_json
}

cmd_status() {
    info "Fetching queue statistics..."
    curl -s "$FABRICATION_URL/api/fabrication/queue/statistics" | format_json
}

cmd_printers() {
    info "Fetching printer status..."
    curl -s "$FABRICATION_URL/api/fabrication/printer_status" | format_json
}

cmd_submit() {
    local stl_path="$1"
    local job_name="$2"
    local material="${3:-pla_black_esun}"
    local priority="${4:-5}"

    if [ -z "$stl_path" ] || [ -z "$job_name" ]; then
        error "Usage: $0 submit <stl_path> <job_name> [material] [priority]"
    fi

    if [ ! -f "$stl_path" ]; then
        error "STL file not found: $stl_path"
    fi

    info "Submitting job '$job_name'..."

    local payload=$(cat <<EOF
{
    "job_name": "$job_name",
    "stl_path": "$stl_path",
    "material_id": "$material",
    "print_settings": {
        "nozzle_temp": 210,
        "bed_temp": 60,
        "layer_height": 0.2,
        "infill": 20,
        "speed": 50
    },
    "priority": $priority
}
EOF
)

    curl -s -X POST "$FABRICATION_URL/api/fabrication/jobs" \
        -H "Content-Type: application/json" \
        -d "$payload" | format_json
}

cmd_cancel() {
    local job_id="$1"

    if [ -z "$job_id" ]; then
        error "Usage: $0 cancel <job_id>"
    fi

    warn "Cancelling job $job_id..."
    curl -s -X DELETE "$FABRICATION_URL/api/fabrication/jobs/$job_id" | format_json
}

cmd_priority() {
    local job_id="$1"
    local priority="$2"

    if [ -z "$job_id" ] || [ -z "$priority" ]; then
        error "Usage: $0 priority <job_id> <priority (1-10)>"
    fi

    if [ "$priority" -lt 1 ] || [ "$priority" -gt 10 ]; then
        error "Priority must be between 1 and 10"
    fi

    info "Updating job $job_id priority to $priority..."
    curl -s -X PATCH "$FABRICATION_URL/api/fabrication/jobs/$job_id/priority" \
        -H "Content-Type: application/json" \
        -d "{\"priority\": $priority}" | format_json
}

cmd_schedule() {
    info "Triggering job scheduler..."
    curl -s -X POST "$FABRICATION_URL/api/fabrication/schedule" | format_json
}

cmd_watch() {
    info "Watching queue (updates every 5s, Ctrl+C to stop)..."
    while true; do
        clear
        echo "=== KITT Print Queue ==="
        echo ""

        # Get statistics
        stats=$(curl -s "$FABRICATION_URL/api/fabrication/queue/statistics")

        if [ "$JQ_AVAILABLE" = true ]; then
            total=$(echo "$stats" | jq -r '.total_jobs')
            queued=$(echo "$stats" | jq -r '.by_status.queued // 0')
            printing=$(echo "$stats" | jq -r '.by_status.printing // 0')
            urgent=$(echo "$stats" | jq -r '.upcoming_deadlines + .overdue')

            echo "Total: $total | Queued: $queued | Printing: $printing | Urgent: $urgent"
        else
            echo "$stats"
        fi

        echo ""
        echo "=== Jobs ==="
        curl -s "$FABRICATION_URL/api/fabrication/queue?limit=10" | format_json

        sleep 5
    done
}

cmd_help() {
    cat <<EOF
KITT Print Queue CLI Helper

Usage: $0 <command> [options]

Commands:
    list              List all jobs in queue
    status            Show queue statistics
    printers          Show printer status
    submit <stl> <name> [material] [priority]
                      Submit new job to queue
                      Example: $0 submit /path/to/model.stl "bracket_v2" pla_black_esun 3
    cancel <job_id>   Cancel a job
    priority <job_id> <priority>
                      Update job priority (1-10, 1=highest)
    schedule          Manually trigger job scheduling
    watch             Watch queue in real-time (updates every 5s)
    help              Show this help message

Environment Variables:
    FABRICATION_URL   Fabrication service URL (default: http://localhost:8300)

Examples:
    # List queue
    $0 list

    # Submit high-priority job
    $0 submit /path/model.stl "urgent_bracket" pla_black_esun 1

    # Cancel job
    $0 cancel job_20251116_123456_abc123

    # Watch queue in real-time
    $0 watch

    # Open web dashboard
    open http://localhost:8300/queue
EOF
}

# Main command dispatcher
case "${1:-help}" in
    list)
        cmd_list
        ;;
    status)
        cmd_status
        ;;
    printers)
        cmd_printers
        ;;
    submit)
        shift
        cmd_submit "$@"
        ;;
    cancel)
        shift
        cmd_cancel "$@"
        ;;
    priority)
        shift
        cmd_priority "$@"
        ;;
    schedule)
        cmd_schedule
        ;;
    watch)
        cmd_watch
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        error "Unknown command: $1\n\nRun '$0 help' for usage information"
        ;;
esac
