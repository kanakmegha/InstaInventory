from pydantic import BaseModel, ConfigDict
from typing import Optional

class User(BaseModel):
    id: int
    budget_cap_weekly: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)

class OrderHistory(BaseModel):
    id: Optional[int] = None
    item_name: str
    quantity: float
    unit: str
    price: float
    ordered_at: str  # ISO8601 string, e.g. "2026-07-17T18:03:15"
    
    model_config = ConfigDict(from_attributes=True)

class Pattern(BaseModel):
    id: Optional[int] = None
    item_name: str
    predicted_cycle_days: float
    confidence: float
    status: str  # e.g., "active", "paused", "dismissed"
    last_confirmed_at: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class Approval(BaseModel):
    id: Optional[int] = None
    pattern_id: int
    proposed_date: str  # YYYY-MM-DD
    proposed_cost: float
    user_response: Optional[str] = None  # e.g., "approved", "rejected", "pending"
    responded_at: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class PersonaSnapshot(BaseModel):
    id: Optional[int] = None
    week_of: str  # YYYY-MM-DD
    avg_weekly_spend: float
    top_items_json: str  # JSON representation of top items
    bulk_acceptance_rate: float
    approval_rate: float
    notes: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
