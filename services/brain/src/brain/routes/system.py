from fastapi import APIRouter
import psutil
import time

router = APIRouter(prefix="/system", tags=["System"])

# Cache network stats to calculate rate
last_net_io = psutil.net_io_counters()
last_time = time.time()

@router.get("/stats")
async def get_system_stats():
    global last_net_io, last_time
    
    # CPU & Memory
    # interval=None returns 0 on first call, but is non-blocking. 
    # Since this is an API called repeatedly, it works well.
    cpu_percent = psutil.cpu_percent(interval=None) 
    
    # Get temperature if available (MacOS might need specific tools, or psutil might have sensors)
    cpu_temp = 0
    try:
        temps = psutil.sensors_temperatures()
        # Common keys: 'coretemp', 'cpu_thermal', etc.
        for name, entries in temps.items():
            if entries:
                cpu_temp = entries[0].current
                break
    except:
        pass

    mem = psutil.virtual_memory()
    
    # Network Rate Calculation
    current_net_io = psutil.net_io_counters()
    current_time = time.time()
    
    elapsed = current_time - last_time
    if elapsed <= 0: elapsed = 0.01 # Avoid div by zero
    
    # Bytes per second
    net_up_speed = (current_net_io.bytes_sent - last_net_io.bytes_sent) / elapsed
    net_down_speed = (current_net_io.bytes_recv - last_net_io.bytes_recv) / elapsed
    
    # Update cache
    last_net_io = current_net_io
    last_time = current_time
    
    # Disk I/O (Optional, can be added similar to network)
    
    return {
        "cpu": {
            "usage": cpu_percent,
            "temp": cpu_temp
        },
        "memory": {
            "used": mem.used / (1024**3), # GB
            "total": mem.total / (1024**3), # GB
            "percent": mem.percent
        },
        "disk": {
            "read": 0, # Placeholder
            "write": 0
        },
        "network": {
            "up": net_up_speed / 1024, # KB/s
            "down": net_down_speed / 1024 # KB/s
        }
    }
