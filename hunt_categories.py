"""User-editable hunt categories for Autopilot.

Persists a list of business types the user wants to hunt for.
Starts with equine defaults but the user can add categories for any product line
(SpillMaster → commercial cleanup; Pets → kennels/vets; AMR → fleet/marine; HouseHold → property mgmt).
"""

import json
from pathlib import Path

CATEGORIES_FILE = "hunt_categories.json"


# Defaults — broader than equine to match the full product catalog
DEFAULT_CATEGORIES = [
    # Equine (Duo Equine)
    {"type": "horse boarding facility", "product": "Duo Equine", "priority": 1, "active": True},
    {"type": "equestrian center", "product": "Duo Equine", "priority": 1, "active": True},
    {"type": "horse stable", "product": "Duo Equine", "priority": 2, "active": True},
    {"type": "horse rescue", "product": "Duo Equine", "priority": 2, "active": True},
    {"type": "horse trainer", "product": "Duo Equine", "priority": 3, "active": True},
    {"type": "horse breeder", "product": "Duo Equine", "priority": 3, "active": True},
    {"type": "tack shop", "product": "Duo Equine", "priority": 4, "active": False},
    {"type": "feed store", "product": "Duo Equine", "priority": 4, "active": False},

    # Pets (Pets product)
    {"type": "kennel", "product": "Pets", "priority": 2, "active": False},
    {"type": "animal shelter", "product": "Pets", "priority": 2, "active": False},
    {"type": "veterinary clinic", "product": "Pets", "priority": 3, "active": False},
    {"type": "grooming salon", "product": "Pets", "priority": 3, "active": False},
    {"type": "pet daycare", "product": "Pets", "priority": 3, "active": False},

    # SpillMaster
    {"type": "waste management company", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "industrial cleanup service", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "food processing facility", "product": "SpillMaster", "priority": 3, "active": False},

    # AMR (Auto/Marine/RV)
    {"type": "rv dealer", "product": "AMR", "priority": 2, "active": False},
    {"type": "marina", "product": "AMR", "priority": 2, "active": False},
    {"type": "rideshare fleet", "product": "AMR", "priority": 3, "active": False},
    {"type": "bus transit company", "product": "AMR", "priority": 3, "active": False},

    # HouseHold (commercial)
    {"type": "property management company", "product": "HouseHold", "priority": 3, "active": False},
    {"type": "airbnb cleaning service", "product": "HouseHold", "priority": 3, "active": False},
]


def load_categories():
    if not Path(CATEGORIES_FILE).exists():
        save_categories(DEFAULT_CATEGORIES)
        return list(DEFAULT_CATEGORIES)
    try:
        with open(CATEGORIES_FILE) as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return list(DEFAULT_CATEGORIES)


def save_categories(cats):
    try:
        with open(CATEGORIES_FILE, 'w') as f:
            json.dump(cats, f, indent=2)
        return True
    except Exception:
        return False


def add_category(business_type, product='', priority=3):
    cats = load_categories()
    if any(c['type'].lower() == business_type.lower() for c in cats):
        return False  # Already exists
    cats.append({
        'type': business_type,
        'product': product,
        'priority': priority,
        'active': True,
    })
    return save_categories(cats)


def update_category(index, **fields):
    cats = load_categories()
    if 0 <= index < len(cats):
        cats[index].update(fields)
        return save_categories(cats)
    return False


def delete_category(index):
    cats = load_categories()
    if 0 <= index < len(cats):
        cats.pop(index)
        return save_categories(cats)
    return False


def get_active_types():
    """Return just the active business-type strings (for autopilot to hunt)."""
    return [c['type'] for c in load_categories() if c.get('active')]


def reset():
    return save_categories(list(DEFAULT_CATEGORIES))
