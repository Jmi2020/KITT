# Model Manager Progress Feedback Fix

## Problem Statement

Model manager TUI appeared frozen during llama.cpp server startup (30-120 seconds) with no visual feedback, making it unclear if the process was working or hung.

**Root Causes:**
1. No progress callbacks during health check loop
2. Invalid model path in .env (broken reference to non-existent file)
3. Progress callback implementation bugs (wrong method reference)

## Changes Made

### 1. Progress Callback Infrastructure (services/model-manager/src/model_manager/supervisor.py)

Added `on_progress` callback parameter to supervisor methods:

```python
def start(
    self,
    config: Optional[ServerConfig] = None,
    wait_for_ready: bool = True,
    on_progress: Optional[Callable[[HealthCheckResult, int, int], None]] = None,
) -> SupervisorState:
    # ...
    if wait_for_ready:
        result = sync_wait_for_ready(
            config.endpoint, max_retries=120, on_progress=on_progress
        )
```

Also updated `restart()` and `switch_model()` methods.

### 2. Real-time Progress UI (services/model-manager/src/model_manager/app.py)

Implemented progress callback with thread-safe UI updates:

```python
def on_progress(result, attempt, max_attempts):
    """Handle progress updates from health checker."""
    try:
        elapsed = int(time.time() - start_time)
        status_msg = result.status.value if result.status else "unknown"

        # Create progress message based on status
        if status_msg == "READY":
            msg = f"Model loaded ({attempt} checks, {elapsed}s elapsed)"
            log_type = "success"
        elif status_msg == "LOADING":
            msg = f"Loading model... ({attempt}/{max_attempts}, {elapsed}s elapsed)"
            log_type = "info"
        # ...

        # Thread-safe UI update - post to event loop
        if self.log_panel:
            self.call_from_thread(self.log_panel.add_log, msg, log_type)
    except Exception as e:
        # Log errors in progress callback without failing
        logging.error(f"Progress callback error: {e}")
```

**Key fixes:**
- Changed `self.app.call_from_thread()` → `self.call_from_thread()` (Textual widgets have this method directly)
- Used `time.time()` for proper elapsed time tracking
- Wrapped in try/except for error resilience

### 3. Model Configuration Fix (.env and .env.example)

**Before (broken):**
```bash
LLAMACPP_PRIMARY_MODEL=Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-q8_0  # Missing .gguf, file doesn't exist
LLAMACPP_PRIMARY_ALIAS=qwen2
```

**After (working):**
```bash
LLAMACPP_PRIMARY_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q8_0.gguf  # 32GB single file
LLAMACPP_PRIMARY_ALIAS=kitty-primary
```

**Why this matters:**
- llama.cpp supports sharded GGUF files - just specify the first shard (00001-of-XXXXX.gguf)
- llama.cpp automatically discovers and loads remaining shards
- 72B model: q8_0 sharded (21 files) - better than fp16 (42 files)
- 32B Coder model: q8_0 merged (single 32GB file)

## Testing Instructions

### Option 1: Test Model Manager TUI

1. **Launch the model manager:**
   ```bash
   cd /Users/Shared/Coding/KITT
   pip install -e services/model-manager/
   kitty-model-manager tui
   ```

2. **Start the server:**
   - Press `s` (Start Server)
   - You should now see real-time progress updates in the log panel:
     - "Server starting..." (immediately)
     - "Loading model... (1/120, Xs elapsed)" (every ~1 second)
     - "Model loaded (N checks, Xs elapsed)" (when ready)

3. **Expected behavior:**
   - No more frozen UI
   - Progress updates every second during 30-120 second load
   - Clear status messages with elapsed time
   - Success message when model is ready

### Option 2: Test llama.cpp Start Script

1. **Verify configuration:**
   ```bash
   source .env
   echo "Model: $LLAMACPP_PRIMARY_MODEL"
   ls -lh "/Users/Shared/Coding/models/$LLAMACPP_PRIMARY_MODEL"
   ```

2. **Start llama.cpp:**
   ```bash
   ./ops/scripts/start-llamacpp.sh
   ```

3. **Expected output:**
   ```
   Starting llama.cpp server...
   Model: /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q8_0.gguf
   [llama.cpp loading logs...]
   Server started on port 8082
   ```

4. **Verify server is running:**
   ```bash
   curl http://localhost:8082/health
   # Should return: {"status":"ok"}
   ```

### Option 3: Full Integration Test

1. **Stop any running llama.cpp servers:**
   ```bash
   pkill llama-server
   ```

2. **Launch KITTY with model manager:**
   ```bash
   ./ops/scripts/start-kitty.sh
   ```

3. **When prompted "No model running, press 'm'", press `m`**

4. **In model manager:**
   - Press `s` to start server
   - Watch for progress updates
   - Wait for "Model loaded" message
   - Press `Esc` or `q` to return to KITTY launcher

5. **KITTY should now proceed with model loaded**

## Files Modified

- `services/model-manager/src/model_manager/supervisor.py` - Added progress callback parameter
- `services/model-manager/src/model_manager/app.py` - Implemented progress UI with bug fixes
- `.env` - Fixed model path to working single GGUF file
- `.env.example` - Updated example with working model path

## Performance Notes

**Model Loading Time:**
- Qwen2.5-Coder-32B q8_0 (32GB) loads in ~30-90 seconds on M3 Ultra
- Progress updates show every ~1 second during health checks
- GPU optimization (LLAMACPP_N_GPU_LAYERS=999) reduces load time vs CPU-only

**Progress Feedback:**
- Health checks run every 1 second (max 120 attempts = 2 minutes timeout)
- Each check shows: status, attempt count, elapsed time
- Textual's `call_from_thread()` ensures thread-safe UI updates

## Troubleshooting

### Issue: "Error: LLAMACPP_PRIMARY_MODEL is required"
**Solution:** Check .env has correct model path (should end with .gguf)

### Issue: Model manager still appears frozen
**Solution:**
1. Verify you have latest app.py changes (check line 433 for `self.call_from_thread`)
2. Reinstall model manager: `pip install -e services/model-manager/ --force-reinstall`
3. Check logs: `tail -f .logs/llamacpp.log`

### Issue: Port 8082 already in use
**Solution:**
```bash
# Find and kill existing llama.cpp process
lsof -i :8082
pkill llama-server
```

### Issue: Model file not found
**Solution:**
```bash
# Verify model exists
ls -lh /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q8_0.gguf

# If missing, download:
huggingface-cli download Qwen/Qwen2.5-Coder-32B-Instruct-GGUF \
  --local-dir /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF \
  --include "*q8_0.gguf"
```

## Next Steps

Once tested and working:
1. Consider adding progress bar widget (Textual ProgressBar) for visual indicator
2. Add log file tailing to show model loading details in real-time
3. Cache model metadata to show estimated load time based on size
4. Add retry logic with exponential backoff for failed health checks
