from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.workflows.investigator import run_investigation


def main() -> None:
    retriever = PassageRetriever()

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
        retriever=retriever,
        max_tool_calls=8,
    )

    record = result["investigation_record"]

    print("\n=== INVESTIGATION ===\n")
    print(result["messages"][-1].content)

    print("\n=== TOOL CALLS ===\n")

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

        print(
            f"{call['tool_name']}: "
            f"{call['status']} "
            f"({count} passage(s))"
        )
        print(f"  Arguments: {call['arguments']}")

    print("\n=== EVIDENCE ===\n")

    for item in record["evidence"]:
        observation = item["observations"][0]

        print(
            f"{item['passage_id']} | "
            f"{observation.get('pub_year')} | "
            f"{observation.get('title')}"
        )
        print(f"  Found by: {len(item['discovered_by'])} operation(s)")

    print("\n=== WARNINGS ===\n")

    for warning in record["warnings"]:
        print(warning)

    print(
        f"\nTotal tool calls: {record['tool_call_count']}"
        f"\nDistinct passages: {len(record['evidence'])}"
    )


if __name__ == "__main__":
    main()

    