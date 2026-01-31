#!/bin/bash
#
# OpenAkita Quick Start Script
# 
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/openakita/openakita/main/scripts/quickstart.sh | bash
#
# Or download and run:
#   chmod +x quickstart.sh && ./quickstart.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
cat << "EOF"
   ____                      _    _    _ _        
  / __ \                    / \  | | _(_) |_ __ _ 
 | |  | |_ __   ___ _ __   / _ \ | |/ / | __/ _` |
 | |  | | '_ \ / _ \ '_ \ / ___ \|   <| | || (_| |
 | |__| | |_) |  __/ | | /_/   \_\_|\_\_|\__\__,_|
  \____/| .__/ \___|_| |_|                        
        |_|    Your Loyal AI Companion 🐕
EOF
echo -e "${NC}"

echo -e "${CYAN}=== OpenAkita Quick Start ===${NC}\n"

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python is not installed.${NC}"
    echo "Please install Python 3.11 or later from https://www.python.org"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo -e "${RED}Error: Python 3.11+ is required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}\n"

# Check venv module availability
echo -e "${YELLOW}Checking venv module...${NC}"
if ! $PYTHON_CMD -m venv --help &> /dev/null; then
    echo -e "${YELLOW}venv module not available. Trying to install python3-venv...${NC}"
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3-venv python3-pip
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-pip
    else
        echo -e "${RED}Error: Cannot install venv module automatically.${NC}"
        echo "Please install python3-venv manually for your distribution."
        exit 1
    fi
fi
echo -e "${GREEN}✓ venv module is available${NC}\n"

# Create virtual environment first (this avoids PEP 668 issues)
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    $PYTHON_CMD -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}\n"

# Check pip inside venv (venv should include pip, but may need ensurepip)
echo -e "${YELLOW}Checking pip in virtual environment...${NC}"
if ! python -m pip --version &> /dev/null; then
    echo -e "${YELLOW}pip not found in venv. Installing pip...${NC}"
    
    # Try ensurepip first
    if python -m ensurepip --upgrade &> /dev/null; then
        echo -e "${GREEN}✓ pip installed via ensurepip${NC}"
    else
        # Fallback to get-pip.py (safe inside venv)
        echo -e "${YELLOW}Downloading get-pip.py...${NC}"
        if command -v curl &> /dev/null; then
            curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
        elif command -v wget &> /dev/null; then
            wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py
        else
            echo -e "${RED}Error: Neither curl nor wget is available to download pip.${NC}"
            exit 1
        fi
        
        python /tmp/get-pip.py
        rm -f /tmp/get-pip.py
        
        if ! python -m pip --version &> /dev/null; then
            echo -e "${RED}Error: Failed to install pip in virtual environment.${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ pip installed via get-pip.py${NC}"
    fi
fi
echo -e "${GREEN}✓ pip is available${NC}\n"

# Install OpenAkita
echo -e "${YELLOW}Installing OpenAkita...${NC}"
pip install --upgrade pip > /dev/null 2>&1
pip install openakita
echo -e "${GREEN}✓ OpenAkita installed${NC}\n"

# Run setup wizard
echo -e "${CYAN}Starting setup wizard...${NC}\n"
openakita init

echo -e "\n${GREEN}=== Installation Complete ===${NC}"
echo -e "To start OpenAkita, run: ${CYAN}openakita chat${NC}"
echo -e "Or with Telegram: ${CYAN}openakita --telegram${NC}\n"
