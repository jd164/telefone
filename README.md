# Phone Number Intelligence & Scam Detection Platform 🇵🇹 🌐

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/Tests-105%20Passing-emerald.svg)](https://pytest.org)
[![Zero-Paid-APIs](https://img.shields.io/badge/APIs-100%25%20Free%20%2F%20Zero--Cost-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

A production-grade, modular asynchronous intelligence platform designed to aggregate, analyze, and score incoming and unknown phone numbers. Primarily optimized for the **Portuguese telecommunications ecosystem (`+351...`, ANACOM PNN)** with full international number compatibility.

The platform provides multi-layered intelligence: regulatory metadata, curated official directories, dynamic geographic institutional block clustering, multi-source OSINT consensus dorking, and real-time community reputation scrapers—**requiring zero paid APIs**.

---

## 🚀 Key Architectural Layers

```
                               Incoming Phone Number (+351...)
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
         Layer 1: Normalizer                                  Layer 2: ANACOM PNN
      (E.164, Carrier, Type)                               (Allocations, Area, VoIP)
                    │                                                   │
                    └─────────────────────────┬─────────────────────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
     Layer 3: Official Directory                         Layer 4: Geographic Matcher
  (Exact match: PSP, GNR, SNS)                       (Dynamic 70+ Institutional Blocks)
                    │                                                   │
                    └─────────────────────────┬─────────────────────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
       Layer 5: OSINT Dork Engine                         Layer 6: Community Scrapers
   (DDG / Brave / Bing Consensus)                      (Tellows, Ligaram-me, ShouldIAnswer)
                    │                                                   │
                    └─────────────────────────┬─────────────────────────┘
                                              ▼
                                 Layer 7: Risk Synthesizer
                        ┌────────────────────────────────────────┐
                        │  Risk Score (0 - 100) & Risk Level     │
                        │  Confidence Score (HIGH / MEDIUM / LOW)│
                        │  Categorization & Bilingual Advice     │
                        └────────────────────────────────────────┘
```

### 1. Regulatory Lookup: ANACOM National Numbering Plan (PNN)
- Offline database mapping all Portuguese operator allocations and geographic areas:
  - **Geographic Fixed**: `21` (Lisbon), `22` (Porto), `231–239` (Central), `241–249`, `251–259` (North), `261–269`, `271–279`, `281–289` (Algarve/Alentejo), `291` (Madeira), `292/295/296` (Azores).
  - **Mobile Allocations**: `91` (Vodafone), `921–927` (MEO), `929` (NOS), `93` (NOS), `96` (MEO), `94` (DIGI).
  - **Nomadic VoIP**: `300–309` ranges (Twilio, Colt, DIDWW, NOS, MEO, Vodafone) with automated nomadic risk baseline adjustment.
  - **Special Services**: `800` (Toll-free), `808` (Shared cost), `707/708` (Universal access), `760/761/762` (Premium mass calling), `112` (National Emergency).

### 2. Verified Official Directory
- Curated offline directory of **189+ official public entities**:
  - National police headquarters, metropolitans, division stations, and territorial detachments (PSP, GNR, PJ).
  - Public healthcare emergency lines (SNS 24, INEM, central and district hospitals).
  - Victim support lines (APAV `116006`, SOS Criança `116111`).
  - Municipal councils and tax authority lines (AT, Segurança Social, CTT).
- Exact match assigns **Risk: 0, Confidence: HIGH, Matched: `trusted_directory_exact`**.

### 3. Dynamic Institutional Block Matcher (`geographic_matcher.py`)
- Automatically clusters verified official numbers by 4-digit and 5-digit prefix ranges across each Portuguese district.
- **70+ active dynamic blocks** in Lisbon, Porto, Coimbra, Braga, Setúbal, Faro, and all administrative districts.
- Automatically handles unlisted suburban police stations and hospital extensions, granting **Confidence: MEDIUM, Risk: 10, Matched: `geographic_prefix_inference`**.

### 4. Zero-Cost OSINT Dork Engine with Multi-Source Consensus (`dork_engine.py`)
- Dispatches broad, non-domain-restricted OSINT queries across free HTML engines (**DuckDuckGo HTML**, **Brave Search HTML**, and **Bing HTML**):
  - `"<number>" PSP`, `"<number>" GNR`, `"<number>" esquadra`, `"<number>" polícia`
- **Institutional Signal Detection (`detect_institutional_signal`)**: Analyzes search snippet text for official police/hospital keywords regardless of the source website domain (e.g. municipal portals, parish councils `jf-*.pt`, national news).
- **Proportional Consensus Scoring**:
  - **1 independent source**: `confidence: MEDIUM`, `matched_by: "dork_inference"`, `risk: 10`.
  - **2+ independent sources**: `confidence: HIGH`, `matched_by: "dork_consensus"`, `risk: 0–5`.
- **Per-Number Debug Logging**: Automatically writes raw query parameters, extracted snippets, and detected regex patterns to `data/dork_debug/<number>.json`.

### 5. Multi-Source Community Reputation Scrapers
- Concurrently queries open crowdsourced spam and complaint databases:
  - **Tellows** (score normalization, search counts)
  - **Ligaram-me** & **QuemLiga** (Portuguese community feedback)
  - **ShouldIAnswer** (sentiment & scam tag detection)
  - **UnknownPhone** (international scam reports)

### 6. Strict Separation of Risk Score and Confidence
- **Risk Score (0–100)**: Reflects the likelihood of the caller being malicious (Burla MBWay, phishing, aggressive telemarketing, silent robocalls).
- **Confidence (HIGH / MEDIUM / LOW)**: Reflects the amount and reliability of data supporting the evaluation.
- Risk is locked to `0` ONLY on high-confidence exact directory matches or multi-source OSINT consensus.

---

## 📁 Repository Structure

```text
telefone/
├── app/
│   ├── api/
│   │   └── routes.py              # FastAPI endpoints (/lookup, /report, /history, /admin)
│   ├── core/
│   │   ├── config.py              # Pydantic settings & environment configuration
│   │   └── observability.py       # Pipeline telemetry & per-number dork debug logging
│   ├── db/
│   │   ├── models.py              # SQLite models (SearchCache, UserReport, LookupHistory, DorkCache)
│   │   └── session.py             # Asynchronous SQLAlchemy session generator
│   ├── engine/
│   │   ├── normalizer.py          # libphonenumber validator & line classifier
│   │   ├── anacom.py              # ANACOM PNN database & prefix parser
│   │   ├── trusted_directory.py   # Verified official directory (189+ police, hospitals, government)
│   │   ├── geographic_matcher.py  # 70+ dynamic institutional prefix clustering engine
│   │   ├── aggregator.py          # Parallel execution coordinator & risk synthesizer
│   │   └── scrapers/
│   │       ├── base.py            # Async scraper base with User-Agent & jitter rotation
│   │       ├── dork_engine.py     # OSINT search dorking with multi-source consensus
│   │       ├── tellows.py         # Tellows integration
│   │       ├── quem_liga.py       # Ligaram-me & ShouldIAnswer scrapers
│   │       ├── search_entity.py   # DuckDuckGo commercial entity verification
│   │       └── unknown_phone.py   # International crowd-sourced reports
│   ├── models/
│   │   └── schemas.py             # Pydantic schemas (requests, responses, telemetry)
│   ├── static/
│   │   ├── css/style.css          # Glassmorphism dark mode stylesheet
│   │   └── js/app.js              # Interactive dashboard with real-time badges
│   ├── templates/
│   │   └── index.html             # Web dashboard interface
│   └── main.py                    # Application entry point & lifespan
├── data/
│   ├── anacom_pnn_pt.json         # Complete Portuguese National Numbering Plan
│   └── paginas_amarelas_pt.json   # Seed verified institutional directory
├── docs/
│   └── index.html                 # Interactive GitHub Pages documentation & demo showcase
├── tests/
│   ├── test_normalizer.py         # Number normalization tests
│   ├── test_anacom.py             # ANACOM prefix resolution tests
│   ├── test_aggregator.py         # Risk synthesis & scoring tests
│   ├── test_dork_engine.py        # Signal detection, consensus, & debug logging tests
│   ├── test_known_numbers.py      # Comprehensive 75-number benchmark dataset
│   └── test_api.py                # API endpoint tests
├── Dockerfile
├── requirements.txt
├── .gitignore
├── .env.example
└── README.md
```

---

## ⚡ Quick Start

### 1. Local Setup

```bash
# Clone the repository
git clone https://github.com/jd164/telefone.git
cd telefone

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The web dashboard is now accessible at `http://127.0.0.1:8000`.

### 2. Running with Docker

```bash
# Build the container
docker build -t telefone-intel .

# Run the container
docker run -d -p 8000:8000 --name telefone-app telefone-intel
```

---

## 📡 API Endpoints

### 1. Number Lookup
`GET /api/v1/lookup?number={phone}&refresh={bool}`

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/lookup?number=217657500"
```

**Response Example:**
```json
{
  "normalized": {
    "raw_input": "217657500",
    "e164": "+351217657500",
    "national_format": "217 657 500",
    "country_code": 351,
    "country_name": "Portugal",
    "line_type": "FIXED_LINE",
    "is_valid": true
  },
  "risk_score": 0,
  "risk_level": "LOW",
  "confidence": "HIGH",
  "matched_by": "trusted_directory_exact",
  "caller_category": "Entidade Oficial (PSP Direção Nacional)",
  "recommendation": "Número oficial e verificado (PSP Direção Nacional). Contacto legítimo de utilidade pública e segurança.",
  "commercial_entity": {
    "is_commercial_entity": true,
    "entity_name": "PSP Direção Nacional",
    "category": "Força de Segurança / Polícia",
    "website": "https://www.psp.pt",
    "address": "Lisboa"
  }
}
```

### 2. Admin Directory Statistics
`GET /api/v1/admin/directory-stats`

Returns live metrics regarding curated versus dynamically discovered entities:
```json
{
  "total_entries": 189,
  "curated_count": 161,
  "scraped_count": 28,
  "by_agency": {
    "PSP": 82,
    "GNR": 17,
    "PJ": 5,
    "Hospitais / Saúde": 18,
    "Câmaras / Autarquias": 23,
    "Serviços Públicos": 11
  },
  "active_institutional_blocks": 70
}
```

### 3. District Coverage Report
`GET /api/v1/admin/coverage-report`

Reports exact directory matches and dynamic institutional blocks across all 20 Portuguese districts.

---

## 🧪 Automated Testing

The project includes an exhaustive automated test suite with **105 passing unit, integration, and benchmark tests**:

```bash
# Run all tests
python -m pytest tests/ -v
```

Test coverage includes:
- **75 Known Numbers Benchmark**: Real-world validation of police stations across all districts, hospital centers, victim support lines, and telemarketing/scam numbers.
- **Dork Engine Tests**: Institutional regex signal detection, 1-source inference, 2+ source consensus, and debug logging.
- **ANACOM PNN Resolution**: Fixed geographic, mobile carriers (Vodafone, MEO, NOS, DIGI), nomadic VoIP (Twilio, Colt), and toll-free ranges.
- **Full API Route Tests**: Health checks, prefix lookups, user reporting, and lookup history.

---

## 🔒 Privacy & Zero Paid APIs Policy

- **Zero Paid APIs**: The entire architecture operates through offline regulatory databases, curated official records, and resilient free search engine scraping.
- **No Third-Party Leakage**: Personal phone numbers are never transmitted to commercial analytics vendors.
- **Isolated Debug Logs**: Raw search debug outputs are kept locally in `data/dork_debug/` and excluded from source control.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
