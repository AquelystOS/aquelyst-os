"""High-Probability Need Intelligence Layer.

Maps business types to SIC/NAICS codes, infers environmental burden indicators
(odor / ammonia / fly / sanitation / microbial / runoff probability), and
auto-tags leads so the rest of the system can prioritize them.

Used by:
- Autopilot (during research, attaches burden tags + need-probability)
- Aqua (system prompt context for prioritization)
- Admin / Customers UI (shows tags on each lead card)

The goal: AqueLystOS doesn't just search for businesses, it INFERS pain.
"""

import re


# ============================================================================
# SIC / NAICS code maps for AqueLyst-relevant industries
# ============================================================================
SIC_MAP = {
    'horse_equine': {
        'codes': ['0272', '0752'],
        'description': 'Horses & Other Equines, Animal Specialty Services',
    },
    'beef_feedlot': {'codes': ['0211'], 'description': 'Beef Cattle Feedlots'},
    'poultry': {'codes': ['0251', '0252', '0253', '0254'],
                 'description': 'Poultry Farms & Processing'},
    'swine': {'codes': ['0213'], 'description': 'Hogs / Swine'},
    'dairy': {'codes': ['0241', '0242'], 'description': 'Dairy Farms'},
    'sheep_goat': {'codes': ['0214', '0219'], 'description': 'Sheep & Goats'},
    'aquaculture': {'codes': ['0273'], 'description': 'Aquaculture'},
    'veterinary': {'codes': ['0741', '0742'],
                    'description': 'Veterinary Services'},
    'kennel_pet': {'codes': ['0752'],
                    'description': 'Animal Specialty Services (incl. kennels, grooming)'},
    'meat_processing': {'codes': ['2011', '2013', '2015'],
                         'description': 'Meat Packing, Sausages, Poultry Processing'},
    'dairy_processing': {'codes': ['2021', '2022', '2023', '2024', '2026'],
                          'description': 'Dairy Products Manufacturing'},
    'food_processing': {'codes': ['2030', '2032', '2033', '2034', '2035', '2037',
                                    '2038', '2050', '2060', '2070', '2080', '2090'],
                         'description': 'Food Processing'},
    'agricultural_chemicals': {'codes': ['2879', '2873'],
                                'description': 'Agricultural Chemicals'},
    'sanitary_services': {'codes': ['4959'],
                           'description': 'Sanitary Services NEC'},
    'refuse_systems': {'codes': ['4953'],
                        'description': 'Refuse Systems'},
    'environmental_remediation': {'codes': ['8748', '4959'],
                                    'description': 'Environmental Remediation'},
    'plumbing_hvac': {'codes': ['1711'],
                       'description': 'Plumbing, Heating, Air Conditioning'},
    'special_trade': {'codes': ['1799'],
                       'description': 'Special Trade Contractors'},
    'wastewater': {'codes': ['4952'],
                    'description': 'Sewerage Systems'},
    'auto_dealer': {'codes': ['5511', '5521'],
                     'description': 'Motor Vehicle Dealers'},
    'rv_marine_dealer': {'codes': ['5551', '5561'],
                          'description': 'Boat Dealers, RV Dealers'},
    'trucking': {'codes': ['4213', '4212'],
                  'description': 'Trucking & Local Trucking'},
    'transit': {'codes': ['4131', '4111'],
                 'description': 'Bus Lines, Transit'},
    'janitorial': {'codes': ['7349'],
                    'description': 'Building Cleaning & Maintenance'},
}

NAICS_MAP = {
    'horse_equine': {'codes': ['112920'],
                      'description': 'Horses & Other Equine Production'},
    'animal_support': {'codes': ['115210'],
                        'description': 'Support Activities for Animal Production'},
    'veterinary': {'codes': ['541940'],
                    'description': 'Veterinary Services'},
    'pet_care': {'codes': ['812910'],
                  'description': 'Pet Care (except Veterinary) Services'},
    'beef_cattle': {'codes': ['112111', '112112'],
                     'description': 'Beef Cattle Ranching, Cattle Feedlots'},
    'dairy': {'codes': ['112120'],
               'description': 'Dairy Cattle & Milk Production'},
    'poultry': {'codes': ['112310', '112320', '112330', '112340'],
                 'description': 'Poultry Production'},
    'swine': {'codes': ['112210'],
               'description': 'Hog & Pig Farming'},
    'sheep_goat': {'codes': ['112410', '112420'],
                    'description': 'Sheep & Goat Farming'},
    'aquaculture': {'codes': ['112511', '112512', '112519'],
                     'description': 'Aquaculture / Fish Farming'},
    'remediation': {'codes': ['562910'],
                     'description': 'Remediation Services'},
    'janitorial': {'codes': ['561720'],
                    'description': 'Janitorial Services'},
    'sewage_treatment': {'codes': ['221320'],
                          'description': 'Sewage Treatment Facilities'},
    'waste_mgmt': {'codes': ['562998', '562212', '562112'],
                    'description': 'Waste Management'},
    'plumbing_hvac': {'codes': ['238220'],
                       'description': 'Plumbing/HVAC Contractors'},
    'cleaning_compounds': {'codes': ['325611', '325612'],
                            'description': 'Soap & Cleaning Compounds Mfg'},
    'meat_processing': {'codes': ['311611', '311612', '311613', '311615'],
                         'description': 'Meat Processing & Rendering'},
    'food_processing': {'codes': ['311'],
                         'description': 'Food Manufacturing (parent code)'},
    'auto_dealer': {'codes': ['441110', '441120'],
                     'description': 'Automobile Dealers'},
    'rv_dealer': {'codes': ['441210'],
                   'description': 'Recreational Vehicle Dealers'},
    'boat_dealer': {'codes': ['441222'],
                     'description': 'Boat Dealers'},
    'trucking': {'codes': ['484110', '484121', '484122', '484220'],
                  'description': 'Truck Transportation'},
    'transit_bus': {'codes': ['485113', '485111', '485210'],
                     'description': 'Transit & Charter Bus'},
}


# ============================================================================
# Environmental burden mapping — what conditions does each business type cause?
# Used for Need-Probability scoring + auto-tagging.
# ============================================================================
BURDEN_BY_TYPE = {
    # Equine
    'horse boarding facility':   ['ODOR', 'AMMONIA', 'FLY', 'MANURE'],
    'equestrian center':         ['ODOR', 'AMMONIA', 'FLY', 'MANURE'],
    'horse stable':              ['ODOR', 'AMMONIA', 'FLY', 'MANURE'],
    'horse breeder':             ['ODOR', 'AMMONIA', 'BIOSECURITY', 'FLY'],
    'thoroughbred farm':         ['ODOR', 'AMMONIA', 'BIOSECURITY', 'FLY'],
    'racetrack':                 ['ODOR', 'AMMONIA', 'BIOSECURITY', 'FLY', 'HIGH_TRAFFIC'],
    'horse rescue':              ['ODOR', 'AMMONIA', 'FLY', 'BIOSECURITY'],
    'equine veterinary clinic':  ['BIOSECURITY', 'MICROBIAL', 'AMMONIA'],

    # Pets
    'kennel':                    ['ODOR', 'BIOSECURITY', 'MICROBIAL', 'URINE'],
    'doggy daycare':             ['ODOR', 'URINE', 'MICROBIAL'],
    'dog boarding facility':     ['ODOR', 'URINE', 'BIOSECURITY', 'MICROBIAL'],
    'animal shelter':            ['ODOR', 'BIOSECURITY', 'MICROBIAL', 'HIGH_TURNOVER'],
    'humane society':            ['ODOR', 'BIOSECURITY', 'MICROBIAL', 'HIGH_TURNOVER'],
    'veterinary clinic':         ['BIOSECURITY', 'MICROBIAL'],
    'emergency vet hospital':    ['BIOSECURITY', 'MICROBIAL', 'BLOOD'],
    'grooming salon':            ['ODOR', 'HAIR', 'WATER'],

    # SpillMaster (commercial / industrial)
    'meat processing plant':     ['BIOLOGICAL', 'MICROBIAL', 'BLOOD', 'AMMONIA', 'WASHDOWN'],
    'poultry processing plant':  ['BIOLOGICAL', 'MICROBIAL', 'AMMONIA', 'FECAL', 'WASHDOWN'],
    'dairy processing plant':    ['MICROBIAL', 'PROTEIN', 'WASHDOWN'],
    'food processing facility':  ['MICROBIAL', 'WASHDOWN', 'OSHA_RISK'],
    'hospital':                  ['BIOSECURITY', 'MICROBIAL', 'PATHOGEN', 'BIOHAZARD'],
    'nursing home':              ['ODOR', 'URINE', 'MICROBIAL', 'INFECTION_CONTROL'],
    'manufacturing plant':       ['INDUSTRIAL', 'WASHDOWN', 'OSHA_RISK'],
    'waste management company':  ['ODOR', 'MICROBIAL', 'RUNOFF', 'HAZMAT'],
    'industrial cleanup service': ['HAZMAT', 'BIOLOGICAL', 'INDUSTRIAL'],
    'recycling facility':        ['ODOR', 'MICROBIAL', 'HEAVY_TRAFFIC'],
    'mortuary funeral home':     ['BIOSECURITY', 'BIOLOGICAL', 'ODOR'],

    # AMR
    'rideshare fleet':           ['INTERIOR_ODOR', 'HIGH_TURNOVER', 'MICROBIAL'],
    'taxi company':              ['INTERIOR_ODOR', 'HIGH_TURNOVER'],
    'limo service':              ['INTERIOR_ODOR', 'HIGH_TURNOVER'],
    'school bus operator':       ['INTERIOR_ODOR', 'BIOLOGICAL', 'MICROBIAL'],
    'rv dealer':                 ['INTERIOR_ODOR', 'HOLDING_TANK', 'MILDEW'],
    'rv park':                   ['SEPTIC', 'GREYWATER', 'HOLDING_TANK'],
    'boat dealer':               ['MILDEW', 'BILGE', 'INTERIOR_ODOR'],
    'marina':                    ['MILDEW', 'GREYWATER', 'BIOFOULING', 'BILGE'],
    'yacht club':                ['MILDEW', 'BIOFOULING', 'BILGE'],
    'auto detail shop':          ['INTERIOR_ODOR', 'CHEMICAL'],
    'car dealership':            ['INTERIOR_ODOR', 'MILDEW'],
    'truck stop':                ['HIGH_TRAFFIC', 'INTERIOR_ODOR', 'WASHDOWN'],
    'trucking company':          ['INTERIOR_ODOR', 'BIOLOGICAL', 'WASHDOWN'],

    # HouseHold
    'property management company':  ['TURNOVER', 'PET_ODOR', 'BIOSECURITY'],
    'apartment complex':            ['TURNOVER', 'PET_ODOR', 'MICROBIAL'],
    'senior living facility':       ['URINE', 'MICROBIAL', 'INFECTION_CONTROL'],
    'house cleaning service':       ['INTERIOR_ODOR', 'PET_ODOR', 'TURNOVER'],
    'mold remediation company':     ['MOLD', 'MICROBIAL', 'BIOHAZARD'],
    'water damage restoration':     ['MOLD', 'MICROBIAL', 'BIOLOGICAL'],
    'fire damage restoration':      ['SMOKE', 'MICROBIAL', 'WASHDOWN'],
    'pest control company':         ['CHEMICAL', 'CROSS_CONTAMINATION'],
    'biohazard residential cleanup': ['BIOHAZARD', 'MICROBIAL', 'BLOOD'],

    # Inversion Misting (large facility / agriculture)
    'poultry farm':              ['AMMONIA', 'FECAL', 'FLY', 'MICROBIAL', 'BIOSECURITY'],
    'broiler farm':              ['AMMONIA', 'FECAL', 'FLY', 'MICROBIAL', 'CAFO'],
    'layer hen facility':        ['AMMONIA', 'FECAL', 'FLY', 'MICROBIAL', 'CAFO'],
    'turkey farm':               ['AMMONIA', 'FECAL', 'FLY', 'MICROBIAL', 'CAFO'],
    'dairy farm':                ['AMMONIA', 'FLY', 'MANURE', 'CAFO', 'RUNOFF'],
    'goat dairy':                ['AMMONIA', 'FLY', 'MANURE', 'CAFO'],
    'swine operation':           ['AMMONIA', 'FECAL', 'FLY', 'CAFO', 'NUISANCE_LAWSUIT_RISK'],
    'hog farm':                  ['AMMONIA', 'FECAL', 'FLY', 'CAFO', 'NUISANCE_LAWSUIT_RISK'],
    'feedlot':                   ['MANURE', 'AMMONIA', 'RUNOFF', 'FLY', 'CAFO'],
    'cattle ranch':              ['MANURE', 'FLY', 'RUNOFF'],
    'aquaculture facility':      ['MICROBIAL', 'BIOFILM', 'AMMONIA'],
    'commercial greenhouse':     ['MICROBIAL', 'PEST_PRESSURE', 'WATER_QUALITY'],
    'rendering plant':           ['ODOR', 'BIOLOGICAL', 'AMMONIA', 'NUISANCE_LAWSUIT_RISK'],
    'pet food manufacturer':     ['BIOLOGICAL', 'MICROBIAL', 'WASHDOWN'],
    'animal feed manufacturer':  ['DUST', 'MICROBIAL'],
    'composting facility':       ['ODOR', 'AMMONIA', 'FLY', 'NUISANCE_LAWSUIT_RISK'],
    'landfill':                  ['ODOR', 'MICROBIAL', 'RUNOFF', 'GAS'],
    'water treatment plant':     ['MICROBIAL', 'BIOLOGICAL', 'AMMONIA'],
    'sewage treatment plant':    ['ODOR', 'MICROBIAL', 'AMMONIA', 'BIOLOGICAL'],
}


def get_codes_for_type(business_type):
    """Return SIC + NAICS codes that best match a business_type string."""
    if not business_type:
        return {'sic': [], 'naics': []}
    t = business_type.lower()
    sic = []
    naics = []
    # Match keywords to category keys
    matches = []
    if 'horse' in t or 'equine' in t or 'equestrian' in t or 'stable' in t:
        matches += ['horse_equine', 'animal_support']
    if 'kennel' in t or 'doggy daycare' in t or 'pet boarding' in t or 'grooming' in t:
        matches += ['kennel_pet', 'pet_care']
    if 'vet' in t:
        matches += ['veterinary']
    if 'feedlot' in t or 'cattle' in t:
        matches += ['beef_feedlot', 'beef_cattle']
    if 'poultry' in t or 'broiler' in t or 'layer hen' in t or 'turkey' in t:
        matches += ['poultry']
    if 'dairy' in t:
        matches += ['dairy', 'dairy_processing']
    if 'swine' in t or 'hog' in t:
        matches += ['swine']
    if 'sheep' in t or 'goat' in t:
        matches += ['sheep_goat']
    if 'aquaculture' in t or 'fish farm' in t:
        matches += ['aquaculture']
    if 'meat processing' in t or 'rendering' in t:
        matches += ['meat_processing']
    if 'food processing' in t or 'commercial kitchen' in t:
        matches += ['food_processing']
    if 'remediation' in t or 'cleanup' in t or 'restoration' in t:
        matches += ['environmental_remediation', 'remediation']
    if 'janitorial' in t or 'cleaning service' in t or 'house cleaning' in t or 'maid' in t:
        matches += ['janitorial']
    if 'sewage' in t or 'wastewater' in t:
        matches += ['wastewater', 'sewage_treatment']
    if 'waste management' in t or 'refuse' in t or 'recycling' in t:
        matches += ['refuse_systems', 'waste_mgmt']
    if 'plumbing' in t or 'hvac' in t:
        matches += ['plumbing_hvac']
    if 'car dealer' in t or 'auto dealer' in t:
        matches += ['auto_dealer']
    if 'rv dealer' in t or 'recreational vehicle' in t:
        matches += ['rv_marine_dealer', 'rv_dealer']
    if 'boat dealer' in t:
        matches += ['boat_dealer']
    if 'trucking' in t or 'truck stop' in t:
        matches += ['trucking']
    if 'bus transit' in t or 'school bus' in t or 'transit' in t:
        matches += ['transit', 'transit_bus']

    for k in matches:
        if k in SIC_MAP:
            sic.extend(SIC_MAP[k]['codes'])
        if k in NAICS_MAP:
            naics.extend(NAICS_MAP[k]['codes'])
    # De-dup
    return {'sic': list(dict.fromkeys(sic)), 'naics': list(dict.fromkeys(naics))}


def get_burden_tags(business_type):
    """Get the environmental burden tags for a business type. These are the
    operational pain conditions Aqua infers without having to ask the prospect."""
    if not business_type:
        return []
    # Exact match
    t = business_type.lower().strip()
    if t in BURDEN_BY_TYPE:
        return list(BURDEN_BY_TYPE[t])
    # Substring fallback — find longest matching key
    for key in sorted(BURDEN_BY_TYPE.keys(), key=len, reverse=True):
        if key in t or t in key:
            return list(BURDEN_BY_TYPE[key])
    return []


# ============================================================================
# Need-Probability scoring — combine match_score with environmental burden
# ============================================================================
def compute_need_probability(business_type, match_score=50, has_size_signal=False,
                              location_state=None):
    """Score how likely this business genuinely NEEDS an AqueLyst product.
    Combines match_score (AI judgment of fit) with environmental burden indicators.
    Returns (score 0-100, list of contributing factors)."""
    score = int(match_score or 50)
    factors = []

    burden = get_burden_tags(business_type)
    # Each burden tag adds confidence
    high_signal_tags = {'AMMONIA', 'FECAL', 'FLY', 'CAFO', 'BIOHAZARD',
                         'NUISANCE_LAWSUIT_RISK', 'BIOSECURITY', 'BIOLOGICAL',
                         'PATHOGEN', 'INFECTION_CONTROL'}
    medium_signal_tags = {'ODOR', 'MICROBIAL', 'MANURE', 'URINE', 'WASHDOWN',
                            'INTERIOR_ODOR', 'MOLD', 'MILDEW', 'BLOOD'}

    high_count = sum(1 for t in burden if t in high_signal_tags)
    med_count = sum(1 for t in burden if t in medium_signal_tags)
    score += high_count * 4
    score += med_count * 2
    if high_count:
        factors.append(f"{high_count} high-signal burden tag(s)")
    if med_count:
        factors.append(f"{med_count} medium-signal burden tag(s)")

    if has_size_signal:
        score += 5
        factors.append("Size indicator captured (scaled operation)")

    # Geography heuristics — agriculture-heavy states get bonus for ag verticals
    AG_STATES = {'IA', 'NE', 'KS', 'TX', 'CA', 'WI', 'MN', 'IN', 'IL', 'OH',
                  'PA', 'NC', 'GA', 'AR', 'MO', 'KY', 'OK', 'SD', 'ND'}
    EQUINE_STATES = {'KY', 'TX', 'CA', 'FL', 'OK', 'CO', 'TN', 'VA', 'NY',
                      'WA', 'OR', 'NJ', 'MA'}

    t = (business_type or '').lower()
    is_ag = any(k in t for k in ['farm', 'cattle', 'dairy', 'poultry',
                                    'swine', 'feedlot', 'cafo', 'feed'])
    is_equine = 'horse' in t or 'equine' in t
    state = (location_state or '').upper()[:2]
    if state in AG_STATES and is_ag:
        score += 3
        factors.append(f"Ag-heavy state ({state})")
    if state in EQUINE_STATES and is_equine:
        score += 3
        factors.append(f"Equine hub state ({state})")

    # Cap at 0–100
    score = max(0, min(100, score))
    return score, factors


def auto_tags(business_type, product_fit=None):
    """Generate canonical CRM tags for a business — used in lead notes + Admin views."""
    tags = []
    burden = get_burden_tags(business_type)
    for b in burden:
        tags.append(b)
    if product_fit:
        if product_fit == 'Duo Equine':
            tags.append('EQUINE')
        elif product_fit == 'Inversion Misting':
            if any(k in (business_type or '').lower() for k in
                    ['poultry', 'dairy', 'swine', 'hog', 'feedlot', 'cafo']):
                tags.append('CAFO')
            tags.append('LARGE_FACILITY')
        elif product_fit == 'SpillMaster':
            tags.append('COMMERCIAL_SANITATION')
        elif product_fit == 'Pets':
            tags.append('ANIMAL_FACILITY')
        elif product_fit == 'AMR':
            tags.append('FLEET')
        elif product_fit == 'HouseHold':
            tags.append('RESIDENTIAL_ADJACENT')
    # De-dup
    return list(dict.fromkeys(tags))


def format_intelligence_block(business_type, product_fit=None,
                                match_score=50, location_state=None,
                                has_size_signal=False):
    """Build a one-paragraph intelligence summary suitable for lead notes
    or Aqua's context."""
    codes = get_codes_for_type(business_type)
    burden = get_burden_tags(business_type)
    need_score, factors = compute_need_probability(
        business_type, match_score, has_size_signal, location_state
    )
    tags = auto_tags(business_type, product_fit)
    parts = [f"🎯 Need-probability: {need_score}/100"]
    if codes['naics']:
        parts.append(f"NAICS: {', '.join(codes['naics'][:3])}")
    if codes['sic']:
        parts.append(f"SIC: {', '.join(codes['sic'][:3])}")
    if burden:
        parts.append(f"Burden indicators: {', '.join(burden[:6])}")
    if tags:
        parts.append(f"Tags: {' · '.join(tags[:6])}")
    if factors:
        parts.append(f"Reasoning: {'; '.join(factors)}")
    return " · ".join(parts)
