import os
import urllib.request
import pytest
from app.db import init_db
from app.seed import seed_mock_orders
from app.instamart_client import get_order_history, find_pack_size_options

def test_get_order_history_mock_mode(monkeypatch, tmp_path):
    """
    1. With USE_MOCK_DATA=True, get_order_history() returns data matching the
       seeded fixture, and NO real network call happens.
       Assert this by monkeypatching urllib.request.urlopen to fail the test.
    """
    # Block any network calls
    def block_urlopen(*args, **kwargs):
        pytest.fail("A real network call was attempted during mock testing!")
        
    monkeypatch.setattr(urllib.request, "urlopen", block_urlopen)
    
    # Initialize and seed a temporary test DB
    db_file = tmp_path / "test_instamart_mock.db"
    db_path = str(db_file)
    init_db(db_path)
    seed_mock_orders(db_path)
    
    # Configure env to enforce mock mode and point to our temp DB
    monkeypatch.setenv("USE_MOCK_DATA", "True")
    monkeypatch.setenv("DB_PATH", db_path)
    
    history = get_order_history()
    
    # Assertions
    assert len(history) >= 60
    
    # Ensure correct keys in normalized output
    first_item = history[0]
    required_keys = {"id", "item_name", "quantity", "unit", "price", "ordered_at"}
    for key in required_keys:
        assert key in first_item, f"Key '{key}' is missing in normalized order history."
        
    assert first_item["item_name"] in {"tomato", "milk", "onion", "eggs", "rice", "oil"}
    assert isinstance(first_item["quantity"], float)
    assert isinstance(first_item["price"], float)
    assert isinstance(first_item["ordered_at"], str)

def test_find_pack_size_options_parsing(monkeypatch):
    """
    2. find_pack_size_options() parsing logic is tested against a hand-written
       fake API response.
    """
    fake_search_response = {
        "jsonrpc": "2.0",
        "result": {
            "products": [
                {
                    "name": "Nandini GoodLife Milk",
                    "variants": [
                        {
                            "spin_id": "milk-500ml-spin",
                            "pack_size": "500 ml",
                            "price": 28.0
                        },
                        {
                            "spin_id": "milk-1l-spin",
                            "pack_size": "1 litre",
                            "price": 54.5
                        }
                    ]
                },
                {
                    "name": "Amul Masti Spiced Buttermilk",
                    "variants": [
                        {
                            "spin_id": "buttermilk-200ml-spin",
                            "pack_size": "200ml",
                            "price": 15.0
                        }
                    ]
                }
            ]
        },
        "id": 1
    }
    
    # Mock the internal HTTP tool call helper
    def mock_call_mcp_tool(tool_name, arguments):
        assert tool_name == "search_products"
        assert arguments == {"query": "milk"}
        return fake_search_response
        
    monkeypatch.setattr("app.instamart_client._call_mcp_tool", mock_call_mcp_tool)
    
    options = find_pack_size_options("milk")
    
    assert len(options) == 3
    
    # Verify Nandini GoodLife 500 ml
    assert options[0]["variant_id"] == "milk-500ml-spin"
    assert options[0]["item_name"] == "Nandini GoodLife Milk (500 ml)"
    assert options[0]["pack_size"] == "500 ml"
    assert options[0]["price"] == 28.0
    # price per unit = price / val = 28.0 / 500 = 0.056
    assert options[0]["price_per_unit"] == 0.056
    assert options[0]["unit"] == "ml"
    
    # Verify Nandini GoodLife 1 Litre
    assert options[1]["variant_id"] == "milk-1l-spin"
    assert options[1]["item_name"] == "Nandini GoodLife Milk (1 litre)"
    assert options[1]["pack_size"] == "1 litre"
    assert options[1]["price"] == 54.5
    # price per unit = 54.5 / 1 = 54.5
    assert options[1]["price_per_unit"] == 54.5
    assert options[1]["unit"] == "litre"
    
    # Verify Amul Masti Spiced Buttermilk 200ml
    assert options[2]["variant_id"] == "buttermilk-200ml-spin"
    assert options[2]["item_name"] == "Amul Masti Spiced Buttermilk (200ml)"
    assert options[2]["pack_size"] == "200ml"
    assert options[2]["price"] == 15.0
    # price per unit = 15.0 / 200 = 0.075
    assert options[2]["price_per_unit"] == 0.075
    assert options[2]["unit"] == "ml"
