# 🕷️ Nexus Crawler

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-6366f1?style=flat-square)](LICENSE)

A distributed web scraping orchestration system built with Python and Redis. Submit crawl jobs via a REST API, distribute work across a horizontally-scalable pool of workers, and monitor progress in real time through a live dashboard — all deployable with a single Docker Compose command.

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │            Redis                         │
  ┌────────┐            │  ┌──────────────┐  ┌─────────────────┐  │
  │ Client │──── REST ──┼─▶│  Task Queue  │  │  Results Store  │  │
  └────────┘            │  └──────┬───────┘  └────────▲────────┘  │
       │                │         │                    │           │
       │                └─────────┼────────────────────┼───────────┘
       │                          │                    │
       ▼                          ▼                    │
  ┌───────────────┐        ┌─────────────┐      ┌─────┴──────┐
  │  Orchestrator │        │  Worker  1  │─────▶│  Scrape &  │
  │     API       │        ├─────────────┤      │   Store    │
  │  :8000        │        │  Worker  2  │─────▶│  Results   │
  └───────────────┘        ├─────────────┤      └────────────┘
                           │  Worker  N  │
                           └─────────────┘
```

---

## Features

- **Distributed scraping** — work fans out across any number of independent worker nodes
- **Per-domain rate limiting** — configurable delays per domain to avoid triggering bans
- **Automatic retries** — failed tasks re-queue with a configurable maximum attempt count
- **URL deduplication** — duplicate URLs within a job are deduplicated before queuing
- **Real-time dashboard** — live React UI shows job progress, worker status, and queue depth
- **Horizontal scaling** — spin up more workers instantly with `--scale worker=N`
- **REST API** — full job lifecycle management over HTTP
- **State tracking** — per-job and per-task status persisted in Redis with TTL

---

## Quick Start

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
git clone https://github.com/ashah5123/nexus-crawler
cd nexus-crawler
docker-compose up --scale worker=3
```

The orchestrator API will be available at `http://localhost:8000`.
Open `dashboard/index.html` in your browser to view the live monitoring dashboard.

Submit your first job:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Crawl",
    "urls": [
      "https://example.com",
      "https://httpbin.org"
    ]
  }'
```

---

## Local Development

**Prerequisites:** Python 3.11+, Redis running on `localhost:6379`

### 1. Clone and install

```bash
git clone https://github.com/ashah5123/nexus-crawler
cd nexus-crawler
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if needed — defaults work out of the box with a local Redis
```

### 3. Start Redis

```bash
# macOS
brew install redis && brew services start redis

# Ubuntu / Debian
sudo apt install redis-server && sudo systemctl start redis
```

### 4. Start the orchestrator

```bash
python3 -m orchestrator.main
# API listening on http://localhost:8000
```

### 5. Start one or more workers (each in its own terminal)

```bash
WORKER_ID=worker-1 python3 -m worker.main
WORKER_ID=worker-2 python3 -m worker.main
```

### 6. Open the dashboard

Open `dashboard/index.html` directly in your browser. It connects to `http://localhost:8000` by default.
To point it at a different host, set `window.NEXUS_API_URL` before the page loads:

```html
<script>window.NEXUS_API_URL = "http://your-host:8000";</script>
```

---

## API Reference

| Method   | Endpoint                  | Description                              |
|----------|---------------------------|------------------------------------------|
| `GET`    | `/health`                 | Health check                             |
| `POST`   | `/jobs`                   | Create and enqueue a new crawl job       |
| `GET`    | `/jobs`                   | List all jobs (newest first)             |
| `GET`    | `/jobs/{job_id}`          | Get a single job by ID                   |
| `GET`    | `/jobs/{job_id}/tasks`    | List all tasks belonging to a job        |
| `DELETE` | `/jobs/{job_id}`          | Cancel a job (marks it as failed)        |
| `GET`    | `/workers`                | List all registered workers              |
| `GET`    | `/stats`                  | Aggregate stats (jobs, workers, queue)   |

### Example requests

```bash
# Create a job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"name": "Docs Crawl", "urls": ["https://docs.example.com"]}'

# Check job status
curl http://localhost:8000/jobs/<job_id>

# List tasks for a job
curl http://localhost:8000/jobs/<job_id>/tasks

# Live stats
curl http://localhost:8000/stats

# Cancel a job
curl -X DELETE http://localhost:8000/jobs/<job_id>
```

### `POST /jobs` request body

| Field  | Type            | Required | Description                        |
|--------|-----------------|----------|------------------------------------|
| `name` | `string`        | ✓        | Human-readable label for the job   |
| `urls` | `string[]`      | ✓        | 1–1000 URLs starting with `http`   |

---

## Environment Variables

| Variable             | Default                    | Description                                           |
|----------------------|----------------------------|-------------------------------------------------------|
| `REDIS_URL`          | `redis://localhost:6379`   | Redis connection URL                                  |
| `HOST`               | `0.0.0.0`                  | Orchestrator bind host                                |
| `PORT`               | `8000`                     | Orchestrator bind port                                |
| `WORKER_ID`          | `worker-<hostname>`        | Unique identifier for a worker instance               |
| `WORKER_CONCURRENCY` | `4`                        | Number of URLs a single worker scrapes in parallel    |

---

## Scaling Workers

Scale the worker pool up or down without restarting the orchestrator or Redis:

```bash
# Start with 5 workers
docker-compose up -d --scale worker=5

# Scale down to 2 (graceful — in-flight tasks complete first)
docker-compose up -d --scale worker=2

# Scale to zero (pause all scraping, queue is preserved)
docker-compose up -d --scale worker=0
```

Worker instances are stateless — they register themselves with Redis on startup and deregister on shutdown. The orchestrator detects offline workers after a 30-second heartbeat timeout and marks them accordingly in the dashboard.

---

## Tech Stack

| Component        | Technology                                                       |
|------------------|------------------------------------------------------------------|
| Orchestrator API | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Queue & State    | [Redis](https://redis.io/) 7                                     |
| HTTP client      | [httpx](https://www.python-httpx.org/) (async)                   |
| HTML parsing     | [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) |
| Data models      | [Pydantic](https://docs.pydantic.dev/) v2                        |
| Workers          | Pure Python asyncio                                              |
| Dashboard        | React 18 (CDN, no build step)                                    |
| Deployment       | [Docker](https://www.docker.com/) + Compose                      |

---

## Project Structure

```
nexus-crawler/
├── orchestrator/
│   ├── api.py          # FastAPI routes and dependency injection
│   ├── main.py         # Uvicorn entrypoint
│   └── state.py        # Job and task lifecycle management
├── worker/
│   ├── main.py         # Worker loop and signal handling
│   ├── scraper.py      # httpx + BeautifulSoup scraping logic
│   └── rate_limiter.py # Per-domain async rate limiter
├── shared/
│   ├── models.py       # Pydantic models (Job, Task, Worker, Result)
│   └── queue.py        # Redis TaskQueue abstraction
├── dashboard/
│   └── index.html      # Single-file React monitoring dashboard
├── Dockerfile.orchestrator
├── Dockerfile.worker
├── docker-compose.yml
└── requirements.txt
```

---

## License

MIT
