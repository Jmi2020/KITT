# Voice Page UI Improvement Plan

Working notes for incremental voice page polish. Keep this updated as phases ship.

## Scope
- History sidebar compactness and clarity
- Empty state guidance and mic toggle affordance
- Status panel spacing/consistency
- Navbar visual alignment with the neon/glass theme
- Footer mic control UX and markdown readability

## Phases

### Phase 1 — History + Empty State
- [ ] Compact conversation tiles (smaller actions, tighter padding, aligned text)
- [ ] Sticky group headers (“Today”, “Yesterday”, etc.) while scrolling
- [ ] Slimmer “New Conversation” affordance matching the glass/neon style
- [ ] Empty state card with quick-start prompts + “Tap mic to start” cue near toggle
- [ ] Pull mic/terminal toggle closer to the empty state

### Phase 2 — Status Panel + Nav
- [ ] Normalize spacing and dividers between Protocol / Wake Word / Audio Input / Tasks
- [ ] Resize “EDIT” chip and Wake Word row to match control sizing
- [ ] Center audio level bars, add subtle live/off badge
- [ ] Re-theme top nav pills/glass to align with voice neon palette; anchor Kitty badge positioning

### Phase 3 — Footer + Background + Markdown
- [ ] Footer mic: status tag under button; hint chips on a single line with smaller padding
- [ ] Background grid: increase center contrast, fade edges
- [ ] Markdown/readability: slightly larger text for responses, max-width and elevation to avoid edge-to-edge spans
- [ ] Keep inference ribbon visible only during processing, with subtle glow bar

### Phase 4 — Grid + Readability + Inference Glow (in progress)
- [ ] Tune background grid contrast/edge fade to highlight the conversation center
- [ ] Improve response markdown readability (font size/line height, max width, table spacing)
- [ ] Add a subtle glow/progress bar to the inference ribbon for long runs

## Notes
- Avoid disturbing main mic ring pulse; keep sidebar meters minimal.
- Respect existing voice engine flows; no backend changes planned.
- Keep changes localized to voice page components and styles.
