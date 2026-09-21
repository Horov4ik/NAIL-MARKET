import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CATEGORIES_FILE = os.path.join(DATA_DIR, "categories.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_categories():
    return _load_json(CATEGORIES_FILE, [])


def add_category(name):
    categories = get_categories()
    categories.append(name)
    _save_json(CATEGORIES_FILE, categories)
    return categories


def remove_category(index):
    categories = get_categories()
    if 0 <= index < len(categories):
        removed = categories.pop(index)
        _save_json(CATEGORIES_FILE, categories)
        return removed
    return None


def get_orders():
    return _load_json(ORDERS_FILE, [])


def save_order(order):
    orders = get_orders()
    order["id"] = (orders[-1]["id"] + 1) if orders else 1
    orders.append(order)
    _save_json(ORDERS_FILE, orders)
    return order["id"]
