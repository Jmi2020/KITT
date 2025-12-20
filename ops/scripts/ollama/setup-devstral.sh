#!/bin/bash
# Setup Devstral 2 123B in Ollama
#
# Prerequisites:
# - Model downloaded via huggingface-cli to ~/models/devstral2/Q5_K_M/
# - Ollama running (ollama serve)
#
# Usage:
#   ./ops/scripts/ollama/setup-devstral.sh

set -e

MODEL_DIR="${HOME}/models/devstral2/Q5_K_M/mistralai_Devstral-2-123B-Instruct-2512-Q5_K_M"
# Split GGUF - reference first file, Ollama finds the rest automatically
GGUF_FILE="${MODEL_DIR}/mistralai_Devstral-2-123B-Instruct-2512-Q5_K_M-00001-of-00003.gguf"

# Check if model exists
if [ ! -f "$GGUF_FILE" ]; then
    echo "Error: Model file not found at $GGUF_FILE"
    echo ""
    echo "Download the model first:"
    echo "  huggingface-cli download bartowski/mistralai_Devstral-2-123B-Instruct-2512-GGUF \\"
    echo "    --include 'mistralai_Devstral-2-123B-Instruct-2512-Q5_K_M/*' \\"
    echo "    --local-dir ~/models/devstral2/Q5_K_M"
    exit 1
fi

# Create Modelfile
MODELFILE=$(mktemp)
cat > "$MODELFILE" << 'EOF'
# Devstral 2 123B Q5_K_M
# Mistral's agentic coding model optimized for software development tasks
FROM {{MODEL_PATH}}

# Optimized parameters for coding tasks
PARAMETER temperature 0.2
PARAMETER num_ctx 16384
PARAMETER num_predict 8192
PARAMETER stop "<|im_end|>"
PARAMETER stop "</s>"

# System template for coding
TEMPLATE """{{if .System}}{{.System}}

{{end}}{{if .Prompt}}{{.Prompt}}{{end}}"""

# Default system prompt for coding tasks
SYSTEM """You are an expert software developer. You write clean, efficient, and well-documented code.
When given a task, you:
1. Plan your implementation carefully
2. Write complete, working code
3. Include proper error handling
4. Add helpful comments where needed
5. Consider edge cases"""
EOF

# Replace placeholder with actual path
sed -i '' "s|{{MODEL_PATH}}|$GGUF_FILE|g" "$MODELFILE"

echo "Creating Ollama model 'devstral:123b'..."
ollama create devstral:123b -f "$MODELFILE"

# Cleanup
rm -f "$MODELFILE"

echo ""
echo "Devstral 2 123B successfully installed!"
echo ""
echo "Test with:"
echo "  ollama run devstral:123b 'Write a Python function to check if a number is prime'"
echo ""
echo "Or use the coding UI at http://localhost:4173/coding"
