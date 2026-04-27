"""Prospecting tool - find equine businesses to target."""

import urllib.parse


# Equine business search categories
EQUINE_BUSINESS_TYPES = [
    "horse boarding",
    "horse stable",
    "equestrian center",
    "horse barn",
    "horse trainer",
    "horse breeder",
    "horse rescue",
    "tack shop",
    "feed store",
    "horse farm",
    "riding school",
    "horse trailer",
    "equine veterinarian",
    "polo club",
    "dressage facility",
]

# US state abbreviations with major equine markets
TOP_EQUINE_STATES = [
    ("KY", "Kentucky"), ("TX", "Texas"), ("FL", "Florida"),
    ("CA", "California"), ("VA", "Virginia"), ("OK", "Oklahoma"),
    ("CO", "Colorado"), ("OH", "Ohio"), ("PA", "Pennsylvania"),
    ("TN", "Tennessee"), ("NY", "New York"), ("OR", "Oregon"),
    ("WA", "Washington"), ("AZ", "Arizona"), ("MT", "Montana"),
    ("WY", "Wyoming"), ("NC", "North Carolina"), ("SC", "South Carolina"),
    ("GA", "Georgia"), ("ID", "Idaho"),
]


def build_google_maps_search_url(business_type, city=None, state=None):
    """Build Google Maps search URL for finding businesses."""
    query_parts = [business_type]
    if city:
        query_parts.append(city)
    if state:
        query_parts.append(state)

    query = " ".join(query_parts)
    encoded = urllib.parse.quote(query)
    return f"https://www.google.com/maps/search/{encoded}/"


def build_google_search_url(business_type, city=None, state=None):
    """Build Google search URL with site:google.com/maps for direct results."""
    query_parts = [business_type]
    if city:
        query_parts.append(city)
    if state:
        query_parts.append(state)
    query_parts.append("contact email")

    query = " ".join(query_parts)
    encoded = urllib.parse.quote(query)
    return f"https://www.google.com/search?q={encoded}"


def build_instagram_search_url(hashtag):
    """Build Instagram hashtag URL for finding equine businesses."""
    clean = hashtag.replace('#', '').replace(' ', '')
    return f"https://www.instagram.com/explore/tags/{clean}/"


def build_facebook_search_url(query):
    """Build Facebook page search."""
    encoded = urllib.parse.quote(query)
    return f"https://www.facebook.com/search/pages/?q={encoded}"


def build_yellow_pages_url(business_type, location):
    """Build YellowPages.com search."""
    bt = urllib.parse.quote(business_type)
    loc = urllib.parse.quote(location)
    return f"https://www.yellowpages.com/search?search_terms={bt}&geo_location_terms={loc}"


def build_yelp_url(business_type, location):
    """Build Yelp search URL."""
    bt = urllib.parse.quote(business_type)
    loc = urllib.parse.quote(location)
    return f"https://www.yelp.com/search?find_desc={bt}&find_loc={loc}"


def get_equine_directories():
    """Return list of free equine business directories."""
    return [
        {
            'name': 'Yelp',
            'url': 'https://www.yelp.com/c/equestrian',
            'description': 'Search for equestrian centers and tack shops',
            'category': 'general'
        },
        {
            'name': 'Yellow Pages',
            'url': 'https://www.yellowpages.com/search?search_terms=horse+stable',
            'description': 'Comprehensive business directory',
            'category': 'general'
        },
        {
            'name': 'Google Maps',
            'url': 'https://www.google.com/maps/search/horse+boarding+facility/',
            'description': 'Find local horse facilities with reviews',
            'category': 'general'
        },
        {
            'name': 'HorseFinders',
            'url': 'https://horsefinders.com/',
            'description': 'Equestrian services directory',
            'category': 'equine'
        },
        {
            'name': 'Stable Finder',
            'url': 'https://stablefinder.com/',
            'description': 'Find horse stables by location',
            'category': 'equine'
        },
        {
            'name': 'Equine.com',
            'url': 'https://www.equine.com/businesses',
            'description': 'Equine business directory',
            'category': 'equine'
        },
        {
            'name': 'United States Equestrian Federation',
            'url': 'https://www.usef.org/',
            'description': 'Find competitions, clubs, and members',
            'category': 'equine'
        },
        {
            'name': 'Instagram (#horseboarding)',
            'url': 'https://www.instagram.com/explore/tags/horseboarding/',
            'description': 'Find boarding facilities on Instagram',
            'category': 'social'
        },
        {
            'name': 'Instagram (#equestrianlife)',
            'url': 'https://www.instagram.com/explore/tags/equestrianlife/',
            'description': 'Find equestrian businesses',
            'category': 'social'
        },
        {
            'name': 'Facebook (Horse Groups)',
            'url': 'https://www.facebook.com/search/groups/?q=horse%20boarding',
            'description': 'Find Facebook horse community groups',
            'category': 'social'
        },
    ]


def get_search_targets():
    """Return categorized search target combinations."""
    return {
        'high_priority': [
            {'type': 'horse boarding facility', 'reason': 'Daily ammonia/manure problems'},
            {'type': 'horse stable', 'reason': 'Multiple stalls, ongoing odor issues'},
            {'type': 'equestrian center', 'reason': 'Premium facilities, large operations'},
            {'type': 'horse rescue', 'reason': 'Multiple horses, budget for solutions'},
        ],
        'medium_priority': [
            {'type': 'horse trainer', 'reason': 'Often has small stable, trailer issues'},
            {'type': 'horse breeder', 'reason': 'Premium operation, quality-focused'},
            {'type': 'riding school', 'reason': 'High traffic, public-facing image'},
            {'type': 'polo club', 'reason': 'High-end, multiple horses'},
        ],
        'distribution_partners': [
            {'type': 'tack shop', 'reason': 'Could resell to end customers'},
            {'type': 'feed store', 'reason': 'Could resell to barn owners'},
            {'type': 'equine veterinarian', 'reason': 'Refer to clients'},
        ]
    }


def generate_search_plan(state=None, city=None):
    """Generate a strategic prospecting plan."""
    plan = []

    targets = get_search_targets()

    for priority, items in targets.items():
        for item in items:
            search_term = item['type']

            search_links = {
                'google_maps': build_google_maps_search_url(search_term, city, state),
                'google_search': build_google_search_url(search_term, city, state),
            }

            if not city and not state:
                search_links['yellow_pages'] = build_yellow_pages_url(search_term, "United States")

            plan.append({
                'priority': priority,
                'business_type': search_term,
                'reason': item['reason'],
                'search_links': search_links,
            })

    return plan
