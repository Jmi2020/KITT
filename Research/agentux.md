Expert(s)	Agent Architect • Machine Learning Engineer • Vision/VLM Engineer • FastAPI/React Full-Stack • DevOps/Observability
Question	Design the Agent UX so a ReAct agent automatically invokes vision tools and reuses saved references, without operators running /vision manually.
Plan	Define when-to-vision triggers, a tool policy registry, and a memory-first flow. Add router hooks that: (1) detect visualizable requests, (2) consult saved references, (3) branch to Vision MCP (search → filter → present), (4) persist chosen refs, (5) pass image_refs to CAD. Back with tests, metrics, and safe defaults. Ground decisions in the ReAct pattern and MCP tool semantics. 🧠 Ⓘ ReAct pattern￼ and 🧰 Ⓘ MCP tools￼.  ￼

⏯️ This response gives: trigger design, prompt patches, a policy registry, router code, ReAct tool-calling snippets, memory reuse, UI cues, and tests/metrics. Links point to background on ReAct, MCP tools, CLIP, SearXNG, Gemma-3 Vision, spaCy noun-chunking.

⸻

🧭 Agent UX goals
    ---

    # Agent UX: Vision-first ReAct flow

    **Expert(s):** Agent Architect • Machine Learning Engineer • Vision/VLM Engineer • FastAPI/React Full-Stack • DevOps/Observability

    **Question:** Design the Agent UX so a ReAct agent automatically invokes vision tools and reuses saved references, without operators running `/vision` manually.

    **Plan:** Define when-to-vision triggers, a tool policy registry, and a memory-first flow. Add router hooks that: (1) detect visualizable requests, (2) consult saved references, (3) branch to Vision MCP (search → filter → present), (4) persist chosen refs, (5) pass `image_refs` to CAD. Back with tests, metrics, and safe defaults. Ground decisions in the ReAct pattern and MCP tool semantics.

    This document contains: trigger design, prompt patches, a policy registry, router code, ReAct tool-calling snippets, memory reuse patterns, UI cues, and tests/metrics. Links point to background on ReAct, MCP tools, CLIP, SearXNG, Gemma‑3 Vision, and spaCy noun‑chunking.

    ---

    ## Agent UX goals

    - Auto-detect requests that benefit from pictures, then invoke Vision MCP without operator commands.
    - Prefer existing saved references; offer “use saved vs fetch new”.
    - Keep it model‑agnostic via MCP tools so your text model (Qwen/Llama) stays the orchestrator, with CLIP/VLM behind a tool boundary.
    - Follow the ReAct loop: reason → act (tool) → observe → refine.

    ---

    ## 1) When should the agent call vision tools?

    ### 1.1 Trigger heuristics (stacked)

    1. Lexical patterns: “show me”, “images of”, “reference images”, “gallery”, “visual example”, “pictures of X”.
    2. Visualizable nouns: extract noun phrases and check against a visual‑concepts set (animal, part, product, tool, etc.). Use spaCy noun chunks or similar.
    3. CAD‑intent overlap: prompt includes “make/build/model/design 3D [thing]”, which benefits from image reference before CAD.
    4. Prior reference hit: the memory already stores saved `image_ref`s for the detected concept.
    5. Disambiguation cue: short ambiguous term (“duck”, “seal”) benefits from an image gallery to steer style or species.

    Keep triggers simple and auditable; you can later add learned classifiers.

    ### 1.2 Minimal policy (YAML)

    ```yaml
    # config/tool_policy.vision.yaml
    vision:
      regex_any:
        - "(?i)\\b(show|find|get)\\s+(me\\s+)?(pictures?|images?|photos?)\\b"
        - "(?i)\\breference\\s+images?\\b"
      noun_chunk_min_len: 1
      max_candidates: 12
      use_saved_first: true
      negative_prompts: ["rubber duck", "cartoon", "logo", "toy"]
      backend_default: "clip"      # or "vlm"
      vlm_endpoint: "${VISION_VLM_ENDPOINT:-}"
      threshold:
        clip: 0.27
        vlm: 0.55
    ```

    ---

    ## 2) Router hook: determine a “vision plan”

    Example router policy (noun‑chunking + lexical triggers):

    ```py
    # services/brain/src/brain/routing/vision_policy.py
    from typing import List, Dict
    import re
    import spacy

    NLP = spacy.load("en_core_web_sm")  # lightweight noun-chunking

    VIS_PATTERNS = [
        re.compile(r"\b(show|find|get)\s+(me\s+)?(pictures?|images?|photos?)\b", re.I),
        re.compile(r"\breference\s+images?\b", re.I),
    ]

    VISUALIZABLE_ALLOWLIST = {
        # expand over time
        "duck","goose","chair","lamp","mount","bracket","case","phone","dog","cat","handle",
        "gear","hinge","fan","propeller","knob","bicycle","boot","mask","bottle"
    }

    def extract_visual_targets(text: str) -> List[str]:
        doc = NLP(text)
        targets = []
        for np in doc.noun_chunks:
            t = np.text.lower().strip()
            if any(w in VISUALIZABLE_ALLOWLIST for w in t.split()):
                targets.append(t)
        return list(dict.fromkeys(targets))  # dedupe, preserve order

    def should_invoke_vision(user_text: str) -> Dict:
        if any(p.search(user_text) for p in VIS_PATTERNS):
            return {"invoke": True, "reason": "lexical"}
        targets = extract_visual_targets(user_text)
        if targets:
            return {"invoke": True, "reason": "visualizable", "targets": targets}
        return {"invoke": False, "reason": "none"}
    ```

    Noun‑chunking plus a concept allowlist gives transparent, controllable triggers.

    ---

    ## 3) ReAct agent prompt patches (teach the model)

    Add to your system prompt (guidance for the agent):

    - When a user asks for pictures, reference images, or describes a physical object to model/print/machine, do the following:
      1. Check memory for saved image references relevant to the object.
      2. If relevant references exist, offer to reuse them. If the user says “new” or none exist, run `vision.image_search` → `vision.image_filter` (backend=`clip` by default; `vlm` if configured).
      3. Present 6–12 ranked images and ask the user to pick any to save.
      4. After selection, call `vision.store_selection` and proceed with CAD using those `image_refs`.

    This encourages the model to reason, then act via tools, then incorporate observations (ReAct loop).

    ---

    ## 4) ReAct tool‑calling scaffolding

    ### 4.1 Plan builder (memory‑first)

    ```py
    # services/brain/src/brain/agent/plan_builders.py
    from .tool_client import run_tool  # thin MCP client
    from ..routing.vision_policy import should_invoke_vision, extract_visual_targets

    async def maybe_plan_vision(ctx, user_text: str) -> dict | None:
        if not ctx.flags.vision_enabled:
            return None
        trig = should_invoke_vision(user_text)
        if not trig["invoke"]:
            return None

        # 1) memory-first
        targets = trig.get("targets") or extract_visual_targets(user_text) or []
        mem_hits = await run_tool("memory", "recall_memory", {"query": "image_ref " + ", ".join(targets)})
        has_refs = bool(mem_hits.get("data"))

        if has_refs and ctx.flags.use_saved_first:
            return {"type": "vision", "mode": "reuse", "refs": mem_hits["data"], "targets": targets}

        # 2) new fetch
        return {"type": "vision", "mode": "fetch", "targets": targets}
    ```

    ### 4.2 ReAct loop integration

    ```py
    # services/brain/src/brain/agent/react_loop.py
    async def step_reason_and_act(ctx, user_text: str):
        # ... existing reasoning ...
        vplan = await maybe_plan_vision(ctx, user_text)
        if vplan and vplan["mode"] == "reuse":
            ctx.ui.emit_card("found_saved_refs", {"targets": vplan["targets"], "refs": vplan["refs"]})
            return

        if vplan and vplan["mode"] == "fetch":
            q = user_text
            res = await run_tool("vision", "image_search", {"q": q, "top_k": 12})
            urls = [h["url"] for h in res["data"]]
            ranked = await run_tool("vision", "image_filter", {
                "q": q, "images": urls, "threshold": ctx.cfg.vision.threshold.clip,
                "backend": ctx.cfg.vision.backend_default
            })
            ctx.session.cache["vision_ranked"] = ranked["data"]
            ctx.ui.emit_gallery("vision_candidates", ranked["data"])  # UI shows pickable tiles
            return
    ```

    The MCP tool pattern fits the ReAct flow: the model requests tools, the tools return observations, and the model continues reasoning.

    ---

    ## 5) Memory‑first reuse of saved images

    ### 5.1 Memory schema (logical)

    ```json
    {
      "kind": "image_ref",
      "label": "duck",
      "keys": [
        {"minio_key": "references/s123/abc.jpg", "url": "https://minio/presigned/abc"},
        {"minio_key": "references/s123/def.jpg", "url": "https://minio/presigned/def"}
      ],
      "meta": {"source": "searxng", "created_at": "2025-11-08T22:05:00Z"}
    }
    ```

    Store this via your Memory MCP after `vision.store_selection`. For later CAD calls, pass these URLs as `image_refs`.

    Presigned URLs (MinIO) are ideal for time‑bound access to stored references.

    ### 5.2 Offer reuse before fetching

    ```py
    # services/brain/src/brain/agent/handlers/vision_handlers.py
    async def on_gallery_choice(ctx, chosen_urls: list[str]):
        stored = await run_tool("vision", "store_selection", {
            "session_id": ctx.session.id, "images": chosen_urls
        })
        # Write to memory
        await run_tool("memory", "store_memory", {
            "kind": "image_ref",
            "label": ctx.session.topic_label,
            "keys": stored["data"]
        })
        ctx.ui.toast("Saved references for future use.")
    ```

    ---

    ## 6) Richer scoring and VLM integration (Gemma‑3 Vision)

    - Default backend: CLIP for fast zero‑shot similarity.
    - Optional backend: VLM (e.g., Gemma‑3 Vision) via HTTP service for deeper reasoning (style, single subject, profile view).

    Choose backend dynamically based on the ask:

    ```py
    backend = "vlm" if ctx.flags.vision_vlm_enabled and "style" in user_text.lower() else "clip"
    ranked = await run_tool("vision", "image_filter", {
        "q": q, "images": urls, "backend": backend,
        "threshold": ctx.cfg.vision.threshold[backend]
    })
    ```

    For richer scoring, blend signals: S = α·S_clip + β·S_vlm, add negative prompts, and deduplicate near‑duplicates by embedding distance (reuse CLIP embeddings).

    ---

    ## 7) UI: make it feel automatic

    - When triggers fire, the UI emits a “references found” banner if memory has them, with a **Use these** button.
    - If fetching: show a gallery card with 6–12 images. Selection writes back to `vision.store_selection`, then the agent continues.
    - A drawer lists “Saved references for this topic” so the user can swap or add more at any time.

    ---

    ## 8) Tests

    - Unit: trigger detection (regex and noun‑chunking), memory‑first branch, vision plan building.
    - Integration: `image_search` → `image_filter` (clip and vlm paths), `store_selection` writing to MinIO and Memory.
    - E2E: “Make a 3D duck lamp” → gallery → choose → CAD called with `image_refs`.

    ---

    ## 9) Metrics & safety

    - Export counters and durations: `vision_triggered_total`, `vision_candidates`, `vision_filter_latency_ms`, `vision_store_success_total`.
    - Respect SearXNG safe‑search and image categories; filter tiny images and unsupported types.
    - Log MCP calls for auditability; MCP is model‑controlled tooling and fits the ReAct safety posture.

    ---

    ## 10) End‑to‑end example

    User: “Design a parametric duck lamp. I want it cute and smooth.”

    Agent flow:

    1. `vision.image_search(q="duck")` → candidates (SearXNG).
    2. `vision.image_filter(..., backend="vlm")` because of “style” cue (Gemma‑3 Vision preferred for style relevance).
    3. UI gallery shows 8 images.
    4. User picks 3 → `vision.store_selection` persists to MinIO and Memory as `image_ref: duck`.
    5. Agent calls CAD with `image_refs=[...]`.

    ---

    ## 11) Drop‑in code: tiny orchestrator glue

    ```py
    # services/brain/src/brain/agent/controller.py
    async def handle_user_turn(ctx, user_text: str):
        vplan = await maybe_plan_vision(ctx, user_text)
        if vplan:
            await step_reason_and_act(ctx, user_text)
            return
        # otherwise continue normal ReAct planning...
    ```

    Config flags (env or config file):

    ```yaml
    vision:
      enabled: true
      use_saved_first: true
      backend_default: clip   # set to vlm if you host Gemma-3 Vision
      threshold:
        clip: 0.27
        vlm: 0.55
    ```

    ---

    ## See also

    - ReAct agent pattern — why “reason → act → observe” works for tools.
    - MCP tools spec — model‑controlled tools, perfect for vision pipes.
    - SearXNG API — image category and parameters.
    - CLIP zero‑shot — similarity scoring foundation.
    - Gemma‑3 Vision details — SigLIP encoder and “pan & scan”.
    - spaCy noun chunks — quick noun phrase extraction.

    If you want, I can bundle these snippets as a single `agent_vision_ux.md` and prepare a minimal PR branch layout.
