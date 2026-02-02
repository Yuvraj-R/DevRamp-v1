# DevRamp

**Faster codebase onboarding through AI-generated, personalized learning courses.**

DevRamp analyzes any GitHub repository and generates interactive courses tailored to what you need to learn. Tell it your role and goals in plain English, and it creates a structured learning path with readings, code walkthroughs, and exercises.

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GitHub URL │ --> │ KnowledgeCortex  │ --> │ CourseGenerator │
│  + Intent   │     │  (Parse & Graph) │     │ (Plan & Create) │
└─────────────┘     └──────────────────┘     └─────────────────┘
                             │                         │
                             v                         v
                    ┌─────────────────────────────────────┐
                    │    Interactive Learning Course      │
                    │  • Readings • Exercises • Quizzes   │
                    └─────────────────────────────────────┘
```

## Architecture

DevRamp is a monorepo with three microservices:

```
DevRamp-v1/
├── DevRamp-ui/        # React frontend
├── KnowledgeCortex/   # Code analysis & knowledge base
└── CourseGenerator/   # AI course generation
```

### DevRamp-ui (Port 5173)

React frontend built with Vite and Tailwind CSS.

- Clean, minimal interface for entering GitHub URLs and learning intent
- Real-time progress tracking during course generation
- Course viewer with sidebar navigation and markdown rendering
- Interactive exercises with immediate feedback

**Stack:** React 19, React Router, Tailwind CSS 4, Vite

### KnowledgeCortex (Port 8000)

The brain of DevRamp. Ingests repositories and builds a queryable knowledge base.

- Clones GitHub repositories
- Parses code using Tree-sitter (Python, JavaScript, TypeScript, Go, Rust, Java, C/C++)
- Builds a Neo4j graph of files, functions, classes, and their relationships
- Generates vector embeddings for semantic search (LanceDB)
- Summarizes code using LLMs
- Provides RAG-based question answering about the codebase

**Stack:** FastAPI, Neo4j, LanceDB, Tree-sitter, OpenAI

### CourseGenerator (Port 8001)

Generates personalized learning courses from the knowledge base.

- Parses natural language learning intent (role, goals, focus areas)
- Plans course structure based on competency levels
- Generates concise, practical content with code references
- Creates exercises matched to skill level
- Stores courses in SQLite for retrieval

**Competency Levels:**
| Level | Name | Focus |
|-------|------|-------|
| 0 | Architecture | System design, how pieces connect |
| 1 | Explain | What the code does |
| 2 | Navigate | Finding your way around |
| 3 | Trace | Following execution paths |
| 4 | Modify | Making targeted changes |
| 5 | Extend | Adding new features |
| 6 | Debug | Diagnosing and fixing issues |

**Stack:** FastAPI, OpenAI (GPT-5.2), SQLite

## Quick Start

### Prerequisites

- **Docker** - For Neo4j database
- **Python 3.11+** - For backend services
- **Node.js 18+** - For frontend
- **OpenAI API key** - Required for LLM calls

### First-Time Setup

1. **Configure environment files**

   Create `KnowledgeCortex/.env`:
   ```bash
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=changeme
   OPENAI_API_KEY=sk-proj-...
   ```

   Create `CourseGenerator/.env`:
   ```bash
   CORTEX_API_URL=http://localhost:8000
   OPENAI_API_KEY=sk-proj-...
   ```

2. **Start everything**

   ```bash
   ./start.sh
   ```

   The script will:
   - Check prerequisites (Docker running, Python, Node)
   - Start Neo4j in Docker
   - Create Python virtual environments if needed
   - Install dependencies (only first run)
   - Start all services in the background
   - Show status dashboard

3. **Open the app**

   Navigate to **http://localhost:5173**

### Managing Services

```bash
./start.sh           # Start all services
./start.sh stop      # Stop all services
./start.sh status    # Check what's running
./start.sh restart   # Restart everything
./start.sh logs      # View all logs
./start.sh logs cortex    # View KnowledgeCortex logs only
./start.sh logs generator # View CourseGenerator logs only
./start.sh logs frontend  # View frontend logs only
```

**Logs location:** `.logs/` directory (gitignored)

**What's running:**
- Neo4j: http://localhost:7474 (browser), bolt://localhost:7687 (database)
- KnowledgeCortex API: http://localhost:8000
- CourseGenerator API: http://localhost:8001
- Frontend: http://localhost:5173

### Manual Setup

If you prefer to run services individually instead of using the start script:

#### 1. Start Neo4j

```bash
cd KnowledgeCortex
docker-compose up -d
```

#### 2. Start KnowledgeCortex

```bash
cd KnowledgeCortex
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/api/server.py
```

#### 3. Start CourseGenerator

```bash
cd CourseGenerator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python src/api/server.py
```

#### 4. Start Frontend

```bash
cd DevRamp-ui
npm install
npm run dev
```

## API Endpoints

### KnowledgeCortex (http://localhost:8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/repos` | List indexed repositories |
| POST | `/repos/ingest` | Ingest a GitHub repository |
| GET | `/repos/{name}` | Get repository details |
| POST | `/query` | Ask questions about a codebase |
| POST | `/search` | Semantic code search |

### CourseGenerator (http://localhost:8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/pipeline/start` | Start full pipeline (clone + ingest + generate) |
| POST | `/generate/start` | Generate course for already-ingested repo |
| GET | `/jobs/{id}` | Get job progress |
| GET | `/courses` | List generated courses |
| GET | `/courses/{id}` | Get course details |

## How It Works

1. **Paste GitHub URL** - User enters a repository URL and describes their learning intent in plain English
2. **Clone & Parse** - KnowledgeCortex clones the repo and parses all source files using Tree-sitter
3. **Build Graph** - Creates a Neo4j graph of files, functions, classes, and relationships
4. **Summarize** - LLM generates concise summaries at file, module, and repository levels
5. **Embed** - Creates vector embeddings for semantic search
6. **Plan Course** - CourseGenerator analyzes the intent and plans a structured learning path
7. **Generate Content** - LLM generates readings, code walkthroughs, and exercises
8. **Interactive Learning** - User works through the course with immediate feedback

## Safeguards

DevRamp includes protections against accidentally burning API credits on irrelevant code:

- **Skipped directories:** `node_modules`, `vendor`, `.venv`, `dist`, `build`, `lib`, `static`, `assets`, caches, IDE files, and 50+ other patterns
- **Skipped files:** Lock files (`package-lock.json`, `yarn.lock`, `Cargo.lock`, etc.)
- **Skipped suffixes:** Minified/bundled code (`*.min.js`, `*.bundle.js`, `*.chunk.js`, etc.)
- **File size limit:** 100KB max per file
- **Minification detection:** Files with lines >1000 chars are skipped (catches minified code that slipped through)

## Troubleshooting

**Port already in use**
```bash
./start.sh stop  # Stop all services first
./start.sh       # Then restart
```

**Neo4j won't start**
```bash
docker ps -a  # Check container status
docker-compose -f KnowledgeCortex/docker-compose.yml down
./start.sh restart
```

**Python dependencies error**
```bash
# Remove virtual environments and reinstall
rm -rf KnowledgeCortex/.venv CourseGenerator/venv
./start.sh  # Will recreate and reinstall
```

**Frontend build error**
```bash
cd DevRamp-ui
rm -rf node_modules package-lock.json
npm install
```

**View logs for debugging**
```bash
./start.sh logs          # All logs
./start.sh logs cortex   # Just KnowledgeCortex
```

## License

MIT
