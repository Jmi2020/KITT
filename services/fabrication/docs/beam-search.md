# Beam Search Segmentation (Phase 2)

## Overview

Beam search explores multiple cutting sequences in parallel to find better solutions than the default greedy algorithm. While greedy picks the single best cut at each step, beam search maintains multiple candidate paths and selects the best final result.

## Greedy vs Beam Search

### Greedy Algorithm (Default)

```
Step 1: Find best cut → Apply it
Step 2: Find best cut → Apply it
Step 3: Find best cut → Apply it
Result: Locally optimal at each step
```

**Pros:** Fast, predictable
**Cons:** May miss globally better solutions

### Beam Search Algorithm

```
Step 1: Find top 3 cuts → Keep all 3 paths
Step 2: For each path, find top 3 cuts → Keep best 9 paths overall
Step 3: Prune to top 3 paths → Continue
Result: Explores multiple possibilities
```

**Pros:** Can find better solutions
**Cons:** Slower, more memory

## How It Works

### SegmentationPath

Each path tracks its state:

```python
@dataclass
class SegmentationPath:
    parts: List[MeshWrapper]      # Current mesh pieces
    cuts: List[CuttingPlane]      # Cuts made so far
    score: float                   # Cumulative quality score

    def is_complete(self) -> bool:
        """All parts fit build volume."""
        return all(part.fits_in_volume(build_volume) for part in self.parts)
```

### BeamSearchSegmenter

```python
class BeamSearchSegmenter:
    def __init__(self, config: SegmentationConfig):
        self.beam_width = config.beam_width
        self.max_depth = config.beam_max_depth
        self.timeout = config.beam_timeout_seconds

    def search(self, mesh: MeshWrapper) -> SegmentationPath:
        beam = [SegmentationPath(parts=[mesh], cuts=[], score=1.0)]

        for depth in range(self.max_depth):
            if time.time() - start > self.timeout:
                break

            candidates = []
            for path in beam:
                if path.is_complete():
                    continue
                # Expand: try all cuts on largest oversized part
                expansions = self._expand(path)
                candidates.extend(expansions)

            # Keep top beam_width paths
            beam = sorted(candidates, key=lambda p: p.score, reverse=True)
            beam = beam[:self.beam_width]

            if all(p.is_complete() for p in beam):
                break

        return beam[0]  # Best complete path
```

### Path Expansion

For each path, the algorithm:
1. Finds the largest part exceeding build volume
2. Generates all candidate cuts for that part
3. Applies each cut to create new paths
4. Scores each new path

## Configuration

```python
from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine

engine = PlanarSegmentationEngine(
    build_volume=(256, 256, 256),
    enable_beam_search=True,
    beam_width=3,              # Paths to keep at each step
    beam_max_depth=10,         # Maximum cuts to explore
    beam_timeout_seconds=60.0, # Safety timeout
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_beam_search` | `False` | Feature toggle |
| `beam_width` | `3` | Number of parallel paths |
| `beam_max_depth` | `10` | Maximum search depth |
| `beam_timeout_seconds` | `60.0` | Timeout before fallback |

## When Beam Search Helps

### Good Candidates

- Complex shapes with multiple valid cut sequences
- Models where early cuts affect later options
- When greedy produces unbalanced parts

### Less Beneficial

- Simple box-like shapes
- Models needing only 1-2 cuts
- When greedy already produces good results

## Performance

| Beam Width | Relative Time | Paths Explored |
|------------|---------------|----------------|
| 1 | 1x (greedy) | 1 |
| 3 | ~3-5x | 3^depth |
| 5 | ~5-10x | 5^depth |

**Tip:** Start with `beam_width=3` for most use cases.

## Fallback Behavior

If beam search fails or times out:
1. Log warning with reason
2. Automatically fall back to greedy algorithm
3. Return greedy result

```python
try:
    result = beam_segmenter.search(mesh)
except BeamSearchTimeout:
    LOGGER.warning("Beam search timed out, falling back to greedy")
    result = greedy_segmenter.segment(mesh)
```

## Testing

```bash
# Run beam search tests
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/test_engine.py::TestBeamSearchSegmentation -v
```

### Test Cases

| Test | Purpose |
|------|---------|
| `test_beam_search_disabled_by_default` | Feature is opt-in |
| `test_beam_search_can_be_enabled` | Config works |
| `test_beam_search_produces_valid_result` | Results are correct |
| `test_beam_search_path_tracking` | Path history maintained |
| `test_beam_search_respects_beam_width` | Width limit enforced |
| `test_beam_search_timeout` | Timeout works |
| `test_greedy_fallback_when_beam_fails` | Fallback behavior |

## Example: L-Shaped Model

Consider an L-shaped model that needs 2 cuts:

**Greedy approach:**
1. Cut 1: Best single cut → Creates uneven pieces
2. Cut 2: Best cut on largest piece → Still unbalanced

**Beam search approach:**
1. Cut 1: Keep top 3 options (different orientations)
2. Cut 2: Expand all 3 → 9 possibilities
3. Final: Select path with most balanced result

Beam search may find a better first cut that enables a better second cut.

## Key Files

| File | Purpose |
|------|---------|
| `engine/beam_search.py` | BeamSearchSegmenter class |
| `engine/planar_engine.py:500-550` | Integration with main engine |
| `schemas.py:115-120` | Config parameters |

## Debugging

Enable verbose logging to see beam search progress:

```python
import logging
logging.getLogger("fabrication.segmentation.engine.beam_search").setLevel(logging.DEBUG)
```

Output shows:
- Paths explored at each depth
- Scores for each candidate
- Pruning decisions
- Final path selection
