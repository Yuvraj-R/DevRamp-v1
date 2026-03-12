#!/bin/bash

# DevRamp Start Script
# Starts all services: Neo4j, KnowledgeCortex, CourseGenerator, Frontend

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$ROOT_DIR/.logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create logs directory
mkdir -p "$LOGS_DIR"

log() { echo -e "${BLUE}[DevRamp]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

# Check if a port is in use
port_in_use() {
    lsof -i :"$1" >/dev/null 2>&1
}

# Kill process on port
kill_port() {
    local port=$1
    local pid=$(lsof -ti :"$port" 2>/dev/null)
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null || true
        sleep 1
    fi
}

# Wait for port to be available
wait_for_port() {
    local port=$1
    local name=$2
    local max_attempts=30
    local attempt=0

    while ! port_in_use "$port"; do
        attempt=$((attempt + 1))
        if [ $attempt -ge $max_attempts ]; then
            error "$name failed to start on port $port"
            return 1
        fi
        sleep 1
    done
    success "$name running on port $port"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Docker
    if ! command -v docker &> /dev/null; then
        error "Docker not installed. Please install Docker first."
        exit 1
    fi

    if ! docker info &> /dev/null; then
        error "Docker is not running. Please start Docker first."
        exit 1
    fi

    # Python
    if ! command -v python3 &> /dev/null; then
        error "Python 3 not installed."
        exit 1
    fi

    # Node
    if ! command -v node &> /dev/null; then
        error "Node.js not installed."
        exit 1
    fi

    success "Prerequisites OK"
}

# Start Neo4j
start_neo4j() {
    log "Starting Neo4j..."
    cd "$ROOT_DIR/KnowledgeCortex"

    # Check if container exists and is running
    if docker ps --format '{{.Names}}' | grep -q 'knowledgecortex-neo4j'; then
        success "Neo4j already running"
        return 0
    fi

    # Check if container exists but stopped
    if docker ps -a --format '{{.Names}}' | grep -q 'knowledgecortex-neo4j'; then
        docker start knowledgecortex-neo4j >/dev/null 2>&1
    else
        docker-compose up -d >/dev/null 2>&1
    fi

    # Wait for Neo4j to be ready
    local max_attempts=30
    local attempt=0
    local neo4j_pass="${NEO4J_PASSWORD:-changeme}"
    while ! docker exec knowledgecortex-neo4j-1 cypher-shell -u neo4j -p "$neo4j_pass" "RETURN 1" >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ $attempt -ge $max_attempts ]; then
            # Try alternate container name
            if docker exec knowledgecortex-neo4j cypher-shell -u neo4j -p "$neo4j_pass" "RETURN 1" >/dev/null 2>&1; then
                break
            fi
            warn "Neo4j taking longer than expected to start (may still be initializing)"
            break
        fi
        sleep 2
    done

    success "Neo4j running on ports 7474 (browser) and 7687 (bolt)"
}

# Setup and start KnowledgeCortex
start_knowledge_cortex() {
    log "Starting KnowledgeCortex..."
    cd "$ROOT_DIR/KnowledgeCortex"

    # Check if already running
    if port_in_use 8000; then
        warn "Port 8000 already in use"
        read -p "Kill existing process? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill_port 8000
        else
            success "Using existing service on port 8000"
            return 0
        fi
    fi

    # Create venv if needed
    if [ ! -d ".venv" ]; then
        log "Creating Python virtual environment..."
        python3 -m venv .venv
    fi

    # Activate and install deps
    source .venv/bin/activate

    if [ ! -f ".venv/.deps_installed" ]; then
        log "Installing KnowledgeCortex dependencies..."
        pip install -r requirements.txt -q
        touch .venv/.deps_installed
    fi

    # Check for .env
    if [ ! -f ".env" ]; then
        warn "KnowledgeCortex/.env not found. Creating template..."
        cat > .env << 'EOF'
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD:-changeme}
OPENAI_API_KEY=your-key-here
EOF
        error "Please add your OPENAI_API_KEY to KnowledgeCortex/.env"
    fi

    # Start server
    nohup python src/api/server.py > "$LOGS_DIR/cortex.log" 2>&1 &
    echo $! > "$LOGS_DIR/cortex.pid"

    wait_for_port 8000 "KnowledgeCortex"
    deactivate
}

# Setup and start CourseGenerator
start_course_generator() {
    log "Starting CourseGenerator..."
    cd "$ROOT_DIR/CourseGenerator"

    # Check if already running
    if port_in_use 8001; then
        warn "Port 8001 already in use"
        read -p "Kill existing process? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill_port 8001
        else
            success "Using existing service on port 8001"
            return 0
        fi
    fi

    # Create venv if needed
    if [ ! -d "venv" ]; then
        log "Creating Python virtual environment..."
        python3 -m venv venv
    fi

    # Activate and install deps
    source venv/bin/activate

    if [ ! -f "venv/.deps_installed" ]; then
        log "Installing CourseGenerator dependencies..."
        pip install -r requirements.txt -q
        touch venv/.deps_installed
    fi

    # Check for .env
    if [ ! -f ".env" ]; then
        warn "CourseGenerator/.env not found. Creating template..."
        cat > .env << 'EOF'
CORTEX_API_URL=http://localhost:8000
OPENAI_API_KEY=your-key-here
EOF
        error "Please add your OPENAI_API_KEY to CourseGenerator/.env"
    fi

    # Create data directory
    mkdir -p data

    # Start server
    nohup python src/api/server.py > "$LOGS_DIR/generator.log" 2>&1 &
    echo $! > "$LOGS_DIR/generator.pid"

    wait_for_port 8001 "CourseGenerator"
    deactivate
}

# Setup and start Frontend
start_frontend() {
    log "Starting Frontend..."
    cd "$ROOT_DIR/DevRamp-ui"

    # Check if already running
    if port_in_use 5173; then
        warn "Port 5173 already in use"
        read -p "Kill existing process? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill_port 5173
        else
            success "Using existing service on port 5173"
            return 0
        fi
    fi

    # Install deps if needed
    if [ ! -d "node_modules" ]; then
        log "Installing frontend dependencies..."
        npm install --silent
    fi

    # Start dev server
    nohup npm run dev > "$LOGS_DIR/frontend.log" 2>&1 &
    echo $! > "$LOGS_DIR/frontend.pid"

    wait_for_port 5173 "Frontend"
}

# Stop all services
stop_all() {
    log "Stopping all DevRamp services..."

    # Stop by PID files
    for pidfile in "$LOGS_DIR"/*.pid; do
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
            fi
            rm "$pidfile"
        fi
    done

    # Kill by port as fallback
    kill_port 5173
    kill_port 8001
    kill_port 8000

    # Stop Neo4j container
    cd "$ROOT_DIR/KnowledgeCortex"
    docker-compose down >/dev/null 2>&1 || true

    success "All services stopped"
}

# Show status
show_status() {
    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "                    DevRamp Status"
    echo "═══════════════════════════════════════════════════════"
    echo ""

    # Neo4j
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'neo4j'; then
        success "Neo4j:           http://localhost:7474"
    else
        error "Neo4j:           not running"
    fi

    # KnowledgeCortex
    if port_in_use 8000; then
        success "KnowledgeCortex: http://localhost:8000"
    else
        error "KnowledgeCortex: not running"
    fi

    # CourseGenerator
    if port_in_use 8001; then
        success "CourseGenerator: http://localhost:8001"
    else
        error "CourseGenerator: not running"
    fi

    # Frontend
    if port_in_use 5173; then
        success "Frontend:        http://localhost:5173"
    else
        error "Frontend:        not running"
    fi

    echo ""
    echo "Logs: $LOGS_DIR/"
    echo "═══════════════════════════════════════════════════════"
    echo ""
}

# Main
main() {
    case "${1:-}" in
        stop)
            stop_all
            ;;
        status)
            show_status
            ;;
        restart)
            stop_all
            sleep 2
            check_prerequisites
            start_neo4j
            start_knowledge_cortex
            start_course_generator
            start_frontend
            show_status
            ;;
        logs)
            case "${2:-}" in
                cortex)
                    tail -f "$LOGS_DIR/cortex.log"
                    ;;
                generator)
                    tail -f "$LOGS_DIR/generator.log"
                    ;;
                frontend)
                    tail -f "$LOGS_DIR/frontend.log"
                    ;;
                *)
                    tail -f "$LOGS_DIR"/*.log
                    ;;
            esac
            ;;
        *)
            echo ""
            echo "  ╔══════════════════════════════════════╗"
            echo "  ║           DevRamp Launcher           ║"
            echo "  ╚══════════════════════════════════════╝"
            echo ""
            check_prerequisites
            start_neo4j
            start_knowledge_cortex
            start_course_generator
            start_frontend
            show_status
            echo "Open http://localhost:5173 to get started!"
            echo ""
            ;;
    esac
}

main "$@"
