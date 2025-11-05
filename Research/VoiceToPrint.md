# Voice-to-Print Implementation Guide
## Replicating & Extending Brian Harms' Voice-Controlled 3D Printing

Based on analysis of Ritual Industries (Brian Harms) demonstrations and related implementations, plus the TenTech detailed breakdown.

---

## Overview: Two Approaches to Voice-to-Print

### Approach 1: Direct Voice Commands (TenTech Method)
**Real-time voice â†’ G-code translation for manual line-by-line control**

### Approach 2: AI-Assisted CAD Generation (Brian Harms/GPT-4o Method)
**Voice â†’ LLM â†’ CAD script â†’ STL â†’ G-code for complete object generation**

---

## APPROACH 1: Real-Time Voice Command System

### Architecture
```
Microphone â†’ Speech Recognition (Whisper/Vosk) â†’ 
NLP Processing (ChatGPT API) â†’ Command Parser â†’ 
G-code Generator â†’ Serial Connection â†’ 3D Printer
```

### Tech Stack (Based on TenTech Implementation)

**Language**: C# (.NET 8) or Python 3.11+

**Speech Recognition**:
- **Vosk** (offline, local, fast)
  - Model: `vosk-model-small-en-us-0.15` (40MB)
  - 16kHz mono audio required
  - Real-time streaming support
- **Alternative**: Whisper.cpp (higher accuracy, 200-400ms latency)

**Audio Processing**:
- **NAudio** (C#) or **PyAudio** (Python)
- Convert stereo 48kHz to mono 16kHz in real-time

**Natural Language Processing**:
- **Option 1**: Custom ML model (sklearn/TensorFlow)
  - Train on command dataset (~10K examples)
  - 7,000 training examples minimum for 56% accuracy
  - **Not recommended** - time-intensive with mediocre results
- **Option 2**: GPT-4 API calls (recommended)
  - Response time: 320ms average
  - System prompt for command extraction
  - Structured JSON output

**Serial Communication**:
- **PySerial** (Python) or **SerialPort** (C#)
- Baud rate: 115200 (OctoPrint) or 250000 (Klipper)

### Implementation Steps

#### 1. Audio Input Setup

**Python (PyAudio + Vosk)**:
```python
import pyaudio
import vosk
import json

# Load Vosk model
model = vosk.Model("vosk-model-small-en-us-0.15")
recognizer = vosk.KaldiRecognizer(model, 16000)

# Audio stream
p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    frames_per_buffer=8192
)

print("Listening...")
while True:
    data = stream.read(4096, exception_on_overflow=False)
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        text = result.get("text", "")
        if text:
            print(f"Recognized: {text}")
            process_command(text)
```

#### 2. Levenshtein Distance for Keyword Matching

**Fuzzy matching for voice recognition errors**:
```python
def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def match_keyword(detected_word, keyword_list, threshold=2):
    """Match detected word to closest keyword if within threshold"""
    best_match = detected_word
    min_distance = float('inf')
    
    for keyword in keyword_list:
        dist = levenshtein_distance(detected_word.lower(), keyword.lower())
        if dist < min_distance:
            min_distance = dist
            best_match = keyword
    
    return best_match if min_distance <= threshold else detected_word

# Usage
keywords = ["print", "move", "home", "level", "heat", "start", "stop", "pause"]
corrected = match_keyword("prent", keywords)  # Returns "print"
```

#### 3. GPT-4 API Integration for Command Extraction

**System Prompt Design**:
```python
import openai

openai.api_key = "YOUR_API_KEY"

SYSTEM_PROMPT = """You are a 3D printer command parser. Extract structured commands from natural language.

Valid commands:
- MOVE: {axis: "X"|"Y"|"Z", distance: number, units: "mm"|"cm"}
- PRINT: {type: "line"|"circle"|"rectangle", params: {...}}
- HOME: {axes: ["X", "Y", "Z"] or "all"}
- LEVEL: {}
- HEAT: {tool: "nozzle"|"bed", temp: number}
- SPEED: {value: number, units: "mm/s"|"%"}
- FAN: {speed: number (0-100)}

Return ONLY valid JSON. If unclear, return {"error": "unclear command"}.

Examples:
Input: "move 10 cm to the left"
Output: {"command": "MOVE", "axis": "X", "distance": -100, "units": "mm"}

Input: "print a 5 cm circle"
Output: {"command": "PRINT", "type": "circle", "radius": 25, "units": "mm"}
"""

def parse_voice_command(text):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        temperature=0.1,
        max_tokens=150
    )
    
    try:
        command = json.loads(response.choices[0].message.content)
        return command
    except json.JSONDecodeError:
        return {"error": "failed to parse"}

# Usage
command = parse_voice_command("please move 10 cm to the back")
print(command)  # {"command": "MOVE", "axis": "Y", "distance": -100, "units": "mm"}
```

#### 4. G-code Generator

**Convert structured commands to G-code**:
```python
class GCodeGenerator:
    def __init__(self):
        self.current_x = 0
        self.current_y = 0
        self.current_z = 0
        self.feedrate = 1500  # mm/min
    
    def move(self, axis, distance, units="mm"):
        """Generate G-code for movement"""
        if units == "cm":
            distance *= 10
        
        if axis == "X":
            self.current_x += distance
            return f"G0 X{self.current_x} F{self.feedrate}"
        elif axis == "Y":
            self.current_y += distance
            return f"G0 Y{self.current_y} F{self.feedrate}"
        elif axis == "Z":
            self.current_z += distance
            return f"G0 Z{self.current_z} F{self.feedrate}"
    
    def print_line(self, axis, distance, units="mm"):
        """Generate G-code for printing a line"""
        if units == "cm":
            distance *= 10
        
        gcode = []
        gcode.append("G1 F1200")  # Print speed
        
        if axis == "X":
            self.current_x += distance
            extrusion = abs(distance) * 0.02  # ~0.02mm extrusion per mm
            gcode.append(f"G1 X{self.current_x} E{extrusion}")
        elif axis == "Y":
            self.current_y += distance
            extrusion = abs(distance) * 0.02
            gcode.append(f"G1 Y{self.current_y} E{extrusion}")
        
        return "\n".join(gcode)
    
    def print_circle(self, radius, units="mm"):
        """Generate G-code for circular arc"""
        if units == "cm":
            radius *= 10
        
        # Use G2/G3 for arc interpolation
        gcode = []
        gcode.append(f"G1 F1200")
        gcode.append(f"G2 X{self.current_x} Y{self.current_y} I{radius} J0")
        return "\n".join(gcode)
    
    def home(self, axes="all"):
        """Home specified axes"""
        if axes == "all":
            return "G28"
        else:
            return f"G28 {' '.join(axes)}"
    
    def level(self):
        """Auto bed leveling"""
        return "G29"
    
    def heat_nozzle(self, temp):
        """Heat nozzle to temperature"""
        return f"M104 S{temp}"
    
    def heat_bed(self, temp):
        """Heat bed to temperature"""
        return f"M140 S{temp}"

# Usage
gen = GCodeGenerator()
gcode = gen.print_line("X", 50, "mm")
print(gcode)
```

#### 5. Serial Communication with Printer

**Send G-code over USB/serial**:
```python
import serial
import time

class PrinterConnection:
    def __init__(self, port="/dev/ttyUSB0", baudrate=115200):
        self.serial = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # Wait for connection
        print(f"Connected to printer on {port}")
    
    def send_gcode(self, gcode):
        """Send G-code command and wait for 'ok'"""
        self.serial.write(f"{gcode}\n".encode())
        
        # Wait for acknowledgment
        while True:
            response = self.serial.readline().decode().strip()
            if response:
                print(f"Printer: {response}")
            if "ok" in response.lower():
                break
    
    def close(self):
        self.serial.close()

# Usage
printer = PrinterConnection("/dev/ttyUSB0", 115200)
printer.send_gcode("G28")  # Home all axes
printer.send_gcode("G0 Z10 F1500")  # Move Z up 10mm
printer.close()
```

#### 6. Complete Integration

**Full voice-to-print pipeline**:
```python
def process_command(voice_text):
    """Main processing pipeline"""
    
    # Step 1: Parse with GPT-4
    command = parse_voice_command(voice_text)
    
    if "error" in command:
        print(f"Error: {command['error']}")
        return
    
    # Step 2: Generate G-code
    gen = GCodeGenerator()
    
    if command["command"] == "MOVE":
        gcode = gen.move(command["axis"], command["distance"])
    elif command["command"] == "PRINT" and command["type"] == "line":
        gcode = gen.print_line(command["axis"], command["distance"])
    elif command["command"] == "PRINT" and command["type"] == "circle":
        gcode = gen.print_circle(command["radius"])
    elif command["command"] == "HOME":
        gcode = gen.home()
    elif command["command"] == "LEVEL":
        gcode = gen.level()
    elif command["command"] == "HEAT":
        if command["tool"] == "nozzle":
            gcode = gen.heat_nozzle(command["temp"])
        else:
            gcode = gen.heat_bed(command["temp"])
    else:
        print("Unknown command")
        return
    
    # Step 3: Send to printer
    print(f"G-code: {gcode}")
    printer.send_gcode(gcode)

# Main loop
printer = PrinterConnection("/dev/ttyUSB0", 115200)

while True:
    data = stream.read(4096)
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        text = result.get("text", "")
        if text:
            print(f"You said: {text}")
            process_command(text)
```

---

## APPROACH 2: AI-Assisted Full Object Generation

### Architecture
```
Voice Input â†’ GPT-4o Audio API â†’ 
Python Script (OpenSCAD/CadQuery) â†’ 
STL File â†’ Slicer (Cura/Bambu Studio) â†’ 
G-code â†’ Printer
```

### Tech Stack

**LLM**: GPT-4o (multimodal audio/text)

**CAD Scripting**:
- **OpenSCAD** (declarative, simple syntax)
- **CadQuery** (Python-based, parametric)
- **BlenderGPT** (add-on for Blender)

**Slicing**: PrusaSlicer, Cura, or Bambu Studio CLI

### Implementation Steps

#### 1. GPT-4o Voice to CAD Script

**Direct voice input to Python OpenSCAD code**:
```python
import openai

openai.api_key = "YOUR_API_KEY"

OPENSCAD_PROMPT = """You are an OpenSCAD code generator. Convert voice descriptions to valid OpenSCAD code.

User will describe an object. Generate ONLY OpenSCAD code, no explanations.

Example:
Input: "Create a 50mm cube with a 10mm hole through the center"
Output:
difference() {
    cube([50, 50, 50], center=true);
    cylinder(h=60, r=5, center=true);
}
"""

def voice_to_openscad(description):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": OPENSCAD_PROMPT},
            {"role": "user", "content": description}
        ],
        temperature=0.3,
        max_tokens=500
    )
    
    code = response.choices[0].message.content
    # Extract code block if wrapped in ```
    if "```" in code:
        code = code.split("```")[1]
        if code.startswith("openscad"):
            code = code[8:]
    
    return code.strip()

# Usage
description = "A cylinder 75mm tall and 30mm diameter with an M8 hex socket on top"
openscad_code = voice_to_openscad(description)

# Save to file
with open("model.scad", "w") as f:
    f.write(openscad_code)

print("OpenSCAD code generated:")
print(openscad_code)
```

#### 2. CadQuery Alternative (Python-native)

**For more complex parametric models**:
```python
CADQUERY_PROMPT = """You are a CadQuery code generator. Generate valid Python CadQuery code.

Example:
Input: "Create a mounting bracket 50mm x 30mm x 5mm thick with 4mm holes in corners"
Output:
import cadquery as cq

result = (
    cq.Workplane("XY")
    .box(50, 30, 5)
    .faces(">Z")
    .workplane()
    .rect(42, 22, forConstruction=True)
    .vertices()
    .hole(4)
)
"""

def voice_to_cadquery(description):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": CADQUERY_PROMPT},
            {"role": "user", "content": description}
        ],
        temperature=0.3
    )
    
    code = response.choices[0].message.content
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    
    return code.strip()

# Execute and export STL
description = "A phone stand with 60 degree angle, 80mm wide"
cadquery_code = voice_to_cadquery(description)

# Write to file
with open("model_cq.py", "w") as f:
    f.write(cadquery_code)
    f.write("\n\nresult.val().exportStl('output.stl')")

# Execute
import subprocess
subprocess.run(["python", "model_cq.py"])
```

#### 3. OpenSCAD Headless Rendering

**Convert .scad â†’ .stl**:
```python
import subprocess

def openscad_to_stl(scad_file, stl_file):
    """Render OpenSCAD to STL using CLI"""
    cmd = [
        "openscad",
        "-o", stl_file,
        scad_file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"STL generated: {stl_file}")
        return True
    else:
        print(f"Error: {result.stderr}")
        return False

# Usage
openscad_to_stl("model.scad", "output.stl")
```

#### 4. Auto-Slicing with PrusaSlicer CLI

**STL â†’ G-code automation**:
```python
def slice_stl_to_gcode(stl_file, gcode_file, printer_profile="prusa_mk4"):
    """Slice STL to G-code using PrusaSlicer CLI"""
    cmd = [
        "prusa-slicer",
        "--load", f"/path/to/profiles/{printer_profile}.ini",
        "--export-gcode",
        "--output", gcode_file,
        stl_file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"G-code generated: {gcode_file}")
        return True
    else:
        print(f"Slicing error: {result.stderr}")
        return False

# Usage
slice_stl_to_gcode("output.stl", "output.gcode", "prusa_mk4")
```

#### 5. Bambu Studio API Integration

**For Bambu Lab printers (X1/P1 series)**:
```python
import requests

def send_to_bambu_printer(gcode_file, printer_ip, access_code):
    """Send G-code to Bambu Lab printer via LAN API"""
    
    url = f"http://{printer_ip}/api/upload"
    
    with open(gcode_file, "rb") as f:
        files = {"file": f}
        data = {"access_code": access_code}
        
        response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        print("File uploaded successfully")
        # Start print
        start_url = f"http://{printer_ip}/api/start"
        requests.post(start_url, data={"access_code": access_code})
        return True
    else:
        print(f"Upload failed: {response.text}")
        return False

# Usage
send_to_bambu_printer("output.gcode", "192.168.1.100", "12345678")
```

#### 6. Complete Voice-to-Print Pipeline

**End-to-end automation**:
```python
def voice_to_print_pipeline(voice_description):
    """
    Complete pipeline:
    Voice â†’ CAD Script â†’ STL â†’ G-code â†’ Print
    """
    
    print(f"Voice input: {voice_description}")
    
    # Step 1: Generate OpenSCAD code
    print("Generating CAD code...")
    openscad_code = voice_to_openscad(voice_description)
    
    with open("temp_model.scad", "w") as f:
        f.write(openscad_code)
    
    # Step 2: Render STL
    print("Rendering STL...")
    if not openscad_to_stl("temp_model.scad", "temp_model.stl"):
        return False
    
    # Step 3: Slice to G-code
    print("Slicing...")
    if not slice_stl_to_gcode("temp_model.stl", "temp_model.gcode"):
        return False
    
    # Step 4: Send to printer
    print("Sending to printer...")
    send_to_bambu_printer("temp_model.gcode", "192.168.1.100", "12345678")
    
    print("Print started!")
    return True

# Usage with voice recognition
while True:
    data = stream.read(4096)
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        text = result.get("text", "")
        
        if text and "create" in text.lower():
            voice_to_print_pipeline(text)
```

---

## Integration with Your Existing Setup

### OctoPrint API Integration

**For H2D, Giga, Artisan printers**:
```python
import requests

class OctoPrintAPI:
    def __init__(self, host, api_key):
        self.host = host
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}
    
    def upload_and_print(self, gcode_file):
        """Upload G-code and start print"""
        url = f"{self.host}/api/files/local"
        
        with open(gcode_file, "rb") as f:
            files = {"file": f}
            data = {"print": "true"}  # Auto-start
            
            response = requests.post(
                url,
                headers=self.headers,
                files=files,
                data=data
            )
        
        return response.status_code == 201

# Usage for multiple printers
printers = {
    "h2d": OctoPrintAPI("http://192.168.1.10", "API_KEY_1"),
    "giga": OctoPrintAPI("http://192.168.1.11", "API_KEY_2"),
    "artisan": OctoPrintAPI("http://192.168.1.12", "API_KEY_3")
}

# Voice command: "print on giga"
def print_on_printer(printer_name, gcode_file):
    if printer_name in printers:
        printers[printer_name].upload_and_print(gcode_file)
```

### Klipper/Moonraker Integration

**For Klipper-based printers**:
```python
import requests

class MoonrakerAPI:
    def __init__(self, host):
        self.host = host
    
    def upload_gcode(self, gcode_file):
        """Upload G-code via Moonraker API"""
        url = f"{self.host}/server/files/upload"
        
        with open(gcode_file, "rb") as f:
            files = {"file": f}
            response = requests.post(url, files=files)
        
        return response.json()
    
    def start_print(self, filename):
        """Start print job"""
        url = f"{self.host}/printer/print/start"
        data = {"filename": filename}
        response = requests.post(url, json=data)
        return response.json()

# Usage
moonraker = MoonrakerAPI("http://192.168.1.15:7125")
moonraker.upload_gcode("output.gcode")
moonraker.start_print("output.gcode")
```

---

## Quirks & Lessons Learned

### From TenTech Implementation

1. **Swearing improves accuracy**: Profanity may trigger more distinct phonetic patterns
   - Hypothesis: Emotional speech has clearer enunciation
   - Use emphasized speech for critical commands

2. **Layer adhesion issues**: Stopping after each line creates blobs
   - Solution: Buffer commands until layer complete
   - Implement retraction at layer changes

3. **Training custom models is time-intensive**: 56% accuracy after 20+ iterations
   - Recommendation: Use GPT-4 API instead
   - Cost: ~$0.01 per command vs. days of training

4. **Serial connection delays**: Wait for "ok" acknowledgment
   - Timeout after 5 seconds
   - Implement command queue

### From Brian Harms Implementation

1. **GPT-4o is non-deterministic**: Same prompt may vary
   - Add validation layer for critical dimensions
   - Preview STL before printing

2. **Voice recognition works better with context**:
   - Maintain conversation history
   - Reference previous objects ("make it 10mm taller")

3. **Bambu Studio Python API is unofficial**:
   - Use Bambu Connect SDK instead
   - MQTT for job status monitoring

---

## Recommended Stack for Your Mac Studio M3 Ultra Setup

```yaml
Hardware:
  - Mac Studio M3 Ultra (256GB RAM)
  - USB microphone (Blue Yeti or Shure MV7)
  - Network: Ubiquiti UniFi (existing)

Software:
  - Docker Desktop (existing)
  - Whisper.cpp (local STT, Metal-accelerated)
  - Ollama (local LLM fallback)
  - GPT-4o API (primary NLP)
  - OpenSCAD + CadQuery
  - PrusaSlicer CLI
  - OctoPrint instances (existing)
  - Klipper/Moonraker (existing)

Integration:
  - FastAPI gateway (from previous doc)
  - MQTT broker (printer status)
  - Redis cache (prompt history)
  - PostgreSQL (job logging)
```

### Docker Compose Addition

```yaml
services:
  voice-to-print:
    build: ./voice-to-print
    volumes:
      - ./models:/models
      - ./output:/output
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      WHISPER_MODEL: base.en
      OLLAMA_HOST: http://ollama:11434
    devices:
      - /dev/snd:/dev/snd  # Audio device
    depends_on:
      - ollama
      - mqtt
      - redis
```

---

## Next Steps

1. **Test Approach 1** with simple commands (home, move)
2. **Validate GPT-4 parsing** with sample voice inputs
3. **Generate sample OpenSCAD** for basic shapes
4. **Integrate with OctoPrint API** for one printer
5. **Scale to multi-printer** fleet with MQTT routing
6. **Add voice feedback** using Piper TTS ("Print started on H2D")

**Estimated implementation time**: 2-3 days for Approach 1, 5-7 days for full Approach 2 integration.
