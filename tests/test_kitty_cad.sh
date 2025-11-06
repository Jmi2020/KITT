#!/bin/bash
# Test KITTY CAD conversation with chain-of-thought prompting

set -e

LLAMACPP_URL="http://localhost:8082/completion"
LOG_FILE="logs/kitty_cad_conversation.jsonl"

mkdir -p logs

echo "🤖 KITTY CAD Conversation Test"
echo "📝 Logging to: $LOG_FILE"
echo ""

# Function to query KITTY
query_kitty() {
    local prompt="$1"
    local label="$2"

    echo "================================================================================"
    echo "$label"
    echo "================================================================================"
    echo ""
    echo "🧠 Sending query to KITTY..."
    echo ""

    # Send request to llama.cpp
    response=$(curl -s -X POST "$LLAMACPP_URL" \
        -H "Content-Type: application/json" \
        -d "{
            \"prompt\": $(echo "$prompt" | jq -Rs .),
            \"n_predict\": 512,
            \"temperature\": 0.7,
            \"top_p\": 0.95,
            \"repeat_penalty\": 1.1,
            \"stop\": [\"User:\", \"Assistant:\", \"<|im_end|>\", \"<|endoftext|>\"]
        }")

    # Extract content
    content=$(echo "$response" | jq -r '.content // ""')
    tokens=$(echo "$response" | jq -r '.tokens_predicted // 0')
    time_ms=$(echo "$response" | jq -r '.timings.predicted_ms // 0')
    time_s=$(echo "scale=2; $time_ms / 1000" | bc)

    echo "🤖 KITTY Response:"
    echo "$content"
    echo ""
    echo "⏱️  Generation time: ${time_s}s"
    echo "📊 Tokens: $tokens"
    echo ""

    # Log to JSONL
    log_entry=$(jq -n \
        --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg label "$label" \
        --arg prompt "$prompt" \
        --arg content "$content" \
        --argjson tokens "$tokens" \
        --argjson time_ms "$time_ms" \
        '{timestamp: $timestamp, label: $label, prompt: $prompt, response: $content, tokens: $tokens, time_ms: $time_ms}')

    echo "$log_entry" >> "$LOG_FILE"
}

# Test 1: Chain-of-thought reasoning
PROMPT1='You are KITTY, a warehouse-grade creative and operational AI assistant.

USER QUERY:
What are the pros and cons of coding CAD shapes in Python with CadQuery versus using a GUI like FreeCAD for 3D printing?

Please think through this step-by-step before answering:

<thinking>
1. What is the user asking? Rephrase the core question.
2. What domain expertise is needed? (e.g., mechanical engineering, 3D printing, CAD)
3. What are the key technical considerations and trade-offs?
4. What practical constraints should I consider? (tools available, skill level, materials)
5. What is my recommended approach and why?
</thinking>

Now provide your answer based on the reasoning above. Be concise but complete, and explain your recommendations clearly.

Answer:'

query_kitty "$PROMPT1" "TEST 1: Chain-of-Thought Reasoning - CadQuery vs FreeCAD"

# Test 2: Expert system with spoken output
PROMPT2='You are KITTY, a warehouse-grade creative and operational AI assistant with expertise across CAD modeling, fabrication, and maker technologies.

OPERATING MODE:
- Verbosity: V=3 (detailed)
- Output mode: spoken

REASONING FRAMEWORK:
Before answering, internally reason through:
1. **Expert Role**: What subject matter expert(s) would best answer this query?
2. **Key Concepts**: What are the core technical concepts, trade-offs, and considerations?
3. **User Intent**: What is the user really trying to accomplish? What are their constraints?
4. **Response Strategy**: How should I structure my answer given the verbosity and output mode?

USER QUERY:
I want to print a custom mounting bracket for my workshop. Should I code it or use CAD software?

RESPONSE INSTRUCTIONS:
Your response will be converted to speech, so:
- Use natural, conversational language
- Avoid markdown, URLs, or formatting
- Break complex ideas into clear spoken sentences
- Use verbal transitions ("first", "next", "finally")
- Explain technical terms in plain language

First, briefly state your expert role and approach. Then provide your authoritative answer following the reasoning framework above. Be practical, honest about trade-offs, and cite specific examples where helpful.

If the question involves CAD or fabrication, consider:
- Parametric vs organic modeling approaches
- Manufacturability and material constraints
- Tool selection (FreeCAD, OpenSCAD, CadQuery, Zoo, Tripo, etc.)
- Print orientation, supports, and post-processing

Answer:'

query_kitty "$PROMPT2" "TEST 2: Expert System (Spoken Mode) - Custom Mounting Bracket"

# Test 3: Terse response
PROMPT3='You are KITTY, a warehouse-grade creative and operational AI assistant with expertise across CAD modeling, fabrication, and maker technologies.

OPERATING MODE:
- Verbosity: V=1 (extremely terse)
- Output mode: spoken

USER QUERY:
Best tool for parametric sheet metal designs?

RESPONSE INSTRUCTIONS:
Your response will be converted to speech, so:
- Use natural, conversational language
- Avoid markdown, URLs, or formatting
- Be extremely brief and to the point

Answer:'

query_kitty "$PROMPT3" "TEST 3: Terse Expert Response (V=1) - Sheet Metal Tool"

echo "================================================================================"
echo "✅ Conversation logged to: $LOG_FILE"
echo "================================================================================"

# Send completion notification
if [[ -x "ops/scripts/notify.sh" ]]; then
    ./ops/scripts/notify.sh "KITTY Test Complete" "CAD conversation test finished. Results in $LOG_FILE" "Glass"
fi
