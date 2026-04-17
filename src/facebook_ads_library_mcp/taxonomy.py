"""Keyword-based niche & product classification.

Lightweight and deterministic: each niche maps to a list of case-insensitive
substrings; the classifier scores an ad by counting how many niche keywords
appear in its concatenated creative text.

The taxonomy is grouped into categories (apparel, supplements, beauty, home,
kids, pets, sports, hobbies, food, automotive, tech, health, lifestyle,
info products, services, seasonal, adult). Use `list_niches` to see the full
keyword lists and edit this file to tune recall/precision.
"""

from __future__ import annotations

from typing import Iterable

# ---------- Apparel & accessories ----------
_APPAREL = {
    "clothes_womens": [
        "women", "womens", "woman's", "dress", "blouse", "skirt", "leggings",
        "maternity", "shapewear", "lingerie", "bra ", "sports bra",
    ],
    "clothes_mens": [
        "mens", "men's", "menswear", "men's shirt", "men's t-shirt", "polo shirt",
        "men's pants", "men's shorts", "button-down", "dad hat",
    ],
    "clothes_baby": [
        "baby clothes", "onesie", "babysuit", "baby romper", "toddler outfit",
        "infant clothing", "baby bodysuit",
    ],
    "kids_clothes": [
        "kids clothes", "children's clothing", "toddler clothes", "boys shirt",
        "girls dress", "school uniform",
    ],
    "shoes": [
        "sneakers", "running shoes", "loafers", "boots", "heels",
        "sandals", "slippers", "footwear",
    ],
    "jewelry": [
        "necklace", "bracelet", "earring", "ring for", "pendant", "charm bracelet",
        "gold plated", "silver jewelry", "diamond ring",
    ],
    "watches": [
        "wristwatch", "chronograph", "automatic watch", "smart watch", "smartwatch",
        "quartz watch", "watch strap",
    ],
    "bags_purses": [
        "handbag", "tote bag", "crossbody", "backpack", "purse", "shoulder bag",
        "leather bag", "duffel bag",
    ],
    "eyewear": [
        "sunglasses", "blue light glasses", "reading glasses", "eyeglasses",
        "polarized", "uv protection",
    ],
}

# ---------- Supplements, health concerns, wellness ----------
_SUPPLEMENTS_HEALTH = {
    "supplements": [
        "supplement", "vitamin", "probiotic", "collagen", "gummies", "capsule",
        "digestive", "gut health", "detox", "cleanse", "ashwagandha",
        "magnesium", "pre-workout", "protein powder", "creatine", "omega-3",
    ],
    "weight_loss": [
        "weight loss", "lose weight", "fat burner", "fat loss", "slimming",
        "belly fat", "metabolism booster", "appetite suppressant",
    ],
    "anti_aging": [
        "anti-aging", "anti aging", "wrinkle", "fine lines", "youthful skin",
        "collagen boost",
    ],
    "joint_pain": [
        "joint pain", "knee pain", "arthritis", "joint support",
        "glucosamine", "cartilage",
    ],
    "back_pain": [
        "back pain", "lower back", "sciatica", "posture corrector", "lumbar support",
    ],
    "hearing_aids": ["hearing aid", "hearing loss", "tinnitus", "hearing amplifier"],
    "diabetes": ["diabetic", "blood sugar", "glucose", "type 2 diabetes", "insulin"],
    "menopause": ["menopause", "perimenopause", "hot flashes", "hormone balance"],
    "prostate": ["prostate", "prostate health", "bph"],
    "sleep_aids": [
        "sleep aid", "melatonin", "insomnia", "better sleep", "deep sleep",
        "sleep support",
    ],
    "mental_health": [
        "anxiety", "stress relief", "depression", "panic attack",
        "mental health", "burnout",
    ],
    "cbd": ["cbd", "cannabidiol", "hemp oil", "full spectrum"],
    "holistic_wellness": [
        "holistic", "ayurveda", "energy healing", "chakra", "essential oil",
        "mindfulness", "breathwork", "sound healing",
    ],
    "biohacking": [
        "biohack", "biohacking", "red light therapy", "cold plunge", "sauna",
        "cgm", "continuous glucose", "peptide",
    ],
}

# ---------- Beauty ----------
_BEAUTY = {
    "skincare": [
        "skincare", "serum", "moisturizer", "cleanser", "toner", "spf ",
        "sunscreen", "retinol", "hyaluronic", "niacinamide", "vitamin c serum",
        "face cream", "eye cream",
    ],
    "makeup": [
        "lipstick", "mascara", "foundation", "eyeliner", "concealer",
        "eyeshadow", "blush", "bronzer", "highlighter",
    ],
    "haircare": [
        "shampoo", "conditioner", "hair mask", "hair growth", "hair loss",
        "scalp treatment", "hair oil", "keratin",
    ],
    "fragrance": ["perfume", "cologne", "eau de parfum", "eau de toilette", "fragrance"],
    "nails": ["gel polish", "nail polish", "press-on nails", "manicure", "acrylic nails"],
}

# ---------- Home & living ----------
_HOME = {
    "home_decor": [
        "home decor", "throw pillow", "rug", "curtain", "vase", "wall decor",
        "coffee table", "bedding set", "duvet", "wall shelf",
    ],
    "lights": [
        "led light", "lamp", "chandelier", "pendant light", "floor lamp",
        "string lights", "night light", "smart bulb",
    ],
    "mattresses_bedding": [
        "mattress", "memory foam", "hybrid mattress", "pillow top", "duvet cover",
        "weighted blanket", "sheet set",
    ],
    "candles": ["scented candle", "soy candle", "candle set", "luxury candle"],
    "cleaning_products": [
        "stain remover", "cleaning spray", "disinfectant", "laundry pods",
        "grout cleaner", "mop",
    ],
    "kitchen_cookware": [
        "nonstick", "cookware", "frying pan", "cast iron", "dutch oven",
        "stock pot", "saucepan",
    ],
    "kitchen_gadgets": [
        "air fryer", "instant pot", "blender", "food processor", "stand mixer",
        "espresso machine", "juicer", "mandoline",
    ],
    "meal_prep": [
        "meal prep containers", "bento", "lunch box", "meal planner",
    ],
    "art_paintings": [
        "painting", "wall art", "canvas print", "art print", "oil painting",
        "watercolor", "framed art", "artwork", "diamond painting",
    ],
}

# ---------- Kids, baby, maternity ----------
_KIDS_BABY = {
    "kids_toys": [
        "toy", "kids toy", "children's toy", "plush", "stuffed animal",
        "building blocks", "puzzle kids", "educational toy", "montessori",
        "lego",
    ],
    "baby_accessories": [
        "baby carrier", "pacifier", "baby bottle", "stroller", "baby monitor",
        "diaper bag", "swaddle", "teether", "baby gate", "high chair",
    ],
    "maternity_pregnancy": [
        "pregnancy", "maternity pillow", "nursing pillow", "breast pump",
        "prenatal", "postpartum", "lactation",
    ],
    "kids_education": [
        "early reader", "phonics", "kids workbook", "learning app",
        "kids flashcards",
    ],
}

# ---------- Pets ----------
_PETS = {
    "pets_dog": [
        "dog", "puppy", "canine", "dog food", "dog toy", "dog collar",
        "dog harness", "dog bed", "dog treat",
    ],
    "pets_cat": [
        "cat", "kitten", "feline", "cat food", "cat toy", "litter box",
        "cat tree", "cat scratcher",
    ],
    "pets_chicken": ["chicken", "hen", "coop", "poultry", "backyard chickens"],
    "pets_rabbit": ["rabbit", "bunny", "hutch", "rabbit hay"],
    "pets_horse": ["equine", "horse riding", "horse tack", "saddle"],
    "pets_bird_fish": ["parrot", "budgie", "aquarium", "fish tank", "pet bird"],
}

# ---------- Sports & outdoor ----------
_SPORTS_OUTDOOR = {
    "pickleball": ["pickleball", "pickleball paddle", "pickleball ball"],
    "golf": ["golf ", "golf club", "golf ball", "putter", "golf swing", "golf cart"],
    "fishing": [
        "fishing", "fishing rod", "fishing reel", "bait", "fishing lure",
        "tackle box", "angler",
    ],
    "hunting": ["hunting", "bow hunting", "archery", "deer stand", "trail camera"],
    "camping_hiking": [
        "camping", "hiking", "tent", "sleeping bag", "hiking boots", "backpacking",
        "trekking pole", "cooler",
    ],
    "survival_prepping": [
        "survival", "prepper", "bug out", "emergency kit", "paracord",
        "fire starter",
    ],
    "rv_van_life": [
        "rv", "motorhome", "van life", "camper", "campervan", "boondock",
        "rv accessory", "travel trailer",
    ],
    "pool": ["swimming pool", "pool cleaner", "pool float", "pool pump", "pool skimmer"],
    "bikers_motorcycle": [
        "biker", "motorcycle", "harley", "biker gear", "leather vest",
        "motorbike jacket", "helmet",
    ],
    "cycling": ["cyclist", "road bike", "mountain bike", "bike helmet", "gravel bike"],
    "running": ["running shoes", "marathon", "5k ", "10k ", "runners", "trail running"],
    "yoga_pilates": ["yoga", "pilates", "yoga mat", "yoga block", "reformer"],
    "fitness_equipment": [
        "home gym", "dumbbell", "kettlebell", "resistance band", "treadmill",
        "exercise bike", "rowing machine",
    ],
    "boxing_martial_arts": ["boxing gloves", "punching bag", "mma", "bjj", "jiu jitsu"],
    "skiing_snowboard": ["ski goggles", "snowboard", "ski boots", "skiing"],
    "surfing_paddle": ["surfboard", "paddle board", "sup "],
}

# ---------- Hobbies & crafts ----------
_HOBBIES = {
    "gardening": [
        "garden", "gardening", "raised bed", "seed starter", "compost",
        "potting soil", "garden tool", "planter", "greenhouse",
    ],
    "lawn_care": ["lawn mower", "grass seed", "fertilizer", "weed killer", "lawn care"],
    "woodworking": [
        "woodworking", "wood carving", "table saw", "chisel", "dovetail",
        "cnc wood", "lathe", "router table",
    ],
    "diy_home_improvement": [
        "diy", "power tool", "drill press", "impact driver", "miter saw",
        "home improvement",
    ],
    "quilting_knitting": [
        "quilt", "quilting", "knit", "knitting", "crochet", "yarn", "knitting needle",
    ],
    "sewing": ["sewing machine", "sewing pattern", "fabric stash"],
    "scrapbooking": ["scrapbook", "scrapbooking", "cardstock", "journaling supplies"],
    "photography_gear": [
        "camera strap", "tripod", "camera lens", "mirrorless", "dslr",
        "photography",
    ],
    "board_games": ["board game", "tabletop", "dnd", "dungeons & dragons", "ttrpg"],
    "music_instruments": [
        "guitar", "piano", "keyboard", "drum kit", "violin", "ukulele",
        "microphone",
    ],
    "3d_printing": ["3d printer", "filament", "resin printer", "pla ", "petg"],
    "rc_hobby": ["rc car", "rc plane", "drone", "quadcopter"],
}

# ---------- Food & drink ----------
_FOOD_DRINK = {
    "coffee_tea": [
        "coffee beans", "espresso", "pour over", "french press", "loose leaf tea",
        "matcha", "cold brew",
    ],
    "wine_alcohol": ["wine club", "craft beer", "whiskey", "bourbon", "tequila"],
    "snacks_food": [
        "protein bar", "healthy snack", "jerky", "granola", "keto snack",
        "gluten free snack",
    ],
    "meal_kits": ["meal kit", "chef prepared", "ready to cook", "hellofresh"],
    "cooking_course": ["cooking class", "recipe book", "chef course"],
}

# ---------- Automotive ----------
_AUTOMOTIVE = {
    "car_accessories": [
        "car phone mount", "dash cam", "car cover", "seat cover", "car organizer",
        "tire inflator",
    ],
    "car_cleaning": ["car wash", "car detailing", "ceramic coating"],
    "truck_accessories": ["pickup truck", "bed liner", "tonneau cover", "lift kit"],
}

# ---------- Tech & gadgets ----------
_TECH = {
    "tech_gadgets": [
        "bluetooth speaker", "power bank", "wireless charger", "portable projector",
        "noise cancelling", "airpods",
    ],
    "smart_home": [
        "smart plug", "smart thermostat", "smart doorbell", "smart lock",
        "home automation", "alexa",
    ],
    "phone_accessories": [
        "phone case", "screen protector", "phone stand", "pop socket",
        "magsafe",
    ],
    "gaming_gear": [
        "gaming mouse", "mechanical keyboard", "gaming chair", "headset",
        "controller",
    ],
    "wearables_tracker": [
        "fitness tracker", "apple watch band", "garmin", "oura ring", "whoop",
    ],
}

# ---------- Lifestyle / identity ----------
_LIFESTYLE = {
    "religion_christian": [
        "bible", "jesus", "christian", "catholic", "faith", "prayer",
        "rosary", "scripture",
    ],
    "off_grid": [
        "off grid", "off-grid", "solar generator", "homestead", "self sufficient",
        "rainwater",
    ],
    "grey_hair_silver": [
        "grey hair", "gray hair", "silver hair", "silver sisters", "going grey",
    ],
    "empty_nesters": [
        "empty nester", "empty nest", "kids moved out", "retirement hobby",
    ],
    "recently_divorced": [
        "divorced", "divorce recovery", "after divorce", "post-divorce",
    ],
    "seniors_55plus": [
        "seniors", "55+", "65+", "aarp", "retiree", "medicare",
    ],
    "veterans": ["veteran", "us marine", "army vet", "navy seal", "vfw"],
    "single_moms": ["single mom", "single mother"],
    "lgbtq": ["lgbtq", "pride flag", "non-binary", "trans"],
    "dating_relationship": [
        "dating app", "relationship coach", "marriage counseling", "attract women",
        "attract men",
    ],
    "wedding": ["wedding dress", "bridesmaid", "wedding planner", "wedding favors"],
}

# ---------- Info products / education / services ----------
_INFO_SERVICES = {
    "online_course": [
        "online course", "masterclass", "cohort course", "bootcamp",
        "self-paced course",
    ],
    "language_learning": [
        "learn spanish", "learn french", "learn italian", "language app",
        "fluent in", "duolingo",
    ],
    "real_estate_investing": [
        "real estate investor", "rental property", "airbnb investing", "brrrr",
        "house hacking",
    ],
    "ecom_dropshipping_course": [
        "dropshipping", "ecom course", "shopify course", "amazon fba",
        "private label",
    ],
    "coaching": [
        "1-on-1 coach", "life coach", "business coach", "mindset coach",
        "high ticket coaching",
    ],
    "mortgage_refinance": [
        "mortgage rate", "refinance", "heloc", "home equity",
    ],
    "credit_repair_debt": [
        "credit repair", "debt relief", "consolidate debt", "bad credit",
    ],
    "crypto": ["bitcoin", "ethereum", "crypto wallet", "defi", "web3"],
    "trading_investing": [
        "stock trading", "options trading", "day trading", "swing trading",
        "forex",
    ],
    "solar_leads": ["solar panels", "solar installation", "go solar"],
    "life_insurance": ["life insurance", "term life", "whole life", "final expense"],
    "saas_software": [
        "saas", "crm software", "project management tool", "free trial saas",
        "no code platform",
    ],
    "marketing_agency": [
        "marketing agency", "lead generation", "paid ads agency", "ppc",
    ],
    "legal_services": ["personal injury", "attorney", "lawyer", "class action"],
    "mental_health_service": ["therapy app", "online therapy", "betterhelp"],
}

# ---------- Seasonal / occasion ----------
_SEASONAL = {
    "christmas": ["christmas", "xmas", "holiday gift", "secret santa", "advent calendar"],
    "halloween": ["halloween", "costume", "jack-o-lantern"],
    "valentines": ["valentine", "galentine"],
    "mothers_fathers_day": ["mother's day", "father's day", "mom gift", "dad gift"],
    "back_to_school": ["back to school", "college dorm", "school supplies"],
}

# ---------- Adult / NSFW (keep permissive; heavy NSFW is blocked by Meta anyway) ----------
_ADULT = {
    "adult_intimacy": [
        "intimacy", "couples", "date night", "adult toy", "pelvic floor",
    ],
}

# Merge all
NICHES: dict[str, list[str]] = {
    **_APPAREL,
    **_SUPPLEMENTS_HEALTH,
    **_BEAUTY,
    **_HOME,
    **_KIDS_BABY,
    **_PETS,
    **_SPORTS_OUTDOOR,
    **_HOBBIES,
    **_FOOD_DRINK,
    **_AUTOMOTIVE,
    **_TECH,
    **_LIFESTYLE,
    **_INFO_SERVICES,
    **_SEASONAL,
    **_ADULT,
}

# Category groupings (useful for UIs / reports)
NICHE_CATEGORIES: dict[str, list[str]] = {
    "apparel": list(_APPAREL),
    "supplements_health": list(_SUPPLEMENTS_HEALTH),
    "beauty": list(_BEAUTY),
    "home": list(_HOME),
    "kids_baby": list(_KIDS_BABY),
    "pets": list(_PETS),
    "sports_outdoor": list(_SPORTS_OUTDOOR),
    "hobbies": list(_HOBBIES),
    "food_drink": list(_FOOD_DRINK),
    "automotive": list(_AUTOMOTIVE),
    "tech": list(_TECH),
    "lifestyle": list(_LIFESTYLE),
    "info_services": list(_INFO_SERVICES),
    "seasonal": list(_SEASONAL),
    "adult": list(_ADULT),
}

# Product context tags — orthogonal to niche, describe the offer type.
PRODUCT_CONTEXT: dict[str, list[str]] = {
    "physical_product": [
        "free shipping", "ships worldwide", "buy now", "order now", "add to cart",
        "in stock", "pre-order",
    ],
    "digital_info_product": [
        "ebook", "course", "masterclass", "webinar", "pdf", "download",
        "guide", "training program",
    ],
    "service": [
        "book a call", "schedule a consultation", "free quote", "appointment",
        "consultation",
    ],
    "subscription": [
        "subscription", "monthly box", "cancel anytime", "/month", "per month",
    ],
    "cod_payment": [
        "cash on delivery", "pay on delivery", "pagamento alla consegna",
        "contrassegno", "c.o.d.", "cod available",
    ],
    "discount_offer": [
        "% off", "percent off", "sale", "discount", "promo", "coupon",
        "limited time",
    ],
    "free_trial_or_sample": [
        "free trial", "free sample", "try it free", "first order free",
    ],
    "lead_gen_form": [
        "get a quote", "contact us", "free consultation", "submit form",
        "request demo",
    ],
    "app_install": [
        "download the app", "available on app store", "google play",
        "install now",
    ],
}


def _score(text: str, keywords: Iterable[str]) -> tuple[int, list[str]]:
    lowered = text.lower()
    hits = [k for k in keywords if k.lower() in lowered]
    return len(hits), hits


def classify(text: str, *, top_k: int = 3) -> dict[str, object]:
    """Return the top niches + product contexts detected in `text`."""
    niche_scores = [
        (niche, *_score(text, kws)) for niche, kws in NICHES.items()
    ]
    niche_scores.sort(key=lambda row: row[1], reverse=True)
    niches = [
        {"niche": name, "score": score, "hits": hits}
        for name, score, hits in niche_scores
        if score > 0
    ][:top_k]

    context_scores = [
        (ctx, *_score(text, kws)) for ctx, kws in PRODUCT_CONTEXT.items()
    ]
    context_scores.sort(key=lambda row: row[1], reverse=True)
    contexts = [
        {"context": name, "score": score, "hits": hits}
        for name, score, hits in context_scores
        if score > 0
    ]

    return {
        "top_niches": niches,
        "product_contexts": contexts,
        "primary_niche": niches[0]["niche"] if niches else None,
        "primary_context": contexts[0]["context"] if contexts else None,
    }
