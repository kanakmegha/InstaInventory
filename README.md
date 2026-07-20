# Smart Restocking & Budget Shield (InstaInventory)

InstaInventory is a money-focused, AI-ready personal grocery assistant designed to sit on top of Swiggy Instamart. It analyzes purchase history to automatically predict restocking cycles, optimize product packaging options for the lowest cost, and enforce weekly budget guardrails.

---

## 1. Business Vertical & Purpose
Groceries represent a major, highly repetitive household expense. Yet, consumers waste significant capital by:
- **Buying in sub-optimal quantities**: Buying small packs frequently rather than single bulk items with lower unit costs.
- **Impulse buying & Budget creep**: Adding unnecessary items or upgrading carts without considering weekly budget limits.
- **Manual tracking fatigue**: Forgetting when essentials run out, leading to last-minute premium shipping charges.

**InstaInventory** solves this by establishing a **Budget-Shielded Restocking Pipeline**:
- It learns household purchase cadences (cycle days) deterministically.
- It dynamically looks up pricing options on Swiggy Instamart and suggests cost-saving bulk upgrades.
- It locks checkout capabilities under a strict weekly budget cap, forcing users to prioritize essential reorders.
- **Safety Assumption**: Automation is strictly advisory. The system *never* executes checkout or places real financial orders automatically. Every transaction requires explicit user review and manual confirmation.

---

## 2. Architecture Overview
InstaInventory is structured as a modular Python package with a clean FastAPI backend and an interactive glassmorphic vanilla web dashboard.

```
instainventory/
  app/
    __init__.py
    db.py                 # SQLite schema initialization and connection management
    models.py             # Pydantic schemas for database serialization
    seed.py               # Generates 8+ weeks of deterministic irregular grocery logs
    pattern_detection.py  # Frequency analysis & drift (declined orders) tracking
    budget_engine.py      # Checks weekly spend bounds & formats approvals
    instamart_client.py   # Client connecting to Swiggy Instamart MCP API
    pack_optimizer.py     # Compares unit prices to recommend bulk savings
    persona.py            # Generates rolling user spending & acceptance snapshots
    main.py               # FastAPI router and static file hosting
  tests/
    test_db.py            # DB schema & seeding assertions
    test_pattern_detection.py # Restock cycles, confidence & drift assertions
    test_budget_engine.py # Spend checks and approvals assertions
    test_instamart_client.py  # Mock mode and product variants parsing assertions
    test_pack_optimizer.py    # Bulk savings calculation assertions
    test_persona.py       # Metrics rollup assertions
    test_api.py           # Integration API endpoint assertions (success + error cases)
  instainventory_demo.html# Vanilla CSS dark-mode glassmorphic client dashboard
  requirements.txt        # Package dependencies
  .gitignore            # Caches and DB exclusions
  .env.example            # Environment variables template
```

---

## 3. Core Engine Mechanics

### Pattern Detection
The restocking cycle (in days) is calculated as the mean interval between consecutive purchases of an item name. 
`confidence` (a float between `0.0` and `1.0`) is calculated as:
$$\text{confidence} = \text{count\_factor} \times \text{variance\_factor}$$
- **Volume Weight (`count_factor`)**: Ensures single intervals are penalized, and scales up to `1.0` at 4+ intervals (5+ orders):
  $$\text{count\_factor} = \min(1.0, 0.4 + 0.15 \times \text{gaps})$$
- **Consistency Weight (`variance_factor`)**: Normalizes the standard deviation of gaps ($\sigma$) against the mean gap ($\mu$) using the Coefficient of Variation ($CV = \sigma / \mu$):
  $$\text{variance\_factor} = \max(0.0, 1.0 - CV)$$
If consecutive restocks are repeatedly declined by the user, `detect_drift` flags a pattern deviation, pausing automatic reorder recommendations and prompting a cycle check-in instead.

### Budget Shield
Before any order approval is rendered, the budget engine calculates:
$$\text{projected\_spend} = \text{spend\_this\_week} + \text{proposed\_order\_cost}$$
If $\text{projected\_spend} > \text{weekly\_limit}$, the order is locked. The UI shows an alert, and restocking recommendations are paused until the budget limit is updated or the current week rolls over.

### Pack Size Optimizer
Sums up the total volume/weight of an item purchased in the last 30 days. It then checks Swiggy Instamart's available variants for that item. If buying the equivalent volume/weight using a larger bulk pack variant yields a cost difference exceeding a threshold (defined as either ₹10 or 10% of the actual paid amount, whichever is higher), the engine returns an optimization recommendation.

---

## 4. Setup & Installation

### Prerequisite: Python 3.9+ installed.

### 1. Create and Activate Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and configure accordingly:
```bash
cp .env.example .env
```
- By default, `USE_MOCK_DATA=True` is enabled, allowing local testing, seeding, and demos with no credentials.

---

## 5. Running the Application

### Start the FastAPI Server
To launch the backend server and host the dashboard on `http://127.0.0.1:8000`:
```bash
PYTHONPATH=. uvicorn app.main:app --reload
```
You can access the interactive frontend dashboard directly at:
[http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 6. Running Tests
Tests are implemented using `pytest`. They automatically mock database sessions using dynamic temporary databases to ensure isolation.

Run the complete test suite from the repository root:
```bash
PYTHONPATH=. pytest -v
```
All 30 unit and integration tests should pass successfully.
