#!/usr/bin/env bash
# Send notifications via multiple channels

set -euo pipefail

TITLE="${1:-Notification}"
MESSAGE="${2:-No message provided}"
SOUND="${3:-default}"

# Source .env if available
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

NOTIFICATIONS_ENABLED="${NOTIFICATIONS_ENABLED:-true}"
NOTIFICATIONS_SMS_ENABLED="${NOTIFICATIONS_SMS_ENABLED:-false}"
NOTIFICATIONS_MACOS_ENABLED="${NOTIFICATIONS_MACOS_ENABLED:-true}"

if [[ "$NOTIFICATIONS_ENABLED" != "true" ]]; then
    echo "Notifications disabled"
    exit 0
fi

# macOS Notification Center
if [[ "$NOTIFICATIONS_MACOS_ENABLED" == "true" ]] && command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\" sound name \"$SOUND\""
    echo "📱 macOS notification sent: $TITLE"
fi

# iMessage - Syncs to all Apple devices automatically!
NOTIFICATIONS_IMESSAGE_ENABLED="${NOTIFICATIONS_IMESSAGE_ENABLED:-false}"
if [[ "$NOTIFICATIONS_IMESSAGE_ENABLED" == "true" ]]; then
    IMESSAGE_RECIPIENT="${IMESSAGE_RECIPIENT:-}"

    if [[ -n "$IMESSAGE_RECIPIENT" ]] && command -v osascript >/dev/null 2>&1; then
        # Send iMessage using AppleScript
        osascript <<EOF >/dev/null 2>&1
tell application "Messages"
    set targetBuddy to "$IMESSAGE_RECIPIENT"
    set targetService to id of 1st account whose service type = iMessage
    set textMessage to "🤖 $TITLE

$MESSAGE"
    set theBuddy to participant targetBuddy of account id targetService
    send textMessage to theBuddy
end tell
EOF
        if [[ $? -eq 0 ]]; then
            echo "💬 iMessage sent to $IMESSAGE_RECIPIENT (will appear on all devices)"
        else
            echo "⚠️  iMessage failed - check Messages app permissions" >&2
        fi
    else
        echo "⚠️  iMessage recipient not configured or Messages not available" >&2
    fi
fi

# ntfy.sh - Free push notifications to all devices
NOTIFICATIONS_NTFY_ENABLED="${NOTIFICATIONS_NTFY_ENABLED:-false}"
if [[ "$NOTIFICATIONS_NTFY_ENABLED" == "true" ]]; then
    NTFY_TOPIC="${NTFY_TOPIC:-}"
    NTFY_SERVER="${NTFY_SERVER:-https://ntfy.sh}"
    NTFY_PRIORITY="${NTFY_PRIORITY:-default}"
    NTFY_TAGS="${NTFY_TAGS:-robot,tools}"

    if [[ -n "$NTFY_TOPIC" ]]; then
        curl -s -X POST "$NTFY_SERVER/$NTFY_TOPIC" \
            -H "Title: $TITLE" \
            -H "Priority: $NTFY_PRIORITY" \
            -H "Tags: $NTFY_TAGS" \
            -d "$MESSAGE" >/dev/null 2>&1

        echo "📱 Push notification sent to all devices via ntfy.sh"
    else
        echo "⚠️  ntfy.sh topic not configured" >&2
    fi
fi

# Pushover - Reliable push notifications
NOTIFICATIONS_PUSHOVER_ENABLED="${NOTIFICATIONS_PUSHOVER_ENABLED:-false}"
if [[ "$NOTIFICATIONS_PUSHOVER_ENABLED" == "true" ]]; then
    PUSHOVER_USER_KEY="${PUSHOVER_USER_KEY:-}"
    PUSHOVER_API_TOKEN="${PUSHOVER_API_TOKEN:-}"

    if [[ -n "$PUSHOVER_USER_KEY" && -n "$PUSHOVER_API_TOKEN" ]]; then
        curl -s -X POST "https://api.pushover.net/1/messages.json" \
            -d "token=$PUSHOVER_API_TOKEN" \
            -d "user=$PUSHOVER_USER_KEY" \
            -d "title=$TITLE" \
            -d "message=$MESSAGE" >/dev/null 2>&1

        echo "📲 Push notification sent via Pushover"
    else
        echo "⚠️  Pushover credentials not configured" >&2
    fi
fi

# Pushcut - iOS automation
NOTIFICATIONS_PUSHCUT_ENABLED="${NOTIFICATIONS_PUSHCUT_ENABLED:-false}"
if [[ "$NOTIFICATIONS_PUSHCUT_ENABLED" == "true" ]]; then
    PUSHCUT_SECRET="${PUSHCUT_SECRET:-}"
    PUSHCUT_NOTIFICATION_NAME="${PUSHCUT_NOTIFICATION_NAME:-KITTY}"

    if [[ -n "$PUSHCUT_SECRET" ]]; then
        curl -s -X POST "https://api.pushcut.io/v1/notifications/$PUSHCUT_NOTIFICATION_NAME" \
            -H "API-Key: $PUSHCUT_SECRET" \
            -H "Content-Type: application/json" \
            -d "{\"title\":\"$TITLE\",\"text\":\"$MESSAGE\"}" >/dev/null 2>&1

        echo "📲 Push notification sent via Pushcut"
    else
        echo "⚠️  Pushcut secret not configured" >&2
    fi
fi

# Twilio SMS
NOTIFICATIONS_SMS_ENABLED="${NOTIFICATIONS_SMS_ENABLED:-false}"
if [[ "$NOTIFICATIONS_SMS_ENABLED" == "true" ]]; then
    TWILIO_ACCOUNT_SID="${TWILIO_ACCOUNT_SID:-}"
    TWILIO_AUTH_TOKEN="${TWILIO_AUTH_TOKEN:-}"
    TWILIO_FROM_NUMBER="${TWILIO_FROM_NUMBER:-}"
    TWILIO_TO_NUMBER="${TWILIO_TO_NUMBER:-}"

    if [[ -n "$TWILIO_ACCOUNT_SID" && -n "$TWILIO_AUTH_TOKEN" && -n "$TWILIO_FROM_NUMBER" && -n "$TWILIO_TO_NUMBER" ]]; then
        SMS_BODY="$TITLE: $MESSAGE"

        response=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
            -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
            -d "From=$TWILIO_FROM_NUMBER" \
            -d "To=$TWILIO_TO_NUMBER" \
            -d "Body=$SMS_BODY")

        if echo "$response" | grep -q '"status"'; then
            echo "📧 SMS sent to $TWILIO_TO_NUMBER"
        else
            echo "⚠️  SMS failed: $response" >&2
        fi
    else
        echo "⚠️  Twilio credentials not configured" >&2
    fi
fi
