# Fabrication Troubleshooting Guide

Common issues and solutions for the KITTY Fabrication Console.

## Quick Diagnostics

### Check Service Status

```bash
# Check if fabrication service is running
curl http://localhost:8300/health

# Check slicer availability
curl http://localhost:8300/api/slicer/status
```

Expected responses:
```json
{"status": "healthy"}
{"available": true, "bin_path": "/usr/bin/CuraEngine", ...}
```

### Check Printer Connectivity

```bash
curl http://localhost:8300/api/segmentation/printers
```

Should list all configured printers with their online status.

---

## Generation Issues

### "Provider unavailable" or Generation Fails

**Symptoms:**
- CAD generation returns error
- "Failed to connect to provider" message

**Solutions:**
1. Check internet connectivity (Tripo/Zoo require internet)
2. Verify API keys are configured in `.env`:
   ```
   TRIPO_API_KEY=your_key_here
   ZOO_API_KEY=your_key_here
   ```
3. Check provider status at their respective dashboards
4. Try a different provider (switch between Tripo and Zoo)

### Model Generation Returns Empty or Broken

**Symptoms:**
- Model file is 0 bytes
- Model doesn't display in viewer

**Solutions:**
1. Check the prompt - be more specific about shape and dimensions
2. Try parametric mode for geometric shapes
3. Try organic mode for natural forms
4. Include dimensions: "6 inch", "150mm tall"

---

## Segmentation Issues

### "Mesh load failed" Error

**Symptoms:**
- Segmentation check or segment operation fails
- Error mentions mesh loading

**Solutions:**
1. Verify file exists at the specified path
2. Check file format is `.3mf` or `.stl`
3. Try re-exporting the model from your CAD software
4. Check file isn't corrupted (try opening in another viewer)

### Segmentation Takes Too Long

**Symptoms:**
- Progress stuck at low percentage
- Operation times out

**Solutions:**
1. Reduce `max_parts` parameter
2. Try `segment_then_hollow` instead of `hollow_then_segment`
3. Simplify the mesh (reduce polygon count) before importing
4. Check system resources (RAM usage)

### Parts Don't Align After Printing

**Symptoms:**
- Segmented parts don't fit together
- Joints are too tight or too loose

**Solutions:**
1. Adjust `joint_tolerance_mm`:
   - Too tight: Increase to 0.4mm or 0.5mm
   - Too loose: Decrease to 0.2mm
2. Calibrate your printer's dimensional accuracy
3. Try a different joint type (integrated vs dowel)

---

## Slicing Issues

### "CuraEngine not available" Error

**Symptoms:**
- Slicing returns 503 error
- Status shows `"available": false`

**Solutions:**
1. Verify CuraEngine is installed:
   ```bash
   docker exec kitt-fabrication which CuraEngine
   # Should return: /usr/bin/CuraEngine
   ```
2. Check the Docker container is running:
   ```bash
   docker ps | grep fabrication
   ```
3. Restart the fabrication service:
   ```bash
   docker-compose restart fabrication
   ```

### "Unknown printer" Error

**Symptoms:**
- Slicing fails with "Unknown printer: X"
- Lists available printers in error message

**Solutions:**
1. Use one of the listed printer IDs exactly as shown
2. Valid IDs: `bambu_h2d`, `elegoo_giga`, `snapmaker_artisan`
3. Check printer profiles exist in `config/slicer_profiles/printers/`

### Slicing Stuck at 0%

**Symptoms:**
- Job status remains "pending" or "running" at 0%
- No progress after several minutes

**Solutions:**
1. Check fabrication service logs:
   ```bash
   docker logs kitt-fabrication --tail 100
   ```
2. Verify input file path is accessible to the container
3. Try a simpler model to test slicing works
4. Restart the fabrication service

### G-code Has Obvious Issues

**Symptoms:**
- Print starts in wrong position
- Temperature settings are wrong
- Missing start/end G-code

**Solutions:**
1. Check printer profile's `machine_start_gcode` and `machine_end_gcode`
2. Verify correct printer was selected
3. Check material temperatures in material profile
4. Review quality preset settings

---

## Printing Issues

### "Printer offline" Status

**Symptoms:**
- Printer shows as offline in the console
- Cannot send print jobs

**Solutions:**

**For Bambu printers:**
1. Check printer is powered on and connected to network
2. Verify Bambu MQTT credentials in `.env`:
   ```
   BAMBU_PRINTER_IP=192.168.x.x
   BAMBU_ACCESS_CODE=your_code
   ```
3. Check printer is on same network as KITT server
4. Restart the Bambu service

**For Elegoo/Moonraker printers:**
1. Check Klipper/Moonraker is running on the printer
2. Verify Moonraker URL in configuration:
   ```
   ELEGOO_MOONRAKER_URL=http://192.168.x.x:7125
   ```
3. Check firewall isn't blocking port 7125
4. Test connectivity: `curl http://printer_ip:7125/printer/info`

### Print Upload Fails

**Symptoms:**
- "Upload failed" error
- G-code not appearing on printer

**Solutions:**
1. Check printer has available storage space
2. Verify network connectivity to printer
3. Check G-code file was generated successfully
4. Try downloading G-code and uploading manually

### Print Starts Then Fails Immediately

**Symptoms:**
- Print starts but stops within seconds
- Error on printer display

**Solutions:**
1. Check bed is clear and clean
2. Verify filament is loaded
3. Check nozzle isn't clogged
4. Review G-code start sequence
5. Check printer firmware for thermal runaway errors

---

## UI Issues

### Steps Won't Unlock

**Symptoms:**
- Step 2/3/4 remain locked despite completing previous step
- "Complete previous step" message persists

**Solutions:**
1. Ensure model is actually selected (click on artifact thumbnail)
2. For Step 3: Either complete segmentation OR skip it explicitly
3. For Step 4: Ensure slicing completed successfully and printer is selected
4. Try the "New Session" button to reset workflow state

### Workflow State Corrupted

**Symptoms:**
- UI shows incorrect state
- Actions don't work as expected

**Solutions:**
1. Click "New Session" to reset
2. Clear browser localStorage:
   ```javascript
   localStorage.clear()
   ```
3. Hard refresh the page (Ctrl+Shift+R / Cmd+Shift+R)

### Progress Bar Stuck

**Symptoms:**
- Slicing/segmentation progress doesn't update
- Appears frozen

**Solutions:**
1. Open browser dev tools (F12) and check Network tab for requests
2. Check Console tab for JavaScript errors
3. Verify fabrication service is still running
4. Refresh the page (progress continues in background)

---

## Voice Integration Issues

### Voice Commands Not Recognized

**Symptoms:**
- "Make me X and print it" doesn't trigger workflow
- Tools not being called

**Solutions:**
1. Verify you're in Maker mode (not Basic or another mode)
2. Check voice service is running:
   ```bash
   ./ops/scripts/start-voice-service.sh
   ```
3. Speak clearly and include trigger phrases:
   - "Design me...", "Make a...", "Create a...", "Print..."

### Tool Calls Fail

**Symptoms:**
- Voice assistant says it will call a tool but nothing happens
- Error messages in voice response

**Solutions:**
1. Check MCP servers are registered:
   ```bash
   curl http://localhost:8000/api/mcp/servers
   ```
2. Verify fabrication MCP server is included
3. Check fabrication service is healthy

---

## Performance Issues

### Slow Response Times

**Symptoms:**
- Operations take much longer than expected
- UI feels sluggish

**Solutions:**
1. Check system resources (CPU, RAM, disk)
2. Reduce model complexity before processing
3. Ensure Docker has adequate resources allocated
4. Check network latency to printers

### High Memory Usage

**Symptoms:**
- System becomes unresponsive during operations
- Out of memory errors

**Solutions:**
1. Process smaller models
2. Increase Docker memory limit
3. Restart fabrication service to free memory
4. Use `segment_then_hollow` for large models

---

## Getting Help

If issues persist:

1. Check logs:
   ```bash
   docker logs kitt-fabrication --tail 200
   docker logs kitt-gateway --tail 200
   ```

2. Gather diagnostics:
   - Service status output
   - Browser console errors
   - Steps to reproduce

3. File an issue with details at:
   https://github.com/your-repo/issues
