"""
Event category classifier using TF-IDF + Logistic Regression.

Categories:
  - Armed Conflict
  - Civil Unrest
  - Diplomacy / Sanctions
  - Economic Disruption
  - Infrastructure / Energy
  - Crime / Terror

Training: bootstrapped from GDELT events (which have structured EventCodes
mapped to categories via taxonomy.py). The trained model is then applied
to free-text Valyu articles.

Fallback: keyword rules when model confidence < threshold.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Armed Conflict",
    "Civil Unrest",
    "Diplomacy / Sanctions",
    "Economic Disruption",
    "Infrastructure / Energy",
    "Crime / Terror",
]

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "event_classifier.joblib"

# ── Keyword fallback rules ───────────────────────────────────────────────

_KEYWORD_RULES: List[Tuple[str, List[str]]] = [
    ("Armed Conflict", [
        "military", "airstrike", "bombing", "troops", "invasion", "shelling",
        "war", "warfare", "artillery", "missile strike", "armed forces",
        "combat", "offensive", "drone strike", "battlefield", "ceasefire",
    ]),
    ("Crime / Terror", [
        "terrorism", "terrorist", "attack", "assassination", "kidnapping",
        "hostage", "shooting", "explosion", "suicide bomb", "extremist",
        "militant", "insurgent", "cartel", "gang", "organized crime",
    ]),
    ("Civil Unrest", [
        "protest", "demonstration", "riot", "unrest", "strike", "uprising",
        "rally", "march", "civil disobedience", "crackdown", "dissent",
        "opposition", "coup", "revolution", "martial law",
    ]),
    ("Diplomacy / Sanctions", [
        "sanctions", "diplomacy", "diplomatic", "treaty", "summit",
        "negotiations", "embargo", "united nations", "bilateral", "alliance",
        "peace talks", "foreign minister", "ambassador", "resolution",
    ]),
    ("Economic Disruption", [
        "economic crisis", "inflation", "recession", "trade war", "tariff",
        "supply chain", "currency", "debt crisis", "bankruptcy", "default",
        "market crash", "stock market", "commodity", "oil price",
    ]),
    ("Infrastructure / Energy", [
        "infrastructure", "pipeline", "power grid", "nuclear plant",
        "energy crisis", "blackout", "cyberattack", "dam", "refinery",
        "oil facility", "gas pipeline", "power outage", "sabotage",
    ]),
]


def classify_by_keywords(text: str) -> Tuple[str, float]:
    """
    Keyword-based classification fallback.
    Returns (category, confidence) where confidence is based on keyword hit density.
    """
    text_lower = text.lower()
    scores: Dict[str, int] = {}

    for category, keywords in _KEYWORD_RULES:
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[category] = count

    if not scores:
        return "Civil Unrest", 0.1  # default fallback

    best = max(scores, key=scores.get)
    # Normalize confidence: more keyword hits = higher confidence, cap at 0.7
    confidence = min(0.7, scores[best] / 5.0)
    return best, confidence


# ── Synthetic training data ──────────────────────────────────────────────

def _generate_training_data() -> Tuple[List[str], List[str]]:
    """
    Generate labeled text samples for each category.
    Expanded with realistic headlines based on real-world event patterns.
    """
    data = {
        "Armed Conflict": [
            "Military forces launched airstrikes on rebel positions in the northern region",
            "Troops were deployed to the border amid escalating tensions between the two nations",
            "Artillery shelling intensified as ground offensive continued in the eastern front",
            "Drone strike kills senior military commander in targeted operation",
            "Naval forces conducted exercises near disputed waters raising war concerns",
            "Ceasefire violations reported as both sides exchange heavy gunfire",
            "Armed forces advance on strategic city amid fierce urban combat",
            "Missile attacks destroy military installations near the capital",
            "War intensifies as ground troops push into contested territory",
            "Military coalition launches bombing campaign against enemy positions",
            "Soldiers killed in ambush by armed insurgent group near border",
            "Air defense systems intercept incoming ballistic missiles",
            "Tank columns advance through enemy lines in major offensive",
            "Military occupation of key province continues despite resistance",
            "Fighter jets bomb weapons depot and ammunition storage facilities",
            "Special forces conduct raid on militant hideout near the city",
            "Warships blockade port as military tensions escalate dramatically",
            "Armed conflict displaces millions as humanitarian crisis deepens",
            "Invasion forces capture strategic airfield after heavy fighting",
            "Counter-offensive recaptures territory lost in earlier battles",
            # Real-world pattern examples
            "Russian forces shell Ukrainian city killing civilians in residential areas",
            "Israel launches military operation in Gaza amid rocket attacks from Hamas",
            "Sudan army clashes with paramilitary RSF forces in Khartoum streets",
            "Myanmar junta airstrikes hit civilian villages in rebel-held territory",
            "Yemen Houthi rebels launch missile attacks on Saudi coalition positions",
            "Ethiopian troops advance into Tigray region as conflict escalates",
            "Iran-backed militia launches drone attack on US base in Iraq",
            "North Korea conducts live fire drills near demilitarized zone border",
            "Syrian government forces barrel bomb rebel-held Idlib province",
            "Separatist forces seize territory in eastern Ukraine after heavy fighting",
            "NATO allies conduct joint military exercises near Russian border",
            "US military deploys aircraft carrier group to Persian Gulf amid Iran tensions",
            "Cross-border shelling between India and Pakistan along Line of Control",
            "Armed groups ambush peacekeeping convoy in central Africa killing soldiers",
            "Chinese military aircraft enter Taiwan air defense zone in show of force",
        ],
        "Crime / Terror": [
            "Terrorist organization claims responsibility for bombing at market square",
            "Suicide bomber detonates explosives at crowded checkpoint killing dozens",
            "Police arrest suspected terror cell planning attacks on public transport",
            "Mass shooting at public gathering leaves multiple casualties and injuries",
            "Hostage crisis unfolds at government building as gunmen make demands",
            "Drug cartel violence surges with multiple killings reported overnight",
            "Extremist group releases video threatening attacks on western targets",
            "Assassination of political figure sparks security crackdown in capital",
            "Kidnapping of foreign nationals by armed group raises security alarms",
            "Organized crime network dismantled in major international police operation",
            "Terror attack on hotel kills foreign tourists and security personnel",
            "Gang violence erupts in major city with shootings across neighborhoods",
            "Bomb threat forces evacuation of government offices and public spaces",
            "Militant group seizes control of town after overwhelming security forces",
            "Insurgent attack on military convoy kills soldiers and destroys vehicles",
            "Serial killer apprehended after months of investigation and manhunt",
            "Human trafficking ring busted in coordinated cross-border police action",
            "Cyber criminals launch ransomware attack on critical government systems",
            "Lone wolf attacker wounds several people in knife attack at station",
            "Piracy incidents increase along major international shipping routes",
            # Real-world pattern examples
            "ISIS claims responsibility for suicide bombing at mosque killing worshippers",
            "Boko Haram kidnaps schoolchildren in northeast Nigeria raid",
            "Al-Shabaab militants storm hotel in Mogadishu in deadly siege",
            "Mexican cartel gunmen massacre civilians in border town attack",
            "Taliban-linked bombing targets government ministry in Kabul",
            "Al-Qaeda affiliate claims deadly attack on French forces in Sahel",
            "Hezbollah operatives arrested planning attacks on foreign soil",
            "PKK militants attack Turkish military outpost killing several soldiers",
            "Somali pirates hijack commercial vessel in Indian Ocean shipping lane",
            "Narco-terrorism threat rises as cartels deploy explosive devices",
            "Jihadist cell disrupted in European capital planning coordinated attacks",
            "Prison break by armed militants frees hundreds of inmates in Nigeria",
            "Vehicle ramming attack at crowded festival injures dozens of people",
            "Separatist guerrilla group bombs oil pipeline in restive region",
            "Terror financing network exposed funneling millions through crypto",
        ],
        "Civil Unrest": [
            "Thousands take to the streets in anti-government protest demanding reforms",
            "Riot police deployed as demonstrations turn violent in capital city",
            "General strike paralyzes the country as workers demand better conditions",
            "Student protests erupt across universities calling for political change",
            "Security forces use tear gas to disperse large crowd of protesters",
            "Opposition leaders call for mass demonstrations against election results",
            "Civil unrest spreads to multiple cities as discontent with government grows",
            "Protesters storm government buildings demanding resignation of officials",
            "Peaceful march turns violent after police confrontation with demonstrators",
            "Labor unions organize nationwide walkout over proposed austerity measures",
            "Pro-democracy movement gains momentum with daily protests in main square",
            "Curfew imposed after days of riots and looting in commercial district",
            "Coup attempt reported as military units surround presidential palace",
            "Revolutionary movement calls for overthrow of authoritarian regime",
            "Martial law declared as civil disorder threatens government stability",
            "Ethnic tensions boil over into communal violence in southern provinces",
            "Teacher strikes close schools across the country for third week",
            "Anti-corruption protests draw record crowds to the capital plaza",
            "Youth uprising challenges decades of political establishment control",
            "Demonstrators block major highways disrupting commerce and transport",
            # Real-world pattern examples
            "Iran protests spread nationwide as security forces open fire on crowds",
            "Hong Kong pro-democracy activists arrested under national security law",
            "French Yellow Vest protests paralyze Paris with barricades and tear gas",
            "Sri Lanka economic crisis sparks mass protests and storming of palace",
            "Myanmar anti-coup protesters face brutal military crackdown killing hundreds",
            "Sudanese civilians march demanding return to civilian government",
            "Thai pro-democracy protesters defy ban and rally at government house",
            "Chilean unrest over inequality leads to constitutional referendum",
            "Belarus opposition protests after disputed election meet police violence",
            "Nigerian EndSARS protesters clash with security forces across Lagos",
            "Peruvian political crisis triggers nationwide protests and road blocks",
            "Colombian farmers blockade highways protesting agricultural policies",
            "Tunisian president faces mass rallies calling for democratic reforms",
            "Bangladesh garment workers strike demanding higher minimum wages",
            "South African riots and looting spread following political arrest",
        ],
        "Diplomacy / Sanctions": [
            "United Nations Security Council votes on new sanctions against regime",
            "Foreign ministers meet for diplomatic talks to resolve border dispute",
            "Trade embargo imposed on nation for human rights violations",
            "Summit between world leaders focuses on nuclear non-proliferation",
            "Peace negotiations resume after months of diplomatic stalemate",
            "Ambassador recalled as bilateral relations deteriorate over spy scandal",
            "International coalition agrees on new round of economic sanctions",
            "Treaty signed establishing diplomatic relations between former rivals",
            "Multilateral talks produce agreement on climate change commitments",
            "Diplomatic crisis erupts over expulsion of embassy staff members",
            "Alliance partners coordinate response to regional security threats",
            "Sanctions target key officials and freeze assets of ruling elites",
            "Foreign policy shift as government seeks rapprochement with adversary",
            "International mediation effort aims to prevent armed confrontation",
            "Resolution condemning aggression passes with overwhelming majority vote",
            "Diplomatic immunity waived in unprecedented legal prosecution case",
            "Bilateral defense agreement strengthens military cooperation ties",
            "Economic sanctions devastate national currency and trade sector",
            "Peace accord signed ending decades of hostility between neighbors",
            "Consulate closure signals further deterioration in foreign relations",
            # Real-world pattern examples
            "US imposes sweeping sanctions on Iran nuclear program and IRGC officials",
            "EU expands Russia sanctions targeting energy sector and oligarchs",
            "China and US trade talks collapse over Taiwan and technology disputes",
            "JCPOA nuclear deal negotiations stall as Iran enriches uranium further",
            "UN General Assembly condemns Russian invasion and demands withdrawal",
            "North Korea sanctions tightened after latest ballistic missile test",
            "G7 leaders agree coordinated sanctions response to authoritarian aggression",
            "India and Pakistan hold backchannel diplomatic talks on Kashmir dispute",
            "Middle East peace summit brings together Arab leaders and Israeli officials",
            "African Union mediates ceasefire between warring Ethiopian factions",
            "BRICS nations challenge western sanctions with alternative payment systems",
            "US State Department issues travel advisory warning against visiting Syria",
            "International Criminal Court issues arrest warrant for head of state",
            "Arms embargo imposed on conflict zone by UN Security Council resolution",
            "Diplomatic freeze between neighbors as territorial waters dispute escalates",
        ],
        "Economic Disruption": [
            "Currency collapses as central bank fails to contain financial crisis",
            "Stock market crashes amid fears of global recession and trade war",
            "Inflation soars to record levels making basic goods unaffordable",
            "Trade war escalates with new tariffs imposed on billions in imports",
            "Supply chain disruptions cause widespread shortages of essential goods",
            "Government defaults on sovereign debt triggering economic emergency",
            "Banking sector faces liquidity crisis as depositors rush to withdraw",
            "Oil prices surge after disruption to major production facilities",
            "Unemployment rises sharply as companies announce mass layoffs",
            "Economic sanctions cripple national economy and isolate country",
            "Commodity prices spike causing food insecurity in vulnerable nations",
            "Debt crisis forces country to seek emergency international bailout",
            "Foreign investment drops dramatically amid political instability",
            "Hyperinflation renders national currency virtually worthless",
            "Trade routes disrupted by conflict affecting global supply chains",
            "Real estate market collapse threatens wider financial system stability",
            "Energy costs skyrocket as gas supplies from main provider are cut",
            "Economic recession deepens with GDP contracting for third quarter",
            "Market volatility increases as geopolitical tensions unsettle investors",
            "Export ban on critical minerals disrupts global technology manufacturing",
            # Real-world pattern examples
            "Lebanon economic collapse leaves millions in poverty as banks freeze deposits",
            "Turkey lira crashes to record low amid unconventional monetary policy",
            "Argentina seeks IMF bailout as peso plummets and inflation hits 100 percent",
            "Sri Lanka runs out of foreign reserves unable to pay for fuel and food imports",
            "Global food prices surge as Ukraine war disrupts grain exports",
            "China property sector crisis deepens as major developers default on debt",
            "Houthi attacks on Red Sea shipping disrupt global trade routes",
            "Venezuela hyperinflation forces millions to flee as economy collapses",
            "Pakistan faces balance of payments crisis with dwindling forex reserves",
            "European energy crisis worsens as Russia cuts natural gas supplies",
            "Global semiconductor shortage cripples auto and tech industries",
            "Zambia becomes first pandemic-era sovereign default in Africa",
            "Egyptian pound devaluation triggers price surge on imported goods",
            "Nigerian economy contracts as oil revenues decline amid OPEC cuts",
            "Global shipping costs spike tenfold amid port congestion and demand",
        ],
        "Infrastructure / Energy": [
            "Cyberattack targets national power grid causing widespread blackouts",
            "Pipeline explosion disrupts gas supply to millions of households",
            "Nuclear power plant placed on emergency alert after equipment failure",
            "Sabotage of undersea cables disrupts internet connectivity across region",
            "Dam failure threatens flooding of downstream communities and farmland",
            "Refinery fire halts fuel production creating nationwide fuel shortage",
            "Power outage lasting days affects hospitals and critical services",
            "Attacks on oil facilities reduce production by significant percentage",
            "Bridge collapse cuts off vital transportation link between provinces",
            "Water treatment plant contamination creates public health emergency",
            "Electrical grid overload causes cascading failures across the network",
            "Gas pipeline leak forces evacuation of residential neighborhoods",
            "Solar farm destroyed by severe weather disrupting renewable energy supply",
            "Port infrastructure damaged by storms halting international shipping",
            "Railway system sabotage disrupts freight and passenger transport",
            "Telecommunications tower attacks leave communities without phone service",
            "Oil spill from damaged tanker creates environmental catastrophe",
            "Mining disaster traps workers underground as rescue operations begin",
            "Airport runway damage from attack grounds all flights indefinitely",
            "Industrial accident at chemical plant releases toxic fumes over city",
            # Real-world pattern examples
            "Colonial Pipeline ransomware attack shuts down fuel supply to US east coast",
            "Nord Stream pipeline explosions suspected sabotage disrupt European gas supply",
            "Ukraine power grid targeted by Russian missile strikes leaving millions dark",
            "Saudi Aramco oil facilities attacked by drone swarm cutting global supply",
            "Zaporizhzhia nuclear plant shelling raises fears of radiation disaster",
            "Houthi attacks damage undersea internet cables in Red Sea corridor",
            "Iran-linked hackers target water treatment systems in multiple countries",
            "Earthquake damages critical infrastructure and collapses buildings",
            "Suez Canal blocked by container ship disrupting global shipping for weeks",
            "Chinese hackers breach US critical infrastructure including power grids",
            "Attacks on electrical transformers cause cascading grid failures",
            "Major port explosion devastates Beirut destroying surrounding neighborhoods",
            "Wildfire destroys power transmission lines causing statewide blackout",
            "Flooding damages roads bridges and water systems across the region",
            "Terror group threatens to contaminate water supply of major city",
        ],
    }

    texts: List[str] = []
    labels: List[str] = []
    for category, samples in data.items():
        texts.extend(samples)
        labels.extend([category] * len(samples))

    return texts, labels


# ── Model training & prediction ──────────────────────────────────────────

_model: Optional[Pipeline] = None


def _load_model() -> Optional[Pipeline]:
    """Load trained model from disk if available."""
    global _model
    if _model is not None:
        return _model
    if MODEL_PATH.exists():
        try:
            _model = joblib.load(MODEL_PATH)
            logger.info("Loaded event classifier from %s", MODEL_PATH)
            return _model
        except Exception as e:
            logger.warning("Failed to load classifier: %s", e)
    return None


def train_classifier(
    texts: Optional[List[str]] = None,
    labels: Optional[List[str]] = None,
) -> Dict:
    """
    Train the TF-IDF + Logistic Regression classifier.

    If no data provided, uses synthetic training data.
    Returns evaluation metrics.
    """
    global _model

    if texts is None or labels is None:
        texts, labels = _generate_training_data()
        logger.info("Using synthetic training data: %d samples", len(texts))

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels,
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            stop_words="english",
            min_df=1,
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            class_weight="balanced",
            solver="lbfgs",
        )),
    ])

    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    logger.info("Classifier accuracy: %.3f", report["accuracy"])

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    logger.info("Saved classifier to %s", MODEL_PATH)

    _model = pipeline
    return report


def classify_event(text: str, confidence_threshold: float = 0.4) -> Tuple[str, float, Dict[str, float]]:
    """
    Classify event text into a category.

    Returns:
        (category, confidence, probabilities_dict)

    Falls back to keyword rules if model not available or confidence < threshold.
    """
    probabilities = {}

    model = _load_model()
    if model is not None:
        try:
            proba = model.predict_proba([text])[0]
            classes = model.classes_
            probabilities = {cls: float(p) for cls, p in zip(classes, proba)}
            best_idx = np.argmax(proba)
            best_category = classes[best_idx]
            best_confidence = float(proba[best_idx])

            if best_confidence >= confidence_threshold:
                return best_category, best_confidence, probabilities
        except Exception as e:
            logger.warning("ML classification failed: %s", e)

    # Fallback to keywords
    category, confidence = classify_by_keywords(text)
    probabilities = probabilities or {category: confidence}
    return category, confidence, probabilities


def ensure_model_trained() -> None:
    """Train model if not already saved to disk."""
    if not MODEL_PATH.exists():
        logger.info("No classifier model found, training with synthetic data...")
        train_classifier()
