# 🎯 Richer Scoring for Vision Filtering: Deep Dive

*From the lens of a Machine Learning / Vision Systems Engineer*

---

## 1. Basic similarity scoring (CLIP)

-   **CLIP uses a contrastive learning setup**: a joint text encoder and image encoder are trained on large amounts of image–caption pairs scraped from the web.
-   **At inference time**:
    1.  Encode the image into an embedding vector `E_I`.
    2.  Encode one or more candidate text prompts into embedding(s) `E_T`.
    3.  Compute cosine similarity:
        ```
        sim(I,T) = (E_I . E_T) / (||E_I|| ||E_T||)
        ```
        (often scaled or converted into a softmax over a set of label-prompts)
-   Many toolkits define a “CLIPScore” metric:
    ```
    CLIPScore(I,C) = max(100 * cos(E_I, E_C), 0)
    ```
-   **In our context**: we use the similarity to the prompt (e.g., “a photo of a duck”) to decide relevance. A higher similarity → more likely the image contains the requested concept.

---

## 2. Why basic scoring might be insufficient for our use-case

While CLIP scoring works well for general objects, in applied systems like yours (image search for CAD reference) we encounter these challenges:

-   **Ambiguity of the prompt**: “duck” might match rubber ducks, cartoon ducks, or other duck-shapes rather than the style you want.
-   **Fine-grained distinctions**: differentiating species of duck, or duck silhouette versus other waterfowl, may confuse CLIP’s zero-shot classifier.
-   **Multiple relevant labels**: The image may contain multiple objects; e.g., a “duck on water with lily pad” — prompt might be “duck only”.
-   **Sampling bias/embedding drift**: CLIP’s embedding space is trained on broad web data; for niche contexts (technical reference images, CAD-friendly photos) the similarity score alone may not align with your aesthetic or structural requirements.
-   **Multiple images vs single score**: If we fetch many images, we need a ranking scheme—not just “above threshold” but “best of set”.

---

## 3. Enhanced scoring strategies (for richer relevance)

To raise the quality of the image filter, you can adopt a layered scoring architecture:

### a) Multi-prompt scoring

Instead of a single text prompt, use a set of prompts that capture good vs bad matches:

-   **Positive prompts**: “a photo of a duck”, “a mallard duck on water”, “duck side view”.
-   **Negative prompts**: “rubber duck”, “toy duck”, “duck cartoon”, “goose”.

Compute similarity to all prompts; then define a composite score such as:

```
S = max(cos(E_I, E_T_p) for p in positive) - max(cos(E_I, E_T_n) for n in negative)
```

Images with high `S` are preferred (they align more with positive prompts than negatives). This helps filter out unwanted variants (e.g., toys, cartoons).

### b) Normalize / calibrate scores

Since cosine similarity ranges roughly from -1 to +1, and different prompts may cluster differently, you may:

-   Convert to softmax over all image-text pairs to get relative likelihoods (CLIP training style).
-   Empirically determine thresholds based on sample distributions in your use-case (e.g., reject images with similarity < 0.3).
-   Rank images by descending similarity and take top-k, rather than accept all above threshold.

### c) Embedding clustering / freshness

If you collect many candidate images, you can:

-   Compute pairwise embedding distance among images to diversify picks (avoid near-duplicates).
-   Remove very similar images (embedding distance < epsilon) so user sees variety.
-   Optionally favour images with larger bounding boxes or resolution metadata (if available) to prefer higher quality references.

### d) Vision-LLM scoring (Gemma 3 or other VLMs)

If you embed a vision-language model (VLM) such as Gemma 3 with vision encoder (“SigLIP”) into your toolchain, you can extend scoring beyond simple similarity:

-   VLM can reason about the image: “Is there exactly one duck? Is the view side profile? Is resolution appropriate for CAD?”
-   Example: Gemma 3’s image encoder uses 896 × 896 resolution and a “pan & scan” cropping strategy to handle varying aspect ratios.
-   You can feed the prompt + image into the VLM and obtain:
    -   A relevance score (“This image shows a duck”)
    -   A style/quality score (“Image is clear, high-resolution, side view”)
-   The VLM score can be combined with CLIP score:
    ```
    S_combined = alpha * S_clip + beta * S_vlm
    ```
    Adjust weights `alpha`, `beta` based on experimentation.

### e) Metadata and heuristics

In addition to pure embedding scores, augment with heuristics:

-   Discard images with very small resolution or very narrow aspect ratio (likely icons).
-   Prefer “clear background”, “single subject”, “side view” (extract via heuristic or via VLM).
-   Rank by resolution, orientation, subject-fill ratio (if bounding boxes available).
-   Use source domain heuristics (e.g., stock photo sites may have high quality).

---

## 4. Putting it together: Pipeline for richer scoring

1.  Run image search → get candidate URLs (top N, e.g., 12).
2.  Download images (or thumbnails) and encode via CLIP (and optionally VLM).
3.  Compute scores:
    -   `s_clip` via similarity to positive/negative prompts.
    -   `s_vlm` via VLM relevance reasoning (optional).
    -   Combined score `S_combined`.
4.  Filter: keep only images with `S_combined` >= T.
5.  Rank: order images by `S_combined` descending.
6.  Deduplicate: compute embedding distances, remove near-duplicates.
7.  Present to user: show top K images in UI gallery with scores visible (or hidden but used for ordering).
8.  On user selection, persist only selected images for CAD reference.

---

## 5. Implementation snippet (pseudo-code)

```python
# assume clip_model, clip_preprocess set up; optional vlm_client

def score_image(url: str, prompt_pos: List[str], prompt_neg: List[str]) -> float:
    img = download_image(url)
    emb_img = clip_model.encode_image(clip_preprocess(img).unsqueeze(0))
    emb_img = emb_img / emb_img.norm(dim=-1, keepdim=True)
    
    # encode prompts
    emb_pos = clip_model.encode_text(tokenize(prompt_pos))
    emb_neg = clip_model.encode_text(tokenize(prompt_neg))
    emb_pos = emb_pos / emb_pos.norm(dim=-1, keepdim=True)
    emb_neg = emb_neg / emb_neg.norm(dim=-1, keepdim=True)
    
    sim_pos = (emb_img @ emb_pos.T).max().item()
    sim_neg = (emb_img @ emb_neg.T).max().item()
    
    s_clip = sim_pos - sim_neg
    
    # optionally query VLM
    s_vlm = 0.0
    if vlm_client:
        s_vlm = vlm_client.score(prompt=chosen_prompt, image_url=url)
        
    # combined
    return alpha * s_clip + beta * s_vlm
```

---

## 6. Why this matters for your CAD workflow

-   **Higher-quality reference images** → better output from your CAD backend (e.g., clearer subject, better angles)
-   By filtering out irrelevant variants (toy ducks, low-resolution, incorrect perspective) you reduce noise in user selection and improve UX.
-   If you later pass these images into image-conditioned CAD models (such as Tripo), your image quality matters; richer scoring increases the chance the model sees a clean reference.
-   The scoring pipeline can be tuned over time (thresholds, weights) to adapt to your camp’s style (Twilight Language), hardware constraints, and project types.

---

---

## 7. Measuring Success and Iterating

A scoring model is only as good as its results. To ensure the enhanced pipeline is a genuine improvement, establish a framework for measurement and iteration.

-   **A/B Testing**: Deploy the new scoring logic to a subset of users and compare it against the baseline (e.g., basic CLIP score). Track metrics to determine which system provides more relevant results.
-   **Human-in-the-loop Feedback**: Incorporate a simple feedback mechanism in the UI (e.g., a thumbs-up/down on presented images). This user-provided data is invaluable for:
    -   Building a high-quality evaluation dataset.
    -   Fine-tuning the weights (`alpha`, `beta`) in your combined score.
    -   Identifying new negative prompts or failure modes.
-   **Monitor Key Metrics**: Track metrics that proxy for user satisfaction and relevance. Examples include:
    -   **Click-Through Rate (CTR)**: The percentage of displayed images that the user selects.
    -   **Average Rank of Selected Image**: A lower average rank suggests the best results are appearing earlier.
    -   **Zero-Result Rate**: The percentage of searches that return no images after filtering. This should be monitored to ensure the filter isn't overly aggressive.

---

## 8. System Considerations

Introducing more models and logic into the pipeline has system-level implications.

### a) Latency & Cost

-   **VLM Calls**: Calling a Vision-Language Model is significantly slower and more expensive than a local CLIP model. Consider using it as a "second-pass" reranker on a smaller set of top candidates from the initial CLIP-based filtering.
-   **Model Choice**: Smaller, distilled versions of CLIP or other embedding models can offer a better speed/accuracy trade-off for the initial filtering stage.
-   **Batching**: If you are processing multiple images, batch the encoding process for better hardware utilization (especially on GPU).

### b) Caching

-   **Embedding Cache**: Store the computed image embeddings (from CLIP) and VLM scores in a database or a key-value store (like Redis). The image URL or a hash of the image content can serve as the key. This avoids re-computing scores for images that have been seen before.
-   **Prompt Embedding Cache**: Text prompt embeddings can also be cached, though this is less critical as text encoding is very fast.

---

## 9. ✅ Summary

-   Use CLIP for fast zero-shot similarity scoring between image ↔ text prompts.
-   Augment with richer signals: negative prompts, metadata heuristics, VLM reasoning (e.g., Gemma-3-Vision) for deeper relevance.
-   Combine scores into a ranking and filtering pipeline so only high-relevance images get shown to the user.
-   This ensures your reference image acquisition step is robust, high quality, and aligned with downstream CAD tasks.

---

## See also

-   🔍 Zero-shot CLIP architecture — how similarity works
-   🧠 Gemma 3 vision-language model technical details — next-gen VLM reasoning
-   📊 CLIPScore metric for image-caption evaluation — reference-free scoring