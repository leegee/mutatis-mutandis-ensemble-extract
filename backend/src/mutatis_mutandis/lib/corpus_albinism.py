import unicodedata
from pathlib import Path

from mutatis_mutandis.lib.cannonical_rules import CanonicalRule, CanonicalRules

CORPUS_MIN_YEAR = 0
CORPUS_MAX_YEAR = 2026
FILTER_DOCUMENT_SIZE = False
MIN_TOKENS_IN_DOC = 200
MAX_TOKENS_IN_DOC = 400_000

def get_lance_indexes_dir(indexes_dir: str | Path) -> Path:
    return Path(indexes_dir) / "lance_albinism_ensemble"

CONCEPT_SETS: CanonicalRules = {
    "WHITE": {
        "forms": {
            # Added 2026-10-15
             "albinovanus", "albino", "albinism", "Albinoes",
            # Older
            "white",
            "whit",
            "hwit",
            "whyte",
            "whiyte",
            "whiyte",
            "whight",
            "whyt", "whyte", "hwyte",
            "whitt",
            "auburn" # early 15c off-white cf alb, but meaning shifted 16c. to "reddish-brown" under influence of Middle English brun
        },
        "false_positives": {
            # "wight", -- useful for spooks though it also means 'anything'
            "whiten",
        },
    },
}


PHRASE_SETS: CanonicalRules = {
    "white_as_wool": {
        "forms": [
            # surface patterns; can be expanded later with regex / lemmas
            ("white", "hair"),
            ("whyte", "hair"),
            {"whyte", "heeris"},
            {"whiyte", "heeris"},
            {"whyte", "woolle"},
            {"whyte", "woll"},
            {"whiyte", "wolle"},
            ("hair", "as", "white", "as", "wool"),
            ("white", "as", "wool"),
            ("white", "like", "wool"),
            ("whyte", "as", "wool"),  
            {"whiyte", "as", "wolle"},
        ],
        "false_positives": [],
    },
}


# Export terms

WHITE = {
    "white", "whyte", "whiyte", "whight", "whit", "whyt", "wight", "wite", "whiet",

}

# OE
WHITE |= {
    "hwīt", "hwit", "hƿīt", "hƿit", "hwīte", "hwite", "hƿīte", "hwītne",
    "hwītes", "hwītre", "hwītum", "hwīta", "hwītra", "hwītan", "hwītena",
    "hwītnes", "hwītian", "hwīt-loc", "hwīt-locced",
    # blāc: "pale, shining, white" (not blæc, "black")
    "blāc", "blac", "blāce", "blācne", "blācan",
    # hwīt without macrons, plus common Anglian/Mercian spellings
    "hwiit", "hwyt", "hwȳt", "hwite", "hwitan", "hwites",
    "hwitne", "hwitum", "hwitra",
    # hwītlocced: "white-haired" (attestation uncertain; keep only if it occurs)
    "hwītloccede", "hwitloccede",
}

APPEARANCE = {
    "hair", "haire", "hayre", "hayr", "heare", "hoary", "hoarie", "heeris", "heer",
    "skin", "skinne", "skyn", "complexion", "flesh", "fur", "furre",
    "furr", "coat", "fleece", "pale", "pallid", "pallide", "wan", "wann",
    "wanne", "bloodless", "luminous", "luminouse", "luminus", "luminious",
    "glowing", "glow", "glowe", "glowinge", "glowed", "shining", "shyning",
    "bright", "brightness", "radiant", "radiance", "resplendent",
    "resplendence", "glistering", "glisteringe", "gleaming", "gleaminge",
    "gleam", "gleame", "glittering", "glitteringe", "lucent", "lucid",
}

APPEARANCE |= {
    # hair
    "hǣr", "hær", "hǣre", "hǣres", "hǣras", "hēr",
    "loc", "locc", "loccas", "loccum", "feax", "fex", "feaxe",
    # hoary / grey
    "hār", "har", "hāre", "hārne", "hārum", "hārwenge", "græg", "grǣg",
    # skin / flesh / fleece / wool
    "fell", "felle", "hȳd", "hyd", "līc", "lic",
    "flǣsc", "flæsc", "flǣsce", "flēos", "fleos", "flēse", "wull", "wulle",
    # complexion / appearance
    "hīw", "hiw", "hīwe", "blēoh", "bleoh", "blēo", "bleo",
    "wlite", "wlites", "wlitig", "ansȳn", "ansyn", "andwlita",
    # pale / wan
    "blāc", "blac", "bleac", "blāce", "fealu", "fealo",
}

LIGHT = {
    "luminous", "luminouse", "luminus", "luminious", "glowing", "glow",
    "glowe", "glowinge", "glowed", "shining", "shyning", "bright",
    "brightness", "radiant", "radiance", "resplendent", "resplendence",
    "glistering", "glisteringe", "gleaming", "gleaminge", "gleam", "gleame",
    "glittering", "glitteringe", "lucent", "lucid",
}

LIGHT |= {
    "beorht", "bryht", "byrht", "berht", "beorhte", "beorhtan", "beorhtnes",
    "torht", "torhtan", "torhtnes",
    "scīr", "scir", "scīre", "scīran", "scīnan", "scinan", "scīnende",
    "scīnan", "scān", "scinon", "scīma", "scima",
    "lēoht", "leoht", "līht", "liht", "lēohte", "lēoma", "leoma",
    "līxan", "lixan", "līxte", "blīcan", "blican", "blāc",
    "glǣm", "glæm", "glītenian", "glitenian", "glisnian", "glisian",
}

SUPERNATURAL = {
    "ghost", "ghosts", "ghostly", "phantom", "phantoms", "phantasme",
    "apparition", "apparitions", "spirit", "spirits", "sprite", "sprites",
    "elf", "elves", "fairy", "fairies", "faerie", "faeries", "fay", "fays",
    "spectre", "spectres", "specter", "specters", "wraith", "wraiths",
    "angel", "angels", "demon", "demons", "daemon", "daemons", "goblin",
    "goblins", "hobgoblin", "hobgoblins", "incubus", "succubus",
}

SUPERNATURAL |= {
    # spirit / ghost
    "gāst", "gast", "gǣst", "gaest", "gāstas", "gǣstas", "gǣsta", "gastes",
    "wiht", "wihta", "wihte", "wihtes",       # also ME "wight"; see below
    "scinn", "scin", "scinna", "scinnan", "scinlāc", "scinlac",
    # angel / demon / devil / fiend
    "engel", "ængel", "englas", "ængelas", "ænglas", "engla",
    "dēofol", "deofol", "dēoful", "deoful", "dēofla", "deofla", "dēoflu",
    "fēond", "feond", "fiend", "fēondas", "hellewiht",
    # elf / goblin / monster
    "ælf", "ælfe", "ylf", "ylfe", "ælfa", "ælfen", "ælfcynn",
    "scucca", "scuccan", "sceocca", "sceoccan",
    "mære", "mǣre", "nicor", "nicras", "eoten", "eotenas", "þyrs", "thyrs",
    "gedwimor", "gedwimer", "dwolma",
}

ALBINISM = {
    "albino", "albinos", "albinoes", "albinism", "albinisms",
    "albinovanus", "albinovani", "albinovanum", "albinovano",
}

# Token distance within which co-occurrence rules apply.
PROXIMITY = 10

TERM_GROUPS = {
    "white": WHITE,
    "appearance": APPEARANCE,
    "light": LIGHT,
    "supernatural": SUPERNATURAL,
    "albinism": ALBINISM,
}

# Prefix (stem) matches, for inflected Old English forms. A token matches if
# lower(token) STARTS WITH the prefix. Exact sets above are unaffected.
# Keep prefixes long/distinctive: short ones match unrelated words and names
# (e.g. "blac" -> "black", "engl" -> "english", "ælf" -> Ælfric/Ælfwine).
PREFIX_GROUPS = {
    "white": {
        "hwīt", "hwit", "hƿīt", "hƿit", "hwȳt", "hwyt",
        "blāc",
    },
    "appearance": {
        "hǣr", "hær",           # hair (note "hærfest" = harvest)
        "feax",
        "flǣsc", "flæsc",
        "hīw",
        "wlit",                 # wlite / wlitig
        "blēoh",
    },
    "light": {
        "beorht", "byrht", "torht",
        "scīn",
        "lēoht", "leoht",
        "līxan", "līxt",
        "blīc",
        "glǣm", "glæm",
        "glīten", "glisn",
    },
    "supernatural": {
        "gāst", "gǣst",
        "ængel", "engel",
        "dēofl", "deofl",
        "fēond", "feond",
        "ylf",
        "scucc", "sceocc",
    },
    "albinism": set(),
}


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _norm_prefix(value: str) -> str:
    """NFC + lowercase, so prefixes compare like lower(token)."""
    return unicodedata.normalize("NFC", value).lower()


def _hit_ctes(table: str, inline: bool = False) -> tuple[str, list]:
    """
    Shared CTEs: term_groups, [term_prefixes], target_tokens, target_hits.

    The single definition of what counts as a hit. With inline=False the term
    VALUES lists use bound parameters (returned in order: exact terms, then
    prefixes); with inline=True the terms are rendered as escaped literals and
    the params list is empty.
    """
    values: list[str] = []
    params: list = []
    for group, terms in TERM_GROUPS.items():
        for term in sorted(terms):
            if inline:
                values.append(f"({_sql_literal(term)}, {_sql_literal(group)})")
            else:
                values.append("(%s, %s)")
                params.extend((term, group))

    prefix_values: list[str] = []
    for group, prefixes in PREFIX_GROUPS.items():
        for prefix in sorted({_norm_prefix(p) for p in prefixes}):
            if inline:
                prefix_values.append(
                    f"({_sql_literal(prefix)}, {_sql_literal(group)})"
                )
            else:
                prefix_values.append("(%s, %s)")
                params.extend((prefix, group))

    # An empty VALUES list is a syntax error, so only emit prefix SQL if needed.
    if prefix_values:
        prefix_cte = f"""
        term_prefixes(prefix, grp) AS (
            VALUES {", ".join(prefix_values)}
        ),"""
        prefix_select = """
            UNION

            SELECT
                t.corpus,
                t.doc_id,
                t.token_idx,
                tp.grp
            FROM {table} AS t
            JOIN term_prefixes AS tp
              ON starts_with(lower(t.token), tp.prefix)""".format(table=table)
    else:
        prefix_cte = ""
        prefix_select = ""

    sql = f"""
        term_groups(term, grp) AS (
            VALUES {", ".join(values)}
        ),{prefix_cte}
        target_tokens AS MATERIALIZED (
            SELECT
                t.corpus,
                t.doc_id,
                t.token_idx,
                tg.grp
            FROM {table} AS t
            JOIN term_groups AS tg
              ON lower(t.token) = tg.term
            {prefix_select}
        ),
        target_hits AS (
            -- Route 1: whiteness near appearance or luminosity
            SELECT w.corpus, w.doc_id, w.token_idx
            FROM target_tokens AS w
            JOIN target_tokens AS a
              ON a.corpus = w.corpus
             AND a.doc_id = w.doc_id
             AND a.grp = 'appearance'
             AND a.token_idx BETWEEN w.token_idx - {PROXIMITY}
                                 AND w.token_idx + {PROXIMITY}
            WHERE w.grp = 'white'

            UNION

            -- Route 2: luminosity near a supernatural figure
            SELECT l.corpus, l.doc_id, l.token_idx
            FROM target_tokens AS l
            JOIN target_tokens AS s
              ON s.corpus = l.corpus
             AND s.doc_id = l.doc_id
             AND s.grp = 'supernatural'
             AND s.token_idx BETWEEN l.token_idx - {PROXIMITY}
                                 AND l.token_idx + {PROXIMITY}
            WHERE l.grp = 'light'

            UNION

            -- Route 3: explicit whiteness near a supernatural figure
            SELECT w.corpus, w.doc_id, w.token_idx
            FROM target_tokens AS w
            JOIN target_tokens AS s
              ON s.corpus = w.corpus
             AND s.doc_id = w.doc_id
             AND s.grp = 'supernatural'
             AND s.token_idx BETWEEN w.token_idx - {PROXIMITY}
                                 AND w.token_idx + {PROXIMITY}
            WHERE w.grp = 'white'

            UNION

            -- Route 4: explicit historical albinism-related vocabulary
            SELECT corpus, doc_id, token_idx
            FROM target_tokens
            WHERE grp = 'albinism'
        )
    """
    return sql, params


def build_corpus_query(
    table: str = "tokens",
    doc_table: str = "documents",
    inline: bool = False,
) -> tuple[str, list]:
    """Document-level selection built from the shared hit definition."""
    ctes, params = _hit_ctes(table, inline=inline)
    sql = f"""
        WITH {ctes},
        selected_docs AS (
            SELECT DISTINCT corpus, doc_id
            FROM target_hits
        )
        SELECT
            d.corpus,
            d.doc_id,
            d.pub_year,
            d.author,
            d.title,
            d.filepath
        FROM selected_docs AS s
        JOIN {doc_table} AS d ON d.doc_id = s.doc_id AND d.corpus = s.corpus
        ORDER BY d.pub_year NULLS LAST, d.title
    """
    return sql, params


# Parameter-free SQL string (terms inlined), generated from the constant sets.
CORPUS_SQL, _ = build_corpus_query(inline=True)


def select_white_corpus_doc_ids():
    from mutatis_mutandis.lib.corpus_db import get_connection
    from mutatis_mutandis.lib.corpus_logging import get_logger
    logger = get_logger(__name__)

    con = get_connection()
    try:
        with con.cursor() as cur:
            cur.execute(CORPUS_SQL)
            rows = cur.fetchall()

        logger.info("White corpus selection returned %d documents", len(rows))

        for row in rows:
            logger.info(
                "Selected document: corpus=%s doc_id=%s year=%s author=%s title=%s",
                row[0], row[1], row[2], row[3], row[4]
            )

        return [row[1] for row in rows]

    finally:
        con.close()


BACKFILL_SQL = """WITH selected_docs AS (
    SELECT DISTINCT corpus, doc_id
    FROM tokens
    WHERE token ILIKE 'albin%'
)
SELECT
    t.corpus,
    t.doc_id,
    d.pub_year,
    t.token_idx,
    t.token
FROM tokens AS t
JOIN documents AS d
    ON d.corpus = t.corpus
   AND d.doc_id = t.doc_id
JOIN selected_docs AS s
    ON s.corpus = t.corpus
   AND s.doc_id = t.doc_id
ORDER BY t.corpus, t.doc_id, t.token_idx;
"""


def build_export_query(TABLE, DOC_TABLE, WINDOW_LEFT, WINDOW_RIGHT) -> tuple[str, list]:
    ctes, params = _hit_ctes(TABLE)

    sql = f"""
        WITH {ctes},
        eligible_hits AS (
            SELECT DISTINCT h.corpus, h.doc_id, h.token_idx
            FROM target_hits AS h
            WHERE NOT EXISTS (
                SELECT 1
                FROM export_indexed_docs AS ix
                WHERE ix.corpus = h.corpus
                  AND ix.doc_id = h.doc_id
            )
            OR h.doc_id = ANY(%s)
        )
        SELECT DISTINCT
            t.corpus,
            t.doc_id,
            d.pub_year,
            t.token_idx,
            t.token
        FROM eligible_hits AS h
        JOIN {TABLE} AS t
          ON t.corpus = h.corpus
         AND t.doc_id = h.doc_id
         AND t.token_idx BETWEEN
             h.token_idx - {WINDOW_LEFT}
             AND h.token_idx + {WINDOW_RIGHT}
        JOIN {DOC_TABLE} AS d
          ON d.corpus = t.corpus
         AND d.doc_id = t.doc_id
        ORDER BY t.corpus, t.doc_id, t.token_idx
    """
    return sql, params



if __name__ == "__main__":
    select_white_corpus_doc_ids()
    