# app/copy.py
import datetime

# Display names map
DISPLAY_NAMES = {
    "milk": "Milk",
    "tomato": "Tomato",
    "eggs": "Eggs",
    "rice": "Rice",
    "oil": "Oil",
    "onion": "Onion",
    "peach": "Peach",
    "atta": "Atta",
    "bread": "Bread"
}

def get_display_name(item_name: str) -> str:
    name_lower = item_name.lower()
    return DISPLAY_NAMES.get(name_lower, item_name.capitalize())

def get_plural_name(item_name: str) -> str:
    name_lower = item_name.lower()
    if "tomato" in name_lower:
        return "tomatoes"
    elif "peach" in name_lower:
        return "peaches"
    elif "milk" in name_lower:
        return "milk"
    elif "rice" in name_lower:
        return "rice"
    elif "oil" in name_lower:
        return "oil"
    elif "egg" in name_lower:
        return "eggs"
    elif "onion" in name_lower:
        return "onions"
    elif "atta" in name_lower:
        return "atta"
    elif "bread" in name_lower:
        return "bread"
    return name_lower + "s"

# Empty States
EMPTY_PATTERNS = "We haven't detected any regular grocery buying patterns yet. Keep buying items to help the system learn your habits."
EMPTY_APPROVALS = "No restock approvals or suggestions are pending right now. We will notify you when it is time to restock."
EMPTY_PERSONA = "We haven't compiled your buying habits snapshot yet. Once you approve suggestions, your shopping profile will appear here."
EMPTY_WEEKLY_ITEMS = "No items ordered this week yet. Approve restocks or place orders to see them listed here."

# Errors
ERROR_PATTERN_NOT_FOUND = "We couldn't find that restocking schedule (not found). Please refresh the page and try again."
ERROR_APPROVAL_NOT_FOUND = "We couldn't find that pending restock suggestion (not found). It might have already been approved or declined. Please check your timeline."
ERROR_CHECKOUT_FAILED = "We couldn't connect to Instamart to place your order. Please check your internet connection or try again in a few minutes."
ERROR_INVALID_CYCLE = "Please enter a valid positive number of days for the cycle interval."

# Mutating Route Success Messages (for tests/API compatibility)
def get_confirm_pattern_msg(pattern_id: int) -> str:
    return f"Pattern {pattern_id} confirmed."

def get_reject_pattern_msg(pattern_id: int) -> str:
    return f"Pattern {pattern_id} rejected/dismissed."

def get_edit_cycle_msg(pattern_id: int, days: float) -> str:
    rounded_days = int(round(days))
    return f"Pattern {pattern_id} cycle updated to {rounded_days} days."

def get_approve_approval_msg(approval_id: int) -> str:
    return f"Approval {approval_id} approved. Order placed successfully."

def get_decline_approval_msg(approval_id: int) -> str:
    return f"Approval {approval_id} declined."

def get_update_budget_cap_msg(weekly_cap: float) -> str:
    return f"Weekly budget cap updated to ₹{int(round(weekly_cap))}."

# Explanations / Suggestions Why
def get_reorder_explanation(item_name: str, cycle_days: int) -> str:
    plural = get_plural_name(item_name)
    return f"You usually reorder {plural} about every {cycle_days} days, and it's been {cycle_days} days."

def get_drift_explanation(item_name: str, suggested_days: int) -> str:
    display_name = get_display_name(item_name)
    return f"We noticed you skipped a few restock suggestions for {display_name.lower()}, which means you might need them less often. Based on your recent orders, would you like to update your schedule to every {suggested_days} days?"

def get_bulk_explanation(item_name: str, total_packs: int, usual_unit: str, suggested_pack_size: str) -> str:
    return f"You bought {total_packs} × {usual_unit} of {item_name} this month, so switching to {suggested_pack_size} packs would save you money on the same overall amount."

# Status Translations
STATUS_ACTIVE = "Tracking this schedule"
STATUS_DISMISSED = "Stopped tracking"
STATUS_DRIFTED = "Schedule might have changed"

# Combined copy dict for frontend use
COPY_DICT = {
    "empty_patterns": EMPTY_PATTERNS,
    "empty_approvals": EMPTY_APPROVALS,
    "empty_persona": EMPTY_PERSONA,
    "empty_weekly_items": EMPTY_WEEKLY_ITEMS,
    "status_active": STATUS_ACTIVE,
    "status_dismissed": STATUS_DISMISSED,
    "status_drifted": STATUS_DRIFTED
}
