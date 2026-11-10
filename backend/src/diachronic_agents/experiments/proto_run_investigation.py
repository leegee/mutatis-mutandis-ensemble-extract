from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.workflows.investigator import run_investigation

# from diachronic_agents.llm.gemini import create_llm
from diachronic_agents.llm.groq import create_llm

from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger("INVESTIGATOR")

def main() -> None:
    retriever = PassageRetriever()

    llm = llm = create_llm()

    question = """
    Investigate how extraordinary whiteness of hair and complexion
    is represented in English writing from approximately 700 to 1914.

    Look for religious, supernatural, medical, and ordinary descriptions.
    Distinguish descriptions of bodily appearance from white clothing,
    objects, and other irrelevant uses of colour.

    Follow promising discoveries with further searches. Inspect passages
    before relying on them as evidence. Distinguish direct evidence from
    interpretation, and report uncertainty.
    """

    result = run_investigation(
        question,
        llm            = llm,
        retriever      = retriever,
        max_tool_calls = 16,
    )

    record = result["investigation_record"]

    logger.info("\n=== INVESTIGATION ===\n")
    logger.info(result["messages"][-1].content)

    logger.info("\n=== TOOL CALLS ===\n")

    for call in record["tool_calls"]:
        result_data = call["result"]
        count = (
            len(result_data.get("results", []))
            if isinstance(result_data, dict)
            and isinstance(result_data.get("results"), list)
            else 1 if isinstance(result_data, dict)
            and result_data.get("passage_id") is not None
            else 0
        )

        logger.info(
            f"{call['tool_name']}: "
            f"{call['status']} "
            f"({count} passage(s))"
        )
        logger.info(f"  Arguments: {call['arguments']}")

    logger.info("\n=== EVIDENCE ===\n")

    for item in record["evidence"]:
        observation = item["observations"][0]

        logger.info(
            f"{item['passage_id']} | "
            f"{observation.get('pub_year')} | "
            f"{observation.get('title')}"
        )
        logger.info(f"  Found by: {len(item['discovered_by'])} operation(s)")

    logger.info("\n=== WARNINGS ===\n")

    for warning in record["warnings"]:
        logger.info(warning)

    logger.info(
        f"\nTotal tool calls: {record['tool_call_count']}"
        f"\nDistinct passages: {len(record['evidence'])}"
    )


if __name__ == "__main__":
    main()

    