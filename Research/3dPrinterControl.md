Excellent! Now I have enough information. Let me create a comprehensive guide with code examples for the user.

## Local Network Control of 3D Printers: API Integration Guide

You have three printers with distinctly different networking approaches, each requiring different integration methods. Here's how to access and control each one over your local network to build your autonomous AI printing system.

### **Bamboo Labs H2D: MQTT + FTP Protocol**

The H2D uses a hybrid approach combining **MQTT for monitoring and control** and **FTP for file uploads**.[1][2] This is the most versatile option for remote automation.

**Discovery & Authentication:**[1][3]
Your H2D broadcasts itself on your local network via UDP. To connect programmatically, you need:
- **Printer IP address** (find via network scan or printer settings)
- **Serial number** (visible on printer or in Bambu Studio)
- **Access code** (16-character code in WiFi settings on printer display or LAN-only mode)

**File Upload via FTPS:**[4][5][6]
Upload G-code files directly to the SD card using FTPS (implicit TLS on port 990):

```python
import ftplib

printer_ip = "192.168.1.100"
access_code = "YOUR_ACCESS_CODE"
gcode_file = "print_job.gcode"

# Connect via FTPS
session = ftplib.FTP_TLS(printer_ip, 990)
session.auth()  # For implicit TLS
session.login("bblp", access_code)
session.prot_p()  # Set secure data connection

# Upload G-code file
with open(gcode_file, 'rb') as file:
    session.storbinary(f'STOR {gcode_file}', file)
    
session.quit()
```

**Monitoring & Control via MQTT:**[7][8][3][9]

```python
import paho.mqtt.client as mqtt
import json
import time

serial_number = "01P45165616"  # Your printer serial
access_code = "YOUR_ACCESS_CODE"
mqtt_host = "mqtt.bambu.com"  # Or local broker if using LAN-only mode
mqtt_port = 8883

client = mqtt.Client(client_id=f"bambu-{serial_number}", protocol=mqtt.MQTTv311)
client.username_pw_set("bblp", access_code)
client.tls_set()

def on_message(client, userdata, msg):
    data = json.loads(msg.payload)
    print(f"Printer status: {data}")
    # Parse print progress, temperature, etc.

client.on_message = on_message
client.connect(mqtt_host, mqtt_port, keepalive=60)

# Subscribe to printer status
client.subscribe(f"device/{serial_number}/report")

# Send commands (example: start pause)
command = {
    "print": {
        "command": "pause"
    }
}
client.publish(f"device/{serial_number}/request", json.dumps(command))

client.loop_forever()
```

**Python Library Alternative:**[3]
For convenience, use the `bambulabs-api` package:

```bash
pip install bambulabs_api
```

```python
import bambulabs_api as bl
import time

printer = bl.Printer("192.168.1.100", "YOUR_ACCESS_CODE", "01P45165616")
printer.connect()
time.sleep(2)

# Get printer status
status = printer.get_status()
print(f"Current state: {status.get('state')}")

# Send G-code
printer.send_gcode("G28")  # Home all axes

# Monitor in real-time
while printer.is_connected():
    status = printer.get_status()
    print(f"Extruder temp: {status.get('extruder_temp')}°C")
    time.sleep(5)
```

### **Elegoo OrangeStorm Giga: Klipper + Fluidd Web Interface**

Your Giga runs **Klipper** (the powerful open-source firmware), which is accessible via **SSH** and controlled through **Moonraker** (the HTTP/WebSocket API).[10][11][12]

**SSH Access & Configuration:**[11]
First, enable root access and connect:

```bash
# SSH into the printer
ssh mks@<printer_ip>
# Password: makerbase

# Or with root access (if enabled)
ssh elegoo@<printer_ip>
# Password: giga3dp
```

Once connected, you can modify the Klipper configuration directly and execute commands.

**Web Interface REST API via Moonraker:**[13][14][15][16]

The Fluidd interface runs on top of Moonraker, which exposes a **JSON-RPC 2.0** API over HTTP and WebSocket. Get printer info:

```python
import requests
import json

printer_ip = "192.168.1.200"
moonraker_port = 7125

# Query printer info
response = requests.get(f"http://{printer_ip}:{moonraker_port}/printer/info")
status = response.json()
print(f"Printer state: {status['result']['state']}")

# Get object status (extruder temp, bed temp, etc.)
query = {
    "jsonrpc": "2.0",
    "method": "printer.objects.query",
    "params": {
        "objects": {
            "extruder": ["temperature", "target"],
            "heater_bed": ["temperature", "target"],
            "print_stats": None
        }
    },
    "id": 1
}

response = requests.post(
    f"http://{printer_ip}:{moonraker_port}/jsonrpc",
    json=query
)
print(response.json())
```

**Execute G-code Commands via WebSocket:**[13][14][17][18]

For real-time control and monitoring, use WebSocket:

```python
import asyncio
import websockets
import json

printer_ip = "192.168.1.200"
moonraker_ws = f"ws://{printer_ip}:7125/websocket"

async def control_printer():
    async with websockets.connect(moonraker_ws) as ws:
        # Identify client
        identify_msg = {
            "jsonrpc": "2.0",
            "method": "server.connection.identify",
            "params": {
                "client_name": "ai_printer_controller",
                "version": "1.0.0",
                "type": "web"
            },
            "id": 1
        }
        await ws.send(json.dumps(identify_msg))
        response = await ws.recv()
        print(f"Connected: {response}")
        
        # Send G-code command (home all axes)
        gcode_msg = {
            "jsonrpc": "2.0",
            "method": "printer.gcode.script",
            "params": {"script": "G28"},
            "id": 2
        }
        await ws.send(json.dumps(gcode_msg))
        response = await ws.recv()
        print(f"G-code response: {response}")
        
        # Upload and start print
        print_msg = {
            "jsonrpc": "2.0",
            "method": "printer.print.start",
            "params": {"filename": "model.gcode"},
            "id": 3
        }
        await ws.send(json.dumps(print_msg))
        
        # Listen for status updates
        while True:
            update = await ws.recv()
            data = json.loads(update)
            if "notify_status_update" in str(data):
                print(f"Status: {data}")

asyncio.run(control_printer())
```

**Python Moonraker Client Library:**[16]

Use the `moonraker-api` package for simplified async control:

```bash
pip install moonraker-api
```

```python
import asyncio
from moonraker_api import MoonrakerClient, MoonrakerListener

class PrinterController(MoonrakerListener):
    def __init__(self, host, port):
        self.client = MoonrakerClient(self, host, port)
    
    async def start(self):
        await self.client.connect()
    
    async def on_notification(self, method, data):
        print(f"Notification: {method} -> {data}")
    
    async def control_print(self):
        # Get printer info
        info = await self.client.request("printer.info")
        print(f"Printer ready: {info['result']['state'] == 'ready'}")
        
        # Send G-code
        await self.client.request("printer.gcode.script", script="G28")
        
        # Start print
        await self.client.request("printer.print.start", filename="model.gcode")

async def main():
    controller = PrinterController("192.168.1.200", 7125)
    await controller.start()
    await controller.control_print()

asyncio.run(main())
```

**File Upload via HTTP:**[19][5]

```python
import requests

printer_ip = "192.168.1.200"
moonraker_port = 7125
gcode_file = "model.gcode"

with open(gcode_file, 'rb') as f:
    files = {'file': f, 'print': 'True'}
    response = requests.post(
        f"http://{printer_ip}:{moonraker_port}/server/files/upload",
        files=files
    )
    print(f"Upload response: {response.json()}")
```

### **Snapmaker Artisan: SACP Protocol over TCP**

The Artisan uses the **Snapmaker Access Control Protocol (SACP)**, a custom binary protocol over TCP port 8888 (not standard HTTP).[20][21][22][23] This requires more specialized handling.

**Network Discovery via UDP:**[24]

Snapmaker devices broadcast their presence on UDP port 20054:

```python
import socket
import json

def discover_snapmaker():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(3)
    
    # Send discovery packet
    message = b"Snapmaker"
    sock.sendto(message, ('<broadcast>', 20054))
    
    try:
        data, addr = sock.recvfrom(4096)
        printer_info = json.loads(data)
        print(f"Found Snapmaker at {addr[0]}: {printer_info}")
        return printer_info
    except socket.timeout:
        print("No Snapmaker found")
    finally:
        sock.close()

discover_snapmaker()
```

**SACP Protocol Connection:**[20][22]

The Snapmaker SACP SDK is available as an npm package (TypeScript), but Python implementations exist via reverse-engineered code:

```python
import socket
import json
import struct

class SnapmakerClient:
    def __init__(self, ip, port=8888):
        self.ip = ip
        self.port = port
        self.socket = None
    
    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.ip, self.port))
        
        # Send initial handshake
        handshake = {
            "command": "enclosure.auth",
            "token": ""
        }
        self.send_command(handshake)
    
    def send_command(self, command_dict):
        # SACP uses JSON over TCP with length-prefixed frames
        json_str = json.dumps(command_dict)
        message = struct.pack('>I', len(json_str)) + json_str.encode()
        self.socket.sendall(message)
    
    def receive_response(self):
        # Read length prefix
        length_data = self.socket.recv(4)
        if not length_
            return None
        length = struct.unpack('>I', length_data)[0]
        
        # Read response
        response_data = b''
        while len(response_data) < length:
            chunk = self.socket.recv(length - len(response_data))
            response_data += chunk
        
        return json.loads(response_data.decode())
    
    def send_gcode(self, gcode_command):
        cmd = {
            "command": "gcode.send",
            "gcode": gcode_command
        }
        self.send_command(cmd)
        return self.receive_response()
    
    def get_status(self):
        cmd = {"command": "system.status"}
        self.send_command(cmd)
        return self.receive_response()
    
    def disconnect(self):
        if self.socket:
            self.socket.close()

# Usage
client = SnapmakerClient("192.168.1.150")
client.connect()
status = client.get_status()
print(f"Artisan status: {status}")
client.send_gcode("G28")  # Home
client.disconnect()
```

**Alternative: Use Snapmaker's Luban Integration:**[21]

The official Snapmaker Luban software uses SACP internally. You can analyze its network requests using Wireshark to reverse-engineer commands, or look at the official Cura plugin source code on GitHub for SACP examples.[21]

***

### **Building Your AI-Driven Print System**

For your autonomous printing architecture, here's a unified interface pattern:

```python
from enum import Enum
from abc import ABC, abstractmethod

class PrinterType(Enum):
    BAMBOO = "bamboo"
    ELEGOO = "elegoo"
    SNAPMAKER = "snapmaker"

class PrinterInterface(ABC):
    @abstractmethod
    def connect(self): pass
    
    @abstractmethod
    def upload_gcode(self, filepath): pass
    
    @abstractmethod
    def start_print(self, filename): pass
    
    @abstractmethod
    def get_status(self): pass
    
    @abstractmethod
    def pause_print(self): pass
    
    @abstractmethod
    def resume_print(self): pass
    
    @abstractmethod
    def cancel_print(self): pass

class PrinterFarm:
    def __init__(self):
        self.printers = {
            "bamboo": BambooH2D("192.168.1.100", "serial", "access_code"),
            "elegoo": ElegooGiga("192.168.1.200"),
            "snapmaker": SnapmakerArtisan("192.168.1.150")
        }
    
    async def upload_and_print_all(self, gcode_file, stl_data=None):
        """Upload G-code to all printers and start printing"""
        results = {}
        for name, printer in self.printers.items():
            try:
                printer.connect()
                printer.upload_gcode(gcode_file)
                printer.start_print(gcode_file)
                results[name] = "printing"
            except Exception as e:
                results[name] = f"error: {e}"
        return results
    
    async def monitor_all(self):
        """Poll all printers for status"""
        statuses = {}
        for name, printer in self.printers.items():
            try:
                status = printer.get_status()
                statuses[name] = status
            except Exception as e:
                statuses[name] = {"error": str(e)}
        return statuses
```

**Integration with CAD Generation:**

```python
import asyncio
from pathlib import Path

class AISlicingPipeline:
    def __init__(self, printer_farm):
        self.farm = printer_farm
    
    async def generate_and_print(self, model_spec):
        """CAD design -> Slicing -> Print"""
        # Step 1: Generate CAD (using Python CAD library like CadQuery, OpenSCAD)
        cad_file = await self.generate_cad(model_spec)
        
        # Step 2: Slice using Orca Slicer CLI or similar
        gcode_file = await self.slice_model(cad_file)
        
        # Step 3: Send to appropriate printer
        printer_name = await self.select_printer()
        printer = self.farm.printers[printer_name]
        
        # Step 4: Monitor print progress
        await self.monitor_print(printer)
    
    async def slice_model(self, cad_file):
        # Call Orca Slicer CLI
        # orca_slicer --model model.stl --output print.gcode
        pass
    
    async def generate_cad(self, spec):
        # Use CadQuery, OpenSCAD, or similar
        pass
    
    async def select_printer(self):
        # Check which printer is idle
        statuses = await self.farm.monitor_all()
        for name, status in statuses.items():
            if status.get("print_state") == "idle":
                return name
```

### **Key Networking Considerations**

- **Assign static IPs** to all printers on your network for reliable automation
- **Firewall rules**: Ensure your home network firewall allows TCP connections to ports 7125 (Moonraker), 8888 (Snapmaker), and 990 (Bambu FTPS)
- **LAN-only mode** for Bamboo Labs provides better security when not using cloud features[1][25]
- For Elegoo, Klipper's Moonraker is more reliable than slicing software APIs for control
- The Snapmaker SACP protocol requires custom socket handling; TypeScript/JavaScript SDKs exist but Python support is community-driven[22]

All three printers can be controlled from a single Python application running on your Mac Studio with proper error handling, status monitoring, and queue management for autonomous operation.

Sources
[1] How does the "LAN only" mode works? - Bambu Lab H2 Series https://forum.bambulab.com/t/how-does-the-lan-only-mode-works/179605
[2] Remote Control & Monitoring - Bambu Lab Wiki https://wiki.bambulab.com/en/software/bambu-studio/remote-control
[3] bambulabs-api - PyPI https://pypi.org/project/bambulabs-api/
[4] We can now connect to FTP on the P1 and A1 Series - Page 3 https://forum.bambulab.com/t/we-can-now-connect-to-ftp-on-the-p1-and-a1-series/6464?page=3
[5] [Feature Request] Upload of GCode to SD-Card · Issue #322 - GitHub https://github.com/bambulab/BambuStudio/issues/322
[6] Access Bambu Lab printer SD Card over Network. - YouTube https://www.youtube.com/watch?v=Hpz_HkLTyaQ
[7] coelacant1/Bambu-Lab-Cloud-API - GitHub https://github.com/coelacant1/Bambu-Lab-Cloud-API
[8] MQTT API : r/BambuLab - Reddit https://www.reddit.com/r/BambuLab/comments/1hmsgdq/mqtt_api/
[9] OBS Script to get print information from an Bambu Lab X1C ... - GitHub https://github.com/Maker-Hub-De/obsBambuLabX1Cmqtt
[10] ELEGOO OrangeStorm Giga FDM 3D Printer - Top 3D Shop https://top3dshop.com/product/elegoo-orangestorm-giga-3d-printer
[11] How do I ssh into OrangeStorm Giga? : r/elegoo - Reddit https://www.reddit.com/r/elegoo/comments/1f318qv/how_do_i_ssh_into_orangestorm_giga/
[12] Fluidd for Klipper - A Detailed Overview - Kingroon https://kingroon.com/blogs/3d-print-101/fluidd-for-klipper-a-detailed-overview
[13] Printer Administration - Moonraker - Read the Docs https://moonraker.readthedocs.io/en/latest/external_api/printer/
[14] Introduction - Moonraker - Read the Docs https://moonraker.readthedocs.io/en/latest/external_api/introduction/
[15] API server - Klipper documentation https://www.klipper3d.org/API_Server.html
[16] cmroche/moonraker-api: Async websocket API client for ... - GitHub https://github.com/cmroche/moonraker-api
[17] Location of the websocket · Arksine moonraker · Discussion #479 https://github.com/Arksine/moonraker/discussions/479
[18] Accessing live gcode with Moonraker - Klipper Discourse https://klipper.discourse.group/t/accessing-live-gcode-with-moonraker/15043
[19] upload file through commandline #128 - Arksine moonraker - GitHub https://github.com/Arksine/moonraker/discussions/128
[20] Artisan API anywhere? : r/snapmaker - Reddit https://www.reddit.com/r/snapmaker/comments/14ity7s/artisan_api_anywhere/
[21] Snapmaker 3in1 Devices #869 - ioBroker/AdapterRequests - GitHub https://github.com/ioBroker/AdapterRequests/issues/869
[22] Snapmaker/Snapmaker-SACP: SACP protocol docs & SDK - GitHub https://github.com/Snapmaker/Snapmaker-SACP
[23] Do Snapmaker 2.0 Devices Have a Webpage? - #51 by HouseLi https://forum.snapmaker.com/t/do-snapmaker-2-0-devices-have-a-webpage/5455/51
[24] Adding Snapmaker to HA (need help on making UDP updatable ... https://community.home-assistant.io/t/adding-snapmaker-to-ha-need-help-on-making-udp-updatable-sensors/655036
[25] Updates and Third-Party Integration with Bambu Connect https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect/
[26] Third-party Integration with Bambu Lab Products https://wiki.bambulab.com/en/software/third-party-integration
[27] ELEGOO Matrix App https://www.elegoo.com/pages/elegoo-matrix-app
[28] TNTBA/OrangeStorm-Giga-Profile-for-Orca - GitHub https://github.com/TNTBA/OrangeStorm-Giga-Profile-for-Orca
[29] Elegoo Orangestorm Giga https://tntba.com/i-got-the-orangestorm-giga/
[30] Bambu Lab X1 X1C MQTT - Page 11 - Configuration https://community.home-assistant.io/t/bambu-lab-x1-x1c-mqtt/489510?page=11
[31] Putting OpenOrangeStorm on the Elegoo Orange Storm Giga https://klipper.discourse.group/t/putting-openorangestorm-on-the-elegoo-orange-storm-giga/23163
[32] Bambu Lab H2D setup guide - SimplyPrint https://simplyprint.io/setup-guide/bambu-lab/h2d
[33] Ethernet Connection - Snapmaker Artisan https://forum.snapmaker.com/t/ethernet-connection/40013
[34] Mainsail and Fluidd Interface Remote Access for Klipper - Obico https://www.obico.io/blog/mainsail-fluidd-remote-access/
[35] 9. Connect to Computer - support@snapmaker.com https://support.snapmaker.com/hc/en-us/articles/4417387340055-9-Connect-to-Computer
[36] Anyways to monitor your print via Webcam using Fluidd or mainsail https://www.reddit.com/r/klippers/comments/1b5bb10/anyways_to_monitor_your_print_via_webcam_using/
[37] MQTT Publish/Subscribe with Mosquitto Pub/Sub examples | Cedalo https://cedalo.com/blog/mqtt-subscribe-publish-mosquitto-pub-sub-example/
[38] Executing GCode through Moonraker/Mainsail - Developers - Klipper https://klipper.discourse.group/t/executing-gcode-through-moonraker-mainsail/5453
[39] MQTT Publish, MQTT Subscribe & Unsubscribe – MQTT Essentials https://www.hivemq.com/blog/mqtt-essentials-part-4-mqtt-publish-subscribe-unsubscribe/
[40] notebook spawns JupyterLab on wrong port 8888 - JupyterHub https://discourse.jupyter.org/t/jupyterhub-from-jupyter-notebook-spawns-jupyterlab-on-wrong-port-8888/13253
[41] How to publish MQTT messages : r/BambuLab - Reddit https://www.reddit.com/r/BambuLab/comments/13hsoq0/how_to_publish_mqtt_messages/
[42] Jupyter Notebook won't start due to ports being already in use #3495 https://github.com/jupyter/notebook/issues/3495
[43] [Recommendation] User-friendly MQTT options - Feature Requests https://forum.bambulab.com/t/recommendation-user-friendly-mqtt-options/2410
[44] Make LAN-only mode actually usable · Issue #4512 - GitHub https://github.com/bambulab/BambuStudio/issues/4512
[45] MintyTrebor/moonNode: A set of node-red nodes to ... - GitHub https://github.com/MintyTrebor/moonNode
[46] Open Source the network plugin · Issue #2381 · bambulab ... - GitHub https://github.com/bambulab/BambuStudio/issues/2381
[47] A Python library for interacting with AWS SageMaker AI ... - GitHub https://github.com/isaacus-dev/isaacus-sagemaker-python
[48] Add the ability to connect Bambu Lab printers in LAN Only Mode https://github.com/SoftFever/OrcaSlicer/issues/8099
[49] canonical/snap-http - GitHub https://github.com/canonical/snap-http
[50] Configuration - Moonraker - Read the Docs https://moonraker.readthedocs.io/en/latest/configuration/
[51] python - How to print streaming information from a websocket(client)? https://stackoverflow.com/questions/40814369/how-to-print-streaming-information-from-a-websocketclient
[52] How to access Fluidd web UI outside of home network? - Reddit https://www.reddit.com/r/ElegooNeptune4/comments/16i7ro5/how_to_access_fluidd_web_ui_outside_of_home/
[53] Web interface not visible · Issue #1473 · fluidd-core/fluidd - GitHub https://github.com/fluidd-core/fluidd/issues/1473
[54] Elegoo Neptune 4 Series - Klipper Remote Access - Obico https://www.obico.io/blog/elegoo-neptune-4-and-obico-ai-3d-printing-revolution/
[55] How to remotely print custom G-code with Bambu Studio? https://forum.bambulab.com/t/how-to-remotely-print-custom-g-code-with-bambu-studio/80649
[56] MCP 3D Printer Server - Glama https://glama.ai/mcp/servers/@DMontgomery40/mcp-3D-printer-server
[57] Configuration reference - Klipper documentation https://damlobster.github.io/klipper/Config_Reference.html
[58] Connecting a Bambu Labs Printer - YouTube https://www.youtube.com/watch?v=FipAon6jLis
