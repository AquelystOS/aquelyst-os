"""User-editable hunt categories for Autopilot.

Persists a list of business types the user wants to hunt for.
Starts with equine defaults but the user can add categories for any product line
(SpillMaster → commercial cleanup; Pets → kennels/vets; AMR → fleet/marine; HouseHold → property mgmt).
"""

import json
from pathlib import Path

CATEGORIES_FILE = "hunt_categories.json"


# Defaults — comprehensive coverage across every product line.
# 50+ categories per product. Only a small subset are pre-active (Duo Equine top fits)
# so autopilot doesn't flood with every category by default.
def _cat(t, p, pr=3, active=False):
    return {"type": t, "product": p, "priority": pr, "active": active}


DEFAULT_CATEGORIES = [
    # ============ Duo Equine — equine biosecurity ============
    _cat("horse boarding facility", "Duo Equine", 1, active=True),
    _cat("equestrian center", "Duo Equine", 1, active=True),
    _cat("horse stable", "Duo Equine", 1, active=True),
    _cat("horse rescue", "Duo Equine", 2, active=True),
    _cat("horse trainer", "Duo Equine", 2),
    _cat("horse breeder", "Duo Equine", 2),
    _cat("thoroughbred farm", "Duo Equine", 1),
    _cat("standardbred farm", "Duo Equine", 1),
    _cat("quarter horse farm", "Duo Equine", 1),
    _cat("warmblood breeder", "Duo Equine", 2),
    _cat("pony breeder", "Duo Equine", 3),
    _cat("racing stable", "Duo Equine", 1),
    _cat("racetrack", "Duo Equine", 1),
    _cat("harness racing track", "Duo Equine", 1),
    _cat("polo club", "Duo Equine", 2),
    _cat("polo facility", "Duo Equine", 2),
    _cat("rodeo arena", "Duo Equine", 2),
    _cat("rodeo grounds", "Duo Equine", 2),
    _cat("riding school", "Duo Equine", 2),
    _cat("riding academy", "Duo Equine", 2),
    _cat("dressage center", "Duo Equine", 2),
    _cat("show jumping facility", "Duo Equine", 2),
    _cat("eventing facility", "Duo Equine", 2),
    _cat("hunter jumper barn", "Duo Equine", 2),
    _cat("western pleasure barn", "Duo Equine", 3),
    _cat("reining facility", "Duo Equine", 3),
    _cat("cutting horse facility", "Duo Equine", 3),
    _cat("barrel racing facility", "Duo Equine", 3),
    _cat("draft horse farm", "Duo Equine", 3),
    _cat("equine veterinary clinic", "Duo Equine", 2),
    _cat("equine vet hospital", "Duo Equine", 2),
    _cat("equine reproduction center", "Duo Equine", 2),
    _cat("equine reproductive vet", "Duo Equine", 3),
    _cat("equine dentistry", "Duo Equine", 3),
    _cat("equine chiropractor", "Duo Equine", 4),
    _cat("equine massage therapist", "Duo Equine", 4),
    _cat("equine therapy center", "Duo Equine", 3),
    _cat("therapeutic riding program", "Duo Equine", 3),
    _cat("hippotherapy center", "Duo Equine", 3),
    _cat("horse rehabilitation center", "Duo Equine", 2),
    _cat("horse retirement facility", "Duo Equine", 2),
    _cat("horse sanctuary", "Duo Equine", 2),
    _cat("horse show venue", "Duo Equine", 3),
    _cat("horse expo center", "Duo Equine", 3),
    _cat("trail riding company", "Duo Equine", 3),
    _cat("dude ranch", "Duo Equine", 2),
    _cat("guest ranch", "Duo Equine", 2),
    _cat("pony club", "Duo Equine", 4),
    _cat("4-h horse program", "Duo Equine", 4),
    _cat("collegiate equestrian team", "Duo Equine", 4),
    _cat("vaulting club", "Duo Equine", 4),
    _cat("foxhunting club", "Duo Equine", 4),
    _cat("carriage driving facility", "Duo Equine", 4),
    _cat("combined driving facility", "Duo Equine", 4),
    _cat("mounted police unit", "Duo Equine", 3),
    _cat("horse hauler", "Duo Equine", 4),
    _cat("horse transporter", "Duo Equine", 4),
    _cat("horse trailer dealer", "Duo Equine", 4),
    _cat("horse trailer service", "Duo Equine", 4),
    _cat("tack shop", "Duo Equine", 4),
    _cat("feed store", "Duo Equine", 4),
    _cat("saddle fitter", "Duo Equine", 4),
    _cat("horse insurance company", "Duo Equine", 4),
    _cat("equine pharmaceutical supplier", "Duo Equine", 4),
    _cat("mule farm", "Duo Equine", 4),
    _cat("donkey rescue", "Duo Equine", 3),
    _cat("zebra/exotic equid facility", "Duo Equine", 4),

    # ============ Pets — kennels, vets, shelters, multi-pet facilities ============
    _cat("kennel", "Pets", 1),
    _cat("dog boarding facility", "Pets", 1),
    _cat("cat boarding facility", "Pets", 2),
    _cat("doggy daycare", "Pets", 1),
    _cat("pet hotel", "Pets", 1),
    _cat("luxury pet resort", "Pets", 2),
    _cat("animal shelter", "Pets", 1),
    _cat("humane society", "Pets", 1),
    _cat("animal rescue", "Pets", 1),
    _cat("breed-specific rescue", "Pets", 2),
    _cat("foster network", "Pets", 3),
    _cat("veterinary clinic", "Pets", 2),
    _cat("veterinary hospital", "Pets", 2),
    _cat("emergency vet hospital", "Pets", 2),
    _cat("veterinary specialty clinic", "Pets", 2),
    _cat("vet referral center", "Pets", 3),
    _cat("mobile vet", "Pets", 3),
    _cat("holistic vet", "Pets", 3),
    _cat("exotic pet vet", "Pets", 3),
    _cat("avian vet", "Pets", 4),
    _cat("spay neuter clinic", "Pets", 2),
    _cat("low cost vet", "Pets", 3),
    _cat("grooming salon", "Pets", 2),
    _cat("mobile groomer", "Pets", 3),
    _cat("self-serve dog wash", "Pets", 3),
    _cat("dog training facility", "Pets", 2),
    _cat("agility training facility", "Pets", 3),
    _cat("protection dog training", "Pets", 3),
    _cat("service dog training", "Pets", 3),
    _cat("guide dog school", "Pets", 3),
    _cat("police K9 unit", "Pets", 3),
    _cat("military working dog kennel", "Pets", 3),
    _cat("pet store", "Pets", 3),
    _cat("specialty pet retailer", "Pets", 3),
    _cat("aquarium store", "Pets", 4),
    _cat("reptile store", "Pets", 4),
    _cat("bird shop", "Pets", 4),
    _cat("dog park", "Pets", 4),
    _cat("pet-friendly cafe", "Pets", 4),
    _cat("dog walker service", "Pets", 4),
    _cat("pet sitter agency", "Pets", 4),
    _cat("pet rescue transport", "Pets", 4),
    _cat("zoo", "Pets", 3),
    _cat("aquarium", "Pets", 3),
    _cat("petting zoo", "Pets", 3),
    _cat("wildlife rehabilitation center", "Pets", 3),
    _cat("exotic animal sanctuary", "Pets", 3),
    _cat("pet cemetery", "Pets", 4),
    _cat("pet crematorium", "Pets", 4),
    _cat("pet ambulance", "Pets", 4),
    _cat("animal control facility", "Pets", 3),

    # ============ SpillMaster — commercial cleanup, food, healthcare, transit ============
    _cat("waste management company", "SpillMaster", 1),
    _cat("industrial cleanup service", "SpillMaster", 1),
    _cat("hazmat cleanup contractor", "SpillMaster", 1),
    _cat("environmental remediation", "SpillMaster", 1),
    _cat("biohazard cleanup company", "SpillMaster", 1),
    _cat("crime scene cleanup", "SpillMaster", 2),
    _cat("food processing facility", "SpillMaster", 2),
    _cat("meat processing plant", "SpillMaster", 1),
    _cat("poultry processing plant", "SpillMaster", 1),
    _cat("seafood processing plant", "SpillMaster", 2),
    _cat("dairy processing plant", "SpillMaster", 2),
    _cat("cheese maker", "SpillMaster", 3),
    _cat("ice cream factory", "SpillMaster", 3),
    _cat("brewery", "SpillMaster", 3),
    _cat("winery", "SpillMaster", 3),
    _cat("distillery", "SpillMaster", 3),
    _cat("juice processing facility", "SpillMaster", 3),
    _cat("bottling plant", "SpillMaster", 3),
    _cat("canning facility", "SpillMaster", 3),
    _cat("bakery", "SpillMaster", 3),
    _cat("commercial kitchen", "SpillMaster", 3),
    _cat("catering company", "SpillMaster", 3),
    _cat("restaurant chain", "SpillMaster", 3),
    _cat("ghost kitchen", "SpillMaster", 4),
    _cat("food truck commissary", "SpillMaster", 4),
    _cat("grocery distribution center", "SpillMaster", 2),
    _cat("hospital", "SpillMaster", 1),
    _cat("nursing home", "SpillMaster", 2),
    _cat("assisted living facility", "SpillMaster", 2),
    _cat("memory care facility", "SpillMaster", 3),
    _cat("urgent care center", "SpillMaster", 3),
    _cat("dialysis center", "SpillMaster", 3),
    _cat("blood bank", "SpillMaster", 3),
    _cat("medical clinic", "SpillMaster", 3),
    _cat("dental clinic", "SpillMaster", 4),
    _cat("veterinary hospital (large)", "SpillMaster", 3),
    _cat("ambulance service", "SpillMaster", 3),
    _cat("mortuary funeral home", "SpillMaster", 3),
    _cat("crematorium", "SpillMaster", 3),
    _cat("pharmaceutical manufacturer", "SpillMaster", 2),
    _cat("biotech facility", "SpillMaster", 3),
    _cat("diagnostic laboratory", "SpillMaster", 3),
    _cat("research facility", "SpillMaster", 3),
    _cat("medical device manufacturer", "SpillMaster", 3),
    _cat("school district", "SpillMaster", 3),
    _cat("university food service", "SpillMaster", 3),
    _cat("university facilities", "SpillMaster", 3),
    _cat("daycare center", "SpillMaster", 4),
    _cat("correctional facility", "SpillMaster", 3),
    _cat("jail or detention center", "SpillMaster", 3),
    _cat("manufacturing plant", "SpillMaster", 2),
    _cat("chemical plant", "SpillMaster", 3),
    _cat("textile mill", "SpillMaster", 4),
    _cat("printing facility", "SpillMaster", 4),
    _cat("recycling facility", "SpillMaster", 3),
    _cat("composting facility", "SpillMaster", 3),
    _cat("water treatment plant", "SpillMaster", 3),
    _cat("sewage treatment plant", "SpillMaster", 3),
    _cat("landfill", "SpillMaster", 3),
    _cat("airport", "SpillMaster", 3),
    _cat("public transit authority", "SpillMaster", 3),
    _cat("port authority", "SpillMaster", 3),
    _cat("military base", "SpillMaster", 3),
    _cat("convention center", "SpillMaster", 3),
    _cat("stadium or arena", "SpillMaster", 3),
    _cat("hotel chain operator", "SpillMaster", 3),
    _cat("casino", "SpillMaster", 3),

    # ============ AMR — Auto / Marine / RV / Aviation / Mass Transit ============
    _cat("car dealership", "AMR", 2),
    _cat("used car dealer", "AMR", 3),
    _cat("luxury car dealer", "AMR", 2),
    _cat("truck dealer", "AMR", 2),
    _cat("semi-truck dealer", "AMR", 2),
    _cat("tractor or farm equipment dealer", "AMR", 3),
    _cat("motorcycle dealer", "AMR", 3),
    _cat("powersports dealer", "AMR", 3),
    _cat("atv utv dealer", "AMR", 4),
    _cat("snowmobile dealer", "AMR", 4),
    _cat("auto detail shop", "AMR", 2),
    _cat("car wash", "AMR", 3),
    _cat("mobile detailing service", "AMR", 3),
    _cat("tow truck company", "AMR", 4),
    _cat("auto body shop", "AMR", 3),
    _cat("car restoration shop", "AMR", 4),
    _cat("rv dealer", "AMR", 1),
    _cat("rv park", "AMR", 2),
    _cat("rv rental company", "AMR", 2),
    _cat("rv repair facility", "AMR", 3),
    _cat("campground", "AMR", 3),
    _cat("marina", "AMR", 1),
    _cat("yacht club", "AMR", 2),
    _cat("boat dealer", "AMR", 2),
    _cat("boat rental company", "AMR", 2),
    _cat("boat repair yard", "AMR", 3),
    _cat("ship yard", "AMR", 3),
    _cat("charter boat company", "AMR", 3),
    _cat("charter fishing company", "AMR", 3),
    _cat("houseboat rental", "AMR", 3),
    _cat("jet ski dealer", "AMR", 4),
    _cat("pontoon dealer", "AMR", 4),
    _cat("ferry operator", "AMR", 3),
    _cat("cruise line", "AMR", 3),
    _cat("rideshare fleet", "AMR", 2),
    _cat("limo service", "AMR", 3),
    _cat("taxi company", "AMR", 3),
    _cat("party bus operator", "AMR", 3),
    _cat("school bus operator", "AMR", 2),
    _cat("city bus transit", "AMR", 2),
    _cat("regional bus line", "AMR", 3),
    _cat("charter bus company", "AMR", 3),
    _cat("airport shuttle service", "AMR", 3),
    _cat("hotel shuttle service", "AMR", 3),
    _cat("hearse funeral fleet", "AMR", 4),
    _cat("truck stop", "AMR", 3),
    _cat("trucking company", "AMR", 2),
    _cat("freight company", "AMR", 3),
    _cat("delivery fleet", "AMR", 2),
    _cat("amazon delivery service partner", "AMR", 2),
    _cat("food delivery fleet", "AMR", 3),
    _cat("waste hauler", "AMR", 3),
    _cat("moving company", "AMR", 3),
    _cat("rental car company", "AMR", 3),
    _cat("rental truck company", "AMR", 3),
    _cat("rental rv company", "AMR", 2),
    _cat("aviation flight school", "AMR", 3),
    _cat("private jet operator", "AMR", 3),
    _cat("fbo aircraft hangar", "AMR", 3),
    _cat("helicopter charter", "AMR", 4),
    _cat("aircraft maintenance facility", "AMR", 3),
    _cat("food truck operator", "AMR", 4),
    _cat("ice cream truck fleet", "AMR", 4),
    _cat("valet service", "AMR", 4),
    _cat("parking garage operator", "AMR", 4),

    # ============ HouseHold — residential & residential-adjacent commercial ============
    _cat("property management company", "HouseHold", 2),
    _cat("airbnb cleaning service", "HouseHold", 2),
    _cat("vacation rental management", "HouseHold", 2),
    _cat("short-term rental property mgr", "HouseHold", 2),
    _cat("corporate housing provider", "HouseHold", 3),
    _cat("hoa", "HouseHold", 3),
    _cat("apartment complex", "HouseHold", 2),
    _cat("condo association", "HouseHold", 3),
    _cat("townhouse community", "HouseHold", 3),
    _cat("luxury rental community", "HouseHold", 3),
    _cat("senior living facility", "HouseHold", 2),
    _cat("retirement community", "HouseHold", 2),
    _cat("group home operator", "HouseHold", 3),
    _cat("boarding house", "HouseHold", 4),
    _cat("co-living operator", "HouseHold", 4),
    _cat("student housing manager", "HouseHold", 3),
    _cat("university housing", "HouseHold", 3),
    _cat("military housing provider", "HouseHold", 3),
    _cat("house cleaning service", "HouseHold", 2),
    _cat("maid service", "HouseHold", 2),
    _cat("janitorial service", "HouseHold", 2),
    _cat("commercial cleaning company", "HouseHold", 2),
    _cat("post-construction cleanup", "HouseHold", 3),
    _cat("move-in move-out cleaning", "HouseHold", 3),
    _cat("estate cleaning service", "HouseHold", 4),
    _cat("hoarder cleanup specialist", "HouseHold", 3),
    _cat("biohazard residential cleanup", "HouseHold", 3),
    _cat("mold remediation company", "HouseHold", 2),
    _cat("water damage restoration", "HouseHold", 2),
    _cat("fire damage restoration", "HouseHold", 3),
    _cat("smoke damage restoration", "HouseHold", 3),
    _cat("sewage cleanup service", "HouseHold", 3),
    _cat("odor remediation specialist", "HouseHold", 2),
    _cat("pet odor specialist", "HouseHold", 2),
    _cat("pest control company", "HouseHold", 3),
    _cat("carpet cleaning service", "HouseHold", 3),
    _cat("upholstery cleaning service", "HouseHold", 4),
    _cat("mattress cleaning service", "HouseHold", 4),
    _cat("window cleaning company", "HouseHold", 4),
    _cat("pressure washing service", "HouseHold", 4),
    _cat("gutter cleaning service", "HouseHold", 4),
    _cat("chimney sweep", "HouseHold", 4),
    _cat("duct cleaning service", "HouseHold", 3),
    _cat("crawl space encapsulation", "HouseHold", 3),
    _cat("attic cleaning service", "HouseHold", 4),
    _cat("basement remediation", "HouseHold", 3),
    _cat("indoor air quality consultant", "HouseHold", 3),
    _cat("residential mold inspector", "HouseHold", 3),
    _cat("real estate brokerage", "HouseHold", 4),
    _cat("home inspector", "HouseHold", 4),
    _cat("real estate photographer", "HouseHold", 4),

    # ============ Inversion Misting System — large-facility custom installs ============
    _cat("warehouse distribution center", "Inversion Misting", 2),
    _cat("cold storage facility", "Inversion Misting", 2),
    _cat("food storage warehouse", "Inversion Misting", 2),
    _cat("large manufacturing plant", "Inversion Misting", 2),
    _cat("agricultural processing", "Inversion Misting", 2),
    _cat("fruit packing house", "Inversion Misting", 3),
    _cat("vegetable processing facility", "Inversion Misting", 3),
    _cat("meat locker", "Inversion Misting", 3),
    _cat("rendering plant", "Inversion Misting", 2),
    _cat("pet food manufacturer", "Inversion Misting", 2),
    _cat("animal feed manufacturer", "Inversion Misting", 2),
    _cat("grain elevator", "Inversion Misting", 3),
    _cat("silo or grain storage", "Inversion Misting", 3),
    _cat("ethanol plant", "Inversion Misting", 3),
    _cat("biodiesel plant", "Inversion Misting", 4),
    _cat("composting site (large)", "Inversion Misting", 3),
    _cat("agricultural fairground", "Inversion Misting", 3),
    _cat("livestock auction barn", "Inversion Misting", 2),
    _cat("poultry farm", "Inversion Misting", 1),
    _cat("broiler farm", "Inversion Misting", 1),
    _cat("layer hen facility", "Inversion Misting", 1),
    _cat("turkey farm", "Inversion Misting", 1),
    _cat("duck farm", "Inversion Misting", 2),
    _cat("dairy farm", "Inversion Misting", 1),
    _cat("goat dairy", "Inversion Misting", 2),
    _cat("sheep farm", "Inversion Misting", 2),
    _cat("swine operation", "Inversion Misting", 1),
    _cat("hog farm", "Inversion Misting", 1),
    _cat("feedlot", "Inversion Misting", 1),
    _cat("cattle ranch", "Inversion Misting", 2),
    _cat("beef cattle operation", "Inversion Misting", 2),
    _cat("aquaculture facility", "Inversion Misting", 3),
    _cat("fish farm", "Inversion Misting", 3),
    _cat("mushroom farm", "Inversion Misting", 4),
    _cat("commercial greenhouse", "Inversion Misting", 3),
    _cat("hydroponic greenhouse", "Inversion Misting", 3),
    _cat("commercial nursery", "Inversion Misting", 3),
    _cat("cannabis cultivation facility", "Inversion Misting", 3),
    _cat("large indoor equestrian arena", "Inversion Misting", 3),
    _cat("large dairy parlor", "Inversion Misting", 2),
    _cat("seed processor", "Inversion Misting", 4),
    _cat("nut processor", "Inversion Misting", 4),
    _cat("citrus processor", "Inversion Misting", 4),
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
