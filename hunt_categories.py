"""User-editable hunt categories for Autopilot.

Persists a list of business types the user wants to hunt for.
Starts with equine defaults but the user can add categories for any product line
(SpillMaster → commercial cleanup; Pets → kennels/vets; AMR → fleet/marine; HouseHold → property mgmt).
"""

import json
from pathlib import Path

CATEGORIES_FILE = "hunt_categories.json"


# Defaults — broad coverage across every product line
DEFAULT_CATEGORIES = [
    # ============ Duo Equine — equine biosecurity ============
    {"type": "horse boarding facility", "product": "Duo Equine", "priority": 1, "active": True},
    {"type": "equestrian center", "product": "Duo Equine", "priority": 1, "active": True},
    {"type": "horse stable", "product": "Duo Equine", "priority": 1, "active": True},
    {"type": "horse rescue", "product": "Duo Equine", "priority": 2, "active": True},
    {"type": "horse trainer", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "horse breeder", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "thoroughbred farm", "product": "Duo Equine", "priority": 1, "active": False},
    {"type": "racing stable", "product": "Duo Equine", "priority": 1, "active": False},
    {"type": "racetrack", "product": "Duo Equine", "priority": 1, "active": False},
    {"type": "polo club", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "rodeo arena", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "riding school", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "riding academy", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "dressage center", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "show jumping facility", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "equine veterinary clinic", "product": "Duo Equine", "priority": 2, "active": False},
    {"type": "equine therapy center", "product": "Duo Equine", "priority": 3, "active": False},
    {"type": "horse show venue", "product": "Duo Equine", "priority": 3, "active": False},
    {"type": "trail riding company", "product": "Duo Equine", "priority": 3, "active": False},
    {"type": "horse trailer dealer", "product": "Duo Equine", "priority": 4, "active": False},
    {"type": "tack shop", "product": "Duo Equine", "priority": 4, "active": False},
    {"type": "feed store", "product": "Duo Equine", "priority": 4, "active": False},

    # ============ Pets — kennels, vets, shelters, multi-pet ============
    {"type": "kennel", "product": "Pets", "priority": 1, "active": False},
    {"type": "dog boarding facility", "product": "Pets", "priority": 1, "active": False},
    {"type": "doggy daycare", "product": "Pets", "priority": 1, "active": False},
    {"type": "animal shelter", "product": "Pets", "priority": 1, "active": False},
    {"type": "humane society", "product": "Pets", "priority": 1, "active": False},
    {"type": "veterinary clinic", "product": "Pets", "priority": 2, "active": False},
    {"type": "emergency vet hospital", "product": "Pets", "priority": 2, "active": False},
    {"type": "exotic pet vet", "product": "Pets", "priority": 3, "active": False},
    {"type": "spay neuter clinic", "product": "Pets", "priority": 2, "active": False},
    {"type": "grooming salon", "product": "Pets", "priority": 2, "active": False},
    {"type": "mobile groomer", "product": "Pets", "priority": 3, "active": False},
    {"type": "dog training facility", "product": "Pets", "priority": 2, "active": False},
    {"type": "pet store", "product": "Pets", "priority": 3, "active": False},
    {"type": "dog park", "product": "Pets", "priority": 4, "active": False},
    {"type": "breed-specific rescue", "product": "Pets", "priority": 2, "active": False},
    {"type": "aquarium store", "product": "Pets", "priority": 4, "active": False},
    {"type": "reptile store", "product": "Pets", "priority": 4, "active": False},

    # ============ SpillMaster — commercial cleanup, food, healthcare, transit ============
    {"type": "waste management company", "product": "SpillMaster", "priority": 1, "active": False},
    {"type": "industrial cleanup service", "product": "SpillMaster", "priority": 1, "active": False},
    {"type": "hazmat cleanup contractor", "product": "SpillMaster", "priority": 1, "active": False},
    {"type": "food processing facility", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "meat processing plant", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "dairy processing plant", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "brewery", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "winery", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "distillery", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "commercial kitchen", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "catering company", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "hospital", "product": "SpillMaster", "priority": 1, "active": False},
    {"type": "nursing home", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "assisted living facility", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "urgent care center", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "dental clinic", "product": "SpillMaster", "priority": 4, "active": False},
    {"type": "school district", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "university food service", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "correctional facility", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "manufacturing plant", "product": "SpillMaster", "priority": 2, "active": False},
    {"type": "chemical plant", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "airport", "product": "SpillMaster", "priority": 3, "active": False},
    {"type": "public transit authority", "product": "SpillMaster", "priority": 3, "active": False},

    # ============ AMR — Auto/Marine/RV/Aviation/Mass Transit ============
    {"type": "rv dealer", "product": "AMR", "priority": 1, "active": False},
    {"type": "rv park", "product": "AMR", "priority": 2, "active": False},
    {"type": "campground", "product": "AMR", "priority": 3, "active": False},
    {"type": "marina", "product": "AMR", "priority": 1, "active": False},
    {"type": "yacht club", "product": "AMR", "priority": 2, "active": False},
    {"type": "boat dealer", "product": "AMR", "priority": 2, "active": False},
    {"type": "charter boat company", "product": "AMR", "priority": 3, "active": False},
    {"type": "car dealership", "product": "AMR", "priority": 2, "active": False},
    {"type": "auto detail shop", "product": "AMR", "priority": 2, "active": False},
    {"type": "car wash", "product": "AMR", "priority": 3, "active": False},
    {"type": "rideshare fleet", "product": "AMR", "priority": 2, "active": False},
    {"type": "limo service", "product": "AMR", "priority": 3, "active": False},
    {"type": "taxi company", "product": "AMR", "priority": 3, "active": False},
    {"type": "school bus operator", "product": "AMR", "priority": 2, "active": False},
    {"type": "bus transit company", "product": "AMR", "priority": 2, "active": False},
    {"type": "truck stop", "product": "AMR", "priority": 3, "active": False},
    {"type": "trucking company", "product": "AMR", "priority": 2, "active": False},
    {"type": "delivery fleet", "product": "AMR", "priority": 2, "active": False},
    {"type": "moving company", "product": "AMR", "priority": 3, "active": False},
    {"type": "rental car company", "product": "AMR", "priority": 3, "active": False},
    {"type": "powersports dealer", "product": "AMR", "priority": 4, "active": False},
    {"type": "aviation flight school", "product": "AMR", "priority": 3, "active": False},
    {"type": "private jet operator", "product": "AMR", "priority": 3, "active": False},
    {"type": "fbo aircraft hangar", "product": "AMR", "priority": 3, "active": False},

    # ============ HouseHold — residential & residential-adjacent commercial ============
    {"type": "property management company", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "airbnb cleaning service", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "vacation rental management", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "hoa", "product": "HouseHold", "priority": 3, "active": False},
    {"type": "apartment complex", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "condo association", "product": "HouseHold", "priority": 3, "active": False},
    {"type": "senior living facility", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "house cleaning service", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "mold remediation company", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "pest control company", "product": "HouseHold", "priority": 3, "active": False},
    {"type": "carpet cleaning service", "product": "HouseHold", "priority": 3, "active": False},
    {"type": "water damage restoration", "product": "HouseHold", "priority": 2, "active": False},
    {"type": "fire damage restoration", "product": "HouseHold", "priority": 3, "active": False},
    {"type": "real estate brokerage", "product": "HouseHold", "priority": 4, "active": False},

    # ============ Inversion Misting System — large-facility custom installs ============
    {"type": "warehouse distribution center", "product": "Inversion Misting", "priority": 2, "active": False},
    {"type": "large manufacturing plant", "product": "Inversion Misting", "priority": 2, "active": False},
    {"type": "agricultural processing", "product": "Inversion Misting", "priority": 2, "active": False},
    {"type": "poultry farm", "product": "Inversion Misting", "priority": 1, "active": False},
    {"type": "dairy farm", "product": "Inversion Misting", "priority": 1, "active": False},
    {"type": "swine operation", "product": "Inversion Misting", "priority": 1, "active": False},
    {"type": "feedlot", "product": "Inversion Misting", "priority": 1, "active": False},
    {"type": "commercial greenhouse", "product": "Inversion Misting", "priority": 3, "active": False},
    {"type": "commercial nursery", "product": "Inversion Misting", "priority": 3, "active": False},
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
