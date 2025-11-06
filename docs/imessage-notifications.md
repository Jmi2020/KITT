# iMessage Notifications - No Apps Required!

Send KITTY notifications to all your Apple devices using iMessage - just like your Bambu printer!

## Why iMessage?

- **No apps to download** - Uses built-in Messages app
- **Syncs to ALL Apple devices** - iPhone, iPad, Mac, Apple Watch
- **100% Free** - No subscription or credits needed
- **Works like your printer** - Same experience as Bambu notifications
- **Private** - Messages only go to you

## Quick Setup (30 seconds)

### 1. Find Your iCloud Email or Phone Number

You can use either:
- **Email**: your.name@icloud.com (recommended)
- **Phone**: +1234567890

To find your iCloud email:
```bash
# Open System Preferences → Apple ID
# Your email is shown at the top
```

### 2. Add to .env File

```bash
# Your iCloud email or phone number
IMESSAGE_RECIPIENT=your.email@icloud.com

# Enable iMessage notifications
NOTIFICATIONS_IMESSAGE_ENABLED=true
```

### 3. Test It

```bash
./ops/scripts/notify.sh "KITTY Test" "Testing iMessage to all devices!"
```

You should receive an iMessage on your iPhone, iPad, Mac, and Apple Watch within seconds!

## How It Works

When KITTY completes a query:
1. Your Mac sends an iMessage to your iCloud email/phone
2. iCloud syncs the message to all your devices
3. You get a notification on iPhone, iPad, Mac, Watch
4. Message appears in your Messages app (searchable history)

## Permissions

The first time you run it, macOS may ask:
- "Terminal wants access to control Messages" → **Allow**
- This is needed for the script to send messages

## Advantages Over Other Methods

| Method | Syncs to All Devices | Cost | Setup Time |
|--------|---------------------|------|------------|
| **iMessage** | ✅ Yes | Free | 30 sec |
| macOS Notifications | ❌ Mac only | Free | 0 sec |
| ntfy.sh | ✅ Yes | Free | 2 min + app download |
| Twilio SMS | ✅ Phone only | $3/month | 10 min |

## Example Usage

### Notify When Query Completes

```bash
# Long-running task
./tests/test_kitty_cad.sh

# iMessage sent automatically when complete!
```

### Manual Notification

```bash
./ops/scripts/notify.sh \
  "3D Print Complete" \
  "Your bracket is ready for post-processing!"
```

### From Python

```python
import subprocess

subprocess.run([
    "./ops/scripts/notify.sh",
    "KITTY Query Done",
    "Your CAD analysis is ready"
])
```

## Troubleshooting

### Error: "Not authorized to send Apple events to Messages" (-1743)

This is the most common error. It means macOS hasn't granted permission yet.

**Solution**:
1. Open **System Preferences** → **Security & Privacy** → **Privacy** tab
2. Scroll to **Automation** in the left sidebar
3. Find **Terminal** (or **Claude Code** / your IDE)
4. Check the box next to **Messages**
5. Close System Preferences and try again

### "Messages wants to control Messages" Permission Dialog

**Solution**: Click "OK" or "Allow"

If you clicked "Don't Allow":
1. Follow the steps above to manually grant permission in System Preferences

### No iMessage Received

**Check these:**

1. **iCloud signed in**: System Preferences → Apple ID (should show your devices)
2. **Messages app open**: The Messages app must be running on your Mac
3. **iMessage enabled**: Messages → Preferences → iMessage → Make sure you're signed in
4. **Correct recipient**: Double-check the email/phone in `.env`

Test manually in Terminal:
```bash
osascript -e 'tell application "Messages" to send "test" to buddy "your.email@icloud.com"'
```

### Message Sent But Not Syncing to Other Devices

**Check Handoff/Continuity settings:**

1. **On Mac**: System Preferences → General → Allow Handoff (enabled)
2. **On iPhone**: Settings → General → AirPlay & Handoff → Handoff (enabled)
3. **All devices**: Signed into same iCloud account

### Security Concerns

**"Won't I spam my message history?"**
- Yes, but you can:
  - Delete conversation periodically
  - Use a separate Apple ID just for notifications
  - Filter/archive in Messages app

**"Can others see these?"**
- No, they're private messages to yourself
- Unless someone has access to your iCloud account

## Best Practices

### 1. Use a Dedicated Contact

Create a contact "KITTY Notifications" with your email:
```bash
IMESSAGE_RECIPIENT="KITTY Notifications"
```

Then messages are grouped separately in Messages app.

### 2. Keep Messages Concise

```bash
# Good - concise
./ops/scripts/notify.sh "Query Done" "3.2 min runtime"

# Bad - too verbose
./ops/scripts/notify.sh "Complete" "Query completed successfully at $(date) with 512 tokens..."
```

### 3. Use Emoji for Quick Scanning

The notification script already includes 🤖 emoji for easy identification.

### 4. Archive Old Notifications

In Messages app:
1. Find KITTY conversation
2. Right-click → Archive
3. Keeps history but removes from main view

## Comparison with Bambu Printer

Your Bambu printer likely works similarly:
- Sends push notification when print complete
- Appears on all your devices
- Can tap to open app for details

KITTY notifications work the same way:
- iMessage when query complete
- Appears on all your devices
- Message includes status/timing details

## Advanced Configuration

### Multiple Recipients

To notify multiple people (team notifications):

```bash
# In notify.sh, modify the iMessage section:
for recipient in "person1@icloud.com" "person2@icloud.com"; do
    osascript -e "tell application \"Messages\" to send \"$textMessage\" to buddy \"$recipient\""
done
```

### Rich Notifications (Links, Formatting)

iMessages support links:
```bash
./ops/scripts/notify.sh \
  "KITTY Complete" \
  "Results: file:///Users/Shared/Coding/KITT/logs/results.html"
```

Tapping the notification opens the link!

## Next Steps

Once iMessage notifications are working:

1. **Test with real queries** - Run a long CAD analysis and verify notifications
2. **Adjust verbosity** - Decide how much detail you want in messages
3. **Set up shortcuts** - Create iOS Shortcuts to view full logs from notification
4. **Monitor workflow** - Use for build notifications, test completions, etc.

## Disable Later

To turn off:
```bash
# In .env
NOTIFICATIONS_IMESSAGE_ENABLED=false
```

Or keep macOS notifications only:
```bash
NOTIFICATIONS_MACOS_ENABLED=true
NOTIFICATIONS_IMESSAGE_ENABLED=false
```
