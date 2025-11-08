# Context Measurement Log

This file tracks prompt-token measurements while we tune KITTY's context budgets.

## How to Measure

1. Enable prompt logging:
   ```bash
   export PROMPT_TOKEN_LOG=1
   ```
2. Run a representative query (CLI or API). Each prompt build logs a breakdown:
   ```text
   Prompt token breakdown: {'identity': 320, 'hallucination_prevention': 410, 'tool_definitions': 950, ... 'total': 6200}
   ```
3. Copy the numbers into the table below with the scenario description.

| Date       | Scenario / Prompt                        | System Tokens | Tool Tokens | Context/History Tokens | Total Tokens | Notes |
|------------|-------------------------------------------|---------------|-------------|------------------------|--------------|-------|
| 2025-11-08 | example: CLI `/agent on` + time-sensitive | TBD           | TBD         | TBD                    | TBD          |       |

Add new rows as we iterate. When adjusting budgets, record before/after runs for easy comparison.
