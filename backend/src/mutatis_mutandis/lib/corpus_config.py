# lib/corpus_config.py

import os
import sys
from pathlib import Path

from mutatis_mutandis.lib.corpus_albinism import get_lance_indexes_dir, build_export_query, CORPUS_MIN_YEAR, CORPUS_MAX_YEAR, CONCEPT_SETS, PHRASE_SETS, FILTER_DOCUMENT_SIZE, MIN_TOKENS_IN_DOC, MAX_TOKENS_IN_DOC

LANCE_MODEL_NAME = "macberth"
LANCE_BUCKET_SIZE = 50

# PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Share the output of the main project
PROJECT_ROOT = Path("D:/") / "src" / "mutatis-mutandis"

CORPUS_ROOT_DIR = Path("G:/") / "corpus"

CORPUS_INPUT_DIRS = {
    "misc": CORPUS_ROOT_DIR / "misc",
    "eebo": CORPUS_ROOT_DIR / "eebo_all",
    "ecco": CORPUS_ROOT_DIR / "ecco_all",
    "cme":  CORPUS_ROOT_DIR / "cme_all",
}
ECCO_HEADER_DIR = Path( CORPUS_ROOT_DIR / "corpus/ecco_all/ecco/headers" )
CLMET_CORPUS_INPUT_DIR = CORPUS_ROOT_DIR / "clmet" / "corpus" / "txt" / "plain"

COLAB_MODE = (
    os.environ.get("COLAB_MODE", "").lower() in ("1", "true", "yes")
    or "google.colab" in sys.modules
)

OUT_DIR = Path("/content/drive/MyDrive/macberth_output") if COLAB_MODE else PROJECT_ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MAPPED_GOOGLE_DRIVE = Path("E:/") / "My Drive" / "passage-pipeline"
MAPPED_GOOGLE_DRIVE.mkdir(parents=True, exist_ok=True)

TMP_DIR = OUT_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

_INDEXES_DIR = OUT_DIR / "indexes"
_INDEXES_DIR.mkdir(parents=True, exist_ok=True)

LANCE_INDEXES_DIR = get_lance_indexes_dir(_INDEXES_DIR)
LANCE_INDEXES_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = OUT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PASSAGE_SCALES = ("local", "medium", "broad")

