# ntfy.sh Quick Setup - Free Push Notifications to All Devices

Get KITTY notifications on your iPhone, iPad, Mac, and any other device!

## What is ntfy.sh?

- **100% Free** and open source
- Works on **iOS, Android, macOS, Linux, Windows, Web**
- **No account required** (just pick a unique topic name)
- **Privacy-friendly** (self-hostable, encrypted)
- Notifications show up on **ALL your devices** instantly

## Setup (2 minutes)

### 1. Pick a Unique Topic Name

Your topic is like a private channel. Make it unique and hard to guess:

```bash
# Good examples:
kitty-jeremiah-workshop-2024
kitty-fab-lab-secret-key-9872
jeremiah-kitt-ai-notifications
```

### 2. Install ntfy.sh App on Your Devices

**iPhone/iPad:**
- App Store: https://apps.apple.com/us/app/ntfy/id1625396347
- Open app → Subscribe to Topic → Enter your topic name
- Done!

**Mac:**
- Use web interface: https://ntfy.sh
- Or install via Homebrew: `brew install ntfy`

**Android:**
- Google Play: https://play.google.com/store/apps/details?id=io.heckel.ntfy
- F-Droid: https://f-droid.org/en/packages/io.heckel.ntfy/

**Web (any device):**
- Just visit: https://ntfy.sh/your-topic-name

### 3. Configure KITT

Add to your `.env` file:

```bash
NTFY_TOPIC=kitty-jeremiah-workshop-2024
NOTIFICATIONS_NTFY_ENABLED=true
```

That's it!

### 4. Test It

```bash
./ops/scripts/notify.sh "KITTY Test" "Notifications working on all devices!"
```

You should receive the notification on your iPhone, iPad, Mac, and any other device where you subscribed!

## Advanced Configuration

### Custom Priority

```bash
# .env
NTFY_PRIORITY=urgent  # Options: min, low, default, high, urgent
```

Higher priority = louder sound and more prominent notification.

### Custom Tags (Emojis)

```bash
# .env
NTFY_TAGS=robot,tools,warning
```

Available tags: https://ntfy.sh/docs/emojis/

### Self-Hosted ntfy Server

For maximum privacy, run your own server:

```bash
# .env
NTFY_SERVER=https://ntfy.yourdomain.com
```

See: https://docs.ntfy.sh/install/

## Security & Privacy

### Public vs Private Topics

By default, anyone who knows your topic name can:
- Send notifications to it
- Subscribe to it

**Best practices:**

1. **Use a hard-to-guess topic name** (include random numbers/words)
2. **Enable authentication** on a self-hosted server
3. **Don't include sensitive data** in notifications (just status updates)

Example good topic: `kitty-fab-2f9a8d3c-notifications`
Example bad topic: `kitty` (too common!)

### Protected Topics (Advanced)

For maximum security, self-host ntfy and use access tokens:

```bash
# Self-hosted with authentication
NTFY_SERVER=https://ntfy.yourdomain.com
NTFY_TOPIC=kitty-secure
NTFY_TOKEN=tk_AgQdq7mVBoFD37zQVN29RhuMzNIz2
```

## Notification Examples

### Query Complete

```bash
./ops/scripts/notify.sh \
  "KITTY Query Complete" \
  "Your CAD analysis finished in 3.2 minutes"
```

### Error Alert

```bash
./ops/scripts/notify.sh \
  "KITTY Error" \
  "Model inference failed - check logs"
```

### Long Task

```bash
# Start notification
./ops/scripts/notify.sh "KITTY Started" "Processing batch job..."

# ... long task runs ...

# Complete notification
./ops/scripts/notify.sh "KITTY Complete" "Batch job finished!"
```

## Comparison with Other Services

| Service | Cost | Setup | All Devices | Privacy |
|---------|------|-------|-------------|---------|
| **ntfy.sh** | Free | 2 min | ✅ | High |
| Pushover | $5 one-time | 5 min | ✅ | Medium |
| Twilio SMS | ~$3/month | 10 min | 📱 Only | Medium |
| macOS Only | Free | 0 min | 🖥️ Only | High |

## Troubleshooting

### Not Receiving Notifications

1. **Check topic name matches** in app and `.env`
2. **Verify topic subscription** in ntfy app
3. **Check notification permissions** for ntfy app
4. **Test manually**:
   ```bash
   curl -d "Test message" https://ntfy.sh/your-topic-name
   ```

### Delayed Notifications

- Free tier has some delays (usually < 10 seconds)
- For instant delivery, self-host ntfy server

### Privacy Concerns

- Use a self-hosted server for sensitive projects
- Or use topic name encryption (coming soon in ntfy)

## Additional Resources

- **Documentation**: https://docs.ntfy.sh
- **GitHub**: https://github.com/binwiederhier/ntfy
- **Self-hosting guide**: https://docs.ntfy.sh/install/
- **API Reference**: https://docs.ntfy.sh/publish/

## Next Steps

Once ntfy.sh is working, you can:

1. **Add it to your voice assistant** - get notified when someone speaks to KITTY
2. **Monitor long processes** - 3D printer status, large renders, etc.
3. **Alert on errors** - immediate notification when something fails
4. **Coordinate with team** - share topic with workshop members
