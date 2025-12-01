## Tripo 3MF Workflow Smoke Test

Use this checklist whenever you need to verify that long-running Tripo jobs (5‑10 min) complete and return 3MF artifacts through the CAD service.

### 1. Configure timeouts

In `.env` (or your shell for an ad-hoc run):

```bash
TRIPO_POLL_TIMEOUT=900        # 15 minutes for /task completion (image_to_model)
KITTY_CLI_TIMEOUT=1200        # 20 minutes before the CLI aborts the HTTP call
```

Restart the CAD service (or the whole stack) so it re-reads the updated values.

### 2. Collect references

Use `kitty-cli /vision "<query>"` to fetch and store at least one high-quality reference image. Confirm that it shows up in `/images` so the CAD command can forward it as an `imageRef`.

### 3. Run a CAD job

```bash
kitty-cli cad "High-detail reference-based mesh test"
```

While it runs:

- CAD logs (`docker compose logs -f cad`) will show upload URLs, `/task` polling, and 3MF conversion traces (server-side first, local trimesh fallback if needed).
- The CLI spinner will continue until the HTTP response is sent or `KITTY_CLI_TIMEOUT` is hit.

### 4. Validate results

- The CLI should report at least one `provider=tripo` artifact with `artifactType="3mf"`.
- Artifacts are stored under the usual MinIO/local path; you can download them via `kitty-cli list` + `kitty-cli queue` or directly from the location path.
- Metadata will include `convert_task_id` when the server-side 3MF finished successfully.

### 5. Fallback sanity check (optional)

Temporarily disable convert to ensure the local `trimesh` fallback still works:

```bash
TRIPO_CONVERT_ENABLED=false
```

Restart CAD, rerun the job, and confirm the CLI still receives a 3MF along with a warning in the CAD logs noting that the local converter handled the export.

> Note: Server-side conversion is now enabled by default (`TRIPO_CONVERT_ENABLED=true`). The local trimesh fallback provides resilience if the Tripo convert API is unavailable.
