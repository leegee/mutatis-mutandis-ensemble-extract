
"""
The system produced some silly pub_years:

    eebo=# \copy (SELECT doc_id, title, author, pub_year FROM documents WHERE pub_year < 1400 OR pub_year > 1900 ORDER BY pub_year) TO 'odd_publication_years.csv' WITH (FORMAT csv, HEADER true);
"""

#!/usr/bin/env python3

from lib.corpus_db import get_connection


# These are records where the stored year is demonstrably malformed.
# Keep the old value in the mapping so a later rerun cannot silently
# overwrite a value that has already been corrected or changed manually.
CORRECTIONS = {
    "A10719": (1069, 1609),
    "A80836": (1160, 1660),
    "A74937": (1455, 1655),
    "A61113": (1461, 1641),
    "A87267": (1465, 1645),
    "A89734": (1468, 1648),
    "A85922": (1469, 1649),
    "A94343": (1469, 1649),
    "A18164": (1939, 1639),
    "A57293": (1941, 1641),
    "A69527": (1941, 1641),
    "A82650": (1942, 1642),
    "A92540": (1949, 1649),
    "A85134": (1958, 1659),
    "A42800": (1967, 1697),
    "B01663": (1983, 1683),
    "A49616": (1983, 1683),
}


def main() -> None:
    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                for doc_id, (expected_old_year, new_year) in CORRECTIONS.items():
                    cur.execute(
                        """
                        SELECT pub_year
                        FROM documents
                        WHERE doc_id = %s
                        """,
                        (doc_id,),
                    )

                    row = cur.fetchone()

                    if row is None:
                        print(f"{doc_id}: NOT FOUND")
                        continue

                    current_year = row[0]

                    if current_year != expected_old_year:
                        print(
                            f"{doc_id}: SKIPPED "
                            f"(expected {expected_old_year}, found {current_year})"
                        )
                        continue

                    cur.execute(
                        """
                        UPDATE documents
                        SET pub_year = %s
                        WHERE doc_id = %s
                        """,
                        (new_year, doc_id),
                    )

                    print(
                        f"{doc_id}: {current_year} -> {new_year}"
                    )

        print(f"\nCorrected {len(CORRECTIONS)} candidate records.")


if __name__ == "__main__":
    main()
