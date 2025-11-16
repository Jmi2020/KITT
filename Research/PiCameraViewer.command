#!/bin/bash

# Terminal colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Fixed Pi Camera Stream${NC}"
echo -e "${YELLOW}Connecting...${NC}"

# Connect with only essential processing - no color manipulation
echo -e "${GREEN}Connected! Press Q to quit, F for fullscreen${NC}"

# Simplified filter chain that only includes the catchup feature
ffplay udp://@:8080 -fflags nobuffer -flags low_delay -framedrop \
  -vf "setpts=0.5*PTS" \
  -x 1280 -y 720

exit 0