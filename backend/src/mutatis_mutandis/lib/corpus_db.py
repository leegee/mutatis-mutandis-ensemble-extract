# lib/corpus_db.py

"""
corpus_db.py - Corpus database access

Connections, schema (wip that should use .sql files), etc

Todo: rename stuff after including more than eebo

"""

import os
import psycopg
from psycopg import sql, Connection
import time

import mutatis_mutandis.lib.corpus_config as config
from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger(__name__)

_DB_RETRIES = 3
_DB_RETRY_DELAY = 5  # seconds

host     = os.environ.get("CORPUS_PGHOST")     or os.environ.get("PGHOST", "localhost")
user     = os.environ.get("CORPUS_USER")       or os.environ.get("PGUSER", "postgres")
port     = os.environ.get("CORPUS_PGPORT")     or os.environ.get("PGPORT", 5432)
dbname   = os.environ.get("CORPUS_PGDATABASE") or os.environ.get("PGDATABASE")
password = os.environ.get("CORPUS_PGPASSWORD") or os.environ.get("PGPASSWORD")

if not dbname:
    raise RuntimeError("Database name must be set via CORPUS_PGDATABASE or PGDATABASE")
if not password:
    raise RuntimeError("Password name must be set via CORPUS_PGPASSWORD or PGPASSWORD")


def get_connection(
    *,
    connect_timeout: int = 5,
    application_name: str = "corpus",
) -> Connection:
    """
    Create and return a PostgreSQL connection with autocommit disabled.
    Callers should use `with conn.transaction():` or call `conn.commit()`.
    Applies session-level tuning suitable for large bulk ingestion.
    """
    last_exc: Exception | None = None

    for attempt in range(1, _DB_RETRIES + 1):
        try:
            conn = psycopg.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port,
                sslmode="disable",
                connect_timeout=connect_timeout,
                application_name=application_name,
            )
            conn.autocommit = False

            # Session-level tuning
            with conn.cursor() as cur:
                cur.execute("SET synchronous_commit = OFF;")
                cur.execute("SET work_mem = '128MB';")
                cur.execute("SET maintenance_work_mem = '1GB';")
                cur.execute("SET temp_buffers = '32MB';")

            return conn

        except Exception as exc:
            last_exc = exc
            logger.warning( f"PostgreSQL connection attempt {attempt}/{_DB_RETRIES} failed: {exc}" )
            if attempt < _DB_RETRIES:
                time.sleep(_DB_RETRY_DELAY)

    raise RuntimeError("Could not establish PostgreSQL connection") from last_exc


def get_autocommit_connection(
    *,
    connect_timeout: int = 5,
    application_name: str = "borpus",
) -> Connection:
    """
    Get a fresh PostgreSQL connection in autocommit mode.
    Safe for COPY / bulk insert operations.
    Applies session-level tuning suitable for high-speed ingestion.
    """
    last_exc: Exception | None = None

    for attempt in range(1, _DB_RETRIES + 1):
        try:
            conn = psycopg.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port,
                sslmode="disable",
                connect_timeout=connect_timeout,
                application_name=application_name,
                autocommit=True,  # enable immediately on connect
            )

            # Session-level tuning for bulk insert
            with conn.cursor() as cur:
                cur.execute("SET synchronous_commit = OFF;")
                cur.execute("SET work_mem = '128MB';")
                cur.execute("SET maintenance_work_mem = '1GB';")
                cur.execute("SET temp_buffers = '32MB';")

            return conn

        except Exception as exc:
            last_exc = exc
            logger.warning( f"PostgreSQL autocommit connection attempt {attempt}/{_DB_RETRIES} failed: {exc}" )
            if attempt < _DB_RETRIES:
                time.sleep(_DB_RETRY_DELAY)

    raise RuntimeError(
        "Could not establish PostgreSQL autocommit connection"
    ) from last_exc



def init_db(conn: Connection, drop_existing: bool = True) -> None:
    """
    Initialise database schema.
    If drop_existing=True, all existing tables are dropped first.
    Intended for clean re-ingestion runs.
    """
    logger.info("Initialising database schema")

    with conn.transaction():
        with conn.cursor() as cur:
            if drop_existing:
                logger.info("Dropping existing tables")
                cur.execute("""
                    -- DROP MATERIALIZED VIEW IF EXISTS document_search CASCADE;
                    -- DROP MATERIALIZED VIEW IF EXISTS pamphlet_tokens CASCADE;
                    DROP MATERIALIZED VIEW IF EXISTS pamphlet_corpus CASCADE;

                    DROP TABLE IF EXISTS tokens CASCADE;
                    DROP TABLE IF EXISTS documents CASCADE;

                    DROP SEQUENCE IF EXISTS vector_id_seq;
                """)

            logger.info("Creating tables")
            # Prototype assumption: doc_id is globally unique across loaded corpora (EEBO/ECCO).
            # Introducing a joint corpus/doc_id PK introduced too much work for consumers so
            # was rolled back and kept in git history.
            # Revisit if additional corpora introduce collisions.
            cur.execute("""
                /* Core document metadata */
                CREATE TABLE documents (
                    corpus TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    title TEXT,
                    author TEXT,
                    pub_year INTEGER,
                    publisher TEXT,
                    pub_place TEXT,
                    source_date_raw TEXT,
                    token_count INTEGER,
                    lang CHAR(3) NOT NULL DEFAULT 'eng',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP GENERATED ALWAYS AS (CURRENT_TIMESTAMP) STORED, -- from v12
                    PRIMARY KEY (doc_id)
                );

                CREATE SEQUENCE vector_id_seq;
                CREATE TABLE tokens (
                    corpus TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    token_idx INTEGER NOT NULL,
                    token TEXT NOT NULL,
                    raw_token text,
                    canonical TEXT,
                    vector_id BIGINT UNIQUE DEFAULT nextval('vector_id_seq'),
                    PRIMARY KEY ( doc_id, token_idx),
                    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                );
            """)

    logger.info("Database schema initiated")



def drop_token_indexes(conn: Connection) -> None:
    logger.info("Dropping token indexes")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany("""
            DROP INDEX IF EXISTS idx_tokens_token            ;
            DROP INDEX IF EXISTS idx_doc_id                  ;
            DROP INDEX IF EXISTS idx_tokens_doc              ;
            DROP INDEX IF EXISTS idx_tokens_token_lower      ;
            DROP INDEX IF EXISTS idx_documents_lang          ;
            DROP INDEX IF EXISTS idx_documents_filepath      ;
            DROP INDEX IF EXISTS idx_tokens_canonical        ;
            DROP INDEX IF EXISTS idx_documents_filter        ;
            DROP INDEX IF EXISTS idx_tokens_corpus_doc_idx   ;
            DROP INDEX IF EXISTS idx_tokens_doc_token_idx    ;
            DROP INDEX IF EXISTS idx_tokens_doc_token        ;
            """)
    logger.info("Token indexes dropped")


def create_token_indexes(conn: Connection) -> None:
    logger.info("Creating basic token indexes")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_token            ON tokens(token);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_doc_id                  ON documents(doc_id);") #
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_doc              ON tokens(doc_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_token_lower      ON tokens (lower(token));")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_lang          ON documents(lang);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_filepath      ON documents(filepath);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_canonical        ON tokens(canonical);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_filter        ON documents(lang, pub_year, token_count);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_corpus_doc_idx   ON tokens(corpus, doc_id, token_idx);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_doc_token_idx    ON tokens(doc_id, token_idx);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tokens_doc_token        ON tokens(doc_id, token);")

    logger.info("Basic token indexes created")


def create_views(conn: Connection) -> None:
    logger.info("Creating view")

    earliest = config.CORPUS_MIN_YEAR
    latest   = config.CORPUS_MAX_YEAR

    # Create non-concurrent indexes and materialized views inside a transaction
    with conn.transaction():
        with conn.cursor() as cur:
            # Materialized view for pamphlet_corpus
            logger.info("Creating materialised view pamphlet_corpus")

            # Just in case I previously messed-up - TODO check and tidy.
            cur.execute("DROP VIEW IF EXISTS pamphlet_corpus CASCADE;")

            if config.FILTER_DOCUMENT_SIZE:
                size_filter = f"""
                    AND token_count BETWEEN {config.MIN_TOKENS_IN_DOC} AND {config.MAX_TOKENS_IN_DOC}
                """
            else:
                size_filter = ""

            logger.info(f"CREATE VIEW pamphlet_corpus with dates {earliest} and {latest} and size filter of '{size_filter}'")
            cur.execute(f"""
                CREATE OR REPLACE VIEW pamphlet_corpus AS
                SELECT *
                FROM documents
                WHERE pub_year >= {earliest}
                AND pub_year <= {latest}
                {size_filter}
                AND (lang = 'eng' OR lang IS NULL);
            """)

            # Index for fast joins (non-concurrent)
            # cur.execute("CREATE INDEX IF NOT EXISTS idx_pamphlet_corpus_docid ON pamphlet_corpus(corpus, doc_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pamphlet_corpus_docid ON pamphlet_corpus(doc_id);")

            # Materialized view for pamphlet_tokens
            logger.info("Creating materialised view pamphlet_tokens")
            # cur.execute("DROP MATERIALIZED VIEW IF EXISTS pamphlet_tokens CASCADE;")

            # TODO Drop vector_id, no longer used
            cur.execute("""
                CREATE OR REPLACE VIEW pamphlet_tokens AS
                SELECT
                    (t.doc_id || '_' || t.token_idx) AS token_occurrence_id,
                    t.corpus,
                    t.doc_id,
                    t.token_idx,
                    d.pub_year,
                    -- t.vector_id,
                    -- t.canonical,
                    t.token
                FROM tokens t
                JOIN pamphlet_corpus d ON t.doc_id = d.doc_id AND t.corpus = d.corpus;
            """)


def drop_tokens_fk(conn: Connection) -> None:
    logger.info("Dropping tokens.doc_id foreign key")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE IF EXISTS tokens DROP CONSTRAINT IF EXISTS tokens_doc_id_fkey;")
    logger.info("tokens.doc_id foreign key dropped")


def create_tokens_fk(conn: Connection) -> None:
    logger.info("NOT creating tokens.doc_id foreign key as v slow and immutable data  makes it irrelevant")


def refresh_views(conn: Connection) -> None:
    logger.info("Refreshing materialized views")

    with conn.transaction():
        with conn.cursor() as cur:
            logger.info(f"Refreshing pamphlet_corpus")
            cur.execute("REFRESH MATERIALIZED VIEW pamphlet_corpus")
            # logger.info(f"Refreshing pamphlet_tokens")
            # cur.execute("REFRESH MATERIALIZED VIEW pamphlet_tokens")
    logger.info("All views refreshed and committed")


def create_tier2_schema(conn: Connection) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS tier2;

                CREATE TABLE IF NOT EXISTS tier2.concepts (
                    concept TEXT PRIMARY KEY,
                    n_events INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tier2.concept_seeds (
                    concept   TEXT NOT NULL
                        REFERENCES tier2.concepts(concept),
                    from_year INTEGER NOT NULL,
                    to_year   INTEGER NOT NULL,
                    event_id  BIGINT NOT NULL
                        REFERENCES events(event_id),
                    role      TEXT NOT NULL,
                    PRIMARY KEY (
                        concept,
                        from_year,
                        to_year,
                        event_id
                    )
                );

                CREATE TABLE IF NOT EXISTS tier2.retrieval_runs (
                    run_id               BIGINT PRIMARY KEY,
                    concept              TEXT NOT NULL
                        REFERENCES tier2.concepts(concept),
                    from_year            INTEGER NOT NULL,
                    to_year              INTEGER NOT NULL,
                    seed_population      TEXT NOT NULL,
                    neighbour_population TEXT NOT NULL,
                    scales               TEXT NOT NULL,
                    top_n                INTEGER NOT NULL,
                    rrf_k                INTEGER NOT NULL,
                    oversample           INTEGER NOT NULL,
                    model                TEXT,
                    created_at           TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tier2.neighbour_edges (
                    edge_id            BIGSERIAL PRIMARY KEY,
                    run_id             BIGINT NOT NULL
                        REFERENCES tier2.retrieval_runs(run_id),
                    seed_event_id      BIGINT NOT NULL
                        REFERENCES events(event_id),
                    neighbour_event_id BIGINT NOT NULL
                        REFERENCES events(event_id),
                    depth              INTEGER NOT NULL,
                    via_event_id       BIGINT
                        REFERENCES events(event_id),
                    rank               INTEGER NOT NULL,
                    score              DOUBLE PRECISION,
                    score_local        DOUBLE PRECISION,
                    score_medium       DOUBLE PRECISION,
                    score_broad        DOUBLE PRECISION
                );

                CREATE TABLE IF NOT EXISTS tier2.event_field (
                    concept  TEXT NOT NULL
                        REFERENCES tier2.concepts(concept),
                    event_id BIGINT NOT NULL
                        REFERENCES events(event_id),
                    role TEXT NOT NULL
                        CHECK (role IN ('seed', 'neighbour', 'both')),
                    PRIMARY KEY (concept, event_id)
                );

                CREATE TABLE IF NOT EXISTS tier2.concept_aggregate (
                    id            BIGSERIAL PRIMARY KEY,
                    concept       TEXT NOT NULL
                        REFERENCES tier2.concepts(concept),
                    kind          TEXT NOT NULL,
                    rank          INTEGER NOT NULL,
                    value         TEXT,
                    window_doc_id TEXT,
                    window_id     INTEGER,
                    count         INTEGER NOT NULL,
                    score         DOUBLE PRECISION NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    tier2_neighbour_edges_unique_via
                ON tier2.neighbour_edges (
                    run_id,
                    seed_event_id,
                    neighbour_event_id,
                    depth,
                    via_event_id
                )
                WHERE via_event_id IS NOT NULL;

                CREATE UNIQUE INDEX IF NOT EXISTS
                    tier2_neighbour_edges_unique_no_via
                ON tier2.neighbour_edges (
                    run_id,
                    seed_event_id,
                    neighbour_event_id,
                    depth
                )
                WHERE via_event_id IS NULL;

                CREATE INDEX IF NOT EXISTS tier2_concept_seeds_concept_idx ON tier2.concept_seeds (concept);
                CREATE INDEX IF NOT EXISTS tier2_retrieval_runs_concept_idx ON tier2.retrieval_runs (concept);
                CREATE INDEX IF NOT EXISTS tier2_neighbour_edges_run_idx ON tier2.neighbour_edges (run_id);
                CREATE INDEX IF NOT EXISTS tier2_neighbour_edges_seed_idx ON tier2.neighbour_edges (seed_event_id);
                CREATE INDEX IF NOT EXISTS tier2_neighbour_edges_neighbour_idx ON tier2.neighbour_edges (neighbour_event_id);
                CREATE INDEX IF NOT EXISTS tier2_event_field_concept_idx ON tier2.event_field (concept);
                CREATE INDEX IF NOT EXISTS tier2_event_field_event_idx ON tier2.event_field (event_id);
                CREATE INDEX IF NOT EXISTS tier2_concept_aggregate_concept_idx ON tier2.concept_aggregate (concept);
            """)


def create_tier3_schema(conn: Connection) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS tier3;

                CREATE TABLE IF NOT EXISTS tier3.event_geometry (
                    concept       TEXT NOT NULL
                        REFERENCES tier2.concepts(concept),
                    event_id      BIGINT NOT NULL
                        REFERENCES events(event_id),
                    nx            DOUBLE PRECISION NOT NULL,
                    ny            DOUBLE PRECISION NOT NULL,
                    gnx           DOUBLE PRECISION,
                    gny           DOUBLE PRECISION,
                    cluster_id    INTEGER NOT NULL,
                    cluster_label TEXT,
                    PRIMARY KEY (concept, event_id)
                );

                CREATE TABLE IF NOT EXISTS tier3.concept_cluster_info (
                    concept          TEXT NOT NULL
                        REFERENCES tier2.concepts(concept),
                    cluster_id       INTEGER NOT NULL,
                    cluster_label    TEXT,
                    centroid_nx      DOUBLE PRECISION,
                    centroid_ny      DOUBLE PRECISION,
                    centroid_gnx     DOUBLE PRECISION,
                    centroid_gny     DOUBLE PRECISION,
                    centroid_vector  BYTEA NOT NULL,
                    point_count      INTEGER NOT NULL,
                    description      TEXT,
                    PRIMARY KEY (concept, cluster_id)
                );

                CREATE INDEX IF NOT EXISTS tier3_event_geometry_concept_idx ON tier3.event_geometry (concept);
                CREATE INDEX IF NOT EXISTS tier3_event_geometry_cluster_idx ON tier3.event_geometry (concept, cluster_id);
                CREATE INDEX IF NOT EXISTS tier3_cluster_info_concept_idx ON tier3.concept_cluster_info (concept);
            """)


def delete_document(
    conn: Connection,
    doc_id: str,
    *,
    corpus: str | None = None,
) -> bool:
    """
    Delete one document and its tokens.

    The tokens foreign key may not exist in normal corpus operation,
    so tokens are deleted explicitly before the document.

    Returns True if a document was deleted, otherwise False.

    doc_id is globally unique in the current schema. The optional
    corpus argument is therefore a safety check.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            if corpus is not None:
                cur.execute(
                    """
                    SELECT 1
                    FROM documents
                    WHERE doc_id = %s
                      AND corpus = %s
                    """,
                    (doc_id, corpus),
                )
            else:
                cur.execute(
                    """
                    SELECT 1
                    FROM documents
                    WHERE doc_id = %s
                    """,
                    (doc_id,),
                )

            if cur.fetchone() is None:
                return False

            cur.execute(
                """
                DELETE FROM tokens
                WHERE doc_id = %s
                """,
                (doc_id,),
            )

            cur.execute(
                """
                DELETE FROM documents
                WHERE doc_id = %s
                """,
                (doc_id,),
            )

    logger.info(
        "Deleted document %s%s",
        doc_id,
        f" (corpus={corpus})" if corpus else "",
    )

    return True


def get_document_filepath(
    conn: Connection,
    doc_id: str,
    *,
    corpus: str | None = None,
) -> str | None:
    with conn.cursor() as cur:
        if corpus is not None:
            cur.execute(
                """
                SELECT filepath
                FROM documents
                WHERE doc_id = %s
                  AND corpus = %s
                """,
                (doc_id, corpus),
            )
        else:
            cur.execute(
                """
                SELECT filepath
                FROM documents
                WHERE doc_id = %s
                """,
                (doc_id,),
            )

        row = cur.fetchone()

    return row[0] if row else None

