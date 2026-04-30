"""Product catalog — gives the sales bot a list of products it can recommend
and link to during conversations.

When the bot writes an email, it pulls from this catalog so it can naturally
say things like "if you want to check out the trailer kit, here's the page: ..."
"""

import json
from pathlib import Path

CATALOG_FILE = "product_catalog.json"


# Default catalog — REAL AqueLyst products. Joseph can edit/add/remove via Setup → Products.
DEFAULT_PRODUCTS = [
    {
        'name': 'Duo Equine — Odor Eliminator & Fly Control',
        'short_description': (
            'Patented molecular converter for barns, stalls, trailers, equine biosecurity, '
            'and livestock housing of any kind (chicken coops, dairy parlors, hog barns, '
            'feedlots, sheep & goat operations). Eliminates ammonia at the source and '
            'reduces fly-attracting compounds.'
        ),
        'long_description': (
            'Built for the equine world and any animal-housing environment that produces '
            'manure, urine, and ammonia odors — designed with one mission: ensure animals '
            'on the farm or facility are SAFE while eliminating odors at the source. '
            'Powered by patented Remedia International technology trusted by the EPA. '
            'A molecular converter that targets odor-causing compounds at their source: '
            'urine, manure, ammonia, wet bedding, fly-attracting organic waste. '
            'Used in horse stalls, barn aisles, tack rooms, trailers, run-in sheds, '
            'high-traffic barn areas, AND in chicken coops/hen houses, broiler & layer '
            'operations, turkey/duck farms, dairy parlors, hog/swine barns, sheep & goat '
            'pens, cattle feedlots, and any commercial livestock housing. Available in 1, '
            '5, and 55 gallon sizes. Inversion misting system available for facility-wide '
            'application across stall rows, coops, and barn aisles.'
        ),
        'price': '$62.50 (1 gal) · 5 gal & 55 gal also available',
        'url': 'https://aquelyst.com/products/duo-equine',
        'best_for': (
            'horse boarding facilities, equestrian centers, stables, trainers, breeders, '
            'rescues, tack shops, feed stores, chicken coops, poultry farms (broiler/layer), '
            'turkey & duck farms, dairy parlors, hog/swine barns, sheep & goat operations, '
            'cattle feedlots — PRIMARY product whenever the question is about animal '
            'manure / ammonia / fly odor in housing'
        ),
        'is_lead_magnet': True,
    },
    {
        'name': 'SpillMaster (SM) — Spill, Waste & Industrial-Grade Odor Eliminator',
        'short_description': (
            'Non-toxic molecular converter for spill cleanup, hazardous-residue remediation, '
            'PCB-contaminated environments, waste areas, and high-impact industrial spaces. '
            'Resolves odors at the source — not masking.'
        ),
        'long_description': (
            'Engineered for professional spill response, hazardous-residue remediation, '
            'and routine industrial cleanup. Patented Remedia International technology. '
            'Effective on organic spills, food spoilage, bodily fluids, trash rooms, '
            'dumpsters, transportation/logistics cleanup, PCB-contaminated zones, '
            'transformer-oil residue, hazardous-waste handling areas, oil-spill response '
            'sites, biohazard / crime-scene environments, mold/fire damage remediation. '
            'Safe for use while people are present. Suitable for commercial facilities, '
            'food service/processing, healthcare, public spaces, transit hubs, waste '
            'management, water-treatment plants, sewage operations, rendering plants, '
            'grain elevators, and industrial-cleanup operations. Available in 1, 5, and '
            '55 gallon sizes. Inversion misting available for large facilities.'
        ),
        'price': '$75.00 (1 gal) · 5 gal & 55 gal also available',
        'url': 'https://aquelyst.com/products/spillmaster',
        'best_for': (
            'PCB control & remediation, oil & chemical spill response, hazmat/biohazard '
            'cleanup, mold & fire-damage restoration, food service/processing, healthcare, '
            'transit hubs, waste management, water treatment, sewage operations, rendering '
            'plants, grain elevators, industrial cleanup operations'
        ),
        'is_lead_magnet': False,
    },
    {
        'name': 'Pets (P) — Home, Kennel & Animal-Space Odor Eliminator',
        'short_description': (
            'Non-toxic, pet-safe molecular converter for the spaces animals live in every day. '
            'No fragrances, no harsh chemicals.'
        ),
        'long_description': (
            'Pet-safe odor elimination at the source. Designed for environments where animals '
            'are present continuously and odor sensitivity is high. Effective on pet urine, '
            'feces, litter areas, kennels, crates, pet bedding, carpets, upholstery, '
            'multi-pet households. Safe for dogs, cats, and other household animals when used '
            'as directed. Suitable for homes, kennels, boarding facilities, shelters, grooming '
            'salons, vet environments, pet daycares, training facilities. '
            'Available in 1, 5, and 55 gallon sizes. Inversion misting available for kennels.'
        ),
        'price': '$46.50 (1 gal) · 5 gal & 55 gal also available',
        'url': 'https://aquelyst.com/products/pets',
        'best_for': (
            'pet owners, kennels, animal shelters, vet clinics, grooming salons, '
            'pet daycares, training facilities, multi-pet households'
        ),
        'is_lead_magnet': False,
    },
    {
        'name': 'HouseHold (H) — Everyday Living-Space Odor Eliminator',
        'short_description': (
            'Non-toxic, family-safe molecular converter for residential odor control. '
            'No perfumes, no aerosols, no chemical residue.'
        ),
        'long_description': (
            'Designed for residential environments. Eliminates odor-causing compounds at the '
            'source rather than masking. Effective on pet accidents, trash/recycling/food waste, '
            'kitchens, refrigerators, bathrooms, drains, moisture-prone spaces, carpets, '
            'upholstery, basements, laundry rooms. Safe for people and pets when used as directed. '
            'Practical alternative to chemical sprays and fragranced deodorizers. '
            'Available in 1, 5, and 55 gallon sizes.'
        ),
        'price': '$38.50 (1 gal) · 5 gal & 55 gal also available',
        'url': 'https://aquelyst.com/products/household',
        'best_for': (
            'homeowners, apartment dwellers, families with kids/pets, '
            'fragrance-sensitive households, daily home maintenance'
        ),
        'is_lead_magnet': False,
    },
    {
        'name': 'AMR — Auto / Marine / RV / Aviation / Mass Transit Odor Eliminator',
        'short_description': (
            'Advanced molecular converter for vehicles, vessels, and large passenger transport. '
            'Eliminates odors at the source in enclosed, high-traffic spaces.'
        ),
        'long_description': (
            'Built for transport environments where ventilation is limited, passenger turnover '
            'is high, and moisture/condensation is common. Effective on automotive interiors, '
            'RV living areas/bathrooms, marine cabins/bilges, aircraft cabins/cargo, buses, '
            'shuttles, mass transit, trains, railcars, cruise ships and passenger vessels. '
            'Addresses smoke, food, trash, moisture-related odors, organic residue. '
            'Safe for interiors, fabrics, and surfaces. Suitable for fleet, rideshare, aviation, '
            'public transit, cruise lines, RVs/campers. '
            'Available in 1, 5, and 55 gallon sizes. Inversion misting for large vessels.'
        ),
        'price': '$36.99 (1 gal) · 5 gal & 55 gal also available',
        'url': 'https://aquelyst.com/products/amr',
        'best_for': (
            'rideshare/fleet operators, marine/boat owners, RV owners, aviation, '
            'transit authorities, cruise lines, ferry operators'
        ),
        'is_lead_magnet': False,
    },
    {
        'name': 'Inversion Misting System (Large-Area Facility Coverage)',
        'short_description': (
            'Automated inversion misting setup for large facilities — works with all '
            'AqueLyst molecular converter products (Duo Equine, SpillMaster, Pets, HouseHold, AMR).'
        ),
        'long_description': (
            'Hands-off, scheduled misting for large-area applications. Compatible with the '
            'full AqueLyst product line. Ideal for full-barn coverage, multi-stall facilities, '
            'large kennels, commercial cleanup zones, large vessel interiors, warehouses. '
            'Reduces manual application labor while maintaining consistent molecular-level '
            'odor elimination. Contact for sizing + custom quote.'
        ),
        'price': 'Custom — contact for quote',
        'url': 'https://aquelyst.com/products/misting-system',
        'best_for': (
            'large equestrian centers, commercial kennels/shelters, industrial cleanup '
            'operations, large vessels (cruise/ferry), warehouses, multi-zone facilities'
        ),
        'is_lead_magnet': False,
    },
]


def load_catalog():
    """Load catalog from disk; falls back to defaults on first run."""
    if not Path(CATALOG_FILE).exists():
        save_catalog(DEFAULT_PRODUCTS)
        return list(DEFAULT_PRODUCTS)
    try:
        with open(CATALOG_FILE) as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return list(DEFAULT_PRODUCTS)


def save_catalog(products):
    """Persist catalog."""
    try:
        with open(CATALOG_FILE, 'w') as f:
            json.dump(products, f, indent=2)
        return True
    except Exception:
        return False


def add_product(name, short_description, url, price='', long_description='',
                  best_for='', is_lead_magnet=False):
    """Append a product."""
    catalog = load_catalog()
    catalog.append({
        'name': name,
        'short_description': short_description,
        'long_description': long_description,
        'price': price,
        'url': url,
        'best_for': best_for,
        'is_lead_magnet': is_lead_magnet,
    })
    return save_catalog(catalog)


def update_product(index, **fields):
    """Update a product by index."""
    catalog = load_catalog()
    if 0 <= index < len(catalog):
        catalog[index].update(fields)
        return save_catalog(catalog)
    return False


def delete_product(index):
    """Remove a product by index."""
    catalog = load_catalog()
    if 0 <= index < len(catalog):
        catalog.pop(index)
        return save_catalog(catalog)
    return False


def reset_catalog():
    """Restore defaults."""
    return save_catalog(list(DEFAULT_PRODUCTS))


def format_for_bot_prompt():
    """Render the catalog as a system-prompt-friendly text block.
    Used by NEPQ engine so the bot knows what to recommend and where to link."""
    catalog = load_catalog()
    if not catalog:
        return ""

    lines = ["## PRODUCTS YOU CAN REFERENCE (use these URLs when relevant)"]

    # Highlight any lead magnet (trial) first
    lead_magnets = [p for p in catalog if p.get('is_lead_magnet')]
    others = [p for p in catalog if not p.get('is_lead_magnet')]

    for product in lead_magnets + others:
        magnet_tag = " ⭐ MAIN CTA — offer this first" if product.get('is_lead_magnet') else ""
        lines.append(f"\n**{product['name']}**{magnet_tag}")
        if product.get('short_description'):
            lines.append(f"- What it is: {product['short_description']}")
        if product.get('best_for'):
            lines.append(f"- Best for: {product['best_for']}")
        if product.get('price'):
            lines.append(f"- Price: {product['price']}")
        if product.get('url'):
            lines.append(f"- Link: {product['url']}")

    lines.append("""
## HOW TO USE PRODUCT LINKS IN MESSAGES
- The 7-day trial is your primary CTA — offer it whenever appropriate
- Only link to a product when it's the natural next step in the conversation
- Phrase it casually: "If you want to take a look, here's the page: [link]"
- Don't dump multiple links in one email
- The link text itself should not be the entire CTA — keep the question/conversation flow first
""")

    return "\n".join(lines)
