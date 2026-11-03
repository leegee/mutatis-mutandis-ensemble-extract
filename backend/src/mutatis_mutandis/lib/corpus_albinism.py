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
            "wight",
            "whiten",
        },
    },
}


# Update to match pattern in phrase_search
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


CORPUS_SQL = """
WITH
white_tokens AS (
    SELECT corpus, doc_id, token_idx
    FROM tokens
    WHERE lower(token) IN (
        'white', 'whyte', 'whight', 'whit', 'whiyte',
        'whyt', 'wight', 'wite', 'whiet'
    )
),
appearance_tokens AS (
    SELECT corpus, doc_id, token_idx
    FROM tokens
    WHERE lower(token) IN (
        'hair', 'haire', 'hayre', 'hayr', 'heare',
        'hoary', 'hoarie',
        'skin', 'skinne', 'skyn', 'complexion', 'flesh',
        'fur', 'furre', 'furr', 'coat', 'fleece',
        'pale', 'pallid', 'pallide', 'wan', 'wann',
        'wanne', 'bloodless',
        'luminous', 'luminouse', 'luminus', 'luminious',
        'glowing', 'glow', 'glowe', 'glowinge', 'glowed',
        'shining', 'shyning', 'bright', 'brightness',
        'radiant', 'radiance', 'resplendent', 'resplendence',
        'glistering', 'glisteringe', 'gleaming', 'gleaminge',
        'gleam', 'gleame', 'glittering', 'glitteringe',
        'lucent', 'lucid'
    )
),
light_tokens AS (
    SELECT corpus, doc_id, token_idx
    FROM tokens
    WHERE lower(token) IN (
        'luminous', 'luminouse', 'luminus', 'luminious',
        'glowing', 'glow', 'glowe', 'glowinge', 'glowed',
        'shining', 'shyning', 'bright', 'brightness',
        'radiant', 'radiance', 'resplendent', 'resplendence',
        'glistering', 'glisteringe', 'gleaming', 'gleaminge',
        'gleam', 'gleame', 'glittering', 'glitteringe',
        'lucent', 'lucid'
    )
),
supernatural_tokens AS (
    SELECT corpus, doc_id, token_idx
    FROM tokens
    WHERE lower(token) IN (
        'ghost', 'ghosts', 'ghostly',
        'phantom', 'phantoms', 'phantasme',
        'apparition', 'apparitions',
        'spirit', 'spirits', 'sprite', 'sprites',
        'elf', 'elves', 'elves',
        'fairy', 'fairies', 'faerie', 'faeries', 'fay', 'fays',
        'spectre', 'spectres', 'specter', 'specters',
        'wraith', 'wraiths', 'angel', 'angels',
        'demon', 'demons', 'daemon', 'daemons',
        'goblin', 'goblins', 'hobgoblin', 'hobgoblins',
        'incubus', 'succubus'
    )
),
albinism_tokens AS (
    SELECT corpus, doc_id, token_idx
    FROM tokens
    WHERE lower(token) IN (
        'albino', 'albinos', 'albinoes',
        'albinism', 'albinisms',
        'albinovanus', 'albinovani',
        'albinovanum', 'albinovano'
    )
),
selected_docs AS (
    -- Route 1: whiteness near appearance or luminosity
    SELECT w.corpus, w.doc_id
    FROM white_tokens w
    JOIN appearance_tokens a
      ON a.corpus = w.corpus
     AND a.doc_id = w.doc_id
     AND a.token_idx BETWEEN w.token_idx - 10 AND w.token_idx + 10

    UNION

    -- Route 2: luminosity near a supernatural figure
    SELECT l.corpus, l.doc_id
    FROM light_tokens l
    JOIN supernatural_tokens s
      ON s.corpus = l.corpus
     AND s.doc_id = l.doc_id
     AND s.token_idx BETWEEN l.token_idx - 10 AND l.token_idx + 10

    UNION

    -- Route 3: explicit whiteness near a supernatural figure
    SELECT w.corpus, w.doc_id
    FROM white_tokens w
    JOIN supernatural_tokens s
      ON s.corpus = w.corpus
     AND s.doc_id = w.doc_id
     AND s.token_idx BETWEEN w.token_idx - 10 AND w.token_idx + 10

    UNION

    -- Route 4: explicit historical albinism-related vocabulary
    SELECT a.corpus, a.doc_id
    FROM albinism_tokens a
)
SELECT
    d.corpus,
    d.doc_id,
    d.pub_year,
    d.author,
    d.title,
    d.filepath
FROM selected_docs s
JOIN documents d ON d.doc_id = s.doc_id AND d.corpus = s.corpus
ORDER BY d.pub_year NULLS LAST, d.title
"""


def select_white_corpus_doc_ids():
    from mutatis_mutandis.lib.corpus_db import get_connection
    from mutatis_mutandis.lib.corpus_logging import logger

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

# Export terms

WHITE = {
    "white", "whyte", "whiyte", "whight", "whit", "whyt", "wight", "wite", "whiet",
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
LIGHT = {
    "luminous", "luminouse", "luminus", "luminious", "glowing", "glow",
    "glowe", "glowinge", "glowed", "shining", "shyning", "bright",
    "brightness", "radiant", "radiance", "resplendent", "resplendence",
    "glistering", "glisteringe", "gleaming", "gleaminge", "gleam", "gleame",
    "glittering", "glitteringe", "lucent", "lucid",
}
SUPERNATURAL = {
    "ghost", "ghosts", "ghostly", "phantom", "phantoms", "phantasme",
    "apparition", "apparitions", "spirit", "spirits", "sprite", "sprites",
    "elf", "elves", "fairy", "fairies", "faerie", "faeries", "fay", "fays",
    "spectre", "spectres", "specter", "specters", "wraith", "wraiths",
    "angel", "angels", "demon", "demons", "daemon", "daemons", "goblin",
    "goblins", "hobgoblin", "hobgoblins", "incubus", "succubus",
}
ALBINISM = {
    "albino", "albinos", "albinoes", "albinism", "albinisms",
    "albinovanus", "albinovani", "albinovanum", "albinovano",
}


def build_export_query(TABLE, DOC_TABLE, WINDOW_LEFT, WINDOW_RIGHT) -> tuple[str, list]:
    groups = {
        "white": WHITE,
        "appearance": APPEARANCE,
        "light": LIGHT,
        "supernatural": SUPERNATURAL,
        "albinism": ALBINISM,
    }

    values = []
    params = []
    for group, terms in groups.items():
        for term in sorted(terms):
            values.append("(%s, %s)")
            params.extend((term, group))

    sql = f"""
        WITH term_groups(term, grp) AS (
            VALUES {", ".join(values)}
        ),
        target_tokens AS MATERIALIZED (
            SELECT DISTINCT
                t.corpus,
                t.doc_id,
                t.token_idx,
                tg.grp
            FROM {TABLE} AS t
            JOIN term_groups AS tg
              ON lower(t.token) = tg.term
        ),
        target_hits AS (
            SELECT w.corpus, w.doc_id, w.token_idx
            FROM target_tokens AS w
            JOIN target_tokens AS a
              ON a.corpus = w.corpus
             AND a.doc_id = w.doc_id
             AND a.grp = 'appearance'
             AND a.token_idx BETWEEN w.token_idx - 10
                                 AND w.token_idx + 10
            WHERE w.grp = 'white'

            UNION

            SELECT l.corpus, l.doc_id, l.token_idx
            FROM target_tokens AS l
            JOIN target_tokens AS s
              ON s.corpus = l.corpus
             AND s.doc_id = l.doc_id
             AND s.grp = 'supernatural'
             AND s.token_idx BETWEEN l.token_idx - 10
                                 AND l.token_idx + 10
            WHERE l.grp = 'light'

            UNION

            SELECT w.corpus, w.doc_id, w.token_idx
            FROM target_tokens AS w
            JOIN target_tokens AS s
              ON s.corpus = w.corpus
             AND s.doc_id = w.doc_id
             AND s.grp = 'supernatural'
             AND s.token_idx BETWEEN w.token_idx - 10
                                 AND w.token_idx + 10
            WHERE w.grp = 'white'

            UNION

            SELECT corpus, doc_id, token_idx
            FROM target_tokens
            WHERE grp = 'albinism'
        ),
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
