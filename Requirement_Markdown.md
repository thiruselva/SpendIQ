# SpendIQ — Implementation Guide

> Smart personal spending intelligence app for local use.  
> Built for: Generic Family · Local Use · May 2026

---

## Table of contents

1. [Overview](#overview)
2. [Core principles](#core-principles)
3. [Tech stack](#tech-stack)
4. [Architecture](#architecture)
5. [Invoice processing pipeline](#invoice-processing-pipeline)
6. [AI integration strategy](#ai-integration-strategy)
7. [Database design](#database-design)
8. [UI design](#ui-design)
9. [Feature modules](#feature-modules)
10. [Project structure](#project-structure)
11. [Setup guide](#setup-guide)
12. [Cost estimates](#cost-estimates)
13. [Roadmap](#roadmap)

---

## Overview

SpendIQ is a locally-running desktop application that aggregates spending data from multiple sources — Gmail receipts, Outlook bills, uploaded PDFs, and manual entries — into a single intelligent dashboard. It uses Claude AI selectively for insights, not for routine data operations.

**Problem it solves:** A household accumulates hundreds of receipts across Walmart, Costco, Amazon, DoorDash, subscriptions, healthcare, and dental. Most of this data is scattered across two email inboxes and numerous PDF invoices with no unified view, no pattern analysis, and no shopping optimization.

**What it is not:** A cloud service, a subscription app, or a bank integration tool. All data stays on your machine.

---

## Core principles

| Principle | What it means |
|-----------|---------------|
| **Extract once** | Run the PDF batch job once. Never re-upload the same invoice. |
| **SQL first, AI second** | Database aggregates data; Claude only sees summaries. |
| **Local by default** | Transactions, receipts, and history never leave your machine except for explicit AI queries. |
| **Cheap AI calls** | Haiku for extraction ($0.25/M tokens), Sonnet for insights only when needed. |
| **Reuse what exists** | The SpendIQ HTML prototype is ~70% of the React code — port it, don't rewrite. |

---

## Tech stack

### Why Electron + React + FastAPI + SQLite

```
UI layer         →   React 18 + Tailwind CSS
Desktop shell    →   Electron 30 (wraps React into .exe / .app)
Backend          →   FastAPI (Python 3.11), runs on port 8765
Database         →   SQLite (single .db file, zero config)
AI               →   Anthropic API (Haiku for parsing, Sonnet for insights)
PDF parsing      →   pdfplumber + pandas
Email sync       →   Gmail API (OAuth2) + Microsoft Graph API (Outlook)
```

### Why not the alternatives

| Option | Why rejected |
|--------|-------------|
| **Tauri** | Requires Rust for backend. Python needed anyway for PDF parsing and AI — adds complexity without benefit. |
| **Streamlit** | Runs in a browser tab, not a real app. Cannot match the SpendIQ UI design. Limits interactivity. |
| **Next.js** | Excellent choice but overkill for a local app — adds unnecessary build complexity for single-user local use. |
| **Plain HTML file** | No persistence. Data resets on every reload. No file system access. |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Your machine                           │
│                                                             │
│  ┌─────────────────┐         ┌──────────────────────────┐   │
│  │  Electron shell │         │     FastAPI backend       │   │
│  │                 │  HTTP   │     (port 8765)           │   │
│  │  React UI       │◄───────►│                          │   │
│  │  - Dashboard    │         │  Routes:                 │   │
│  │  - Transactions │         │  GET  /transactions      │   │
│  │  - Insights     │         │  POST /transactions      │   │
│  │  - Shopping     │         │  POST /import/pdf        │   │
│  │  - Import       │         │  POST /import/csv        │   │
│  │                 │         │  GET  /insights/summary  │   │
│  └─────────────────┘         │  POST /ai/analyze        │   │
│                               │  POST /ai/shopping-list  │   │
│                               │                          │   │
│                               │  SQLite (.db file)       │   │
│                               │  pdfplumber parser       │   │
│                               │  pandas CSV parser       │   │
│                               └──────────┬───────────────┘   │
│                                          │                   │
└──────────────────────────────────────────┼───────────────────┘
                                           │ HTTPS (on demand only)
                              ┌────────────▼──────────────┐
                              │   Anthropic Claude API    │
                              │                           │
                              │  Haiku  → extraction      │
                              │  Sonnet → insights        │
                              └───────────────────────────┘
```

### What crosses the network

Only three actions send data to Anthropic:

1. **"Analyze my spending" button** — sends a text summary of aggregated totals (~300 tokens), not raw transactions
2. **"AI generate list" button** — sends purchase frequency patterns (~200 tokens)
3. **Batch invoice parser** — sends extracted PDF text for each invoice once during the initial setup job

Everything else — charts, filters, transaction CRUD, shopping list management — is pure local logic.

---

## Invoice processing pipeline

This is the most important design decision. 190 invoices must never be re-uploaded on every session.

### Stage 1 — Local text extraction (free)

```python
# extract_invoices.py
import pdfplumber
import os
import json

INVOICE_DIR = "./invoices"
OUTPUT_FILE = "./data/extracted.json"

results = []
for filename in os.listdir(INVOICE_DIR):
    if not filename.endswith(".pdf"):
        continue
    filepath = os.path.join(INVOICE_DIR, filename)
    try:
        with pdfplumber.open(filepath) as pdf:
            text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
        results.append({
            "file": filename,
            "text": text,
            "chars": len(text)
        })
        print(f"✓ {filename} ({len(text)} chars)")
    except Exception as e:
        print(f"✗ {filename}: {e}")

with open(OUTPUT_FILE, "w") as f:
    json.dump(results, f, indent=2)

print(f"\nExtracted {len(results)} invoices → {OUTPUT_FILE}")
```

**Output:** `extracted.json` — one entry per invoice with raw text. Runs in ~2 minutes on 190 files. Zero API cost.

---

### Stage 2 — Structured parsing with Claude Haiku (one-time, ~$0.50)

```python
# parse_invoices.py
import json
import sqlite3
from anthropic import Anthropic

client = Anthropic()
db = sqlite3.connect("./data/spendiq.db")

PROMPT_TEMPLATE = """Extract transaction details from this invoice.
Return ONLY valid JSON, no explanation, no markdown:

{{
  "date": "YYYY-MM-DD",
  "vendor": "store or service name",
  "amount": 0.00,
  "category": "grocery|food|subscription|health|dental|shopping|other",
  "items": ["item1", "item2"]
}}

If any field cannot be determined, use null.

Invoice text:
{text}"""

with open("./data/extracted.json") as f:
    invoices = json.load(f)

for inv in invoices:
    # Skip already processed
    existing = db.execute(
        "SELECT id FROM transactions WHERE file_name = ?",
        (inv["file"],)
    ).fetchone()
    if existing:
        print(f"→ Skip (already processed): {inv['file']}")
        continue

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # cheapest model
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": PROMPT_TEMPLATE.format(
                    text=inv["text"][:3000]  # cap tokens per invoice
                )
            }]
        )
        raw = response.content[0].text.strip()
        data = json.loads(raw)

        db.execute("""
            INSERT INTO transactions
                (date, vendor, amount, category, file_name, raw_text)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get("date"),
            data.get("vendor"),
            data.get("amount"),
            data.get("category", "other"),
            inv["file"],
            inv["text"][:5000]
        ))
        db.commit()
        print(f"✓ {inv['file']} → {data.get('vendor')} ${data.get('amount')}")

    except Exception as e:
        print(f"✗ {inv['file']}: {e}")

db.close()
print("Done. All invoices stored in spendiq.db")
```

**Cost breakdown:**
- Average tokens per invoice: ~500 input + 100 output = 600 tokens
- 190 invoices × 600 tokens = 114,000 tokens
- Haiku pricing: $0.25 per million input tokens, $1.25 per million output
- **Total estimated cost: ~$0.15–$0.50**

Using the Batch API (submit all at once) cuts this by a further 50%.

---

### Stage 3 — SQLite schema

```sql
-- Core transactions table
CREATE TABLE transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    vendor      TEXT NOT NULL,
    amount      REAL,
    category    TEXT DEFAULT 'other',
    source      TEXT DEFAULT 'upload',  -- gmail | outlook | upload | manual
    file_name   TEXT,
    raw_text    TEXT,
    is_verified INTEGER DEFAULT 0,      -- 1 = user confirmed amount
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Shopping lists
CREATE TABLE shopping_lists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    item        TEXT NOT NULL,
    store       TEXT,
    frequency   TEXT,
    est_price   REAL,
    list_type   TEXT DEFAULT 'weekly',  -- weekly | monthly | subscriptions
    is_done     INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Vendor rules for auto-categorization
CREATE TABLE vendor_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern     TEXT NOT NULL,          -- e.g. "walmart", "costco"
    category    TEXT NOT NULL,
    store_name  TEXT
);

-- Pre-seed vendor rules
INSERT INTO vendor_rules (pattern, category, store_name) VALUES
    ('walmart',     'grocery',      'Walmart'),
    ('costco',      'grocery',      'Costco'),
    ('doordash',    'food',         'DoorDash'),
    ('uber eats',   'food',         'Uber Eats'),
    ('amazon',      'shopping',     'Amazon'),
    ('wellness',    'health',       'Wellness Clinic'),
    ('dental',      'dental',       'Dental'),
    ('apple',       'subscription', 'Apple'),
    ('netflix',     'subscription', 'Netflix'),
    ('anthropic',   'subscription', 'Anthropic Claude');

-- Useful indexes
CREATE INDEX idx_tx_date     ON transactions(date);
CREATE INDEX idx_tx_vendor   ON transactions(vendor);
CREATE INDEX idx_tx_category ON transactions(category);
```

---

### Stage 4 — AI insight queries (tiny tokens)

```python
# FastAPI route — /api/insights/ai-analyze
@app.post("/api/insights/ai-analyze")
async def ai_analyze():
    # Step 1: SQL does the heavy aggregation (free)
    summary = db.execute("""
        SELECT
            category,
            vendor,
            COUNT(*) as trips,
            ROUND(SUM(amount), 2) as total,
            ROUND(AVG(amount), 2) as avg_order
        FROM transactions
        WHERE date >= date('now', '-90 days')
            AND amount IS NOT NULL
        GROUP BY category, vendor
        ORDER BY total DESC
        LIMIT 20
    """).fetchall()

    # Step 2: Format as compact text (~300 tokens)
    summary_text = "\n".join(
        f"{row['vendor']}: ${row['total']} across {row['trips']} trips "
        f"(avg ${row['avg_order']}, category: {row['category']})"
        for row in summary
    )

    # Step 3: Send only the summary to Claude Sonnet
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""You are a personal finance coach. Analyze this 90-day spending summary and give
5 specific, actionable insights. Be direct and concrete.

Spending summary:
{summary_text}

Focus on: patterns, what to move to Costco, subscription audit,
and one specific savings tip."""
        }]
    )

    return {"insight": response.content[0].text}
```

---

## AI integration strategy

### Model selection guide

| Task | Model | Why | Est. cost |
|------|-------|-----|-----------|
| Extract fields from 190 PDFs | `claude-haiku-4-5` | Fast, cheap, accurate for structured JSON | ~$0.15–$0.50 total |
| Parse a single uploaded receipt | `claude-haiku-4-5` | Same — structured extraction only | ~$0.001 per file |
| AI spending coach analysis | `claude-sonnet-4-6` | Nuanced advice, pattern recognition | ~$0.01 per query |
| Smart shopping list generation | `claude-sonnet-4-6` | Creative suggestions with context | ~$0.01 per query |

### What data gets sent to Claude

| Feature | Sent to API | Not sent |
|---------|-------------|----------|
| Spending coach | Aggregated totals by vendor/category | Raw transactions, email content |
| Shopping list | Purchase frequency and store patterns | Item prices, personal details |
| Receipt parser | Extracted text from that one PDF | Other invoices, database contents |
| Batch job | Text from each invoice (one-time only) | Stored after that, never again |

### API key storage

```bash
# .env file — never commit to git
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx

# FastAPI reads it at startup
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
```

---

## Database design

### Core data flow

```
PDF / Email / CSV / Manual
        │
        ▼
   FastAPI parser
        │
        ▼
   transactions table   ──────────►  shopping_lists table
        │                                    │
        ▼                                    ▼
   SQL aggregation               React shopping list UI
        │
        ▼
   Summary text (~300 tokens)
        │
        ▼
   Claude API (on demand)
        │
        ▼
   Insight text → React UI
```

### Useful SQL queries for the app

```sql
-- Monthly spending trend
SELECT
    strftime('%Y-%m', date) as month,
    ROUND(SUM(amount), 2) as total,
    COUNT(*) as transactions
FROM transactions
WHERE amount IS NOT NULL
GROUP BY month
ORDER BY month;

-- Top vendors last 90 days
SELECT vendor, ROUND(SUM(amount), 2) as total, COUNT(*) as visits
FROM transactions
WHERE date >= date('now', '-90 days') AND amount IS NOT NULL
GROUP BY vendor
ORDER BY total DESC LIMIT 10;

-- Items bought on repeat (same vendor, within 14 days)
SELECT vendor, COUNT(*) as freq,
       MIN(date) as first, MAX(date) as last
FROM transactions
GROUP BY vendor
HAVING COUNT(*) > 3
ORDER BY freq DESC;

-- Unknown amounts (needs manual fill)
SELECT id, date, vendor, file_name
FROM transactions
WHERE amount IS NULL
ORDER BY date DESC;
```

---

## UI design

### Design system

The SpendIQ interface follows a clean, flat aesthetic inspired by modern productivity tools. No gradients, no shadows, no decorative effects.

```
Typography:   DM Sans (UI), DM Mono (amounts/dates/codes)
Background:   #f0efec (warm off-white page)
Surface:      #ffffff (cards), #f6f5f2 (secondary)
Accent:       #2d6a4f / #40916c (green — money/positive)
Warning:      #e76f51 (orange — overspending alerts)
Info:         #3a86ff (blue — neutral information)
Border:       rgba(0,0,0,0.07) at 0.5px
Radius:       10px components, 16px cards
```

### Color encoding

| Color | Meaning | Used for |
|-------|---------|----------|
| Green `#40916c` | Positive / savings | Confirmed amounts, savings badges, produce category |
| Orange `#e76f51` | Warning / overspend | High spend alerts, unknown amounts, repeat purchases |
| Blue `#3a86ff` | Neutral info | Subscriptions, informational insights, dairy category |
| Purple `#7b2d8b` | Subscription | Recurring charges |
| Red `#e63946` | Health / urgent | Healthcare spending, dental |
| Amber `#f4a261` | Gold tips | Optimization suggestions |

### Navigation structure

```
SpendIQ
├── Overview          (KPIs, category chart, MoM bar chart, quick insights)
├── Transactions      (filterable table — category, source, month, search)
├── AI Insights       (store bars, frequency grid, AI coach button)
├── Shopping List     (weekly / monthly / subscriptions tabs, AI generate)
└── Import Bills      (drag-drop zone, connected sources, gap tracker)
```

### Screen designs

#### Overview screen

```
┌─────────┬─────────┬─────────┬─────────┐
│ Total   │ Monthly │ Tracked │ Subscr. │  ← KPI row (4 cards)
│ $1,042  │  $347   │  68%    │ $17.99  │
└─────────┴─────────┴─────────┴─────────┘

┌──────────────────┬──────────────────┐
│  Category donut  │  Month-over-     │
│  chart           │  month bar chart │
└──────────────────┴──────────────────┘

┌────────────────────────────────────────┐
│  Quick insights (4 insight cards)      │
│  ⚠ 32% transactions missing amounts   │
│  ℹ Costco 2×/month — consolidate      │
│  ✓ Health $270 — well tracked         │
│  💡 DoorDash amounts unknown          │
└────────────────────────────────────────┘
```

#### Transactions screen

```
[Search...]  [Category ▼]  [Source ▼]  [Month ▼]  [Import] [+ Add]

Date        Store / Service         Category        Amount    Source
──────────────────────────────────────────────────────────────────
2026-05-18  Wellness Clinic         Health          $30.00    gmail
2026-05-15  Walmart delivery        Grocery         unknown   gmail  [edit]
2026-05-14  DoorDash - Local Rest.  Food delivery   unknown   gmail  [edit]
2026-05-13  Anthropic Claude Pro    Subscription    unknown   gmail  [edit]
```

#### AI Insights screen

```
┌──────────────────────┬──────────────────────┐
│  Top stores          │  Most frequent       │
│  Costco     ████ $0  │  Costco      6×      │
│  Health     ███ $270 │  Health      9×      │
│  Dental     ██ $170  │  DoorDash    3×      │
│  Apple      ▌ $5.98  │  iCloud+     2×      │
└──────────────────────┴──────────────────────┘

┌────────────────────────────────────────────┐
│  Costco order frequency (bar chart)        │
│  Feb:1  Mar:2  Apr:2  May:1               │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│  AI spending coach           [Analyze ↗]   │
│                                            │
│  (AI insight text appears here after       │
│   clicking Analyze — ~3 seconds)          │
└────────────────────────────────────────────┘
```

#### Shopping list screen

```
[Weekly] [Monthly] [Subscriptions]    [AI generate ↗] [Copy]

── COSTCO ────────────────────────────────────────────────────
☐  Whole milk (1 gallon)     Every week       ~$6
☐  Eggs (18-pack)            Every week       ~$8
☑  Brioche buns (12-ct)      Bi-weekly        ~$7    ← checked off
☐  Snack variety pack        Weekly           ~$3

── WALMART ───────────────────────────────────────────────────
☐  Organic bananas           Every week       ~$3
☐  Green cabbage             Every week       ~$2
☐  Bread (whole wheat)       Every week       ~$4

[Add item...]  [Costco ▼]  [+ Add]
```

#### Import screen

```
┌─────────────────────────────┐  ┌──────────────────────────────┐
│   ↑                         │  │  Tracking gaps               │
│   Drop files or click       │  │                              │
│   PDF · CSV · .eml          │  │  ⚠ Amazon — export order CSV │
│                             │  │  ⚠ Costco — use Instacart    │
│  invoice_march.pdf  ✓ 3     │  │    app for itemized receipts │
│  amazon_2025.csv    parsing │  │  ⚠ DoorDash — check app      │
│                             │  │  ℹ Bank CSV fills all gaps   │
│  [Parse & import with AI]   │  │  💡 Outlook .eml supported   │
└─────────────────────────────┘  └──────────────────────────────┘
```

---

## Feature modules

### Module 1 — Transaction manager

**Purpose:** Single source of truth for all spending records.

**Sources supported:**
- Gmail (OAuth2 — order/receipt emails auto-fetched)
- Outlook / Microsoft 365 (Microsoft Graph API)
- PDF upload (pdfplumber extraction + Haiku parsing)
- CSV upload (pandas for bank/Amazon exports)
- Manual entry

**Auto-categorization:** Vendor rules table matches vendor name patterns to categories. Unknown vendors get flagged for manual review.

---

### Module 2 — Invoice batch processor

**Purpose:** One-time job to process the full 190-invoice backlog.

**Steps:**
1. Point script at your invoice folder
2. pdfplumber extracts text from all files
3. Haiku parses each one into structured JSON
4. Results inserted into SQLite, skipping already-processed files
5. Done — never run again (except for new files)

**Incremental mode:** Running the script again on the same folder skips already-processed files using `WHERE file_name = ?` check. Safe to re-run at any time.

---

### Module 3 — AI insights engine

**Purpose:** Turn stored transaction data into actionable advice.

**Spending coach:** Aggregates last 90 days by vendor/category. Sends ~300-token summary to Sonnet. Returns 5 specific, actionable insights in ~3 seconds.

**Pattern detection (local, no AI):**
- Repeat purchases within 14 days (SQL query)
- Month-over-month spend change per category
- Vendors with unknown amounts
- Subscription count and estimated monthly total

---

### Module 4 — Smart shopping list

**Purpose:** Suggest a consolidated weekly/monthly list based on purchase history.

**AI generate mode:** Sends purchase frequency data to Sonnet. Returns 8–10 suggested items with store, frequency, and estimated price as JSON. Items appended to the active list.

**Manual mode:** Add any item, assign to store, mark done during the trip.

**Copy to clipboard:** Formats list as plain text grouped by store, ready to paste into Notes or WhatsApp.

---

### Module 5 — Costco vs Walmart optimizer

**Purpose:** For any uploaded Walmart receipt, identify which items are cheaper at Costco in bulk.

**Logic:**
1. Parse Walmart receipt → extract line items + prices
2. Match items against a local price comparison table (maintained manually or via AI)
3. Flag items where Costco bulk price / weeks of use < Walmart unit price
4. Highlight repeat purchases across multiple Walmart trips (buy more, fewer trips)

---

## Project structure

```
spendiq/
├── electron/
│   ├── main.js              # Electron main process
│   ├── preload.js           # IPC bridge (renderer ↔ main)
│   └── package.json
│
├── frontend/                # React app (Vite)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── Overview.jsx
│   │   │   ├── Transactions.jsx
│   │   │   ├── Insights.jsx
│   │   │   ├── ShoppingList.jsx
│   │   │   └── Import.jsx
│   │   ├── hooks/
│   │   │   ├── useTransactions.js
│   │   │   └── useInsights.js
│   │   └── api/
│   │       └── client.js    # fetch() wrappers for FastAPI
│   └── package.json
│
├── backend/                 # Python FastAPI
│   ├── main.py              # FastAPI app + all routes
│   ├── database.py          # SQLite connection + schema
│   ├── parsers/
│   │   ├── pdf_parser.py    # pdfplumber extraction
│   │   ├── csv_parser.py    # pandas CSV import
│   │   └── email_parser.py  # Gmail + Outlook sync
│   ├── ai/
│   │   ├── extractor.py     # Haiku invoice parsing
│   │   └── insights.py      # Sonnet analysis queries
│   ├── scripts/
│   │   ├── extract_invoices.py   # Stage 1: local PDF text extraction
│   │   └── parse_invoices.py     # Stage 2: Haiku batch parsing
│   └── requirements.txt
│
├── data/
│   ├── spendiq.db           # SQLite database (gitignored)
│   ├── extracted.json       # Raw PDF text cache (gitignored)
│   └── invoices/            # Your PDF files (gitignored)
│
├── .env                     # API keys (gitignored)
├── .gitignore
└── README.md
```

---

## Setup guide

### Prerequisites

```bash
node --version    # 20+
python --version  # 3.11+
```

### Step 1 — Clone and install

```bash
git clone https://github.com/yourname/spendiq
cd spendiq

# Frontend
cd frontend && npm install

# Backend
cd ../backend
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install fastapi uvicorn sqlalchemy pdfplumber pandas \
            anthropic python-dotenv google-auth requests
```

### Step 2 — Environment

```bash
# Create .env in backend/
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
GMAIL_CLIENT_ID=your-gmail-oauth-client-id
GMAIL_CLIENT_SECRET=your-gmail-oauth-secret
```

### Step 3 — Initialize database

```bash
cd backend
python database.py   # creates spendiq.db with schema + seed rules
```

### Step 4 — Process your 190 invoices (one-time)

```bash
# Copy all your PDFs into backend/data/invoices/
cp ~/Downloads/invoices/* backend/data/invoices/

# Stage 1: extract text locally (free, ~2 min)
python scripts/extract_invoices.py

# Stage 2: parse with Haiku (~$0.15–0.50, ~5 min)
python scripts/parse_invoices.py
```

### Step 5 — Run the app

```bash
# Terminal 1: start backend
cd backend && uvicorn main:app --port 8765 --reload

# Terminal 2: start frontend
cd frontend && npm run dev

# Terminal 3: start Electron
cd electron && npm start
```

### Step 6 — Build installer (optional)

```bash
cd electron
npm run build     # bundles React + Electron into .exe / .dmg
```

---

## Cost estimates

| Activity | Model | Tokens | Cost |
|----------|-------|--------|------|
| Initial 190 invoice batch (one-time) | Haiku | ~114K | ~$0.15–$0.50 |
| Each new uploaded receipt | Haiku | ~600 | ~$0.001 |
| AI spending coach click | Sonnet | ~1,000 | ~$0.015 |
| AI shopping list generate | Sonnet | ~800 | ~$0.012 |
| Monthly total (normal use) | Mixed | ~10K | ~$0.15–$0.25 |

**Estimated total monthly running cost: under $0.30.**

---

## Roadmap

### v1.0 — Core (4–6 weeks)
- [x] SpendIQ HTML prototype (complete)
- [ ] Electron + React scaffold
- [ ] FastAPI backend with SQLite
- [ ] PDF batch processor (190 invoices)
- [ ] Gmail sync
- [ ] Manual entry + CSV import
- [ ] AI spending coach
- [ ] Shopping list with AI generate

### v1.1 — Enhanced (2–3 weeks)
- [ ] Outlook / Microsoft 365 sync
- [ ] Costco vs Walmart optimizer
- [ ] Receipt photo capture (mobile)
- [ ] Export to Excel / CSV
- [ ] Budget setting and alerts

### v1.2 — Intelligence (2–3 weeks)
- [ ] Seasonal pattern detection (festival months, back to school)
- [ ] Price trend tracking per item over time
- [ ] Automatic Costco trip planner (combine monthly items into one trip)
- [ ] Subscription audit with cancel recommendations

### v2.0 — Multi-device (future)
- [ ] Optional encrypted cloud sync between family devices
- [ ] Mobile companion app (React Native)
- [ ] Shared shopping lists with real-time check-off

---

*Document generated May 2026 · SpendIQ v0.1 prototype*
