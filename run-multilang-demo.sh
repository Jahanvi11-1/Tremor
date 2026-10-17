#!/bin/bash
#
# Quick demo of multi-language parsing
# Run with: ./run-multilang-demo.sh
#

set -e  # Exit on error

echo "======================================================================"
echo "TREMOR MULTI-LANGUAGE DEMO"
echo "======================================================================"
echo ""

# Step 1: Check if Docker is running
echo "Step 1: Checking Docker..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ ERROR: Docker is not running. Please start Docker and try again."
    exit 1
fi
echo "✅ Docker is running"
echo ""

# Step 2: Start FalkorDB
echo "Step 2: Starting FalkorDB..."
docker compose up -d
sleep 3  # Give it a moment to start
echo "✅ FalkorDB started"
echo ""

# Step 3: Check Python environment
echo "Step 3: Setting up Python environment..."
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Step 4: Install dependencies
echo "Step 4: Installing dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Step 5: Initialize demo repo git history (if needed)
echo "Step 5: Preparing demo repository..."
if [ ! -d "demo-multi-lang/.git" ]; then
    echo "Initializing git repo for demo..."
    cd demo-multi-lang
    git init > /dev/null 2>&1
    git config user.email "demo@example.com"
    git config user.name "Demo User"
    git add -A
    git commit -m "Initial commit: Multi-language demo" > /dev/null 2>&1
    cd ..
fi
echo "✅ Demo repository ready"
echo ""

# Step 6: Load multi-language repository
echo "======================================================================"
echo "Step 6: Loading multi-language repository into FalkorDB..."
echo "======================================================================"
echo ""

REPO_PATH=./demo-multi-lang python src/multi_loader.py

echo ""
echo "======================================================================"
echo "DEMO COMPLETE!"
echo "======================================================================"
echo ""
echo "The demo repository has been loaded into FalkorDB."
echo ""
echo "What's loaded:"
echo "  • 3 modules (2 Python + 1 SQL)"
echo "  • 13 functions (9 Python + 4 SQL)"
echo "  • All nodes tagged with 'language' property"
echo ""
echo "Next steps:"
echo ""
echo "1. Open FalkorDB Browser:"
echo "   http://localhost:3000"
echo ""
echo "2. Try these Cypher queries:"
echo ""
echo "   # View all modules"
echo "   MATCH (m:Module) RETURN m.name, m.language, m.path"
echo ""
echo "   # View all functions by language"
echo "   MATCH (f:Function)"
echo "   RETURN f.language, count(f) AS count"
echo "   ORDER BY count DESC"
echo ""
echo "   # View SQL procedures"
echo "   MATCH (f:Function {language:'sql'})"
echo "   RETURN f.name, f.module"
echo ""
echo "   # View Python functions"
echo "   MATCH (f:Function {language:'python'})"
echo "   RETURN f.name, f.module"
echo "   ORDER BY f.name"
echo ""
echo "   # View function calls"
echo "   MATCH (f1:Function)-[:CALLS]->(f2:Function)"
echo "   RETURN f1.name, f1.language, f2.name, f2.language"
echo ""
echo "3. View file contents:"
echo "   demo-multi-lang/backend/api.py"
echo "   demo-multi-lang/backend/database.py"
echo "   demo-multi-lang/db/procedures.sql"
echo ""
echo "4. Try with your own repo:"
echo "   REPO_PATH=/path/to/your/repo python src/multi_loader.py"
echo ""
echo "5. Read full guide:"
echo "   cat QUICKSTART_MULTILANG.md"
echo ""
echo "======================================================================"
