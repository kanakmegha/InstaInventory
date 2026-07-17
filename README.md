# InstaInventory

A Python project for tracking Swiggy Instamart order patterns, automated restocking recommendations, and budget compliance snapshots.

## Project Structure
- `instainventory/app/`: Core application module.
  - `db.py`: Database connection and schema manager.
  - `models.py`: Pydantic data schemas.
  - `seed.py`: Seeding module for generating mock order history.
- `instainventory/tests/`: Database and service test suite.

## Setup & Execution

### 1. Set up Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Tests
```bash
pytest
```
