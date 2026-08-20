#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEO Keyword Clustering Agent
Script orchestrato da Claude Code (piano Pro, senza API key).
Le regole sono caricate da rules.json nella stessa cartella.
"""

import argparse
import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

# -- Brand fuzzy match ----------------------------------------------------------

def _edit_distance(a: str, b: str) -> int:
    """Distanza di Levenshtein iterativa O(n*m)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            )
        prev = curr
    return prev[lb]


# Soglia: max distanza di edit ammessa per token di lunghezza n.
# token brevi (≤5 char) → max 1 errore; token medi (6-9) → max 2; lunghi (≥10) → max 3.
def _brand_token_threshold(token_len: int) -> int:
    if token_len <= 5:
        return 1
    if token_len <= 9:
        return 2
    return 3


def _brand_span_in_tokens(word_alpha: list, brand_compact_alpha: str):
    """
    Cerca una sequenza contigua di token (alpha-only, in ordine) la cui
    concatenazione corrisponde al brand compattato (match esatto o typo), es.
    ["non", "solo", "sport"] -> "nonsolosport". Gestisce cosi i brand fatti di
    piu parole comuni ma salvati come un unico token nella colonna Brand (es.
    "Nonsolosport"), anche quando la keyword aggiunge altre parole prima o
    dopo (citta, "outlet", "negozio", ...). Ritorna (start, end) inclusivi o None.
    """
    if not brand_compact_alpha or len(brand_compact_alpha) <= 4:
        return None
    threshold = _brand_token_threshold(len(brand_compact_alpha))
    target_len = len(brand_compact_alpha)
    n = len(word_alpha)
    for start in range(n):
        compact = ""
        for end in range(start, n):
            compact += word_alpha[end]
            if len(compact) > target_len + threshold:
                break
            if len(compact) < target_len - threshold:
                continue
            if _edit_distance(compact, brand_compact_alpha) <= threshold:
                return start, end
    return None


def fuzzy_brand_match(kw_lower: str, brand: str) -> bool:
    """
    Ritorna True se almeno UN token della keyword è un misspelling di un token
    del nome brand (distanza di edit ≤ soglia adattiva), oppure se una sequenza
    contigua di token della keyword ricompone (esatta o typo) il brand scritto
    come token unico compatto (es. brand="Nonsolosport" e keyword "non solo
    sport padova").

    Gestisce anche:
    - brand con numeri nel nome (es. Piacenza1733 → "piacenza")
    - brand scritti senza spazi (es. "loropiana" → confrontato con brand senza spazi)
    - ignora token del brand ≤ 3 caratteri (preposizioni, articoli)
    """
    if not brand:
        return False

    brand_lower = brand.lower()

    # Estrai solo la parte alfabetica da ogni token (es. "piacenza1733" → "piacenza")
    brand_tokens = [
        re.sub(r"[^a-zà-ÿ]", "", t)
        for t in brand_lower.split()
    ]
    brand_tokens = [t for t in brand_tokens if len(t) > 3]
    if not brand_tokens:
        return False

    # Controlla anche brand senza spazi: "loropiana" vs "loropiana" (brand compatto)
    brand_compact = re.sub(r"\s+", "", brand_lower)
    brand_compact_alpha = re.sub(r"[^a-zà-ÿ]", "", brand_compact)
    kw_compact = re.sub(r"[\s\-_/]+", "", kw_lower)
    if brand_compact_alpha and len(brand_compact_alpha) > 4:
        if _edit_distance(kw_compact, brand_compact_alpha) <= _brand_token_threshold(len(brand_compact_alpha)):
            return True

    kw_word_tokens = [t for t in re.split(r"[\s\-_/]+", kw_lower) if t]
    kw_tokens_alpha = [re.sub(r"[^a-zà-ÿ]", "", t) for t in kw_word_tokens]

    if _brand_span_in_tokens(kw_tokens_alpha, brand_compact_alpha) is not None:
        return True

    for kw_tok_alpha in kw_tokens_alpha:
        if len(kw_tok_alpha) < 3:
            continue
        for bt in brand_tokens:
            # Skip se la lunghezza differisce troppo (ottimizzazione)
            if abs(len(kw_tok_alpha) - len(bt)) > _brand_token_threshold(len(bt)):
                continue
            dist = _edit_distance(kw_tok_alpha, bt)
            if dist <= _brand_token_threshold(len(bt)):
                return True
    return False


def _remove_brand_tokens(kw_lower: str, brand: str) -> str:
    """
    Rimuove dalla keyword i token riconducibili al brand: match esatto/typo di
    un singolo token del brand, oppure una sequenza contigua di token della
    keyword che, concatenati, corrispondono al brand scritto come un unico
    token compatto (es. brand="Nonsolosport" ma la keyword scrive "non solo
    sport padova" -> rimuove "non"/"solo"/"sport", lascia "padova").
    """
    brand_lower = brand.lower().strip() if brand else ""
    brand_tokens = [re.sub(r"[^a-zà-ÿ]", "", t) for t in brand_lower.split()]
    brand_tokens = [t for t in brand_tokens if t]
    if not brand_tokens:
        return kw_lower

    brand_compact_alpha = re.sub(r"[^a-zà-ÿ]", "", brand_lower.replace(" ", ""))

    kw_tokens = re.split(r"([\s\-_/]+)", kw_lower)  # mantieni separatori
    word_idx = [i for i, t in enumerate(kw_tokens) if re.sub(r"[^a-zà-ÿ0-9]", "", t.strip())]
    word_alpha = [re.sub(r"[^a-zà-ÿ]", "", kw_tokens[i]) for i in word_idx]

    span_positions = set()
    span = _brand_span_in_tokens(word_alpha, brand_compact_alpha)
    if span is not None:
        start, end = span
        span_positions = set(word_idx[start:end + 1])

    kept = []
    for i, tok in enumerate(kw_tokens):
        tok_clean = re.sub(r"[^a-zà-ÿ0-9]", "", tok.strip())
        if not tok_clean or re.match(r"^[\s\-_/]+$", tok):
            kept.append(tok)
            continue
        if i in span_positions:
            continue
        tok_alpha = re.sub(r"[^a-zà-ÿ]", "", tok_clean)
        matched_brand = any(
            abs(len(tok_alpha) - len(bt)) <= _brand_token_threshold(len(bt))
            and _edit_distance(tok_alpha, bt) <= _brand_token_threshold(len(bt))
            for bt in brand_tokens
        )
        if not matched_brand:
            kept.append(tok)
    return re.sub(r"\s+", " ", "".join(kept)).strip(" -_,")


def _strip_brand_tokens(kw_lower: str, brand: str) -> str:
    """
    Rimuove dalla keyword le porzioni riconducibili al brand (match esatto, typo,
    o brand scritto con spaziatura diversa dall'originale, es. "lori blu" per
    brand "Loriblu"), cosi le colonne opzionali (Materiale/Colore, Genere, ...)
    non classificano per errore parole che fanno parte del nome brand invece
    che descrivere davvero il prodotto.
    """
    if not brand:
        return kw_lower

    brand_lower = brand.lower().strip()
    brand_compact_alpha = re.sub(r"[^a-zà-ÿ]", "", brand_lower.replace(" ", ""))
    if not brand_compact_alpha:
        return kw_lower

    # L'intera keyword (spazi/trattini ignorati) è il brand con typo o
    # spaziatura diversa (es. "lori blu" -> "loriblu"): nessun residuo.
    kw_compact_alpha = re.sub(r"[^a-zà-ÿ]", "", re.sub(r"[\s\-_/]+", "", kw_lower))
    if (
        len(brand_compact_alpha) > 4
        and _edit_distance(kw_compact_alpha, brand_compact_alpha)
        <= _brand_token_threshold(len(brand_compact_alpha))
    ):
        return ""

    return _remove_brand_tokens(kw_lower, brand)

# Force UTF-8 output on Windows
if sys.platform == "win32":
    import os
    import io
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# -- Config ---------------------------------------------------------------------

# RULES_DIR punta di default al vecchio percorso in-repo, ma viene sempre
# ridiretto in main() su <workdir>/rules: le regole sono sincronizzate lì a
# ogni sessione a partire dai Google Sheet condivisi (vedi --mode sync-rules),
# non più committate in git.
RULES_DIR = Path(__file__).parent.parent / "rules"
CACHE_DIR = Path(__file__).parent.parent / "cache"

SUPPORTED_LANGS = {"IT", "EN", "ES", "FR", "DE"}
DEFAULT_LANG = "IT"
DEFAULT_BATCH_SIZE = 500
DEFAULT_CONFIDENCE_THRESHOLD = 0.85
FUZZY_THRESHOLD = 0.82

ALWAYS_ON_COLUMNS = ["Brand correlati"]


def available_verticals() -> list[str]:
    """Vertical scoperti dalle sottocartelle materializzate in RULES_DIR
    (a loro volta sincronizzate dalle sottocartelle reali su Google Drive,
    escluse quelle riservate come _attributi). Nessuna lista fissa nel codice:
    aggiungere un vertical e' un'operazione solo su Drive."""
    if not RULES_DIR.exists():
        return []
    return sorted(
        p.name for p in RULES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )


def _slugify(name: str) -> str:
    """Normalizza un nome di tab/cluster in una chiave interna stabile
    (minuscolo, accenti rimossi, spazi/punteggiatura -> underscore).
    "Genere" -> "genere", "Intento di Ricerca" -> "intento_di_ricerca"."""
    n = name.strip().lower()
    accents = str.maketrans("àáâäèéêëìíîïòóôöùúûü", "aaaaeeeeiiiioooouuuu")
    n = n.translate(accents)
    n = re.sub(r"[^a-z0-9]+", "_", n).strip("_")
    return n or "attributo"

GENDER_MALE = {"uomo", "man", "male", "maschile", "him", "uomini"}
GENDER_FEMALE = {"donna", "woman", "female", "femminile", "her", "donne"}

SYSTEM_PROMPT = """SEO clustering. Brand={brand}. Settore={sector}.
Ogni keyword appartiene a uno dei brand indicati. Clusterizza in base al significato della keyword, non al brand.
Rispondi SOLO JSON valido, zero testo extra, zero backtick.

Formato risposta:
{{
  "r": [["cluster","sotto_cluster"], ...],
  "new_rules": [{{"rule":"nome_regola","term":"termine","cluster":"...","sotto_cluster":"..."}}],
  "new_brands": ["nome brand competitor", ...]
}}

"r": array ordinato come le keyword in input. Un elemento per keyword.
"new_rules": termini NUOVI trovati nel batch che varrebbe aggiungere alle regole automatiche (solo se certi, max 5). Lascia [] se nessuno.
"new_brands": nomi di brand competitor/terzi che compaiono nelle keyword e NON sono già nella lista brand correlati sotto (solo se certi, max 5, no il brand principale={brand}). Lascia [] se nessuno.

Brand correlati già noti (non riproporli): {known_brands}

Cluster validi per questo vertical: {valid_clusters}|Brand correlato|Altro
Sotto cluster: specifico per tipo/genere (es: Sneaker Uomo, Outlet Online, Cashmere Donna, Nero)."""

# -- Rules loader ---------------------------------------------------------------

_rules_cache: dict[str, dict] = {}
_attributi_cache: dict[str, dict] = {}
_brands_cache: dict | None = None
_cities_cache: dict | None = None


def _brands_path() -> Path:
    return RULES_DIR / "brands.json"


def _cities_path() -> Path:
    return RULES_DIR / "cities.json"


def _attributi_path(lang: str) -> Path:
    return RULES_DIR / "_attributi" / f"{lang.lower()}.json"


def load_brands() -> dict:
    """Carica la mappa canonico -> varianti dei brand correlati, condivisa fra
    tutte le lingue (schema: {"canonical": {"Dr. Martens": ["dr martens", ...]}})."""
    global _brands_cache
    if _brands_cache is not None:
        return _brands_cache
    path = _brands_path()
    if not path.exists():
        _brands_cache = {"canonical": {}}
        return _brands_cache
    with path.open(encoding="utf-8-sig") as f:
        data = json.load(f)
    if "canonical" not in data and "terms" in data:
        # rules/brands.json di una sessione precedente allo schema canonico/varianti
        # (non ancora ri-materializzato da --mode sync-rules): ogni termine resta
        # il canonico di se stesso, stesso comportamento di prima.
        data["canonical"] = {t: [t.strip().lower()] for t in data.get("terms", [])}
    _brands_cache = data
    return _brands_cache


def _brand_variant_set(brands_data: dict) -> set[str]:
    """Tutte le varianti note (lowercase), unione di canonico+varianti — usato
    per i controlli di duplicato quando si aggiungono nuovi brand."""
    out: set[str] = set()
    for canon, variants in brands_data.get("canonical", {}).items():
        out.add(canon.strip().lower())
        out.update(v.strip().lower() for v in variants)
    return out


def _brand_canonical_names(brands_data: dict) -> list[str]:
    """Nomi canonici (una voce per brand, non una per variante di spelling) —
    usato per la lista brand correlati mostrata nei prompt AI."""
    return sorted(brands_data.get("canonical", {}).keys())


def load_cities() -> dict:
    """Carica la lista di città note, condivisa fra tutti i vertical e lingue
    (Sheet 'Clustering rules/Cities'). Usata per riconoscere il pattern
    "brand + città" (es. "yamamay milano"), instradato a Punti Vendita -> Store."""
    global _cities_cache
    if _cities_cache is not None:
        return _cities_cache
    path = _cities_path()
    if not path.exists():
        _cities_cache = {"terms": []}
        return _cities_cache
    with path.open(encoding="utf-8-sig") as f:
        _cities_cache = json.load(f)
    return _cities_cache


def load_attributi(lang: str = DEFAULT_LANG) -> dict:
    """Carica gli attributi opzionali (Genere, Stagionalita, ...), condivisi fra
    tutti i vertical per quella lingua (sincronizzati da _Attributi/<lang> su
    Drive). Il set di attributi e' interamente dinamico: qualunque tab lì
    presente diventa una colonna di output, senza bisogno di whitelist."""
    lang_upper = lang.upper() if lang else DEFAULT_LANG
    if lang_upper not in SUPPORTED_LANGS:
        lang_upper = DEFAULT_LANG
    if lang_upper in _attributi_cache:
        return _attributi_cache[lang_upper]
    path = _attributi_path(lang_upper)
    if not path.exists():
        data = {"rules": {}}
    else:
        with path.open(encoding="utf-8-sig") as f:
            data = json.load(f)
    _attributi_cache[lang_upper] = data
    return data


def load_rules(lang: str = DEFAULT_LANG, vertical: str = None) -> dict:
    if not vertical:
        print(f"Errore: --vertical mancante. Vertical disponibili: {available_verticals()}")
        sys.exit(1)
    lang_upper = lang.upper() if lang else DEFAULT_LANG
    if lang_upper not in SUPPORTED_LANGS:
        lang_upper = DEFAULT_LANG
    cache_key = f"{vertical}/{lang_upper}"
    if cache_key in _rules_cache:
        return _rules_cache[cache_key]
    rules_path = RULES_DIR / vertical / f"{lang_upper.lower()}.json"
    if not rules_path.exists():
        print(f"Errore: regole non trovate per il vertical '{vertical}' -> {rules_path}")
        print(f"   Vertical sincronizzati in questa sessione: {available_verticals()}")
        print(f"   Esegui prima --mode sync-rules per materializzare le regole dai Google Sheet.")
        sys.exit(1)
    with rules_path.open(encoding="utf-8-sig") as f:
        data = json.load(f)
    data["rules"].update(load_attributi(lang_upper).get("rules", {}))
    data["rules"]["related_brands"] = load_brands()
    data["rules"]["known_cities"] = load_cities()
    _rules_cache[cache_key] = data
    return data


def save_vertical(workdir: Path, vertical: str):
    (workdir / "vertical.json").write_text(json.dumps({"vertical": vertical}), encoding="utf-8")


def load_vertical(workdir: Path, cli_vertical: str = None) -> str:
    """Ritorna il vertical passato da CLI, altrimenti quello salvato da --mode prepare."""
    if cli_vertical:
        return cli_vertical
    vertical_path = workdir / "vertical.json"
    if not vertical_path.exists():
        print(f"Errore: --vertical non specificato e {vertical_path} non trovato. Esegui prima --mode prepare con --vertical, oppure passa --vertical esplicitamente.")
        sys.exit(1)
    return json.loads(vertical_path.read_text(encoding="utf-8"))["vertical"]


# -- Cache ----------------------------------------------------------------------

def _cache_files_sorted() -> list[Path]:
    """Ritorna i file JSONL nella cartella cache ordinati dalla più recente alla più vecchia."""
    if not CACHE_DIR.exists():
        return []
    files = sorted(CACHE_DIR.glob("*.jsonl"), reverse=True)
    return files


def load_cache() -> dict:
    """Carica la cache keyword -> (cluster, sotto_cluster) leggendo tutti i file
    dalla versione più recente alla più vecchia. In caso di duplicati vince la più recente."""
    cache = {}
    for path in _cache_files_sorted():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    key = entry["k"]
                    if key not in cache:
                        cache[key] = (entry["c"], entry["s"])
                except Exception:
                    pass
    return cache


def save_cache_entries(new_entries: list[tuple[str, str, str]]):
    """Crea un nuovo file JSONL datato nella cartella cache e vi scrive le entry."""
    if not new_entries:
        return
    import datetime
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CACHE_DIR / f"cache_{timestamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for kw, c, s in new_entries:
            f.write(json.dumps({"k": kw, "c": c, "s": s}, ensure_ascii=False) + "\n")


# -- Fuzzy match ----------------------------------------------------------------

def _subcluster_terms(sub_def) -> list[str]:
    """Estrae i termini trigger da un sottocluster (lista diretta o dict con 'terms')."""
    if isinstance(sub_def, list):
        return sub_def
    if isinstance(sub_def, dict):
        return sub_def.get("terms", [])
    return []


def _build_subcluster_lookup(rule: dict) -> dict[str, str]:
    """Costruisce {keyword -> sotto_cluster} dai sottocluster."""
    lookup = {}
    for sub_name, sub_def in rule.get("subclusters", {}).items():
        for kw in _subcluster_terms(sub_def):
            lookup[kw] = sub_name
    return lookup


def _all_subcluster_keywords(rule: dict) -> list[str]:
    """Ritorna tutte le keyword definite nei sottocluster della regola."""
    kws = []
    for sub_def in rule.get("subclusters", {}).values():
        kws.extend(_subcluster_terms(sub_def))
    return kws


# Cache per id(rules) (NON dentro il dict rules stesso: rules puo' essere
# riserializzato su disco da mode_add_rules, e non deve contenere chiavi extra).
_product_terms_cache: dict[int, set] = {}
_genere_terms_cache: dict[int, set] = {}


def _product_term_set(rules: dict) -> set:
    """Tutti i termini prodotto noti (esclude regole a colonna, related_brands e
    known_cities). Usato dalla regola brand_navigation per riconoscere un
    remainder breve (es. "body", "bra") come parola prodotto vera e non come
    typo del brand.
    """
    key = id(rules)
    cached = _product_terms_cache.get(key)
    if cached is not None:
        return cached
    terms: set = set()
    for rule_key, rule in rules.get("rules", {}).items():
        if rule_key in ("related_brands", "known_cities") or "column" in rule:
            continue
        terms.update(t.lower() for t in _all_subcluster_keywords(rule))
    _product_terms_cache[key] = terms
    return terms


def _genere_term_set(rules: dict) -> set:
    """Tutti i termini della colonna Genere (Uomo/Donna/Kids), in minuscolo.
    Usato dalla regola brand_navigation per instradare "brand + genere" sempre
    a Brand Navigazionale, indipendentemente dalla lunghezza della parola
    (evita l'incoerenza "brand uomo" -> Brand Secco vs "brand donna" -> Brand
    Navigazionale, dovuta solo al fatto che "uomo" ha <=4 caratteri).
    """
    key = id(rules)
    cached = _genere_terms_cache.get(key)
    if cached is not None:
        return cached
    terms: set = set()
    for vals in rules.get("rules", {}).get("genere", {}).get("keywords", {}).values():
        terms.update(v.lower() for v in vals)
    _genere_terms_cache[key] = terms
    return terms


def _build_rule_keyword_list(rules: dict) -> list[tuple[str, str, str]]:
    """Costruisce lista piatta (keyword, cluster, sotto_cluster) da tutte le regole."""
    flat: list[tuple[str, str, str]] = []
    rule_defs = rules.get("rules", {})
    for rule_key, rule in rule_defs.items():
        cluster = rule.get("cluster", "")
        if not cluster:
            continue
        default_sub = rule.get("default_subcluster", cluster)
        lookup = _build_subcluster_lookup(rule)
        for kw in _all_subcluster_keywords(rule):
            sub = lookup.get(kw, default_sub)
            flat.append((kw, cluster, sub))
    return flat


def fuzzy_classify(keyword: str, rule_keywords: list[tuple[str, str, str]]) -> tuple[str, str, float]:
    """Prova a classificare con similarità stringa se nessuna regola esatta matcha."""
    kw = keyword.lower().strip()
    len_kw = len(kw)
    best_score = 0.0
    best_cluster = ""
    best_sotto = ""
    for rule_kw, cluster, sotto in rule_keywords:
        len_rule_kw = len(rule_kw)
        # Ottimizzazione di lunghezza per evitare SequenceMatcher lenti
        if (2.0 * min(len_kw, len_rule_kw) / (len_kw + len_rule_kw)) < FUZZY_THRESHOLD:
            continue
        score = SequenceMatcher(None, kw, rule_kw).ratio()
        if score > best_score:
            best_score = score
            best_cluster = cluster
            best_sotto = sotto
    if best_score >= FUZZY_THRESHOLD:
        return best_cluster, best_sotto, best_score * 0.80  # Scala confidence per non sovrastimare
    return "", "", 0.0


# -- Helpers --------------------------------------------------------------------

def detect_columns(df: pd.DataFrame) -> dict:
    cols = {c.lower(): c for c in df.columns}
    mapping = {}
    for alias in ["keyword", "kw", "parola chiave", "query", "keywords"]:
        if alias in cols:
            mapping["keyword"] = cols[alias]
            break
    for alias in ["brand", "marchio", "competitor"]:
        if alias in cols:
            mapping["brand"] = cols[alias]
            break
    for alias in ["brand/not brand", "type", "tipo", "brand_not_brand"]:
        if alias in cols:
            mapping["type"] = cols[alias]
            break
    for alias in ["country", "paese", "lang", "language", "lingua", "mercato", "market"]:
        if alias in cols:
            mapping["country"] = cols[alias]
            break
    return mapping


def log(msg: str, level: str = "info"):
    icons = {"info": "->", "ok": "[OK]", "err": "", "warn": "[WARN]"}
    print(f"  {icons.get(level, '.')} {msg}", flush=True)


_TERM_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _term_matches(term: str, kw_lower: str) -> bool:
    """
    True se il termine è presente in kw come parola/frase intera, non come sotto-stringa
    di un'altra parola (es. "blu" non deve matchare dentro "loriblu").
    """
    compiled = _TERM_PATTERN_CACHE.get(term)
    if compiled is None:
        compiled = re.compile(r"(?<![a-zà-ÿ])" + re.escape(term) + r"(?![a-zà-ÿ])")
        _TERM_PATTERN_CACHE[term] = compiled
    return compiled.search(kw_lower) is not None


# Collisioni lessicali note fra un termine brand correlato e una frase non-brand
# che lo contiene per intero (es. "valentino" dentro "san valentino", l'evento,
# non il brand Valentino). Se la frase esclusa e' presente, il termine non conta
# come brand correlato.
_BRAND_TERM_COLLISIONS: dict[str, list[str]] = {
    "valentino": ["san valentino"],
}


def _term_excluded_by_collision(term: str, kw_lower: str) -> bool:
    return any(phrase in kw_lower for phrase in _BRAND_TERM_COLLISIONS.get(term, []))


def _find_related_brand(rb_rule: dict, kw_lower: str, exclude_lower: str) -> str:
    """Cerca un brand correlato (terzo, diverso dal brand principale) nella
    keyword, usando la mappa canonico -> varianti di rules/brands.json (vedi
    materialize_brands_from_sheet). Ritorna il nome CANONICO, non la variante
    matchata: grafie diverse dello stesso brand (es. "dr martens"/"dr. martens"/
    "drmartens") restituiscono sempre lo stesso related_brand invece di una
    forma diversa per ciascuna variante incontrata."""
    for canon, variants in rb_rule.get("canonical", {}).items():
        if exclude_lower and (exclude_lower == canon.lower() or exclude_lower in variants):
            continue
        for t in variants:
            if _term_matches(t, kw_lower) and not _term_excluded_by_collision(t, kw_lower):
                return canon
    return ""


def _kw_contains(kw_lower: str, words: list) -> str | None:
    """Ritorna la prima parola trovata nella keyword (come parola intera), None se nessuna."""
    for word in words:
        if _term_matches(word, kw_lower):
            return word
    return None


def _match_subcluster(kw_lower: str, rule: dict) -> tuple[str, str] | tuple[None, None]:
    """
    Cerca la keyword nei sottocluster della regola.
    Ritorna (hit_keyword, sotto_cluster) se trovata, (None, None) altrimenti.
    """
    for sub_name, sub_def in rule.get("subclusters", {}).items():
        terms = _subcluster_terms(sub_def)
        hit = _kw_contains(kw_lower, terms)
        if hit:
            return hit, sub_name
    return None, None


def _detect_gender(kw_lower: str) -> str:
    if any(g in kw_lower for g in GENDER_MALE):
        return "male"
    if any(g in kw_lower for g in GENDER_FEMALE):
        return "female"
    return "unisex"


# -- Rule-based classifier ------------------------------------------------------

# I Cluster sono interamente dinamici, come i vertical e gli attributi: rule_key
# è direttamente il nome display del Cluster così come appare nella colonna
# 'Cluster' dello Sheet (nessuna mappa fissa, nessuna whitelist — vedi
# materialize_cluster_rules_from_sheets). Un Cluster con un nome mai visto prima
# funziona subito con il match generico su subclusters/requires_any qui sotto
# (ultimo branch di classify_by_rules), nessuna modifica di codice necessaria.
# Solo questi nomi hanno in più una logica di discriminazione dedicata (typo/
# fuzzy sul brand, online-vs-fisico, ...) o una confidence specifica invece del
# flat 0.85 del branch generico — un Cluster rinominato perde solo questo bonus,
# non smette di funzionare:
#   "Brand Navigation", "Outlet e Sconti", "Punti Vendita", "Calzature",
#   "Costumi e Beachwear", "Abbigliamento", "Accessori", "Profumeria",
#   "Istituzionale"


def _is_ignorable(keyword: str) -> bool:
    """True se la keyword è solo numeri, caratteri speciali o troppo corta per avere senso."""
    kw = keyword.strip()
    if not kw:
        return True
    # Rimuovi spazi e caratteri speciali: se non resta nulla di alfabetico, ignora
    alpha_only = re.sub(r"[^a-zA-ZÀ-ÿ]", "", kw)
    return len(alpha_only) < 2


def classify_by_rules(keyword: str, brand: str, rules: dict) -> tuple[str, str, float, str]:
    """
    Classifica keyword usando le regole da rules.json.
    Ritorna (cluster, sotto_cluster, confidence, brand_correlato).
    confidence=0 -> va all'AI. brand_correlato è vuoto se nessun brand correlato trovato.
    """
    if _is_ignorable(keyword):
        return "Ignora", "", 1.0, ""

    kw = keyword.lower().strip()
    priority = rules.get("priority_order", [])
    rule_defs = rules.get("rules", {})

    # Calcola brand correlato una volta sola, indipendentemente dall'ordine delle altre regole
    rb_rule = rule_defs.get("related_brands", {})
    brand_lower_rb = brand.lower().strip() if brand else ""
    related_brand = _find_related_brand(rb_rule, kw, brand_lower_rb)

    # Se la keyword contiene già un altro brand riconosciuto per match esatto,
    # non lasciare che un fuzzy match (typo-tolerante) del brand principale la
    # rivendichi come propria (es. "yamaha pesaro" non è un typo di "yamamay",
    # è un brand terzo vero e va lasciato classificare come Brand correlato).
    has_other_known_brand = bool(related_brand)

    for rule_key in priority:
        rule = rule_defs.get(rule_key)
        if not rule:
            continue

        # Regole colonne opzionali (hanno "column", non "cluster")
        if "column" in rule and "cluster" not in rule:
            continue

        # Brand Navigation -- solo keyword che sono "brand puro"
        # Match brand token: controlla nome completo OPPURE ogni singolo token
        # del nome brand (es. "Brunello Cucinelli" matcha anche "cucinelli").
        # Fuzzy brand match cattura misspelling (cucinello, falconari, ...).
        # Keyword con modificatori prodotto vanno al cluster prodotto.
        if rule_key == "Brand Navigation":
            brand_tokens = brand.lower().split() if brand else []
            exact_brand_hit = brand and (
                brand.lower() in kw
                or any(token in kw.split() for token in brand_tokens if len(token) > 3)
            )
            brand_in_kw = exact_brand_hit or (
                brand and not has_other_known_brand and fuzzy_brand_match(kw, brand)
            )
            if brand_in_kw:
                # Rimuovi i token brand dalla keyword per ottenere il remainder.
                # Gestisce sia match esatti che fuzzy (misspelling): rimuove qualsiasi
                # token della keyword che sia sufficientemente simile a un token brand.
                # Caso speciale: keyword senza spazi (es. "lorpiana", "gransasso") —
                # se l'intera keyword matcha il brand compatto, remainder è vuoto.
                brand_compact_alpha = re.sub(
                    r"[^a-zà-ÿ]", "", re.sub(r"\s+", "", brand.lower() if brand else "")
                )
                kw_compact = re.sub(r"[\s\-_/]+", "", kw)
                # Confronta anche la versione solo-alpha della kw_compact
                # (gestisce kw tipo "piacenza1733" dove il numero non fa parte del brand)
                kw_compact_alpha = re.sub(r"[^a-zà-ÿ]", "", kw_compact)
                compact_cmp = kw_compact_alpha if kw_compact_alpha else kw_compact
                if (
                    brand_compact_alpha
                    and len(brand_compact_alpha) > 4
                    and _edit_distance(compact_cmp, brand_compact_alpha)
                    <= _brand_token_threshold(len(brand_compact_alpha))
                    and " " not in kw.strip()
                ):
                    # La keyword è solo il brand compattato (senza spazi)
                    return rule["cluster"], "Brand Secco", 0.92, related_brand

                remainder = _remove_brand_tokens(kw, brand)
                remainder_norm = remainder.strip().lower()

                # Remainder è un termine prodotto vero (es. "body", "bra", "tuta"):
                # NON è brand secco, lascia classificare dalle regole prodotto più
                # sotto nella priority_order, anche se è breve (<=4 caratteri).
                if remainder_norm and remainder_norm in _product_term_set(rules):
                    continue

                # Remainder è un genere/kids (es. "uomo", "donna", "man", "kids"):
                # sempre Brand Navigazionale, indipendentemente dalla lunghezza
                # della parola (evita "brand uomo" -> Secco vs "brand donna" ->
                # Navigazionale solo perché "uomo" ha <=4 caratteri).
                if remainder_norm in _genere_term_set(rules):
                    return rule["cluster"], "Brand Navigazionale", 0.90, related_brand

                # Remainder è una città nota (es. "yamamay milano"): non è
                # navigazionale, è ricerca di un punto vendita fisico in quella
                # città -> Punti Vendita/Store (lista città condivisa in
                # rules/cities.json, vedi Clustering rules/Cities su Drive).
                known_cities = rule_defs.get("known_cities", {}).get("terms", [])
                if any(_term_matches(city, remainder_norm) for city in known_cities):
                    pv_rule = rule_defs.get("Punti Vendita", {})
                    pv_cluster = pv_rule.get("cluster", "Punti Vendita")
                    pv_sub = pv_rule.get("default_subcluster", "Store")
                    return pv_cluster, pv_sub, 0.93, related_brand

                # Remainder vuoto o quasi: puro brand
                if len(remainder) <= 3:
                    return rule["cluster"], "Brand Secco", 0.95, related_brand

                # Remainder breve (es. typo, variante) o stop word navigazionale: ancora brand
                stop_words = rule.get("brand_stop_words", [
                    "shop", "sito", "website", "official", "ufficiale",
                    "online", "it", "com", "www", "spa", "srl", "group", "italia"
                ])
                if remainder in stop_words:
                    return rule["cluster"], "Brand Secco", 0.92, related_brand

                # Remainder breve (≤4 char) e non è una parola prodotto: brand puro
                if len(remainder) <= 4:
                    return rule["cluster"], "Brand Secco", 0.92, related_brand

                # Qualsiasi altro remainder (parola prodotto, modificatore, ecc.)
                # -> NON è brand navigation, lascia classificare dalle regole prodotto.
                # Se nessuna regola prodotto matcha, torneremo qui sotto come fallback.
            continue

        # Outlet e Sconti — cerca match in termini, poi discrimina online vs fisico con requires_any
        if rule_key == "Outlet e Sconti":
            hit, _ = _match_subcluster(kw, rule)
            if hit:
                sub = rule["default_subcluster"]
                for sub_name, sub_def in rule.get("subclusters", {}).items():
                    if isinstance(sub_def, dict):
                        req = sub_def.get("requires_any", [])
                        if req and any(_term_matches(r, kw) for r in req):
                            sub = sub_name
                            break
                return rule["cluster"], sub, 0.90, related_brand
            continue

        # Punti Vendita — Near me via requires_any, altrimenti Store
        if rule_key == "Punti Vendita":
            hit, _ = _match_subcluster(kw, rule)
            if hit:
                sub = rule["default_subcluster"]
                for sub_name, sub_def in rule.get("subclusters", {}).items():
                    if isinstance(sub_def, dict):
                        req = sub_def.get("requires_any", [])
                        if req and any(_term_matches(r, kw) for r in req):
                            sub = sub_name
                            break
                return rule["cluster"], sub, 0.88, related_brand
            continue

        # Calzature — subclusters (no gender suffix: genere è colonna dedicata)
        if rule_key == "Calzature":
            hit, base_sub = _match_subcluster(kw, rule)
            if hit:
                if not base_sub:
                    base_sub = rule.get("default_subcluster", "Scarpe")
                return rule["cluster"], base_sub, 0.86, related_brand
            continue

        # Costumi e Beachwear
        if rule_key == "Costumi e Beachwear":
            hit, sub = _match_subcluster(kw, rule)
            if hit:
                if not sub:
                    sub = rule.get("default_subcluster", "Swimwear")
                return rule["cluster"], sub, 0.88, related_brand
            continue

        # Abbigliamento — subclusters (no gender suffix: genere è colonna dedicata)
        if rule_key == "Abbigliamento":
            hit, base_sub = _match_subcluster(kw, rule)
            if hit:
                if not base_sub:
                    base_sub = rule.get("default_subcluster", "Abbigliamento Generico")
                return rule["cluster"], base_sub, 0.85, related_brand
            continue

        # Accessori
        if rule_key == "Accessori":
            hit, sub = _match_subcluster(kw, rule)
            if hit:
                if not sub:
                    sub = rule.get("default_subcluster", "Accessori")
                return rule["cluster"], sub, 0.85, related_brand
            continue

        # Profumeria — primo subcluster che matcha vince (termini specifici prima del generico)
        if rule_key == "Profumeria":
            hit, sub = _match_subcluster(kw, rule)
            if hit:
                if not sub:
                    sub = rule.get("default_subcluster", "Fragranze")
                return rule["cluster"], sub, 0.86, related_brand
            continue

        # Istituzionale — requires_any sui sottocluster
        if rule_key == "Istituzionale":
            hit, _ = _match_subcluster(kw, rule)
            if hit:
                sub = rule.get("default_subcluster", "Governance")
                for sub_name, sub_def in rule.get("subclusters", {}).items():
                    req = sub_def.get("requires_any", [])
                    if req and any(r in kw for r in req):
                        sub = sub_name
                        break
                return rule["cluster"], sub, 0.88, related_brand
            continue

        # Brand correlati — popola related_brand e prosegue con le altre regole
        if rule_key == "related_brands":
            if not related_brand:
                related_brand = _find_related_brand(rule, kw, brand.lower().strip() if brand else "")
            continue

        # Regole generiche — match su subclusters con requires_any opzionale
        if "cluster" in rule and "subclusters" in rule:
            hit, base_sub = _match_subcluster(kw, rule)
            if hit:
                sub = base_sub or rule.get("default_subcluster", rule["cluster"])
                # Affina con requires_any se presente nel sottocluster
                for sub_name, sub_def in rule.get("subclusters", {}).items():
                    if isinstance(sub_def, dict):
                        req = sub_def.get("requires_any", [])
                        if req and any(_term_matches(r, kw) for r in req):
                            sub = sub_name
                            break
                return rule["cluster"], sub, 0.85, related_brand
            continue

    # Fallback: nessuna regola prodotto ha matchato, ma il brand è nella keyword.
    # Distingue tra brand secco (solo brand ±typo) e brand con contesto generico.
    if brand:
        brand_tokens_fb = [
            re.sub(r"[^a-zà-ÿ]", "", t)
            for t in brand.lower().split()
            if len(re.sub(r"[^a-zà-ÿ]", "", t)) > 3
        ]
        brand_in_kw_fb = (
            brand.lower() in kw
            or any(token in kw.split() for token in brand_tokens_fb)
            or (not has_other_known_brand and fuzzy_brand_match(kw, brand))
        )
        if brand_in_kw_fb:
            # Calcola remainder rimuovendo i token brand dalla keyword
            remainder_fb = _remove_brand_tokens(kw, brand)
            remainder_fb_norm = remainder_fb.strip().lower()

            if remainder_fb_norm in _genere_term_set(rules):
                return "Brand Navigation", "Brand Navigazionale", 0.90, related_brand
            if len(remainder_fb) <= 3:
                return "Brand Navigation", "Brand Secco", 0.88, related_brand
            return "Brand Navigation", "Brand Navigazionale", 0.86, related_brand

    return "", "", 0.0, related_brand


# Cache per id(rules): mappa colonna -> rule_key, derivata dinamicamente dal
# campo "column" di ogni regola attributo (nessuna whitelist fissa: una tab
# nuova in _Attributi diventa automaticamente una colonna nuova in output).
_col_to_rule_cache: dict[int, dict[str, str]] = {}


def _column_to_rule_map(rules: dict) -> dict[str, str]:
    key = id(rules)
    cached = _col_to_rule_cache.get(key)
    if cached is not None:
        return cached
    mapping = {
        rule["column"]: rule_key
        for rule_key, rule in rules.get("rules", {}).items()
        if "column" in rule
    }
    _col_to_rule_cache[key] = mapping
    return mapping


def classify_optional(keyword: str, rules: dict, selected_cols: list[str]) -> dict:
    """Classifica le colonne opzionali selezionate (derivate dinamicamente
    dalle regole attributo presenti in 'rules', non da una lista fissa)."""
    kw = keyword.lower().strip()
    result = {}
    rule_defs = rules.get("rules", {})
    col_to_rule = _column_to_rule_map(rules)

    for col in selected_cols:
        rule_key = col_to_rule.get(col)
        if not rule_key:
            result[col] = ""
            continue
        rule = rule_defs.get(rule_key, {})
        matched = ""
        for val, words in rule.get("keywords", {}).items():
            if any(_term_matches(w, kw) for w in words):
                matched = val
                break
        result[col] = matched

    return result


# Priorita' storica fra gli attributi noti quando piu' di uno potrebbe fare da
# cluster_fallback per la stessa keyword (Evento > Stagionalita > Outfit >
# Recensioni > Materiale/Colore > Genere). Attributi nuovi aggiunti via Sheet
# (non in questa lista) partecipano comunque al fallback, solo con priorita'
# piu' bassa — l'ordine delle tab nello Sheet non li influenza.
_LEGACY_FALLBACK_ORDER = ["evento", "stagionalita", "outfit", "recensioni", "materiale_colore", "genere"]

_fallback_order_cache: dict[int, list[str]] = {}


def _fallback_order(rules: dict) -> list[str]:
    key = id(rules)
    cached = _fallback_order_cache.get(key)
    if cached is not None:
        return cached
    rule_defs = rules.get("rules", {})
    with_fallback = [k for k, r in rule_defs.items() if "column" in r and r.get("cluster_fallback")]
    ordered = [k for k in _LEGACY_FALLBACK_ORDER if k in with_fallback]
    ordered += [k for k in with_fallback if k not in ordered]
    _fallback_order_cache[key] = ordered
    return ordered


def classify_optional_fallback(keyword: str, rules: dict) -> tuple[str, str, float]:
    """
    Fallback in cascata sugli attributi che hanno 'cluster_fallback' (ordine:
    vedi _LEGACY_FALLBACK_ORDER, poi eventuali attributi nuovi). Se una regola
    matcha, usa il suo 'cluster_fallback' come cluster principale.
    """
    kw = keyword.lower().strip()
    rule_defs = rules.get("rules", {})
    for rule_key in _fallback_order(rules):
        rule = rule_defs.get(rule_key, {})
        cluster_fb = rule.get("cluster_fallback", "")
        for val, words in rule.get("keywords", {}).items():
            if any(_term_matches(w, kw) for w in words):
                # il genere va solo nella colonna dedicata, mai come sotto cluster
                sotto = "" if rule_key == "genere" else val
                return cluster_fb, sotto, 0.80
    return "", "", 0.0


# -- Materializzazione regole da Google Sheet ------------------------------------
#
# Le regole vivono nella cartella Drive "Clustering rules" (uno Sheet per
# vertical/lingua per i cluster, uno Sheet "_Attributi/<lang>" condiviso fra
# tutti i vertical per gli attributi opzionali, uno Sheet "Brands" condiviso).
# Ogni Sheet è monotab (formato compresso, vedi sotto) e si scarica come
# .csv — un curl anonimo sull'endpoint di export di Google Sheets
# (.../export?format=csv) diretto su disco sotto <workdir>/sheets_raw/, o il
# tool connettore Drive download_file_content(exportMimeType="text/csv") in
# ambienti dove il curl non è disponibile (es. claude.ai) — mai attraverso il
# contesto del modello in altro modo (niente read_file_content/Write per riga:
# il connettore Drive serve solo per trovare gli ID dei file via
# search_files). --mode sync-rules legge ogni .csv e materializza lo schema
# JSON interno atteso da load_rules()/load_attributi()/load_brands(), sotto
# <workdir>/rules/.
#
# Il contenuto del CSV diventa una TSV interna equivalente (prima riga header,
# ignorata; righe successive = celle separate da TAB) prima di passare per lo
# stesso parsing di sempre. Due formati di tab-cluster sono supportati (si
# riconoscono dalla prima cella dell'header, vedi
# materialize_cluster_rules_from_sheets): legacy (una riga per termine,
# applicabile solo se l'intero Sheet è un unico cluster — _parse_cluster_tab)
# e compresso (colonna Cluster esplicita, una riga per Sottocluster con
# Terms/Richiede Anche separati da '|' — _parse_cluster_tab_compressed), che è
# l'unico che ha senso per un Sheet monotab con più cluster.

# Fallback per l'ordine di valutazione dei cluster "noti" (i piu' specifici
# prima dei generici, nomi display così come appaiono nella colonna 'Cluster'
# dello Sheet), usato solo per i cluster senza un valore esplicito nella
# colonna 'Cluster Order' dello Sheet compresso (vedi
# materialize_cluster_rules_from_sheets, che quel valore lo preferisce quando
# presente). Un cluster nuovo non presente qui sotto (nessuna voce fissa, e
# senza 'Cluster Order' impostato) finisce comunque in coda, nell'ordine in
# cui le sue tab sono state lette — niente modifica di codice necessaria. Gli
# attributi non hanno un ordine reciproco (colonne indipendenti) quindi non
# compaiono qui.
PRIORITY_ORDER_BASE = [
    "Brand Navigation",
    "Outlet e Sconti",
    "Punti Vendita",
    "Profumeria",
    "Calzature",
    "Costumi e Beachwear",
    "Squadre di Calcio",
    "Abbigliamento",
    "Accessori",
    "Ispirazionale",
    "Carriere e HR",
    "Istituzionale",
]


def _read_tsv_rows(raw_text: str) -> list[list[str]]:
    """Righe TSV di una tab (prima riga = header, ignorata)."""
    lines = [ln for ln in raw_text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return []
    return [ln.split("\t") for ln in lines[1:]]


def _cell(row: list[str], i: int | None) -> str:
    return row[i].strip() if i is not None and i < len(row) else ""


def _header_indices(raw_text: str) -> dict[str, int]:
    """Mappa nome-colonna (lowercase) -> indice, dalla riga di header di una tab.
    Permette a _parse_cluster_tab_compressed di leggere le colonne per nome
    invece che per posizione fissa, cosi' colonne opzionali (es. 'Cluster
    Order'/'Sottocluster Order') possono essere presenti o assenti senza
    rompere il parsing delle altre."""
    lines = [ln for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return {}
    return {h.strip().lower(): i for i, h in enumerate(lines[0].split("\t"))}


def _csv_to_tabs(path: Path) -> dict[str, str]:
    """Apre un .csv scaricato via export Google Sheet (una sola tab: l'export
    CSV di Drive copre sempre e solo un tab, quindi lo Sheet sorgente deve
    essere monotab — vedi CLAUDE.md, formato compresso). Restituisce
    {nome_tab: testo_tsv}, nella stessa forma attesa da
    _parse_cluster_tab/_parse_attributo_tab (prima riga header, ignorata). Il
    nome-tab usato come chiave (stem del file) non ha peso per il formato
    compresso (ignorato da materialize_*_from_sheets)."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [row for row in csv.reader(f) if any(c.strip() for c in row)]
    return {path.stem: "\n".join("\t".join(row) for row in rows)}


def _find_single_sheet_file(staging: Path, stem: str) -> Path | None:
    """File .csv di uno Sheet unico non per-lingua (brands, cities) in una cartella di staging."""
    csv_path = staging / f"{stem}.csv"
    return csv_path if csv_path.exists() else None


def _apply_terms_to_subcluster(subclusters: dict, sotto: str, terms: list[str], richiede: str, note: str) -> None:
    """Aggiunge una lista di termini (e opzionalmente 'Richiede anche'/Note, che
    si applicano all'intero sottocluster, non al singolo termine — vedi
    classify_by_rules) all'entry di subclusters[sotto]. Condiviso da
    _parse_cluster_tab (una riga = un termine) e _parse_cluster_tab_compressed
    (una riga = lista di termini separati da '|')."""
    entry = subclusters.setdefault(sotto, {"terms": []})
    for t in terms:
        if t and t not in entry["terms"]:
            entry["terms"].append(t)
    if richiede:
        reqs = entry.setdefault("requires_any", [])
        for r in re.split(r"[,|]", richiede):
            r = r.strip().lower()
            if r and r not in reqs:
                reqs.append(r)
    if note:
        entry["note"] = note


def _parse_cluster_tab(tab_name: str, raw_text: str) -> dict:
    """Tab-cluster (formato legacy, una tab per cluster): Sotto Cluster | Termine
    | Richiede anche | Note, una riga per termine. Convenzioni: Termine="(default)"
    sulla riga -> Sotto Cluster diventa default_subcluster; in "Brand Navigation",
    Sotto Cluster="(stop word)" -> brand_stop_words. Le città vivono ora nello
    Sheet condiviso 'Clustering rules/Cities' (rules/cities.json): righe "Brand
    + Città" ancora presenti per la vecchia convenzione vengono ignorate con un
    avviso. Vedi anche _parse_cluster_tab_compressed per il formato a tab unica."""
    subclusters: dict = {}
    default_subcluster = ""
    brand_stop_words: list[str] = []
    is_brand_navigation = tab_name.strip().lower() == "brand navigation"
    legacy_city_terms: list[str] = []

    for row in _read_tsv_rows(raw_text):
        sotto = _cell(row, 0)
        termine = _cell(row, 1)
        richiede = _cell(row, 2)
        note = _cell(row, 3)

        if is_brand_navigation and sotto.lower() == "(stop word)":
            if termine:
                brand_stop_words.append(termine.lower())
            continue
        if is_brand_navigation and sotto == "Brand + Città":
            if termine:
                legacy_city_terms.append(termine.lower())
            continue
        if termine == "(default)":
            default_subcluster = sotto
            continue
        if not termine:
            continue

        target = sotto or tab_name
        _apply_terms_to_subcluster(subclusters, target, [termine.lower()], richiede, note)

    if legacy_city_terms:
        log(
            f"tab '{tab_name}': {len(legacy_city_terms)} righe 'Brand + Città' ignorate "
            f"(es. {', '.join(legacy_city_terms[:5])}...) — le città vivono ora nello Sheet "
            f"condiviso 'Clustering rules/Cities', rimuovi queste righe quando comodo",
            "warn",
        )

    rule: dict = {"cluster": tab_name, "subclusters": subclusters}
    if default_subcluster:
        rule["default_subcluster"] = default_subcluster
    if brand_stop_words:
        rule["brand_stop_words"] = brand_stop_words
    return rule


def _parse_order_value(raw: str) -> float | None:
    """Converte una cella 'Cluster Order'/'Sottocluster Order' in float, None se
    vuota o non numerica (probabile typo: viene ignorata, non blocca il parsing)."""
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_cluster_tab_compressed(raw_text: str) -> dict[str, dict]:
    """Tab-cluster compressa (formato a tab unica, tutti i cluster di un vertical/
    lingua nella stessa tab): Cluster | Sottocluster | Cluster Order |
    Sottocluster Order | Terms | Richiede Anche | Note, una riga per
    (Cluster, Sottocluster) — Terms e Richiede Anche sono liste separate da '|'
    invece di una riga per termine (vedi CLAUDE.md, sezione 'Sincronizza da
    Google Drive'). Più righe per lo stesso (Cluster, Sottocluster) vengono
    unite (utile per i blocchi incollati da --mode add-rules, che aggiungono
    una riga per termine invece di editare la lista pipe esistente).

    'Cluster Order'/'Sottocluster Order' sono opzionali (letti per nome
    colonna, non per posizione fissa: uno Sheet senza queste due colonne
    continua a funzionare esattamente come prima). Quando presenti, fissano
    esplicitamente l'ordine di valutazione — rispettivamente tra i cluster
    (vedi materialize_cluster_rules_from_sheets) e tra i sottocluster dello
    stesso cluster (qui sotto, riordina 'subclusters' prima di restituirlo,
    dato che classify_by_rules/_match_subcluster valutano i sottocluster
    nell'ordine del dict). Il valore è preso dalla prima riga non vuota
    incontrata per quel (Cluster) / (Cluster, Sottocluster); righe successive
    senza valore non lo sovrascrivono. Sottocluster senza valore esplicito
    finiscono in coda, nell'ordine di prima apparizione (comportamento
    storico). Restituisce {nome_cluster: rule_dict}, stesso schema di
    _parse_cluster_tab con l'aggiunta della chiave 'cluster_order' (opzionale,
    consumata e rimossa da materialize_cluster_rules_from_sheets)."""
    cols = _header_indices(raw_text)
    idx_cluster = cols.get("cluster", 0)
    idx_sotto = cols.get("sottocluster", 1)
    idx_cluster_order = cols.get("cluster order")
    idx_sotto_order = cols.get("sottocluster order")
    idx_terms = cols.get("terms", 2)
    idx_richiede = cols.get("richiede anche", 3)
    idx_note = cols.get("note", 4)

    by_cluster: dict[str, dict] = {}

    for row in _read_tsv_rows(raw_text):
        cluster_name = _cell(row, idx_cluster)
        sotto = _cell(row, idx_sotto)
        terms_raw = _cell(row, idx_terms)
        richiede = _cell(row, idx_richiede)
        note = _cell(row, idx_note)
        if not cluster_name or not sotto:
            continue

        state = by_cluster.setdefault(
            cluster_name,
            {
                "subclusters": {},
                "default_subcluster": "",
                "brand_stop_words": [],
                "legacy_city_terms": [],
                "cluster_order": None,
                "sotto_order": {},
            },
        )

        if idx_cluster_order is not None and state["cluster_order"] is None:
            order = _parse_order_value(_cell(row, idx_cluster_order))
            if order is not None:
                state["cluster_order"] = order
        if idx_sotto_order is not None and sotto not in state["sotto_order"]:
            order = _parse_order_value(_cell(row, idx_sotto_order))
            if order is not None:
                state["sotto_order"][sotto] = order

        is_brand_navigation = cluster_name.strip().lower() == "brand navigation"
        terms = [t.strip().lower() for t in terms_raw.split("|") if t.strip()]

        if is_brand_navigation and sotto.lower() == "(stop word)":
            for t in terms:
                if t not in state["brand_stop_words"]:
                    state["brand_stop_words"].append(t)
            continue
        if is_brand_navigation and sotto == "Brand + Città":
            state["legacy_city_terms"].extend(terms)
            continue
        if terms_raw.strip() == "(default)":
            state["default_subcluster"] = sotto
            continue
        if not terms:
            continue

        _apply_terms_to_subcluster(state["subclusters"], sotto, terms, richiede, note)

    result: dict[str, dict] = {}
    for cluster_name, state in by_cluster.items():
        if state["legacy_city_terms"]:
            log(
                f"cluster '{cluster_name}': {len(state['legacy_city_terms'])} righe 'Brand + Città' ignorate "
                f"(es. {', '.join(state['legacy_city_terms'][:5])}...) — le città vivono ora nello Sheet "
                f"condiviso 'Clustering rules/Cities', rimuovi queste righe quando comodo",
                "warn",
            )
        subclusters = state["subclusters"]
        sotto_order = state["sotto_order"]
        if sotto_order:
            ordered_keys = sorted(subclusters.keys(), key=lambda k: sotto_order.get(k, float("inf")))
            subclusters = {k: subclusters[k] for k in ordered_keys}
        rule: dict = {"cluster": cluster_name, "subclusters": subclusters}
        if state["default_subcluster"]:
            rule["default_subcluster"] = state["default_subcluster"]
        if state["brand_stop_words"]:
            rule["brand_stop_words"] = state["brand_stop_words"]
        if state["cluster_order"] is not None:
            rule["cluster_order"] = state["cluster_order"]
        result[cluster_name] = rule
    return result


def _parse_attributo_tab(tab_name: str, raw_text: str) -> dict:
    """Tab-attributo (formato legacy): Valore | Termine | Cluster fallback
    (opzionale), una riga per termine. Cluster fallback è unico per l'intera
    tab (preso dalla prima riga non vuota che lo specifica), non per singolo
    Valore/termine. Vedi anche _parse_attributo_tab_compressed."""
    keywords: dict[str, list[str]] = {}
    cluster_fallback = ""
    for row in _read_tsv_rows(raw_text):
        valore = _cell(row, 0)
        termine = _cell(row, 1)
        fallback = _cell(row, 2)
        if fallback and not cluster_fallback:
            cluster_fallback = fallback
        if not valore or not termine:
            continue
        terms = keywords.setdefault(valore, [])
        if termine.lower() not in terms:
            terms.append(termine.lower())

    rule: dict = {"column": tab_name, "keywords": keywords, "default": ""}
    if cluster_fallback:
        rule["cluster_fallback"] = cluster_fallback
    return rule


def _parse_attributo_tab_compressed(tab_name: str, raw_text: str) -> dict:
    """Tab-attributo (formato compresso): Valore | Terms | Cluster Fallback,
    una riga per Valore — Terms è una lista separata da '|' invece di una riga
    per termine. Cluster Fallback resta unico per l'intera tab, come nel
    formato legacy (non serve ripeterlo su ogni riga, ma non fa danno se
    presente su più righe: vince la prima non vuota)."""
    keywords: dict[str, list[str]] = {}
    cluster_fallback = ""
    for row in _read_tsv_rows(raw_text):
        valore = _cell(row, 0)
        terms_raw = _cell(row, 1)
        fallback = _cell(row, 2)
        if fallback and not cluster_fallback:
            cluster_fallback = fallback
        if not valore or not terms_raw:
            continue
        terms = keywords.setdefault(valore, [])
        for t in terms_raw.split("|"):
            t = t.strip().lower()
            if t and t not in terms:
                terms.append(t)

    rule: dict = {"column": tab_name, "keywords": keywords, "default": ""}
    if cluster_fallback:
        rule["cluster_fallback"] = cluster_fallback
    return rule


def materialize_cluster_rules_from_sheets(vertical: str, lang: str, tabs: dict[str, str]) -> Path:
    """tabs: {nome_tab: testo_tsv_grezzo} per tutte le tab-cluster di uno Sheet
    vertical/lingua. Scrive <workdir>/rules/<vertical>/<lang>.json nello stesso
    schema di un vecchio rules/<vertical>/<lang>.json (solo cluster).

    Ogni tab può essere nel formato legacy (nome tab = nome cluster, una riga
    per termine: Sotto Cluster | Termine | Richiede anche | Note) oppure nel
    formato compresso a tab unica (colonna Cluster esplicita, una riga per
    Sottocluster: Cluster | Sottocluster | Cluster Order | Sottocluster Order |
    Terms | Richiede Anche | Note, vedi CLAUDE.md — le due colonne Order sono
    opzionali). Il formato si riconosce dalla prima cella dell'header ("Cluster"
    per il compresso); i due formati possono coesistere nello stesso Sheet
    durante la migrazione tab-per-tab.

    I Cluster sono interamente dinamici (rule_key = nome display del Cluster,
    nessuna whitelist): un nome mai visto prima entra comunque in 'rules' e
    viene classificato dal branch generico di classify_by_rules, senza alcuna
    modifica di codice — solo un piccolo set di nomi noti (vedi commento sopra
    la sezione "Rule-based classifier") ha in più una logica di discriminazione
    o una confidence dedicata.

    Ordine di valutazione tra cluster (priority_order, consumato da
    classify_by_rules): se lo Sheet compresso specifica 'Cluster Order', quel
    valore decide l'ordine esplicitamente; i cluster senza valore (tab legacy
    non ancora migrate, o Sheet compresso senza la colonna) restano ordinati
    secondo il fallback storico PRIORITY_ORDER_BASE, in coda a quelli con
    ordine esplicito."""
    rules: dict[str, dict] = {}
    cluster_order: dict[str, float] = {}
    for tab_name, raw_text in tabs.items():
        first_line = raw_text.splitlines()[0] if raw_text.strip() else ""
        is_compressed = first_line.split("\t")[0].strip().lower() == "cluster"

        if is_compressed:
            for cluster_name, rule in _parse_cluster_tab_compressed(raw_text).items():
                rule_key = cluster_name.strip()
                order = rule.pop("cluster_order", None)
                if order is not None:
                    cluster_order[rule_key] = order
                rules[rule_key] = rule
            continue

        rule_key = tab_name.strip()
        if not rule_key:
            continue
        rules[rule_key] = _parse_cluster_tab(rule_key, raw_text)

    explicit_order = sorted(cluster_order, key=lambda k: cluster_order[k])
    implicit = [k for k in rules if k not in cluster_order]
    known_implicit = [k for k in PRIORITY_ORDER_BASE if k in implicit]
    extra_implicit = [k for k in implicit if k not in known_implicit]
    priority_order = explicit_order + known_implicit + extra_implicit + ["related_brands"]

    out = {
        "_comment": "Materializzato da Google Sheet (cartella Drive 'Clustering rules') via --mode sync-rules. Non editare a mano: modifica lo Sheet e ri-sincronizza.",
        "_version": "sheets",
        "priority_order": priority_order,
        "rules": rules,
    }
    out_path = RULES_DIR / vertical / f"{lang.lower()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _rules_cache.pop(f"{vertical}/{lang.upper()}", None)
    return out_path


def _parse_attributi_tab_unified(raw_text: str) -> dict[str, dict]:
    """Tab-attributo compressa a tab unica per tutti gli attributi (come
    _parse_cluster_tab_compressed per i cluster): Attributo | Valore | Terms |
    Cluster Fallback, una riga per (Attributo, Valore). Restituisce
    {nome_attributo: rule_dict}, stesso schema di _parse_attributo_tab —
    'column' prende il valore esatto scritto nella colonna Attributo (diventa
    l'header della colonna in output, come il nome tab nel formato legacy)."""
    by_attr: dict[str, dict] = {}
    for row in _read_tsv_rows(raw_text):
        attr_name = _cell(row, 0)
        valore = _cell(row, 1)
        terms_raw = _cell(row, 2)
        fallback = _cell(row, 3)
        if not attr_name or not valore:
            continue

        state = by_attr.setdefault(attr_name, {"keywords": {}, "cluster_fallback": ""})
        if fallback and not state["cluster_fallback"]:
            state["cluster_fallback"] = fallback
        if not terms_raw:
            continue
        terms = state["keywords"].setdefault(valore, [])
        for t in terms_raw.split("|"):
            t = t.strip().lower()
            if t and t not in terms:
                terms.append(t)

    result: dict[str, dict] = {}
    for attr_name, state in by_attr.items():
        rule: dict = {"column": attr_name, "keywords": state["keywords"], "default": ""}
        if state["cluster_fallback"]:
            rule["cluster_fallback"] = state["cluster_fallback"]
        result[attr_name] = rule
    return result


def materialize_attributi_from_sheets(lang: str, tabs: dict[str, str]) -> Path:
    """tabs: {nome_tab: testo_tsv_grezzo} per tutte le tab dello Sheet
    _Attributi/<lang>, condiviso fra tutti i vertical. Nessuna whitelist: ogni
    tab presente diventa un attributo (rule_key = slug del nome, column = nome
    esatto della tab), quindi una colonna nuova in output.

    Una tab può essere in tre formati, riconosciuti dall'header (prima cella
    "Attributo" per il compresso a tab unica; altrimenti seconda cella "Terms"
    per il compresso per-attributo, "Termine" per il legacy) e possono
    coesistere nello stesso Sheet durante la migrazione:

    - legacy (una tab per attributo, nome tab = attributo): Valore | Termine |
      Cluster fallback, una riga per termine.
    - compresso per-attributo (una tab per attributo): Valore | Terms |
      Cluster Fallback, una riga per Valore, Terms separati da '|'.
    - compresso a tab unica (tutti gli attributi nella stessa tab, come i
      cluster): Attributo | Valore | Terms | Cluster Fallback, una riga per
      (Attributo, Valore) — vedi CLAUDE.md."""
    rules: dict[str, dict] = {}
    for tab_name, raw_text in tabs.items():
        first_line = raw_text.splitlines()[0] if raw_text.strip() else ""
        header_cols = first_line.split("\t")
        is_unified = header_cols[0].strip().lower() == "attributo"
        is_compressed = len(header_cols) > 1 and header_cols[1].strip().lower() == "terms"

        if is_unified:
            for attr_name, rule in _parse_attributi_tab_unified(raw_text).items():
                rules[_slugify(attr_name)] = rule
            continue

        rule_key = _slugify(tab_name)
        if is_compressed:
            rules[rule_key] = _parse_attributo_tab_compressed(tab_name.strip(), raw_text)
        else:
            rules[rule_key] = _parse_attributo_tab(tab_name.strip(), raw_text)
    out = {
        "_comment": "Materializzato da Google Sheet (_Attributi, condiviso fra tutti i vertical) via --mode sync-rules. Non editare a mano.",
        "rules": rules,
    }
    out_path = _attributi_path(lang)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _attributi_cache.pop(lang.upper(), None)
    return out_path


def materialize_brands_from_sheet(raw_text: str) -> Path:
    """raw_text: TSV a due colonne "Brand | Canonico" (header ignorato).
    Canonico è opzionale: se vuoto, il brand è il canonico di se stesso (il
    caso della stragrande maggioranza dei brand, che non hanno varianti di
    spelling note). Righe con lo stesso Canonico si uniscono sotto la stessa
    voce — usalo per unificare grafie diverse dello stesso brand (es. "dr
    martens"/"dr. martens"/"drmartens" -> canonico "Dr. Martens"), così
    classify_by_rules restituisce sempre lo stesso related_brand indipendente
    da quale variante compare nella keyword. Un file a singola colonna (senza
    Canonico) resta valido: ogni brand diventa il canonico di se stesso, stesso
    comportamento di prima."""
    canonical: dict[str, list[str]] = {}
    for row in _read_tsv_rows(raw_text):
        brand = _cell(row, 0)
        if not brand:
            continue
        variant = brand.strip().lower()
        # Canonico esplicito se presente (grafia corretta scritta a mano nello
        # Sheet); altrimenti il brand stesso con .title(), stesso comportamento
        # di sempre per i brand senza varianti note (la stragrande maggioranza).
        display = _cell(row, 1).strip() or brand.strip().title()
        variants = canonical.setdefault(display, [])
        if variant not in variants:
            variants.append(variant)
    data = {
        "_comment": "Materializzato da Google Sheet (Brands, condiviso) via --mode sync-rules.",
        "canonical": {k: sorted(v) for k, v in canonical.items()},
    }
    path = _brands_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    global _brands_cache
    _brands_cache = None
    return path


def materialize_cities_from_sheet(raw_text: str) -> Path:
    """raw_text: TSV a singola colonna "Città" (header ignorato)."""
    terms: list[str] = []
    for row in _read_tsv_rows(raw_text):
        val = _cell(row, 0)
        if val:
            t = val.strip().lower()
            if t not in terms:
                terms.append(t)
    data = {"_comment": "Materializzato da Google Sheet (Cities, condiviso) via --mode sync-rules.", "terms": sorted(terms)}
    path = _cities_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    global _cities_cache
    _cities_cache = None
    return path


# -- Batch management -----------------------------------------------------------

def write_batch_prompt(keywords: list[str], brand: str, sector: str, known_brands: list[str], valid_clusters: list[str]) -> str:
    known_brands_str = ", ".join(sorted(known_brands)) if known_brands else "(nessuno)"
    valid_clusters_str = "|".join(valid_clusters) if valid_clusters else "(nessuno sincronizzato)"
    header = (
        SYSTEM_PROMPT
        .replace("{brand}", brand)
        .replace("{sector}", sector)
        .replace("{known_brands}", known_brands_str)
        .replace("{valid_clusters}", valid_clusters_str)
    )
    kw_text = "\n".join(keywords)
    return f"{header}\n\n{kw_text}"


def save_batch_prompts(batches: list[dict], output_dir: Path, known_brands: list[str], valid_clusters: list[str]) -> tuple[Path, list]:
    prompts_dir = output_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, batch in enumerate(batches):
        prompt_path = prompts_dir / f"batch_{i:04d}.txt"
        prompt_path.write_text(
            write_batch_prompt(
                batch["keywords"],
                batch["brand"],
                batch["sector"],
                known_brands,
                valid_clusters,
            ),
            encoding="utf-8",
        )
        manifest.append({
            "batch_id": i,
            "brand": batch["brand"],
            "n_keywords": len(batch["keywords"]),
            "indices": batch["indices"],
            "keywords": batch["keywords"],
            "prompt_file": str(prompt_path),
            "result_file": str(output_dir / "results" / f"batch_{i:04d}.json"),
        })

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path, manifest


def apply_results(df_out: pd.DataFrame, manifest: list[dict], results_dir: Path) -> tuple[int, int, list, list]:
    done = 0
    errors = 0
    all_suggestions: list[dict] = []
    all_brand_suggestions: list[str] = []
    new_cache_entries: list[tuple[str, str, str]] = []

    for batch in manifest:
        result_path = Path(batch["result_file"])
        if not result_path.exists():
            log(f"batch {batch['batch_id']:04d} -- risultato mancante, skip", "warn")
            errors += batch["n_keywords"]
            continue
        try:
            raw = json.loads(result_path.read_text(encoding="utf-8"))

            # Formato compatto: {"r": [[c, sc], ...], "new_rules": [...], "new_brands": [...]}
            if isinstance(raw, dict) and "r" in raw:
                rows = raw["r"]
                suggestions = raw.get("new_rules", [])
                if isinstance(suggestions, list):
                    all_suggestions.extend(suggestions)
                brand_suggestions = raw.get("new_brands", [])
                if isinstance(brand_suggestions, list):
                    all_brand_suggestions.extend(brand_suggestions)
            # Fallback: vecchio formato array di oggetti
            elif isinstance(raw, list):
                rows = [[item.get("cluster", ""), item.get("sotto_cluster", "")] for item in raw]
            else:
                raise ValueError("formato JSON non riconosciuto")

            batch_keywords = batch.get("keywords", [])
            for j, pair in enumerate(rows):
                cluster = pair[0] if len(pair) > 0 else ""
                sotto = pair[1] if len(pair) > 1 else ""
                # indices è lista di liste (una per keyword unica, con tutte le sue occorrenze)
                idx_group = batch["indices"][j] if j < len(batch["indices"]) else []
                if isinstance(idx_group, list):
                    for idx in idx_group:
                        df_out.at[idx, "Cluster"] = cluster
                        df_out.at[idx, "Sotto Cluster"] = sotto
                else:
                    # Retrocompatibilità: indice singolo (vecchio formato senza dedup)
                    df_out.at[idx_group, "Cluster"] = cluster
                    df_out.at[idx_group, "Sotto Cluster"] = sotto

                # Accumula per cache
                if cluster and j < len(batch_keywords):
                    new_cache_entries.append((batch_keywords[j], cluster, sotto))

            done += len(rows)
        except Exception as e:
            log(f"batch {batch['batch_id']:04d} -- errore parsing: {e}", "err")
            errors += batch["n_keywords"]

    if new_cache_entries:
        save_cache_entries(new_cache_entries)
        log(f"{len(new_cache_entries)} nuove entry salvate in cache ({CACHE_DIR.name}/)", "ok")

    return done, errors, all_suggestions, all_brand_suggestions


# -- Modes ----------------------------------------------------------------------

def mode_prepare(args):
    import datetime
    t_prepare_start = datetime.datetime.now()

    if not args.vertical or args.vertical not in available_verticals():
        print(f"Errore: --vertical obbligatorio in modalità prepare. Vertical sincronizzati: {available_verticals()}")
        print("   Chiedi all'utente quale vertical è più adatto al brand/settore corrente, poi esegui --mode sync-rules prima di procedere.")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Errore: file non trovato -> {input_path}")
        sys.exit(1)

    df = pd.read_csv(input_path)
    print(f"\nFile caricato: {input_path.name}")
    print(f"   {len(df)} righe - colonne: {df.columns.tolist()}")

    col_map = detect_columns(df)

    REQUIRED_COLUMNS = [
        ("keyword", "Keyword", ["Keyword", "Kw", "Parola Chiave", "Query", "Keywords"]),
        ("brand", "Brand", ["Brand", "Marchio", "Competitor"]),
        ("type", "Brand/Not Brand", ["Brand/Not Brand", "Type", "Tipo", "Brand_Not_Brand"]),
    ]
    missing = [(label, aliases) for key, label, aliases in REQUIRED_COLUMNS if key not in col_map]
    if missing:
        print(f"\n[ERRORE] Colonne obbligatorie mancanti -- clustering NON avviato.")
        print(f"   Colonne trovate nel file: {df.columns.tolist()}")
        print(f"\n   Mancano {len(missing)} colonna/e obbligatoria/e:")
        for label, aliases in missing:
            print(f"   - {label}  (nomi accettati: {', '.join(aliases)})")
        print(f"\n   Carica di nuovo il file aggiungendo le colonne mancanti, poi ripeti --mode prepare.")
        sys.exit(1)

    col_kw      = col_map["keyword"]
    col_brand   = col_map.get("brand")
    col_country = col_map.get("country")

    if col_country:
        langs_in_file = sorted(df[col_country].dropna().unique().tolist())
        print(f"   Colonna Country rilevata: {col_country} — lingue presenti: {langs_in_file}")
    else:
        print(f"   Nessuna colonna Country trovata — uso regole default ({DEFAULT_LANG})")

    output_dir = Path(args.workdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results").mkdir(exist_ok=True)
    save_vertical(output_dir, args.vertical)
    print(f"   Vertical: {args.vertical}")

    if col_brand and args.brand:
        df = df[df[col_brand] == args.brand].copy()
        print(f"   Filtro brand: {args.brand} ({len(df)} righe)")

    # Pre-carica le regole per tutte le lingue presenti nel CSV
    langs_needed = set()
    if col_country:
        for val in df[col_country].dropna():
            v = str(val).strip().upper()
            langs_needed.add(v if v in SUPPORTED_LANGS else DEFAULT_LANG)
    langs_needed.add(DEFAULT_LANG)
    rules_by_lang: dict[str, dict] = {lang: load_rules(lang, args.vertical) for lang in langs_needed}
    rule_kw_lists: dict[str, list] = {
        lang: _build_rule_keyword_list(rules) for lang, rules in rules_by_lang.items()
    }

    # Colonne opzionali derivate dinamicamente dagli attributi sincronizzati (una
    # tab in _Attributi = una colonna in output): unione su tutte le lingue usate,
    # cosi' una lingua con un attributo in meno non fa saltare la colonna per le altre.
    optional_cols_set: set[str] = set()
    for rules in rules_by_lang.values():
        for rule in rules.get("rules", {}).values():
            if "column" in rule:
                optional_cols_set.add(rule["column"])
    optional_cols = sorted(optional_cols_set)
    print(f"\n[OK] Colonne opzionali: {optional_cols}")
    print(f"[OK] Colonne always-on: {ALWAYS_ON_COLUMNS}")

    # Cluster validi per questo vertical (usati nel prompt AI, --mode process-batches):
    # derivati dalle tab già sincronizzate, non da una lista fissa nel codice —
    # unione su tutte le lingue caricate, cosi' una lingua con un cluster in meno
    # non fa saltare quel cluster dalla lista per le altre.
    valid_clusters_set: set[str] = set()
    for rules in rules_by_lang.values():
        for rule in rules.get("rules", {}).values():
            if "cluster" in rule:
                valid_clusters_set.add(rule["cluster"])
    valid_clusters = sorted(valid_clusters_set)
    print(f"[OK] Cluster validi: {valid_clusters}")

    # Rimuove dal DataFrame le colonne di output eventualmente già presenti (CSV ri-processato),
    # così le colonne extra originali (Volume, KD, CPC, URL…) restano intatte e in posizione.
    output_cols = ["Cluster", "Sotto Cluster"] + optional_cols + ALWAYS_ON_COLUMNS
    existing_output = [c for c in output_cols if c in df.columns]
    if existing_output:
        df = df.drop(columns=existing_output)

    # Riordina: prima le colonne originali, poi quelle di clustering in fondo
    original_cols = list(df.columns)
    df["Cluster"] = ""
    df["Sotto Cluster"] = ""
    for col in optional_cols:
        df[col] = ""
    for col in ALWAYS_ON_COLUMNS:
        df[col] = ""
    df = df[original_cols + output_cols]

    # Carica cache per keyword già classificate in run precedenti
    cache = load_cache()

    cache_hit_count = 0
    fuzzy_count = 0
    rule_based_count = 0
    ai_needed = []

    for idx, row in df.iterrows():
        keyword = str(row[col_kw])
        brand_raw = str(row[col_brand]) if col_brand else ""
        brand = "" if brand_raw.lower() in ("nan", "none", "") else brand_raw

        # Determina lingua della riga
        if col_country:
            country_raw = str(row[col_country]).strip().upper()
            lang = country_raw if country_raw in SUPPORTED_LANGS else DEFAULT_LANG
        else:
            lang = DEFAULT_LANG
        rules = load_rules(lang, args.vertical)
        rule_kw_list = rule_kw_lists.get(lang, rule_kw_lists[DEFAULT_LANG])

        kw_norm = keyword.lower().strip()
        # Testo senza le porzioni riconducibili al brand (esatto/typo/spaziatura),
        # usato per le colonne opzionali cosi non ereditano parole del nome brand
        # (es. "blu" da "loriblu" o dalla sua variante spaziata "lori blu").
        kw_for_optional = _strip_brand_tokens(kw_norm, brand)

        # 1. Cache hit
        if kw_norm in cache:
            df.at[idx, "Cluster"], df.at[idx, "Sotto Cluster"] = cache[kw_norm]
            cache_hit_count += 1
            if optional_cols:
                opt = classify_optional(kw_for_optional, rules, optional_cols)
                for col, val in opt.items():
                    df.at[idx, col] = val
            continue

        # 2. Regole esatte
        cluster, sotto, confidence, rb = classify_by_rules(keyword, brand, rules)
        if rb:
            df.at[idx, "Brand correlati"] = rb

        if confidence >= DEFAULT_CONFIDENCE_THRESHOLD:
            df.at[idx, "Cluster"] = cluster
            df.at[idx, "Sotto Cluster"] = sotto
            rule_based_count += 1
        elif rb:
            # 3. Brand terzo riconosciuto ma nessuna regola prodotto ha matchato:
            # ha priorità sui fallback delle colonne opzionali (Genere/Materiale/Stagionalità...),
            # che sono attributi descrittivi e non devono sostituire il Cluster principale.
            df.at[idx, "Cluster"] = "Brand correlato"
            df.at[idx, "Sotto Cluster"] = rb
            rule_based_count += 1
        else:
            # 4. Fallback colonne opzionali in cascata (Evento > Stagionalità > Outfit > Recensioni > Materiale/Colore > Genere)
            fb_cluster, fb_sotto, fb_conf = classify_optional_fallback(kw_for_optional, rules)
            if fb_cluster:
                df.at[idx, "Cluster"] = fb_cluster
                df.at[idx, "Sotto Cluster"] = fb_sotto
                rule_based_count += 1
            else:
                # 5. Fuzzy match
                fz_cluster, fz_sotto, fz_conf = fuzzy_classify(keyword, rule_kw_list)
                if fz_cluster:
                    df.at[idx, "Cluster"] = fz_cluster
                    df.at[idx, "Sotto Cluster"] = fz_sotto
                    fuzzy_count += 1
                else:
                    # Fallback finale: keyword senza brand → Altro
                    brand_tokens_check = [
                        re.sub(r"[^a-zà-ÿ]", "", t)
                        for t in brand.lower().split()
                        if len(re.sub(r"[^a-zà-ÿ]", "", t)) > 3
                    ] if brand else []
                    brand_in_kw_check = brand and (
                        brand.lower() in keyword.lower()
                        or any(tok in keyword.lower().split() for tok in brand_tokens_check)
                    )
                    if not brand_in_kw_check:
                        df.at[idx, "Cluster"] = "Altro"
                        df.at[idx, "Sotto Cluster"] = ""
                        rule_based_count += 1
                    else:
                        ai_needed.append((idx, keyword, brand))

        if optional_cols:
            opt = classify_optional(kw_for_optional, rules, optional_cols)
            for col, val in opt.items():
                df.at[idx, col] = val

    t_prepare_end = datetime.datetime.now()
    elapsed_prepare = (t_prepare_end - t_prepare_start).total_seconds()

    print(f"\n Classificazione:")
    print(f"   {cache_hit_count:,} da cache  |  {rule_based_count:,} da regole  |  {fuzzy_count:,} da fuzzy")
    pct = len(ai_needed) / len(df) * 100 if len(df) else 0
    print(f"   {len(ai_needed):,} keyword ambigue -> batch per AI ({pct:.1f}%)")
    prep_min = int(elapsed_prepare // 60)
    prep_sec = elapsed_prepare % 60
    prep_str = f"{prep_min}m {prep_sec:.1f}s" if prep_min else f"{prep_sec:.1f}s"
    print(f"   Tempo classificazione ruleset: {prep_str}")

    # Deduplicazione: manda ogni keyword unica una sola volta all'AI
    kw_to_indices: dict[str, list] = {}
    for idx, kw, brand in ai_needed:
        key = kw.lower().strip()
        kw_to_indices.setdefault(key, []).append(idx)

    unique_ai = []
    for kw_norm, indices in kw_to_indices.items():
        # Prendi brand dalla prima occorrenza
        first_idx = indices[0]
        brand = str(df.at[first_idx, col_brand]) if col_brand else ""
        unique_ai.append((indices, kw_norm, brand))

    saved_by_dedup = len(ai_needed) - len(unique_ai)
    if saved_by_dedup:
        print(f"   {saved_by_dedup:,} keyword duplicate rimosse (propagazione post-AI)")

    # Costruisce batch ignorando il brand — tutte le keyword ambigue in batch unici
    all_indices_flat = [item[0] for item in unique_ai]
    all_keywords_flat = [item[1] for item in unique_ai]
    all_brands_flat = [item[2] for item in unique_ai]

    # Raccoglie i brand unici presenti per il prompt header
    brands_in_dataset = sorted(
        b for b in set(all_brands_flat)
        if b and b.lower() not in ("nan", "none", "")
    )
    brand_label = ", ".join(brands_in_dataset) if brands_in_dataset else args.sector

    batches = []
    for i in range(0, len(all_keywords_flat), args.batch_size):
        batches.append({
            "brand":    brand_label,
            "sector":   args.sector,
            "indices":  all_indices_flat[i : i + args.batch_size],
            "keywords": all_keywords_flat[i : i + args.batch_size],
        })

    df.to_csv(output_dir / "base.csv", index=False)

    # Salva lista keyword da inviare all'AI per analisi pattern
    ai_keywords_path = output_dir / "ai_needed.json"
    ai_keywords_path.write_text(
        json.dumps([kw for kw in all_keywords_flat], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n[OK] Preparazione completata!")
    print(f"   Base CSV: {output_dir / 'base.csv'}")
    print(f"   Keyword da analizzare: {output_dir / 'ai_needed.json'} ({len(all_keywords_flat):,} keyword uniche)")

    # Salva il tempo di classificazione nel manifest per la sintesi finale
    timing_path = output_dir / "timing.json"
    timing_path.write_text(
        json.dumps({"ruleset_seconds": round(elapsed_prepare, 2)}, ensure_ascii=False),
        encoding="utf-8"
    )

    if all_keywords_flat:
        print(f"\n Prossimo step: analisi pattern per nuove regole")
        print(f'   python scripts/cluster.py --mode analyze --workdir {output_dir}')
    else:
        print(f"\n[OK] Tutte le keyword classificate automaticamente! No AI needed.")
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps([], indent=2), encoding="utf-8")

    if batches:
        known_brands = _brand_canonical_names(load_brands())
        manifest_path, _ = save_batch_prompts(batches, output_dir, known_brands, valid_clusters)
        print(f"\n {len(batches)} batch pronti (generati ma NON ancora processati)")
        print(f"   Esegui prima --mode analyze per ottimizzare le regole, poi --mode process-batches")


def mode_analyze(args):
    """
    Analizza le keyword non classificate dalle regole (salvate in ai_needed.json)
    e identifica pattern ricorrenti che potrebbero diventare nuove regole.
    Salva i suggerimenti in output/workdir/rule_proposals.json.
    """
    workdir = Path(args.workdir)
    ai_needed_path = workdir / "ai_needed.json"

    if not ai_needed_path.exists():
        print(f"Errore: {ai_needed_path} non trovato. Esegui prima --mode prepare.")
        sys.exit(1)

    vertical = load_vertical(workdir, args.vertical)

    keywords = json.loads(ai_needed_path.read_text(encoding="utf-8"))
    if not keywords:
        print("[OK] Nessuna keyword da analizzare.")
        return

    print(f"\n Analisi pattern su {len(keywords):,} keyword non classificate...")

    # ---- Estrai token e conta frequenze ----
    token_freq: dict[str, int] = {}
    token_cooc: dict[str, dict[str, int]] = {}  # co-occorrenze token→token

    for kw in keywords:
        tokens = re.split(r"[\s\-_/]+", kw.lower().strip())
        tokens = [t for t in tokens if len(t) >= 3 and not t.isdigit()]
        for tok in tokens:
            token_freq[tok] = token_freq.get(tok, 0) + 1
        for i, t1 in enumerate(tokens):
            for t2 in tokens[i+1:]:
                pair = tuple(sorted([t1, t2]))
                token_cooc.setdefault(pair[0], {})
                token_cooc[pair[0]][pair[1]] = token_cooc[pair[0]].get(pair[1], 0) + 1

    # ---- Identifica token frequenti (soglia: ≥3 occorrenze) ----
    MIN_FREQ = 3
    frequent = sorted(
        [(tok, cnt) for tok, cnt in token_freq.items() if cnt >= MIN_FREQ],
        key=lambda x: -x[1]
    )

    # ---- Raggruppa token per categoria semantica (euristiche) ----
    # Le categorie sono definite da token seme presenti nelle regole (solo le
    # lingue effettivamente sincronizzate in questa sessione: a differenza dei
    # vecchi rules/<vertical>/*.json committati, non tutte le 5 lingue esistono
    # sempre — sync-rules materializza solo quelle scaricate dagli Sheet).
    known_keywords: set[str] = set()
    for lang in SUPPORTED_LANGS:
        if not (RULES_DIR / vertical / f"{lang.lower()}.json").exists():
            continue
        rules = load_rules(lang, vertical)
        for rule in rules.get("rules", {}).values():
            known_keywords.update(_all_subcluster_keywords(rule))
            kws = rule.get("keywords", {})
            if isinstance(kws, dict):
                for wlist in kws.values():
                    if isinstance(wlist, list):
                        known_keywords.update(wlist)

    proposals = []
    seen_terms: set[str] = set()

    # Pattern 1: token singolo frequente non già nelle regole
    for tok, cnt in frequent[:60]:
        if tok in known_keywords or tok in seen_terms:
            continue
        if len(tok) < 4:
            continue
        seen_terms.add(tok)
        # Esempi di keyword che contengono questo token
        examples = [kw for kw in keywords if tok in kw.lower()][:5]
        proposals.append({
            "term": tok,
            "count": cnt,
            "examples": examples,
            "suggested_cluster": "",
            "suggested_sotto_cluster": "",
            "source": "token_freq"
        })

    # Pattern 2: bigrammi frequenti (coppia di token) ≥ 3 volte
    bigrams: dict[str, int] = {}
    for kw in keywords:
        tokens = re.split(r"[\s\-_/]+", kw.lower().strip())
        tokens = [t for t in tokens if len(t) >= 3 and not t.isdigit()]
        for i in range(len(tokens) - 1):
            bg = f"{tokens[i]} {tokens[i+1]}"
            bigrams[bg] = bigrams.get(bg, 0) + 1

    for bg, cnt in sorted(bigrams.items(), key=lambda x: -x[1])[:30]:
        if cnt < MIN_FREQ:
            break
        if bg in seen_terms:
            continue
        if any(tok in known_keywords for tok in bg.split()):
            continue
        seen_terms.add(bg)
        examples = [kw for kw in keywords if bg in kw.lower()][:5]
        proposals.append({
            "term": bg,
            "count": cnt,
            "examples": examples,
            "suggested_cluster": "",
            "suggested_sotto_cluster": "",
            "source": "bigram_freq"
        })

    # Ordina per frequenza
    proposals.sort(key=lambda x: -x["count"])

    proposals_path = workdir / "rule_proposals.json"
    proposals_path.write_text(
        json.dumps(proposals, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\n[OK] {len(proposals)} pattern identificati -> {proposals_path}")
    print(f"\n Top pattern da valutare:")
    for p in proposals[:20]:
        ex = p["examples"][0] if p["examples"] else ""
        print(f"   [{p['count']:4d}x]  '{p['term']}'   es: \"{ex}\"")

    print(f"\n Prossimo step: aggiungi cluster/sotto_cluster in {proposals_path}")
    print(f"   poi esegui: python scripts/cluster.py --mode add-rules --workdir {workdir}")
    print(f"   oppure salta direttamente ai batch: python scripts/cluster.py --mode process-batches --workdir {workdir}")


def _apply_rules_to_ruleset(entries: list, vertical: str, lang: str) -> tuple:
    """
    Aggiunge una lista di {"term", "cluster", "sotto_cluster"} alla copia
    effimera di sessione <workdir>/rules/<vertical>/<lang>.json (materializzata
    da --mode sync-rules), utile per riclassificare subito in questa sessione.
    Non è più la fonte di verità permanente: quella vive negli Sheet Google
    Drive, dove i termini vanno incollati a mano (vedi _format_paste_block_rules).
    Ritorna (added, skipped, rules_path).
    """
    rules = load_rules(lang, vertical)
    rules_path = RULES_DIR / vertical / f"{lang.upper().lower()}.json"
    rule_defs = rules["rules"]

    added = []
    skipped = []

    for e in entries:
        cluster = e["cluster"].strip()
        term = e["term"].strip().lower()
        rule_key = cluster

        rule = rule_defs.get(rule_key)
        if not rule:
            skipped.append({"term": term, "reason": f"regola '{rule_key}' non trovata"})
            continue

        sotto = (e.get("sotto_cluster") or "").strip()
        subclusters = rule.setdefault("subclusters", {})

        # Controlla se il termine è già presente in qualche sottocluster
        existing_sub = None
        for sub_name, kw_list in subclusters.items():
            if isinstance(kw_list, list) and term in kw_list:
                existing_sub = sub_name
                break
            if isinstance(kw_list, dict) and term in kw_list.get("terms", []):
                existing_sub = sub_name
                break
        if existing_sub:
            skipped.append({"term": term, "reason": f"già presente nel sottocluster '{existing_sub}'"})
            continue

        target_sub = sotto if sotto else rule.get("default_subcluster", "")
        if not target_sub:
            skipped.append({"term": term, "reason": "nessun sotto_cluster indicato e nessun default_subcluster nella regola"})
            continue

        if target_sub not in subclusters:
            subclusters[target_sub] = {"terms": [term]}
        else:
            existing = subclusters[target_sub]
            if isinstance(existing, list):
                if term not in existing:
                    existing.append(term)
            elif isinstance(existing, dict):
                terms_list = existing.setdefault("terms", [])
                if term not in terms_list:
                    terms_list.append(term)

        added.append({"term": term, "cluster": cluster, "rule_key": rule_key, "sotto_cluster": sotto})

    if added:
        # related_brands/known_cities vivono in rules/brands.json e rules/cities.json
        # (condivisi), non vanno riscritti nel file lingua
        rule_defs.pop("related_brands", None)
        rule_defs.pop("known_cities", None)
        rules_path.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
        _rules_cache.pop(f"{vertical}/{lang.upper()}", None)  # invalida cache in-memory

    return added, skipped, rules_path


def _format_paste_block_rules(added: list, vertical: str, lang: str) -> str:
    """Blocco pronto da incollare nella tab-cluster dello Sheet vertical
    'Clustering rules/<vertical>/<lang>'. Formato compresso a tab unica (Cluster
    | Sottocluster | Cluster Order | Sottocluster Order | Terms | Richiede
    Anche | Note): una riga per termine è comunque valida, si unisce alla riga
    esistente dello stesso (Cluster, Sottocluster) al prossimo --mode sync-rules
    (vedi _parse_cluster_tab_compressed) — non serve editare a mano la lista
    '|' esistente. Cluster Order/Sottocluster Order sono lasciate vuote: il
    termine si unisce a un (Cluster, Sottocluster) già esistente nello Sheet,
    che ha già il suo ordine impostato altrove — una cella vuota non lo
    sovrascrive (vedi _parse_cluster_tab_compressed).
    Se il vertical/lingua di destinazione non è ancora stato migrato al formato
    compresso (tab ancora una-per-cluster, header 'Sotto Cluster | Termine | ...'),
    ignora la colonna Cluster e incolla solo Sottocluster/Termine nella tab che
    corrisponde al cluster indicato, come nel vecchio formato."""
    lines = [
        f"Clustering rules / {vertical} / {lang.upper()}",
        "-- Incolla nella tab unica delle regole (formato compresso: Cluster | Sottocluster | Cluster Order | Sottocluster Order | Terms | Richiede Anche | Note) --",
        "Cluster\tSottocluster\tCluster Order\tSottocluster Order\tTerms\tRichiede Anche\tNote",
    ]
    for a in sorted(added, key=lambda a: (a["cluster"], a.get("sotto_cluster", ""))):
        lines.append(f"{a['cluster']}\t{a.get('sotto_cluster', '')}\t\t\t{a['term']}\t\t")
    return "\n".join(lines)


def mode_add_rules(args):
    """
    Legge rule_proposals.json (con suggested_cluster compilati dall'utente/AI),
    aggiunge i termini validi alla copia effimera di sessione (per riclassificare
    subito) e produce un blocco pronto da incollare nella tab giusta dello
    Sheet Google Drive del vertical/lingua corrente (la sync automatica non è
    possibile: il connettore Drive non sa scrivere su file esistenti).
    """
    workdir = Path(args.workdir)
    proposals_path = workdir / "rule_proposals.json"

    if not proposals_path.exists():
        print(f"Errore: {proposals_path} non trovato. Esegui prima --mode analyze.")
        sys.exit(1)

    vertical = load_vertical(workdir, args.vertical)

    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    valid = [p for p in proposals if p.get("suggested_cluster", "").strip()]

    if not valid:
        print("[WARN] Nessun suggerimento con cluster compilato. Compila 'suggested_cluster' in rule_proposals.json.")
        sys.exit(0)

    lang = getattr(args, "lang", DEFAULT_LANG) or DEFAULT_LANG
    entries = [
        {"term": p["term"], "cluster": p["suggested_cluster"], "sotto_cluster": p.get("suggested_sotto_cluster", "")}
        for p in valid
    ]
    print(f"\n Aggiunta regole alla copia di sessione: {vertical}/{lang.lower()}.json (lingua: {lang.upper()})")
    added, skipped, rules_path = _apply_rules_to_ruleset(entries, vertical, lang)

    for a in added:
        a["sheet_target"] = f"Clustering rules/{vertical}/{lang.upper()} → tab '{a['cluster']}'"

    if added:
        print(f"\n[OK] {len(added)} termini aggiunti alla copia di sessione ({rules_path}):")
        for a in added:
            print(f"   + '{a['term']}' -> {a['cluster']} [{a['rule_key']}]")
    else:
        print("\n[WARN] Nessun termine aggiunto.")

    if skipped:
        print(f"\n[WARN] {len(skipped)} termini saltati:")
        for s in skipped:
            print(f"   - '{s['term']}': {s['reason']}")

    report_path = workdir / "rules_added.json"
    report_path.write_text(
        json.dumps({"added": added, "skipped": skipped}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n Report: {report_path}")

    if added:
        paste_block = _format_paste_block_rules(added, vertical, lang)
        paste_path = workdir / f"paste_rules_{vertical}_{lang.lower()}.txt"
        paste_path.write_text(paste_block, encoding="utf-8")
        print(f"\n Incolla queste righe negli Sheet Google Drive (vedi anche {paste_path}):\n")
        print(paste_block)
        print(f"\n Prossimo step: ri-esegui prepare per riclassificare con le nuove regole")
        print(f'   python scripts/cluster.py --mode prepare --input [file.csv] --workdir {workdir}')
        print(f"   oppure processa i batch esistenti:")
        print(f'   python scripts/cluster.py --mode process-batches --workdir {workdir}')


def _apply_brand_candidates(candidates: list) -> tuple:
    """
    Aggiunge una lista di nomi brand alla copia effimera di sessione
    <workdir>/rules/brands.json (condivisa fra tutti i vertical/lingue).
    Ritorna (added, skipped).
    """
    brands_data = load_brands()
    existing_lower = _brand_variant_set(brands_data)
    canonical = brands_data.setdefault("canonical", {})

    added = []
    skipped = []
    for term in candidates:
        t_norm = str(term).strip().lower()
        if not t_norm:
            continue
        if t_norm in existing_lower:
            skipped.append(t_norm)
            continue
        # nuovo brand: nessuna variante di spelling nota, è il canonico di se stesso
        canonical[t_norm] = [t_norm]
        existing_lower.add(t_norm)
        added.append(t_norm)

    if added:
        _brands_path().write_text(json.dumps(brands_data, indent=2, ensure_ascii=False), encoding="utf-8")
        global _brands_cache
        _brands_cache = None  # invalida cache in-memory

    return added, skipped


def _format_paste_block_brands(added: list) -> str:
    lines = ["Clustering rules / Brands", "\n-- Incolla nella tab 'Brand' --", "Brand"]
    lines.extend(added)
    return "\n".join(lines)


def mode_add_brands(args):
    """
    Legge brands_suggestions.json (prodotto da --mode merge quando l'AI segnala
    brand competitor non ancora noti), li aggiunge alla copia effimera di
    sessione (per riclassificare subito) e produce un blocco pronto da incollare
    nella tab 'Brand' dello Sheet condiviso "Clustering rules/Brands".
    """
    suggestions_path = Path(args.brands_suggestions)

    if not suggestions_path.exists():
        print(f"Errore: {suggestions_path} non trovato. Esegui prima --mode merge.")
        sys.exit(1)

    candidates = json.loads(suggestions_path.read_text(encoding="utf-8"))
    if not candidates:
        print("[OK] Nessun brand da aggiungere.")
        return

    added, skipped = _apply_brand_candidates(candidates)

    if added:
        print(f"\n[OK] {len(added)} brand aggiunti alla copia di sessione ({_brands_path().name}):")
        for a in added:
            print(f"   + '{a}'")
    else:
        print("\n[WARN] Nessun brand nuovo aggiunto.")

    if skipped:
        print(f"\n[WARN] {len(skipped)} brand già presenti, saltati: {', '.join(skipped)}")

    report_path = suggestions_path.parent / "brands_added.json"
    report_path.write_text(
        json.dumps({"added": added, "skipped": skipped, "sheet_target": "Clustering rules/Brands → tab 'Brand'" if added else ""}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n Report: {report_path}")

    if added:
        paste_block = _format_paste_block_brands(added)
        paste_path = suggestions_path.parent / "paste_brands.txt"
        paste_path.write_text(paste_block, encoding="utf-8")
        print(f"\n Incolla questi brand nello Sheet Google Drive 'Clustering rules/Brands' (vedi anche {paste_path}):\n")
        print(paste_block)


def mode_sync_rules(args):
    """
    Materializza in <workdir>/rules/ le regole già scaricate dagli Sheet Google
    Drive come .csv (un file per Sheet, monotab — export?format=csv o il
    connettore Drive download_file_content(exportMimeType="text/csv") dove il
    curl non è disponibile, es. claude.ai) sotto <workdir>/sheets_raw/, senza
    mai passare per il contesto del modello (vedi CLAUDE.md, sezione
    "Sincronizza da Google Drive").

    Struttura attesa dello staging:
      sheets_raw/brands.csv              (Sheet "Brands", condiviso)
      sheets_raw/cities.csv              (Sheet "Cities", condiviso)
      sheets_raw/_attributi/<LANG>.csv   (Sheet "_Attributi/<lang>")
      sheets_raw/<vertical>/<LANG>.csv   (Sheet "<vertical>/<lang>")
    """
    workdir = Path(args.workdir)
    staging = workdir / "sheets_raw"
    if not staging.exists():
        print(f"Errore: {staging} non trovato.")
        print("   Prima di --mode sync-rules, scarica i .csv degli Sheet Google Drive in questa cartella (vedi CLAUDE.md).")
        sys.exit(1)

    brands_file = _find_single_sheet_file(staging, "brands")
    if brands_file:
        raw_text = next(iter(_csv_to_tabs(brands_file).values()), "")
        path = materialize_brands_from_sheet(raw_text)
        log(f"brands -> {path}", "ok")
    else:
        log("nessun brands.csv trovato in staging, nessun brand condiviso sincronizzato", "warn")

    cities_file = _find_single_sheet_file(staging, "cities")
    if cities_file:
        raw_text = next(iter(_csv_to_tabs(cities_file).values()), "")
        path = materialize_cities_from_sheet(raw_text)
        log(f"cities -> {path}", "ok")
    else:
        log("nessun cities.csv trovato in staging, nessuna città condivisa sincronizzata", "warn")

    attributi_dir = staging / "_attributi"
    n_attributi_langs = 0
    if attributi_dir.exists():
        for sheet_path in sorted(attributi_dir.glob("*.csv")):
            lang = sheet_path.stem
            tabs = _csv_to_tabs(sheet_path)
            if not tabs:
                continue
            path = materialize_attributi_from_sheets(lang, tabs)
            log(f"_attributi/{lang} ({len(tabs)} attributi) -> {path}", "ok")
            n_attributi_langs += 1
    if not n_attributi_langs:
        log("nessun .csv in sheets_raw/_attributi, nessun attributo sincronizzato", "warn")

    n_verticals = 0
    for vertical_dir in sorted(p for p in staging.iterdir() if p.is_dir() and p.name != "_attributi"):
        for sheet_path in sorted(vertical_dir.glob("*.csv")):
            lang = sheet_path.stem
            tabs = _csv_to_tabs(sheet_path)
            if not tabs:
                continue
            path = materialize_cluster_rules_from_sheets(vertical_dir.name, lang, tabs)
            log(f"{vertical_dir.name}/{lang} ({len(tabs)} cluster) -> {path}", "ok")
            n_verticals += 1

    if not n_verticals:
        print("\n[WARN] Nessun vertical sincronizzato: verifica la struttura sotto sheets_raw/.")
    else:
        print(f"\n[OK] Sync completata. Vertical disponibili ora: {available_verticals()}")


def mode_process_batches(args):
    """
    Stampa un riepilogo dei batch da processare (quelli senza risultato).
    L'AI (Claude) li legge e scrive i JSON risultato, quindi chiama --mode merge.
    """
    workdir = Path(args.workdir)
    manifest_path = workdir / "manifest.json"

    if not manifest_path.exists():
        print(f"Errore: manifest non trovato in {workdir}.")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results_dir = workdir / "results"
    results_dir.mkdir(exist_ok=True)

    pending = []
    done = []
    for b in manifest:
        rp = Path(b["result_file"])
        if rp.exists():
            done.append(b)
        else:
            pending.append(b)

    print(f"\n Stato batch:")
    print(f"   {len(done):,} completati  |  {len(pending):,} da processare")

    if not pending:
        print(f"\n[OK] Tutti i batch completati. Esegui merge:")
        print(f'   python scripts/cluster.py --mode merge --workdir {workdir} --output output/clustered.csv')
        return

    print(f"\n Batch da processare:")
    for b in pending:
        print(f"   batch {b['batch_id']:04d}  |  {b['n_keywords']:,} kw  |  {b['prompt_file']}")

    print(f"\n-> L'AI deve leggere ogni prompt e scrivere il JSON risultato in results/")
    print(f"   Poi esegui: python scripts/cluster.py --mode merge --workdir {workdir} --output output/clustered.csv")


def mode_merge(args):
    import shutil
    import datetime

    workdir = Path(args.workdir)
    manifest_path = workdir / "manifest.json"

    if not manifest_path.exists():
        print(f"Errore: manifest non trovato in {workdir}. Esegui prima --mode prepare.")
        sys.exit(1)

    t_start = datetime.datetime.now()

    # Carica timing dal prepare (se disponibile)
    timing_path = workdir / "timing.json"
    ruleset_seconds = None
    if timing_path.exists():
        try:
            ruleset_seconds = json.loads(timing_path.read_text(encoding="utf-8")).get("ruleset_seconds")
        except Exception:
            pass

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    df_out = pd.read_csv(workdir / "base.csv")

    print(f"\n Unione risultati...")
    done, errors, suggestions, brand_suggestions = apply_results(df_out, manifest, workdir / "results")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False)

    print(f"\n[OK] Output: {output_path}")
    print(f"   Processate via AI: {done:,}  |  Errori: {errors:,}")

    if suggestions:
        # Salva accanto al CSV finale, non dentro workdir
        suggestions_path = output_path.parent / "rules_suggestions.json"
        seen = set()
        unique = []
        for s in suggestions:
            key = (s.get("rule", ""), s.get("term", ""))
            if key not in seen:
                seen.add(key)
                unique.append(s)
        suggestions_path.write_text(json.dumps(unique, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n Suggerimenti nuove regole: {len(unique)} termini -> {suggestions_path}")
        print("   Leggi il file e valida manualmente prima di aggiungere a rules.json")

    if brand_suggestions:
        known_brands_lower = _brand_variant_set(load_brands())
        seen_brands = set()
        unique_brands = []
        for b in brand_suggestions:
            b_norm = str(b).strip().lower()
            if not b_norm or b_norm in known_brands_lower or b_norm in seen_brands:
                continue
            seen_brands.add(b_norm)
            unique_brands.append(b_norm)
        if unique_brands:
            brands_suggestions_path = output_path.parent / "brands_suggestions.json"
            brands_suggestions_path.write_text(
                json.dumps(sorted(unique_brands), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"\n Brand competitor rilevati (nuovi): {len(unique_brands)} -> {brands_suggestions_path}")
            print("   Leggi il file e valida manualmente prima di aggiungere a rules/brands.json")

    # -- Sintesi prestazionale -------------------------------------------------------
    t_end = datetime.datetime.now()
    elapsed = (t_end - t_start).total_seconds()

    total_rows = len(df_out)
    col_map = detect_columns(df_out)
    col_brand = col_map.get("brand")

    n_brands = df_out[col_brand].nunique() if col_brand else 0

    has_cluster = "Cluster" in df_out.columns
    has_sotto   = "Sotto Cluster" in df_out.columns

    n_clusters    = df_out["Cluster"].nunique() if has_cluster else 0
    n_sottoclust  = df_out["Sotto Cluster"].nunique() if has_sotto else 0

    # Righe classificate da AI: quelle il cui cluster è stato scritto da apply_results
    # Usiamo il manifest per ricostruire gli indici AI
    ai_indices: set = set()
    for batch in manifest:
        for idx_group in batch.get("indices", []):
            if isinstance(idx_group, list):
                ai_indices.update(idx_group)
            else:
                ai_indices.add(idx_group)

    n_ai    = len(ai_indices)
    n_rules = total_rows - n_ai

    # Distribuzione cluster (top 10)
    cluster_dist = (
        df_out["Cluster"].value_counts().head(10).to_dict()
        if has_cluster else {}
    )

    # Batch AI e stima token (euristica ~4 caratteri/token sui file prompt/result,
    # letti prima della pulizia della workdir). Non è un conteggio API reale:
    # qui il clustering lo fa Claude in chat, senza chiamate a un endpoint misurabile.
    n_batches = len(manifest)
    avg_batch_size = round(sum(b.get("n_keywords", 0) for b in manifest) / n_batches) if n_batches else 0

    total_chars_prompt = 0
    total_chars_result = 0
    for batch in manifest:
        pf = Path(batch["prompt_file"])
        rf = Path(batch["result_file"])
        if pf.exists():
            total_chars_prompt += len(pf.read_text(encoding="utf-8"))
        if rf.exists():
            total_chars_result += len(rf.read_text(encoding="utf-8"))
    est_tokens_input  = total_chars_prompt // 4
    est_tokens_output = total_chars_result // 4
    est_tokens_total  = est_tokens_input + est_tokens_output

    def _fmt_seconds(secs):
        if secs is None:
            return "n/d"
        m = int(secs // 60)
        s = secs % 60
        return f"{m}m {s:.1f}s" if m else f"{s:.1f}s"

    ruleset_str = _fmt_seconds(ruleset_seconds)
    ai_str      = _fmt_seconds(elapsed)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              SINTESI PRESTAZIONALE — CLUSTERING              ║
╠══════════════════════════════════════════════════════════════╣
║  File output   : {str(output_path):<44}║
║  Righe totali  : {total_rows:>10,}                                  ║
║  Brand         : {n_brands:>10,}                                  ║
╠══════════════════════════════════════════════════════════════╣
║  CLASSIFICAZIONE                                             ║
║  Via regole / cache / fuzzy : {n_rules:>10,}                      ║
║  Via AI (batch)             : {n_ai:>10,}                      ║
║  Errori batch               : {errors:>10,}                      ║
╠══════════════════════════════════════════════════════════════╣
║  TASSONOMIA                                                  ║
║  Cluster distinti           : {n_clusters:>10,}                      ║
║  Sotto Cluster distinti     : {n_sottoclust:>10,}                      ║
╠══════════════════════════════════════════════════════════════╣
║  BATCH AI                                                    ║
║  Batch processati           : {n_batches:>10,}                      ║
║  Media keyword per batch    : {avg_batch_size:>10,}                      ║
║  Token stimati input        : {est_tokens_input:>10,}                      ║
║  Token stimati output       : {est_tokens_output:>10,}                      ║
║  Token stimati totale       : {est_tokens_total:>10,}                      ║
╠══════════════════════════════════════════════════════════════╣
║  TEMPI                                                       ║
║  Classificazione ruleset    : {ruleset_str:<34}║
║  Batch AI (merge)           : {ai_str:<34}║
╚══════════════════════════════════════════════════════════════╝""")
    print("   (Token stimati da lunghezza testo prompt/risposta, ~4 caratteri/token — non è un conteggio API)")

    if cluster_dist:
        print("\n Top cluster per volume:")
        for cl, cnt in cluster_dist.items():
            pct = cnt / total_rows * 100 if total_rows else 0
            bar = "█" * int(pct / 2)
            print(f"   {cl:<32} {cnt:>6,}  ({pct:5.1f}%)  {bar}")

    # Salva la sintesi in JSON accanto al CSV finale, così Claude può leggerla
    # e presentarla come tabella markdown anche dopo la pulizia della workdir.
    summary = {
        "output_file": str(output_path),
        "righe_totali": total_rows,
        "brand": n_brands,
        "classificate_regole_cache_fuzzy": n_rules,
        "classificate_ai": n_ai,
        "errori_batch": errors,
        "cluster_distinti": n_clusters,
        "sotto_cluster_distinti": n_sottoclust,
        "batch_processati": n_batches,
        "media_keyword_per_batch": avg_batch_size,
        "token_stimati_input": est_tokens_input,
        "token_stimati_output": est_tokens_output,
        "token_stimati_totale": est_tokens_total,
        "tempo_classificazione_ruleset": ruleset_str,
        "tempo_batch_ai": ai_str,
        "top_cluster": cluster_dist,
    }
    summary_path = output_path.parent / f"{output_path.stem}-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n Sintesi salvata anche in: {summary_path}")

    # Pulizia workdir
    if workdir.exists():
        shutil.rmtree(workdir)
        print(f"\n[OK] Workdir eliminata: {workdir}")


# -- Main -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SEO Keyword Clustering Agent")
    parser.add_argument("--mode",           choices=["sync-rules", "prepare", "analyze", "add-rules", "add-brands", "process-batches", "merge"], default="prepare")
    parser.add_argument("--input",          help="CSV di input (richiesto in modalità prepare)")
    parser.add_argument("--output",         default="output/clustered.csv")
    parser.add_argument("--workdir",        default="output/workdir")
    parser.add_argument("--sector",         default="abbigliamento e calzature")
    parser.add_argument("--brand",          default=None)
    parser.add_argument("--vertical",       default=None,
                        help="Verticale del ruleset da usare (obbligatorio in --mode prepare; chiedere sempre all'utente quale sia il più adatto "
                             "fra le sottocartelle presenti in 'Clustering rules' su Google Drive — nessuna lista fissa qui). "
                             "In analyze/add-rules viene letto da workdir/vertical.json se omesso.")
    parser.add_argument("--batch-size",     type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--lang",           choices=["IT", "EN", "ES", "FR", "DE"], default=None,
                        help="Lingua per add-rules (default: IT). In prepare viene letta dalla colonna Country del CSV.")
    parser.add_argument("--resume",         action="store_true", default=False,
                        help="Salta i batch in results/ già completati (riprende da dove era rimasto).")
    parser.add_argument("--brands-suggestions", default="output/brands_suggestions.json",
                        help="Path del JSON prodotto da --mode merge con i brand competitor rilevati (per --mode add-brands).")
    args = parser.parse_args()

    # Le regole non sono più committate in git: vengono materializzate per
    # sessione sotto <workdir>/rules/ da --mode sync-rules, a partire dai
    # Google Sheet condivisi in "Clustering rules". Ogni modalità le legge da lì.
    global RULES_DIR
    RULES_DIR = Path(args.workdir) / "rules"

    if args.mode == "sync-rules":
        mode_sync_rules(args)
    elif args.mode == "prepare":
        if not args.input:
            print("Errore: --input richiesto in modalità prepare.")
            sys.exit(1)
        mode_prepare(args)
    elif args.mode == "analyze":
        mode_analyze(args)
    elif args.mode == "add-rules":
        mode_add_rules(args)
    elif args.mode == "add-brands":
        mode_add_brands(args)
    elif args.mode == "process-batches":
        mode_process_batches(args)
    else:
        mode_merge(args)


if __name__ == "__main__":
    main()
