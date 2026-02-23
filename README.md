# Global Events Risk Intelligence Dashboard

A real-time geopolitical risk dashboard that aggregates conflict and crisis events from public sources, applies natural language processing and machine learning to assess severity and threat, and visualizes global risk across an interactive 3D map.

**👉 [Start here: Full technical overview](docs/PROJECT_OVERVIEW.md)** – What the system does, how it works end-to-end, data science methods, and talking points for interviews.

## What it does

- **Live global risk map** – Interactive Mapbox 3D globe color-coded by risk tier (critical/high/medium/low/info)
- **Event intelligence** – Real-time event feed with severity scores, classification (armed conflict, civil unrest, terrorism, etc.), and sentiment analysis
- **Risk scoring** – ML-powered severity assessment using NLP, geopolitical context, and structured signals; baseline anomaly detection for spikes
- **Country deep-dives** – Click any country to see recent events, news, risk trends, risk context, and related countries
- **Analytics & movers** – Track which countries are rising/falling in risk tier, risk distribution histograms, category breakdowns
- **Data sources** – GDELT (open event archive, no auth) + Valyu (premium conflict intelligence API with keyword filtering and expert curation)

## Tech stack

| Backend | Frontend |
|---------|----------|
| Python 3.11+ | React 19, TypeScript |
| FastAPI (REST API) | Mapbox GL (3D globe) |
| SQLAlchemy + SQLite | Recharts (analytics) |
| scikit-learn + spaCy (ML/NLP) | Zustand (state management) |
| pandas, scipy, statsmodels | Tailwind CSS, Parcel (bundler) |

## Data sources

- **GDELT** – Public event database (15M+ events, daily updates). No authentication required. Data flow: CSV → normalize → daily metrics → API.
- **Valyu** – Premium conflict intelligence (curated events, keyword filtering, expert classification). Requires API key. Data flow: REST API → normalize → same pipeline.

Both sources feed the same ML pipeline (severity scoring, entity extraction, event classification, anomaly detection, trend analysis).

## Getting started

### Prerequisites

- **Node.js** 18+ (for frontend)
- **Python** 3.11+ (for backend)
- **API keys:**
  - `MAPBOX_TOKEN` – Get free at https://account.mapbox.com/ (required for 3D map)
  - `VALYU_API_KEY` – Request at https://valyu.network/ (required for live event data; optional if you only want GDELT)

### Quick Start (TL;DR)

```bash
# Terminal 1: Backend
source .venv/bin/activate  # Or create: python -m venv .venv && source .venv/bin/activate
./run-backend.sh
# → API at http://localhost:8000 | Docs at http://localhost:8000/docs

# Terminal 2: Frontend
cd frontend && npm run dev
# → App at http://localhost:1234
```

### 1. Clone and set up backend

```bash
# Clone repo
git clone <repo-url>
cd "Global Events Risk Intelligence Dashboard"

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# (Optional) Load historical data from GDELT
python -m backend.app.pipeline.run_day1 --days 14

# (Optional) Compute risk scores and detect anomalies
python -m backend.app.pipeline.run_day2

# Start backend API (from project root)
./run-backend.sh
# API runs at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

**Note:** The backend requires Python 3.11+. If `python` command not found, use `python3`.

### 2. Set up and run frontend

```bash
cd frontend

# Install dependencies (--legacy-peer-deps handles version conflicts)
npm install --legacy-peer-deps

# Set up environment
cp .env.example .env

# Edit .env and fill in your tokens:
cat .env
# - API_URL=http://localhost:8000 (or your backend URL)
# - MAPBOX_TOKEN=your_mapbox_token_here (get free at https://account.mapbox.com/)
# - VALYU_API_KEY=your_valyu_api_key_here (request at https://valyu.network/ — optional)

# Start dev server (from frontend/ directory)
npm run dev
# App opens at http://localhost:1234
# HMR (hot reload) enabled — changes auto-refresh
```

**Note on dependencies:** The `--legacy-peer-deps` flag is required due to peer dependency conflicts in mapbox-gl and three.js. This is expected and safe.

### 3. Live data ingestion (optional)

The dashboard ships with historical data. To continuously pull fresh events:

```bash
# From project root:
python -m backend.app.pipeline.run_live

# Or trigger via the API:
curl -X POST http://localhost:8000/pipeline/run-valyu
```

---

## Project structure

```
Global Events Risk Intelligence Dashboard/
├── backend/                    # FastAPI + ML pipeline
│   ├── app/
│   │   ├── main.py            # App factory, router registration
│   │   ├── db.py              # SQLAlchemy engine
│   │   ├── models.py          # ORM (Event, DailyMetric, Spike, RiskSnapshot)
│   │   ├── ml/                # 7 ML modules
│   │   │   ├── severity_scorer.py     # NLP severity 0–100
│   │   │   ├── event_classifier.py    # Predict event category
│   │   │   ├── risk_classifier.py     # Map severity → risk tier
│   │   │   ├── entity_extractor.py    # Extract people/places/orgs
│   │   │   ├── trend_detector.py      # 7d/30d trend (up/down/stable)
│   │   │   ├── anomaly_detection.py   # Detect spikes
│   │   │   └── time_series.py         # EWMA, STL decomposition
│   │   ├── pipeline/          # ETL pipeline
│   │   │   ├── ingest_gdelt.py        # Fetch GDELT CSV
│   │   │   ├── ingest_valyu.py        # Fetch Valyu REST API
│   │   │   ├── normalize.py           # Standardize → ORM rows
│   │   │   ├── aggregate_daily.py     # Group by country/date → metrics
│   │   │   ├── day2_baselines_risk.py # Baselines, z-scores, risk
│   │   │   └── run_live.py            # Orchestrate live ingest
│   │   └── routes/            # 13 REST endpoints (map, events, metrics, etc.)
│   ├── requirements.txt        # Python dependencies
│   └── tests/
│
├── frontend/                   # React + TypeScript + Mapbox GL
│   ├── src/
│   │   ├── App.tsx            # Root component, tab routing
│   │   ├── api.ts             # All HTTP calls + TypeScript types
│   │   ├── components/        # 15+ React components (map, sidebar, panels, etc.)
│   │   │   ├── MapboxGlobe.tsx   # 3D globe, auto-rotate, click/hover
│   │   │   ├── CountryPanel.tsx  # Slide-in: context, metrics, events, news
│   │   │   ├── EventCard.tsx     # Event display in feed
│   │   │   └── ...
│   │   └── stores/            # Zustand state (selected country, filters)
│   ├── index.html             # Entry point
│   ├── .env.example           # Env template
│   └── package.json
│
├── docs/                      # Design documents, schema, roadmaps
├── migrations/                # Database migrations
├── run-backend.sh             # Start backend with hot-reload
└── README.md                  # This file
```

---

## ML pipeline explained

The data flows through a two-phase pipeline:

### Phase 1: Ingest + Normalize
Raw events (GDELT CSV or Valyu API) → standardized ORM `Event` rows → `DailyMetric` aggregates by country/date.

### Phase 2: Risk Scoring
1. **Severity scoring** – NLP analyzes event text for keywords, sentiment, and geopolitical context. Outputs 0–100 score.
2. **Event classification** – ML classifies event into 1 of 12 categories (armed conflict, civil unrest, terrorism, crime, diplomatic incident, etc.)
3. **Entity extraction** – Identifies people, places, organizations mentioned (military bases, key actors, etc.)
4. **Risk tier mapping** – Converts severity score to tier (info / low / medium / high / critical) using Jenks natural breaks + real-world anchors.
5. **Anomaly detection** – Detects spikes: events ≥2 std deviations above rolling baseline.
6. **Trend detection** – Calculates 7-day and 30-day trend direction (up / down / stable) using slope analysis.

All metrics (severity, tier, trend, spike status, top category) are cached in `daily_metrics` for fast API response.

---

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness check |
| `GET /map` | All countries with lat/lon, risk tier, severity, event count |
| `GET /countries/{code}/insights` | Deep dive: recent events, news, risk context, related countries |
| `GET /events` | Event feed with filters |
| `GET /metrics` | Country risk metrics and trends |
| `GET /spikes` | Anomalies (events > 2σ above baseline) |
| `GET /brief` | Daily summary by date |
| `GET /analytics/*` | Risk distribution, tier breakdowns, sparklines, movers |
| `POST /pipeline/run-valyu` | Trigger fresh Valyu ingest |
| `POST /pipeline/re-enrich` | Re-score all existing events (useful after ML updates) |

Full docs: http://localhost:8000/docs (after backend starts)

---

## Running tests

```bash
# Backend tests (from project root)
pytest backend/tests/ -v
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `python: command not found` | Use `python3` instead (e.g., `python3 -m venv .venv`) |
| `./run-backend.sh: not found` | Make sure you're in project root, not inside `backend/` folder. Or run: `cd .. && ./run-backend.sh` |
| Frontend won't load | Check `.env` has `API_URL=http://localhost:8000` and backend is running on port 8000 |
| No Mapbox token | Map will be blank; get a free token at https://account.mapbox.com/ and add to `frontend/.env` |
| Port 8000 or 1234 in use | Kill conflicting process or change port in `run-backend.sh` (line 11) and `frontend/package.json` (dev script) |
| `npm ERR! code ERESOLVE` | This is expected; use `npm install --legacy-peer-deps` as shown above |

---

## Building for production

**Backend** – Deploy the `backend/` folder as a FastAPI app. SQLite is fine for small-to-medium scale; swap to PostgreSQL if needed.

**Frontend** – Build and deploy the `frontend/dist/` folder:
```bash
cd frontend
npm run build
# dist/ folder ready for static hosting (Vercel, Netlify, S3, etc.)
```

---

## Why this exists

Geopolitical risk intelligence is expensive and fragmented. This project demonstrates:
- How to stitch together multiple data sources into a unified feed
- How to apply NLP/ML to increase signal-to-noise (severity scoring, anomaly detection)
- How to build a fast, interactive dashboard at scale (Mapbox 3D, real-time filtering, caching)
- That open data (GDELT) + smart processing beats proprietary blobs

---

## Notes

- **No AI disclaimer needed** – This is a data pipeline + visualization. No LLMs or generative models.
- **Transparency** – All scoring logic is deterministic and auditable (see `backend/app/ml/` for equations).
- **Reproducibility** – Running the pipeline again produces the same results (deterministic, no randomness in production).

---

## License

[Add license here]

## Contact

[Add contact info here]
