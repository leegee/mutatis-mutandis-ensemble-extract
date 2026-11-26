#!/usr/bin/env python3
"""
We need to seed the table `normalized_places` with the locations
of `QUALIFIERS` sometimes those are the only thing that resolves `documents.pub_places`.
"""

import psycopg
import time
import requests
import re
import unicodedata
from collections import defaultdict

from lib.corpus_db import get_connection, analysis_db_connection
from lib.corpus_logging import logger
from lib.corpus_config import CORPUS_TIER2_DB_PATH


GEOCODE_URL = "https://nominatim.openstreetmap.org/search"


# VARIANT to CANONICAL MAP (lowercase keys)
PLACE_MAP = {
    "london": "London",
    "lo": "London",
    "londres": "London",
    "llundain": "London",
    "oxford": "Oxford",
    "oxon": "Oxford",
    "yorke": "York",
    "york": "York",
    "edinburgh": "Edinburgh",
    "edenburgh": "Edinburgh",
    "warsaw": "Warsaw",
    "amsterdam": "Amsterdam",
    "amsterodam": "Amsterdam",
    "antwerp": "Antwerp",
    "antwerpen": "Antwerp",
    "bruxelles": "Brussels",
    "brussels": "Brussels",
    "dublin": "Dublin",
    "waterford": "Waterford",
    "leiden": "Leiden",
    "leyden": "Leiden",
    "ghent": "Ghent",
    "gant": "Ghent",
    "paris": "Paris",
    "rouen": "Rouen",
    "douai": "Douai",
    "saint omer": "Saint-Omer",
    "hamburgh": "Hamburg",
    "hamburg": "Hamburg",
    "rotterdam":"Rotterdam",
    "roterdame":"Rotterdam",
    "rhydychen": "Oxford",
    "norwich": "Norwich",
    "nottingham": "Nottingham",

    # Cambridge
    "cambridge": "Cambridge",
    "cambridg": "Cambridge",

    # Cant
    "cantabrigi": "Canterbury",
    "cantabrigiae": "Canterbury",

    # Boston
    "boston": "Boston, Mass.",

    # Aberdeen
    "aberdeen": "Aberdeen",
    "aberdene": "Aberdeen",

    # Edinburgh
    "edinburg": "Edinburgh",
    "edinbvrgh": "Edinburgh",
    "edenborough": "Edinburgh",
    "edenbrough": "Edinburgh",
    "edenburg": "Edinburgh",
    "edenburgi": "Edinburgh",
    "edynburgh": "Edinburgh",

    # Hague
    "hague": "The Hague",
    "hagh": "The Hague",
    "haghe": "The Hague",
    "hage": "The Hague",
    "gravenhagh": "The Hague",

    # Waterford
    "vvaterford": "Waterford",

    # Dublin
    "dvblin": "Dublin",
    "dubdin": "Dublin",

    # Leiden
    "leyden": "Leiden",

    # Delft
    "delft": "Delft",
    "delf": "Delft",
    "delff": "Delft",
    "delph": "Delft",

    # Brussels
    "bruxells": "Brussels",

    # Middelburg
    "middelburgh": "Middelburg",
    "middleburg": "Middelburg",

    # Antwerp
    "anwerp": "Antwerp",
    "antwarp": "Antwerp",

    # Ghent
    "ghent": "Ghent",

    # Douai
    "doway": "Douai",
    "dovvay": "Douai",

    # Aberdeen
    "aberderdene": "Aberdeen",   # if present elsewhere
    "abderdene": "Aberdeen",
    "aberden": "Aberdeen",
    "aberdoni": "Aberdeen",
    "aberdoniis": "Aberdeen",
    "abredeis": "Aberdeen",
    "abredoni": "Aberdeen",

    # Amsterdam
    "amstelodami": "Amsterdam",
    "amstelredam": "Amsterdam",
    "amsterledam": "Amsterdam",
    "amstersdam": "Amsterdam",

    # Antwerp
    "antworp": "Antwerp",

    # Saint-Omer
    "audomari": "Saint-Omer",
    "omer": "Saint-Omer",
    "omers": "Saint-Omer",

    # Beauvais
    "beauvais": "Beauvais",

    # Breda
    "breda": "Breda",

    # Bristol
    "bristol": "Bristol",
    "bristoll": "Bristol",

    # Bruges
    "bruges": "Bruges",

    # Caen
    "caen": "Caen",

    # Colchester
    "colechester": "Colchester",

    # Cologne
    "cologne": "Cologne",

    # Constantinople
    "constantinople": "Constantinople",

    # Cork
    "corck": "Cork",
    "corcke": "Cork",
    "cork": "Cork",
    "corke": "Cork",

    # Dordrecht
    "dordrecht": "Dordrecht",
    "dort": "Dordrecht",

    # Douai
    "douay": "Douai",

    # Durham
    "durham": "Durham",

    # Edinburgh
    "edinbourg": "Edinburgh",
    "edinburh": "Edinburgh",
    "edingburgh": "Edinburgh",

    # Exeter
    "exeter": "Exeter",
    "exon": "Exeter",
    "extern": "Exeter",

    # Falmouth
    "falmouth": "Falmouth",

    # Franckfort
    "franckfort": "Frankfurt",

    # Geneva
    "genevah": "Geneva",

    # Glasgow
    "glasgow": "Glasgow",
    "glasgu": "Glasgow",

    # Haarlem
    "haarlem": "Haarlem",

    # Hague
    "hag": "The Hague",
    "haye": "The Hague",

    # Hamburg
    "hamborough": "Hamburg",

    # Ipswich
    "ipswich": "Ipswich",

    # Kilkenny
    "kilkenny": "Kilkenny",

    "kosmoburg": "London",

    # Leith
    "leith": "Leith",

    # Liège
    "liege": "Liège",
    "lvyck": "Liège",

    # Lille
    "lille": "Lille",

    # London variants
    "llyndain": "London",
    "lodnon": "London",
    "lodon": "London",
    "lond": "London",
    "londdn": "London",
    "londen": "London",
    "londgn": "London",
    "londinensis": "London",
    "londini": "London",
    "londn": "London",
    "londnon": "London",
    "londod": "London",
    "londou": "London",
    "londre": "London",
    "lonkon": "London",
    "lonndo": "London",
    "lonndon": "London",
    "lonnon": "London",
    "lonon": "London",
    "lonpuo": "London",
    "loudon": "London",
    "loydon": "London",
    "ludd": "London",
    "lundain": "London",
    "ondon": "London",

    # Loreto
    "loreto": "Loreto",

    # Louvain / Leuven
    "louain": "Leuven",
    "louanii": "Leuven",
    "louvain": "Leuven",
    "lovain": "Leuven",

    # Newcastle
    "newcastle": "Newcastle",

    # Oxford
    "oxen": "Oxford",   # OCR variant

    # Philadelphia
    "Philadelphia": "Philadelphia",

    # Reading
    "reading": "Reading",

    # Rochester
    "rochester": "Rochester",

    # Rouen
    "roan": "Rouen",
    "rouan": "Rouen",

    # Salisbury
    "salisbury": "Salisbury",

    # Savoy
    "savoy": "Savoy, London",

    # Shrewsbury
    "shrewsbury": "Shrewsbury",

    # Swarthmore
    "swarthmore": "Swarthmore",

    # Troyes
    "troyes": "Troyes",

    # Waterford
    "warerford": "Waterford",

    # Westminster
    "westminster": "Westminster",

    # Worcester
    "worcester": "Worcester",

    "aire": "Aire-sur-la-Lys",      # often linked with Saint-Omer printing
    "buckden": "Buckden",
    "chelmsford": "Chelmsford",
    "chester": "Chester",
    "cirencester": "Cirencester",
    "finsbury": "Finsbury, London",
    "gateshead": "Gateshead",
    "pomadie": "Pomerania",
    "sicilia": "Sicily",
    "smithfield": "Smithfield, London",
    "wakefield": "Wakefield",

    "gateside": "Gateside, Scotland",

    "carolopoli": "Charleville, France",

    "gottenberge": "Gothenburg",
    "edinb": "Edinburgh",
    "edin": "Edinburgh",
    "england": "England",
    "scotland": "Scotland",
    "ireland": "Ireland",
    "europ": "Europe",
    "europe": "Europe",
    "franca": "France",
    "france": "France",
    "holland": "Netherlands",
    "netherlands": "Netherlands",
    "lon": "London",
    "abroad": "Sine Loco",
    "s.l.": "Sine Loco",
    "[s.l.": "Sine Loco",
    "[s.l": "Sine Loco",
    "[s.l,": "Sine Loco",
    "s. l.": "Sine Loco",
    "[S.1.": "Sine Loco",
    "n.p.": "Sine Loco",
    "n. p.": "Sine Loco",
    "doüay": "Douai, France",
    "roüen": "Rouen",
    "lo[ndon": "London",
    "L[ondo]n": "London",
    "[liège?": "Liège",
    "[lo]ndon": "London",
    "nod-nol.": "London",
    "obedience": "Sine Loco",
}


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    # remove combining diacritics (Doüay → douay, roüen → rouen)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # normalize punctuation variants
    s = re.sub(r"[\[\]().,:;?']", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


CLEAN_PLACE_MAP = {
    norm_key(k): v
    for k, v in PLACE_MAP.items()
}


QUALIFIERS = {
    "england",
    "scotland",
    "ireland",
    "london",
    "netherlands",
    "holland",
    "mass",
    "massachusetts",
    "yorkshire",
    "oxfordshire",
    "cambridgeshire",
    "sine loco",
}




UNKNOWN = defaultdict(str)


def final_sql(conn: psycopg.Connection):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS place_normalization_geom_idx ON place_normalization USING GIST (geom);
        """)


def normalize_pub_place(raw: str | None):
    if not raw:
        return None

    s = unicodedata.normalize("NFKC", raw).lower()
    logger.info("IN %s ", s)

    found = []

    # pure variant scan
    key = norm_key(s)

    # Sort by length so Lo for London doesn't match Londonderry
    for variant, canonical in sorted(
        CLEAN_PLACE_MAP.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if variant in key:
            logger.info("VAR ---------- %s -> %s", variant, canonical)
            found.append(canonical)


    # dedupe preserving order
    found = list(dict.fromkeys(found))

    # if multiple, drop Sine Loco, London (or other low-priority)
    if len(found) > 1:
        found = [f for f in found if norm_key(f) != norm_key("sine loco")]
        if len(found) > 1:
            found = [
                f for f in found
                if norm_key(f) not in QUALIFIERS
            ] or found

    logger.info("FIN ------------------------------------------------------------------------------------ %s", found)

    # logging unknowns (only for iteration)
    if not found:
        for token in re.findall(r"[a-z]+", s):
            if token not in CLEAN_PLACE_MAP:
                UNKNOWN[token] += f"{token} "
        return None

    return found



def geocode(place: str):
    if (place == "Sine Loco"):
        return 54.75, 2.25 # Dogger Bank for visibility

    try:
        r = requests.get(
            GEOCODE_URL,
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": "eebo-geocoder/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        if not data:
            return None

        return float(data[0]["lat"]), float(data[0]["lon"])

    except Exception as e:
        logger.warning("Geocode failed for %s: %s", place, e)
        return None


def create_place(conn: psycopg.Connection):
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

        # cur.execute("DROP TABLE IF  EXISTS place_normalization;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS place_normalization (
                raw_place TEXT PRIMARY KEY,
                normalized_places TEXT[],
                geom GEOGRAPHY(POINT, 4326),
                lat DOUBLE PRECISION,
                lng DOUBLE PRECISION
            )
        """)

        cur.execute("""
            SELECT DISTINCT pub_place FROM documents
            WHERE pub_place IS NOT NULL
            ORDER BY pub_place
        """)

        rows = cur.fetchall()
        logger.info("Processing %d rows", len(rows))

        total = 0
        matched = 0
        unmatched = []

        for (raw,) in rows:
            total += 1
            norm = normalize_pub_place(raw)
            cur.execute("""
                INSERT INTO place_normalization (raw_place, normalized_places)
                VALUES (%s, %s)
                ON CONFLICT (raw_place)
                DO UPDATE SET normalized_places = EXCLUDED.normalized_places
            """, (raw, norm))
            # logger.info("%s \t\t %s",  norm, raw)
            if norm:
                matched += 1
            else:
                unmatched.append(raw)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS place_normalization_geom_idx ON place_normalization USING GIST (geom);
            CREATE INDEX IF NOT EXISTS place_normalization_lat_idx ON place_normalization (lat);
            CREATE INDEX IF NOT EXISTS place_normalization_lng_idx ON place_normalization (lng);
        """)

    conn.commit()

    # coverage report
    # logger.info("")
    # logger.info("=== COVERAGE ===")
    # logger.info("Total rows:     %d", total)
    # logger.info("Matched rows:   %d", matched)
    # logger.info("Unmatched rows: %d", len(unmatched))
    # logger.info("Coverage:       %.1f%%", 100.0 * matched / total)

    # unmatched examples
    logger.info("")
    logger.info("=== UNMATCHED ROWS ===")
    for raw in unmatched[:200]:
        logger.info(raw)


def geocode_places(conn: psycopg.Connection):
    done = set()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT raw_place, normalized_places, geom
            FROM place_normalization
            WHERE geom IS NULL
        """)

        rows = cur.fetchall()
        logger.info("Need geocoding: %d rows", len(rows))

        for raw_place, normalized, geom in rows:
            if geom is not None:
                continue

            if normalized:
                key = normalized[0] if isinstance(normalized, list) else normalized
            else:
                key = raw_place

            key = key.strip()

            if key in done:
                continue

            done.add(key)

            logger.info("Geocoding: %s", key)

            result = geocode(key)

            if not result:
                logger.warning("No result for: %s", key)
                continue

            lat, lon = result

            cur.execute("""
                UPDATE place_normalization
                SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    lat  = %s,
                    lng  = %s
                WHERE %s = ANY(normalized_places)
                OR (normalized_places IS NULL AND raw_place = %s)
            """, (lon, lat, lat, lon, key, key))

            conn.commit()
            time.sleep(1.1)

    logger.info("Geocoding complete")


def export_document_places_sqlite(conn, sqlite):
    pg_rows = []

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                d.doc_id,
                d.pub_place,
                p.normalized_places[1],
                p.lat,
                p.lng
            FROM documents d
            LEFT JOIN place_normalization p
                ON d.pub_place = p.raw_place
        """)

        pg_rows = cur.fetchall()

    cur = sqlite.cursor()

    cur.execute("DROP TABLE IF EXISTS document_places")

    cur.execute("""
        CREATE TABLE document_places (
            doc_id TEXT PRIMARY KEY,
            raw_place TEXT,
            normalized_place TEXT,
            lat REAL,
            lng REAL
        )
    """)

    cur.executemany("""
        INSERT INTO document_places (
            doc_id, raw_place, normalized_place, lat, lng
        )
        VALUES (?, ?, ?, ?, ?)
    """, pg_rows)

    cur.execute("CREATE INDEX document_places_lat_idx ON document_places(lat)")
    cur.execute("CREATE INDEX document_places_lng_idx ON document_places(lng)")

    sqlite.commit()
    logger.info( "Exported %d document place rows", len(pg_rows) )


def main():
    conn = get_connection(application_name="normalize_places")
    create_place(conn)
    geocode_places(conn)
    sqlite = analysis_db_connection(CORPUS_TIER2_DB_PATH)
    export_document_places_sqlite( conn, sqlite )
    sqlite.close()
    final_sql(conn)


if __name__ == "__main__":
    main()
