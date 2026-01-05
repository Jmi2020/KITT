🛠 **Overview**

Meshy provides a RESTful API for programmatically creating 3D assets.  All endpoints share a predictable base URL (`https://api.meshy.ai`) and use standard HTTP verbs.  Requests must be authenticated with an API key supplied in the `Authorization` header.  The API exposes asynchronous task‑creation endpoints (e.g., text‑to‑3D, image‑to‑3D, multi‑image‑to‑3D).  These endpoints return a task identifier which you poll to fetch the generated model.  Below is a detailed guide on integrating the API into your backend.

### 1. Obtain an API Key

1. **Create/Login to a Meshy account** – sign up at Meshy.ai or log in if you already have an account.
2. **Request API access** – navigate to the API section of the dashboard, provide project details, and request access.
3. **Generate an API key** – once approved, generate an API key.  Keep it secure; you’ll need it to authenticate each API call.

### 2. Set Up Credentials in Your Backend

* **Store the key securely**: place the API key in a secure secrets manager or environment variable (e.g., `MESHY_API_KEY`).  Never hard‑code it.
* **Authorization header**: Meshy expects the header `Authorization: Bearer <YOUR_API_KEY>` on every request.

### 3. Understand the Base URL and Endpoints

* **Base URL**: `https://api.meshy.ai` .
* **Versioning and paths**: most endpoints are under `/openapi/v1/`.
* **Task‑creation endpoints**:

  * **Text‑to‑3D**: `POST /openapi/v1/text-to-3d` (not fully shown in the snippet but inferred from the docs; there are preview and refine stages).
  * **Image‑to‑3D**: `POST /openapi/v1/image-to-3d`.
  * **Multi‑Image‑to‑3D**: `POST /openapi/v1/multi-image-to-3d`.
  * **Rigging/animation**: `POST /openapi/v1/rigging` (optional for auto‑rigging).
* **Task status and retrieval**:

  * `GET /openapi/v1/{task-type}/{id}` – retrieve details and model URLs.
  * `GET /openapi/v1/{task-type}` – list tasks (supports pagination).
  * `DELETE /openapi/v1/{task-type}/{id}` – remove tasks.

### 4. Designing the Integration Workflow

#### a. Choosing an HTTP client

Select an HTTP client library appropriate for your backend language (e.g., `requests` or `httpx` for Python, `axios` or native `fetch` for Node.js, `HttpClient` for .NET).  Ensure the client supports asynchronous calls and streaming if you plan to poll tasks or download binary GLB/FBX/OBJ files.

#### b. Creating tasks (example: text‑to‑3D)

1. **Prepare the request body**.  For text‑to‑3D, include:

   * `mode`: `"preview"` for generating the base mesh (without textures); after evaluating the preview you can call a refine stage with `mode`: `"refine"` to generate textures.
   * `prompt`: a text description of the desired model.
   * Optional fields like `negative_prompt`, `art_style`, `should_remesh` etc.

2. **Send a POST request**:

   ```python
   import os, requests

   api_key = os.environ["MESHY_API_KEY"]
   headers = {"Authorization": f"Bearer {api_key}"}
   payload = {
       "mode": "preview",
       "prompt": "A detailed medieval castle with towers and moat",
       "negative_prompt": "low detail, pixelated",
       "art_style": "realistic",
       "should_remesh": False
   }

   resp = requests.post("https://api.meshy.ai/openapi/v1/text-to-3d", json=payload, headers=headers)
   resp.raise_for_status()
   task_id = resp.json().get("result")
   ```

   The response includes a UUID‐like `result` field representing the task ID.

3. **Poll for task completion**:

   ```python
   import time

   def poll_task(task_id):
       while True:
           status_resp = requests.get(f"https://api.meshy.ai/openapi/v1/text-to-3d/{task_id}", headers=headers)
           status_resp.raise_for_status()
           task_info = status_resp.json()
           if task_info.get("status") in ["succeeded", "failed"]:
               return task_info
           time.sleep(5)  # wait a few seconds before polling again
   ```

4. **Retrieve model URLs**:
   Once the task status is `succeeded`, the task object includes `model_urls` with signed URLs (GLB, FBX, OBJ).  Use your HTTP client to download the files and store them in your backend or cloud storage.

#### c. Creating Image‑to‑3D tasks

1. **Provide the image**: supply an `image_url` parameter (public URL) or a `data:image/jpeg;base64,…` data URI as per the docs.
2. **Optional parameters**: choose `ai_model` (e.g., `"meshy-4"`), `topology`, `texture` options etc.  The default model is `meshy-4`.
3. **Send POST** to `/openapi/v1/image-to-3d`.  The response returns a `result` task ID.  Poll `GET /openapi/v1/image-to-3d/{id}` for status and retrieve the model URLs similarly.

#### d. Creating Multi‑Image‑to‑3D tasks

When you have multiple images from different angles, call `POST /openapi/v1/multi-image-to-3d` with an array of image URLs or data URIs.  Poll `GET /openapi/v1/multi-image-to-3d/{id}` until the task succeeds.  On success, the API returns signed URLs for the GLB/FBX/OBJ models.

#### e. Handling rate limits, retries and errors

* Meshy’s free and paid tiers impose per‑second request limits and concurrent task caps; design your backend to queue requests and respect these limits.
* Handle HTTP status codes: 4xx codes indicate client errors (e.g., invalid parameters); 429 indicates rate‑limit throttling; 5xx indicates server errors.
* Implement exponential backoff for retries when encountering transient errors.

#### f. Security considerations

* Use HTTPS (the API uses HTTPS by default).
* Never expose your API key in client‑side code or logs.
* Rotate keys periodically and monitor credit usage via the dashboard.

#### g. Integration patterns

* **Synchronous microservice**: for smaller tasks you can block until the task finishes; ensure timeouts are generous (Meshy tasks can take tens of seconds).
* **Asynchronous worker**: recommended for production.  Submit tasks to Meshy, store the task IDs, then have a background worker poll and fetch results.  Notify the client (e.g., via WebSocket or push notification) when models are ready.
* **Webhook support**: Meshy docs hint at webhook support (webhook endpoints available in enterprise tiers) enabling automatic callbacks when tasks complete.  If available, configure your backend to receive events and avoid polling.

### 5. Sample Node.js Implementation (Express)

```javascript
// server.js
const express = require('express');
const axios = require('axios');
require('dotenv').config();

const app = express();
app.use(express.json());

const apiKey = process.env.MESHY_API_KEY;
const headers = { Authorization: `Bearer ${apiKey}` };

// Submit a text‑to‑3D task
app.post('/generate-model', async (req, res) => {
  const { prompt } = req.body;
  try {
    const response = await axios.post(
      'https://api.meshy.ai/openapi/v1/text-to-3d',
      { mode: 'preview', prompt },
      { headers }
    );
    const taskId = response.data.result;
    res.json({ taskId });
  } catch (err) {
    res.status(500).json({ error: err.response?.data || err.message });
  }
});

// Polling endpoint for clients
app.get('/task-status/:id', async (req, res) => {
  try {
    const statusResponse = await axios.get(
      `https://api.meshy.ai/openapi/v1/text-to-3d/${req.params.id}`,
      { headers }
    );
    res.json(statusResponse.data);
  } catch (err) {
    res.status(500).json({ error: err.response?.data || err.message });
  }
});

app.listen(3000, () => {
  console.log('Backend server running on port 3000');
});
```

This sample uses `axios` to create tasks and poll for status.  In production, you’d offload polling to a worker and store results in a database.

### 6. Next Steps and Best Practices

* Explore other Meshy endpoints like auto‑rigging & animation for rigging humanoid models.
* Consider using Meshy’s plugins for direct integration into Blender, Unity or game engines if your workflow demands it.
* Monitor credit usage and upgrade plans if you need higher rate limits or enterprise features (e.g., guaranteed uptime, indefinite asset retention).
