# KITTY Notifications

KITTY supports multiple notification channels to alert you when long-running queries complete.

## Supported Channels

1. **macOS Notification Center** (default)
2. **Twilio SMS** (requires account)
3. **Future**: Webhook, Slack, Discord, email

## Quick Start - macOS Notifications

macOS notifications work out of the box:

```bash
./ops/scripts/notify.sh "Test Title" "Test message" "Glass"
```

Available sounds: `default`, `Glass`, `Submarine`, `Ping`, `Pop`, `Sosumi`

## Setting Up Twilio SMS

### 1. Create Twilio Account

1. Sign up at https://www.twilio.com/try-twilio
2. Verify your phone number
3. Get a Twilio phone number

### 2. Get Credentials

From the Twilio Console (https://console.twilio.com):
- Copy your **Account SID**
- Copy your **Auth Token**
- Note your **Twilio Phone Number**

### 3. Configure KITT

Add to your `.env` file:

```bash
# Twilio SMS notifications
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+1234567890
TWILIO_TO_NUMBER=+1234567890

# Enable SMS notifications
NOTIFICATIONS_ENABLED=true
NOTIFICATIONS_SMS_ENABLED=true
NOTIFICATIONS_MACOS_ENABLED=true
```

### 4. Test It

```bash
./ops/scripts/notify.sh "KITTY Test" "This is a test notification"
```

You should receive both a macOS notification and an SMS.

## Using in Shell Scripts

```bash
#!/bin/bash

# Your long-running task
some_long_task

# Notify when done
./ops/scripts/notify.sh "Task Complete" "Your task finished successfully!" "Glass"
```

## Using in Python

```python
from common.notifications import notify

# Send notification
await notify(
    title="KITTY Query Complete",
    message="Your CAD analysis is ready!",
    sound="Glass",  # macOS only
    sms=True,       # Send SMS if enabled
    macos=True      # Send macOS notification if enabled
)
```

## Integration with Brain Service

The brain orchestrator can automatically notify you when queries complete:

```python
from brain.orchestrator import BrainOrchestrator
from common.notifications import notify

# After query completion
result = await orchestrator.generate_response(...)

# Notify
await notify(
    title="KITTY Responded",
    message=f"Query completed in {result.latency_ms}ms",
)
```

## Notification Preferences

Environment variables to control notifications:

```bash
# Master switch
NOTIFICATIONS_ENABLED=true

# Channel-specific
NOTIFICATIONS_SMS_ENABLED=false
NOTIFICATIONS_MACOS_ENABLED=true
```

## Cost Considerations

### Twilio Pricing (as of 2024)

- **Trial Account**: Free credits (~$15)
- **SMS (US)**: $0.0079 per message sent
- **Phone Number**: $1.15/month for a US number

For occasional notifications (e.g., 10 queries/day), expect ~$0.08/day = $2.40/month + $1.15 number fee = **~$3.55/month**.

### Free Alternatives

- macOS Notification Center: Free, local only
- Webhook to your own server: Free
- Discord/Slack webhooks: Free

## Security Best Practices

1. **Never commit credentials** - use `.env` file (already in `.gitignore`)
2. **Use environment variables** - don't hardcode tokens
3. **Rotate credentials** - if accidentally exposed
4. **Limit permissions** - Twilio account should only have SMS send permission

## Troubleshooting

### macOS Notifications Not Appearing

1. Check System Preferences → Notifications
2. Ensure Terminal or your IDE has notification permissions
3. Test with: `osascript -e 'display notification "test" with title "Test"'`

### SMS Not Sending

1. Check Twilio dashboard for error logs
2. Verify phone numbers are in E.164 format (+1234567890)
3. For trial accounts, verify recipient number in Twilio console
4. Check your Twilio account balance

### SMS Received But Truncated

- SMS has a 160-character limit
- Messages are automatically split into segments
- Each segment counts as one message for billing

## Examples

### Notify After CAD Generation

```bash
./tests/test_kitty_cad.sh && \
./ops/scripts/notify.sh "CAD Test Complete" "Check logs/kitty_cad_conversation.jsonl"
```

### Notify on Error

```bash
./tests/test_kitty_cad.sh || \
./ops/scripts/notify.sh "CAD Test Failed" "Check logs for errors" "Basso"
```

### Python Async Notification

```python
import asyncio
from common.notifications import NotificationService

async def long_task():
    notifier = NotificationService(enable_sms=True)

    # Your task
    result = await some_long_computation()

    # Notify
    await notifier.notify(
        title="Computation Complete",
        message=f"Result: {result}",
    )

asyncio.run(long_task())
```

## Future Enhancements

Planned notification channels:
- [ ] Webhook/HTTP POST
- [ ] Slack integration
- [ ] Discord webhooks
- [ ] Email (SMTP)
- [ ] Push notifications (via ntfy.sh)
- [ ] Voice call (Twilio voice)
