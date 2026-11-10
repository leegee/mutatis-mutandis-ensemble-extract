import json

from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.workflows.investigator import run_investigation

# from diachronic_agents.llm.gemini import create_llm
from diachronic_agents.llm.groq import create_llm

from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_config import OUT_DIR


logger    = get_logger("INVESTIGATOR")
retriever = PassageRetriever()
agent_llm = create_llm("openai/gpt-oss-20b")
plain_llm = create_llm("qwen/qwen3.8-27b", max_tokens=900,)


result = run_investigation(
    question=(
        "How is extraordinary whiteness of hair or complexion "
        "represented in English writing?"
    ),
    llm                   = agent_llm,
    plain_llm             = plain_llm,
    retriever             = retriever,
    start_year            = 1500,
    end_year              = 1699,
    period_size           = 50,
    max_tool_calls        = 32,
    max_period_tool_calls = 8,
)

logger.info("===================== DONE =====================")

logger.info(
    json.dumps(
        result["investigation_record"],
        indent=2,
        ensure_ascii=False,
    )
)

with open(OUT_DIR / 'run_investigation.json', 'w', encoding='utf-8',  ensure_ascii=False, default=str) as file:
    json.dump(result, file, indent=4)
