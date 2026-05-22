# CLAUDE.md — SpendIQ Project Guide

> Local-first personal spending intelligence for families.
> Built with React + Vite + Tailwind CSS + shadcn/ui + FastAPI + SQLite + AI (Gemini / Claude).

---

## Quick Start

### Prerequisites
- Python 3.11+ (via pyenv)
- Node.js 18+ (via nvm)
- Google Gemini or Anthropic API key

### Backend Setup
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
cp .env.example .env        # Edit with your API key
uvicorn main:app --port 8765 --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Open App
Navigate to **http://localhost:5173**

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Electron Shell                        │
│              (electron/main.js, preload.js)              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐          ┌────────────────────────┐   │
│  │   React UI   │  proxy   │     FastAPI Backend     │   │
│  │  (Vite:5173) │ ──────►  │     (Uvicorn:8765)     │   │
│  │              │          │                        │   │
│  │  Overview    │          │  /api/transactions     │   │
│  │  Transactions│  HTTP    │  /api/dashboard/*      │   │
│  │  AI Insights │ ◄──────  │  /api/insights/*       │   │
│  │  Shopping    │          │  /api/ai/*             │   │
│  │  Import      │          │  /api/import/*         │   │
│  └──────────────┘          │  /api/shopping-list    │   │
│                            └────────┬───────────────┘   │
│                                     │                   │
│                            ┌────────┴───────────┐       │
│                            │      SQLite        │       │
│                            │  spendiq.db (real)  │       │
│                            │  spendiq_demo.db    │       │
│                            └────────────────────┘       │
│                                     │                   │
│                            ┌────────┴───────────┐       │
│                            │   AI Provider      │       │
│                            │  Gemini / Claude    │       │
│                            └────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

### Data Flow
1. **Import** → PDF/Excel/CSV files uploaded → parsed by `parsers/` → AI extraction (optional) → stored in SQLite with line items
2. **Dashboard** → SQL aggregation queries → JSON API → React charts (Recharts)
3. **AI Insights** → Aggregated spending summary + line item history sent to Gemini/Claude → Analysis returned
4. **Shopping List** → AI generates from purchase patterns + actual bought products → stored in `shopping_lists` table

---

## Folder Structure

```
SpendIQ/
├── CLAUDE.md                    # ← This file
├── .gitignore
│
├── backend/                     # FastAPI + SQLite
│   ├── .env                     # Environment variables (not committed)
│   ├── .env.example             # Template for .env
│   ├── requirements.txt         # Python dependencies
│   ├── main.py                  # FastAPI app — all API routes
│   ├── database.py              # SQLite connection, schema, vendor rules
│   ├── demo_data.py             # Sample data for demo mode (transactions + line items)
│   ├── analyze_samples.py       # Dev utility: inspect resource file formats
│   │
│   ├── ai/                      # AI integration layer
│   │   ├── __init__.py
│   │   ├── provider.py          # Unified Gemini/Claude interface
│   │   ├── extractor.py         # Invoice text → structured JSON
│   │   └── insights.py          # Spending coach + shopping list AI
│   │
│   ├── parsers/                 # File import parsers
│   │   ├── __init__.py
│   │   ├── pdf_parser.py        # pdfplumber text extraction
│   │   ├── csv_parser.py        # CSV + Excel (.xlsx/.xls) parser
│   │   ├── email_parser.py      # Gmail/Outlook stubs
│   │   ├── walmart_parser.py    # Walmart Excel order parser → line_items
│   │   └── costco_parser.py     # Costco Same-Day PDF receipt parser → line_items
│   │
│   ├── scripts/                 # Batch processing
│   │   ├── extract_invoices.py  # Stage 1: PDF → text
│   │   ├── parse_invoices.py    # Stage 2: text → AI → DB
│   │   └── import_bills.py      # Batch import from resources/ (main importer)
│   │
│   ├── resources/               # Sample bills for batch import
│   │   ├── walmart/             # Walmart order Excel files (.xlsx)
│   │   └── costco/              # Costco Same-Day receipt PDFs
│   │
│   └── data/                    # SQLite databases (gitignored)
│       ├── spendiq.db           # Real data
│       ├── spendiq_demo.db      # Demo data
│       └── invoices/            # Uploaded PDFs
│
├── frontend/                    # React + Vite + Tailwind + shadcn/ui
│   ├── package.json
│   ├── vite.config.js           # API proxy → localhost:8765 + @ path alias
│   ├── tailwind.config.js       # Tailwind config with shadcn/ui theme tokens
│   ├── postcss.config.js        # PostCSS for Tailwind
│   ├── jsconfig.json            # @ → ./src alias for VS Code
│   ├── index.html               # Inter/JetBrains Mono fonts, SEO meta
│   └── src/
│       ├── main.jsx             # Entry point
│       ├── index.css            # Tailwind directives + shadcn/ui CSS variables
│       ├── App.jsx              # Router + dark sidebar + mobile drawer
│       ├── lib/
│       │   └── utils.js         # cn() Tailwind merge helper (clsx + tailwind-merge)
│       ├── api/
│       │   └── client.js        # Fetch wrapper for all API calls
│       ├── components/
│       │   ├── ui/              # shadcn/ui primitive components
│       │   │   ├── button.jsx
│       │   │   ├── badge.jsx
│       │   │   ├── card.jsx
│       │   │   ├── dialog.jsx
│       │   │   ├── input.jsx
│       │   │   ├── label.jsx
│       │   │   ├── select.jsx
│       │   │   ├── checkbox.jsx
│       │   │   ├── tabs.jsx
│       │   │   ├── table.jsx
│       │   │   ├── separator.jsx
│       │   │   ├── progress.jsx
│       │   │   └── skeleton.jsx
│       │   ├── Overview.jsx     # KPI cards, donut + bar charts (recharts)
│       │   ├── Transactions.jsx # Sortable table, inline edit, line-item expand
│       │   ├── Insights.jsx     # Top vendors, frequency, AI coach
│       │   ├── ShoppingList.jsx # Tabs, checkbox items, AI generate with feedback
│       │   └── Import.jsx       # react-dropzone, progress bar, import results
│       └── hooks/
│           ├── useTransactions.js
│           └── useInsights.js
│
└── electron/                    # Desktop packaging (future)
    ├── main.js                  # Spawns backend + loads frontend
    ├── preload.js               # IPC bridge
    └── package.json
```

---

## Database Design

### Tables

#### `transactions`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `date` | TEXT | YYYY-MM-DD |
| `vendor` | TEXT | Store/service name |
| `amount` | REAL | Dollar amount (nullable — unknown amounts allowed) |
| `category` | TEXT | `grocery`, `food`, `shopping`, `subscription`, `health`, `dental`, `other` |
| `source` | TEXT | `gmail`, `upload`, `manual`, `walmart`, `costco` |
| `file_name` | TEXT | Source file name |
| `raw_text` | TEXT | Original extracted text (for PDFs) |
| `is_verified` | INTEGER | 0=unverified, 1=verified |
| `created_at` | TEXT | ISO timestamp |

#### `line_items`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `transaction_id` | INTEGER | Foreign key → `transactions(id)` ON DELETE CASCADE |
| `product_name` | TEXT | Name of the purchased item |
| `quantity` | REAL | Quantity purchased (default 1) |
| `unit_price` | REAL | Price per unit |
| `total_price` | REAL | Total price for the line item |
| `item_status` | TEXT | Status (e.g. 'Shopped', 'Delivered') |
| `item_number` | TEXT | Item/SKU number |
| `discount` | REAL | Discount applied to item (shown in red in UI) |
| `created_at` | TEXT | ISO timestamp |

#### `shopping_lists`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT | List name |
| `item` | TEXT | Item description |
| `store` | TEXT | Target store (Costco, Walmart, etc.) |
| `frequency` | TEXT | `Every week`, `Bi-weekly`, `Monthly`, `As needed` |
| `est_price` | REAL | Estimated price |
| `list_type` | TEXT | `weekly`, `monthly`, `subscriptions` |
| `is_done` | INTEGER | Checkbox state |
| `created_at` | TEXT | ISO timestamp |

#### `vendor_rules`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `pattern` | TEXT | Lowercase match pattern |
| `category` | TEXT | Auto-assigned category |
| `store_name` | TEXT | Normalized display name |

### Indexes
```sql
idx_tx_date      ON transactions(date)
idx_tx_vendor    ON transactions(vendor)
idx_tx_category  ON transactions(category)
idx_tx_source    ON transactions(source)
idx_li_txid      ON line_items(transaction_id)
idx_li_product   ON line_items(product_name)
```

### Dual Database Strategy
| Mode | File | Behavior |
|------|------|----------|
| `DEMO_MODE=true` | `data/spendiq_demo.db` | Pre-seeded with ~46 transactions + 8 line items + 8 shopping items |
| `DEMO_MODE=false` | `data/spendiq.db` | Your real imported data |

Both coexist. Switching just toggles which file `get_db()` connects to. `load_dotenv(override=True)` ensures the env var is always re-read fresh.

---

## API Routes

### Transactions
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/transactions` | List with filters (category, source, month, search) |
| `POST` | `/api/transactions` | Create (auto-categorizes via vendor rules) |
| `PUT` | `/api/transactions/{id}` | Update (amount, category, verified) |
| `DELETE` | `/api/transactions/{id}` | Delete |
| `GET` | `/api/transactions/{id}/items` | Get itemized line items (products) for an order |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard/summary` | KPIs: total 30d, 90d, count, avg |
| `GET` | `/api/dashboard/category-breakdown` | Spend per category |
| `GET` | `/api/dashboard/monthly-trend` | Monthly totals |

### Insights
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/insights/top-vendors` | Top 10 vendors by spend (last N days) |
| `GET` | `/api/insights/frequency` | Most frequent vendors |
| `GET` | `/api/insights/quick` | Auto-generated insight cards |

### AI
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/ai/analyze` | AI spending coach (aggregated data only) |
| `POST` | `/api/ai/shopping-list` | Generate smart shopping list (uses vendor + line item history) |
| `GET` | `/api/ai/provider` | Which AI provider is active |

### Import
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/import/pdf` | Upload PDF → AI parse → insert |
| `POST` | `/api/import/csv` | Upload CSV/Excel → parse → insert |

### Shopping List
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/shopping-list` | List items (filter by list_type) |
| `POST` | `/api/shopping-list` | Add item |
| `PUT` | `/api/shopping-list/{id}` | Update (toggle done, edit) |
| `DELETE` | `/api/shopping-list/{id}` | Delete item |

### Utility
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/categories` | Distinct categories |
| `GET` | `/api/sources` | Distinct sources |
| `GET` | `/api/months` | Distinct months |

---

## AI Provider System

### Architecture
```
provider.py (unified interface)
├── get_provider()        → detects which API key is set
├── call_llm()            → routes to the right provider
│   ├── _call_gemini()    → google-genai SDK
│   └── _call_anthropic() → anthropic SDK
├── clean_json_response() → strips markdown fences from JSON responses
└── get_provider_info()   → for frontend display badge
```

### Model Tiers
| Tier | Use Case | Gemini | Claude |
|------|----------|--------|--------|
| `fast` | Invoice extraction | `gemini-2.5-flash-lite` | `claude-3-5-haiku-latest` |
| `smart` | Spending insights + shopping list | `gemini-2.5-flash-lite` | `claude-3-5-sonnet-latest` |

> **Note**: If `gemini-2.5-flash-lite` returns 503 (high demand), change model to `gemini-2.5-flash` in `ai/provider.py`.

### Provider Priority
1. If `AI_PROVIDER` env var is set → use that provider
2. If `GEMINI_API_KEY` is set → use Gemini
3. If `ANTHROPIC_API_KEY` is set → use Claude
4. Neither → graceful fallback to local rule-based analysis

### AI Shopping List Logic
The `/api/ai/shopping-list` endpoint:
1. Queries all vendors from last 180 days (no minimum frequency gate)
2. Also pulls top 30 actual products from `line_items` for richer context
3. Sends combined context to AI → gets 8–10 personalized items
4. Inserts only **new** items (exact-match deduplication by `item` + `list_type`)
5. Returns `{ items, saved, message }` — frontend shows green toast

### Privacy
- Only **aggregated summaries** are sent to AI — never raw transactions
- Invoice text is capped at 3000 chars per request
- All data stays in local SQLite

---

## Design System

SpendIQ uses **Tailwind CSS v3 + shadcn/ui** (Radix UI primitives styled with Tailwind utility classes).

### Theme Tokens (CSS Variables in `src/index.css`)
| Variable | Usage |
|----------|-------|
| `--background` / `--foreground` | Page background and primary text |
| `--card` / `--card-foreground` | Card surfaces |
| `--primary` / `--primary-foreground` | Primary buttons and accents |
| `--muted` / `--muted-foreground` | Subtle backgrounds and helper text |
| `--sidebar` / `--sidebar-foreground` | Dark sidebar navigation |
| `--border` / `--input` | Form controls and dividers |
| `--destructive` | Delete actions and error states |
| `--radius` | Border radius base (0.5rem) |

### shadcn/ui Components (`src/components/ui/`)
| Component | Used In |
|-----------|---------|
| `Button` | All pages — primary/outline/ghost/icon variants |
| `Badge` | Category chips (grocery/food/etc), source labels |
| `Card` | All page sections, KPI summary cards |
| `Dialog` | Add Transaction modal, Add Shopping Item modal |
| `Tabs` | Shopping List (weekly/monthly/subscriptions) |
| `Input` | Search bar, all forms |
| `Select` | Category, source, month filters |
| `Checkbox` | Shopping list item completion |
| `Table` | Transactions page with expandable line items |
| `Progress` | Import page file upload progress bar |
| `Skeleton` | Loading state placeholders |
| `Separator` | Section dividers in Insights |

### Typography
- **UI / Body**: Inter (Google Fonts)
- **Numbers / Code**: JetBrains Mono

### Category Color Mapping
| Category | Badge Classes |
|----------|--------------|
| grocery | `bg-emerald-100 text-emerald-800` |
| food | `bg-orange-100 text-orange-800` |
| shopping | `bg-blue-100 text-blue-800` |
| subscription | `bg-purple-100 text-purple-800` |
| health | `bg-rose-100 text-rose-800` |
| dental | `bg-cyan-100 text-cyan-800` |
| other | `bg-gray-100 text-gray-700` |

### Layout
- **Sidebar**: Fixed dark sidebar (`--sidebar` CSS var), collapsible on mobile via slide-in drawer
- **Main content**: Scrollable flex column, `p-6` padding
- **Header**: Sticky top bar showing current page name + mobile hamburger

### Accessibility (A11y)
- Radix UI primitives handle focus trapping, ARIA roles, and keyboard navigation automatically
- All form inputs have associated `<label>` elements
- Text contrast follows 4.5:1 minimum via Tailwind colors
- `@media (prefers-reduced-motion: reduce)` respected via Tailwind's `motion-safe:` modifier

---

## Configuration (.env)

```bash
# ── Demo Mode ──
DEMO_MODE=false          # true = demo DB, false = real DB

# ── AI Provider ──
GEMINI_API_KEY=...       # Google Gemini (preferred)
ANTHROPIC_API_KEY=...    # Anthropic Claude (alternative)
AI_PROVIDER=gemini       # Force specific provider (optional)

# ── Email Sync (future) ──
# GMAIL_CLIENT_ID=...
# GMAIL_CLIENT_SECRET=...
```

> **Important**: Both `main.py` and `import_bills.py` use `load_dotenv(override=True)` so changing `.env` takes effect on restart without env cache issues.

---

## Key Dependencies

### Backend (Python)
| Package | Version | Purpose |
|---------|---------|---------| 
| fastapi | 0.115.0 | API framework |
| uvicorn | 0.30.0 | ASGI server |
| pdfplumber | 0.11.0 | PDF text extraction |
| pandas | 2.2.0 | CSV/Excel parsing |
| openpyxl | 3.1.5 | Excel .xlsx support |
| anthropic | 0.40.0 | Claude API SDK |
| google-genai | 1.14.0 | Gemini API SDK |
| python-dotenv | 1.0.1 | .env loading |

### Frontend (Node)
| Package | Version | Purpose |
|---------|---------|---------| 
| react | 18.x | UI framework |
| react-router-dom | 6.x | Client-side routing |
| recharts | 2.x | Charts (pie, bar) |
| lucide-react | latest | Icon library |
| vite | 5.x | Build tool + dev server |
| tailwindcss | 3.x | Utility-first CSS framework |
| @radix-ui/* | latest | Accessible UI primitives (shadcn/ui) |
| class-variance-authority | latest | Component variant management |
| clsx + tailwind-merge | latest | Conditional Tailwind class merging |
| @tanstack/react-table | 8.x | Headless sortable table |
| react-dropzone | latest | Drag-and-drop file upload |

---

## Common Operations

### Batch import bills from resources/ folder
```bash
cd backend

# Dry-run: preview what will be imported (no DB writes)
./venv/bin/python scripts/import_bills.py --dry-run

# Import everything (Walmart + Costco)
./venv/bin/python scripts/import_bills.py

# Import only one store
./venv/bin/python scripts/import_bills.py --source walmart
./venv/bin/python scripts/import_bills.py --source costco
```

**File locations:**
- `backend/resources/walmart/` → `.xlsx` files from Walmart order history
- `backend/resources/costco/` → `.pdf` receipts from Costco Same-Day

> The importer automatically detects duplicate orders (by vendor + date + filename) — safe to re-run multiple times.

### Import bills via UI
1. Go to **Import** tab in the app
2. Drag-and-drop PDF, Excel, or CSV files onto the drop zone
3. Click **Import Files** — PDFs use AI text extraction, Excel uses direct column mapping

### View line items for an order
```bash
# In SQLite CLI:
sqlite3 backend/data/spendiq.db
SELECT t.date, t.vendor, li.product_name, li.quantity, li.unit_price, li.total_price
FROM line_items li JOIN transactions t ON li.transaction_id = t.id
ORDER BY t.date DESC, li.id;
```

Or via API: `GET /api/transactions/{id}/items`

Or in the UI: click the **▶ chevron** on any Transactions row to expand its itemized receipt.

### Start fresh (real data)
```bash
rm backend/data/spendiq.db
# Restart backend — empty DB is created automatically
```

### Switch demo ↔ real mode
Edit `DEMO_MODE` in `backend/.env`, restart backend. No data is lost — each mode has its own separate DB file.

### Add new vendor categorization rule
```bash
sqlite3 backend/data/spendiq.db
INSERT INTO vendor_rules (pattern, category, store_name)
VALUES ('trader joe', 'grocery', 'Trader Joe''s');
```

---

## Accessing SQLite Database

### Database File Locations
```
backend/data/spendiq.db        # Your real data
backend/data/spendiq_demo.db   # Demo data
```

### CLI Access (built into macOS)
```bash
# Open real database
sqlite3 backend/data/spendiq.db

# Open demo database
sqlite3 backend/data/spendiq_demo.db
```

### Useful SQLite Commands
```sql
-- List all tables
.tables

-- Show table schema
.schema transactions
.schema line_items
.schema shopping_lists
.schema vendor_rules

-- Pretty-print output
.mode column
.headers on

-- All transactions (newest first)
SELECT * FROM transactions ORDER BY date DESC;

-- Line items for a specific transaction
SELECT product_name, quantity, unit_price, total_price, item_status, discount
FROM line_items WHERE transaction_id = 1;

-- All line items with vendor context
SELECT t.date, t.vendor, li.product_name, li.quantity, li.total_price
FROM line_items li
JOIN transactions t ON li.transaction_id = t.id
ORDER BY t.date DESC;

-- Total spending by category
SELECT category, ROUND(SUM(amount), 2) as total, COUNT(*) as count
FROM transactions
WHERE amount IS NOT NULL
GROUP BY category
ORDER BY total DESC;

-- Monthly spending trend
SELECT strftime('%Y-%m', date) as month, ROUND(SUM(amount), 2) as total
FROM transactions
WHERE amount IS NOT NULL
GROUP BY month
ORDER BY month;

-- Top 10 vendors by spend
SELECT vendor, ROUND(SUM(amount), 2) as total, COUNT(*) as visits
FROM transactions
WHERE amount IS NOT NULL
GROUP BY vendor
ORDER BY total DESC
LIMIT 10;

-- Transactions missing amounts
SELECT date, vendor, category, source
FROM transactions
WHERE amount IS NULL;

-- All vendor auto-categorization rules
SELECT * FROM vendor_rules;

-- Shopping list items
SELECT item, store, frequency, est_price, list_type,
       CASE is_done WHEN 1 THEN '✓' ELSE '☐' END as status
FROM shopping_lists
ORDER BY list_type, store;

-- Exit
.quit
```

### Access from Python
```python
import sqlite3

conn = sqlite3.connect("backend/data/spendiq.db")
conn.row_factory = sqlite3.Row

# Query transactions
rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC LIMIT 5").fetchall()
for row in rows:
    print(dict(row))

# Query line items
items = conn.execute(
    "SELECT * FROM line_items WHERE transaction_id = ?", (1,)
).fetchall()
for item in items:
    print(dict(item))

conn.close()
```

### GUI Tools (Optional)
- **DB Browser for SQLite** — [sqlitebrowser.org](https://sqlitebrowser.org) — Free, cross-platform
  ```bash
  brew install --cask db-browser-for-sqlite
  # Then: File → Open Database → backend/data/spendiq.db
  ```
- **TablePlus** — [tableplus.com](https://tableplus.com) — Premium, native macOS
- **VS Code Extension** — Search "SQLite Viewer" in extensions

### ⚠️ Important Notes
- **Don't modify the DB while the backend is running** — SQLite uses WAL mode and the server holds a connection. Stop the backend first or use read-only queries.
- **Backup before manual edits**:
  ```bash
  cp backend/data/spendiq.db backend/data/spendiq_backup.db
  ```
- The demo DB can always be regenerated — just delete `spendiq_demo.db` and restart with `DEMO_MODE=true`.
