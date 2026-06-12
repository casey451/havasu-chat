"""Searcher-facing display nouns for taxonomy leaves (SEO polish, PR-B).

The taxonomy stores tidy internal labels ("Plumbing", "Electrical",
"Grooming"), but people google the NOUN for the businesses ("lake havasu
plumbers", "dog groomers lake havasu"). Leaf pages must rank for the
searcher's word, so titles / H1s / breadcrumbs / FAQ copy render the noun
from this map instead of the raw ``Category.name``. This also fixes the
auto-fill grammar ("How are these plumbing ranked?" → "these plumbers").

Keyed by leaf slug (``categories.slug`` for ``level = 1`` rows). A leaf
missing here keeps its taxonomy name — only entries whose name is NOT
already the natural search term belong in the map. Presentation only; the
taxonomy data itself is untouched.
"""

from __future__ import annotations

SEO_NOUNS: dict[str, str] = {
    # Home & Property Services
    "plumbing": "Plumbers",
    "electrical": "Electricians",
    "roofing": "Roofers",
    "cleaning": "Cleaning Services",
    "hvac": "HVAC Companies",
    "pest-control": "Pest Control Companies",
    "landscaping-and-lawn": "Landscapers & Lawn Care",
    "pools-and-spas": "Pool & Spa Services",
    "self-storage": "Self-Storage Facilities",
    "solar": "Solar Companies",
    "security-and-alarms": "Security & Alarm Companies",
    "handyman": "Handyman Services",
    # Health & Medical
    "primary-care": "Doctors & Primary Care",
    "chiropractic": "Chiropractors",
    "physical-therapy": "Physical Therapists",
    "eye-care": "Eye Doctors & Optometrists",
    "urgent-care-and-er": "Urgent Care Clinics",
    "dermatology-and-skin": "Dermatologists",
    "mental-and-behavioral-health": "Mental Health Providers",
    # Eat & Drink
    "cafes-and-coffee": "Cafés & Coffee Shops",
    "food-trucks-and-catering": "Food Trucks & Caterers",
    # Pets (slugs are leaf-scoped: "grooming"/"training" are the pet leaves)
    "grooming": "Pet Groomers",
    "training": "Pet Trainers",
    "pet-stores-and-supplies": "Pet Stores",
    "boarding-and-daycare": "Pet Boarding & Daycare",
    "pet-sitting": "Pet Sitters",
    # Beauty & Personal Care
    "tattoo-and-piercing": "Tattoo & Piercing Shops",
    "tanning": "Tanning Salons",
    "med-spas-and-aesthetics": "Med Spas",
    # Fitness & Wellness
    "yoga-and-pilates": "Yoga & Pilates Studios",
    "martial-arts": "Martial Arts Studios",
    "personal-training": "Personal Trainers",
    # Auto, RV & Marine
    "auto-repair": "Auto Repair Shops",
    "auto-parts": "Auto Parts Stores",
    "car-wash": "Car Washes",
    "tires": "Tire Shops",
    "car-rental": "Car Rentals",
    "boat-sales": "Boat Dealers",
    "powersports-and-atv": "Powersports & ATV Dealers",
    "towing-and-roadside": "Towing & Roadside Assistance",
    # Cleaner searcher nouns than the slash-bearing taxonomy names; agent-noun
    # plurals ("detailers") read naturally in the shared FAQ grammar and match
    # what searchers actually type.
    "auto-marine-detailing": "Boat & Auto Detailers",
    "auto-detailing": "Auto Detailers",
    "boat-and-rv-storage-service": "Boat & RV Storage",
    # Professional & Financial
    "real-estate": "Real Estate Agents",
    "insurance": "Insurance Agents",
    "accountants-and-tax": "Accountants & Tax Preparers",
    "print-signs-and-marketing": "Print & Sign Shops",
    # Shopping & Retail
    "clothing-and-apparel": "Clothing Stores",
    "gifts-and-boutiques": "Gift Shops & Boutiques",
    "hardware-and-home-improvement": "Hardware Stores",
    "furniture-and-mattress": "Furniture & Mattress Stores",
    "sporting-goods": "Sporting Goods Stores",
    "convenience": "Convenience Stores",
    "grocery-and-markets": "Grocery Stores & Markets",
    "appliances-and-electronics": "Appliance & Electronics Stores",
    "jewelry": "Jewelers",
    "thrift-and-consignment": "Thrift & Consignment Stores",
    "specialty-food": "Specialty Food Stores",
    "smoke-vape-and-cannabis": "Smoke & Vape Shops",
    "shoes": "Shoe Stores",
    "hobby-and-craft": "Hobby & Craft Stores",
    # Community & Civic
    "places-of-worship": "Churches & Places of Worship",
    "government-and-mvd": "Government Offices & MVD",
    # Things to Do & Attractions
    "theaters-and-cinema": "Movie Theaters",
    # Outdoors & Recreation
    "disc-golf": "Disc Golf Courses",
    # On the Water
    "kayak-and-paddle": "Kayak & Paddleboard Rentals",
}


def display_noun(slug: str | None, fallback: str) -> str:
    """The searcher-facing noun for a leaf, or ``fallback`` (the taxonomy
    name) when the name already IS the natural search term."""
    if not slug:
        return fallback
    return SEO_NOUNS.get(slug.strip().lower(), fallback)
