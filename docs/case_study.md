# Semantic Passage Search Across Historical Texts

From a Postgres database of document metadata and tokens extracted from TEI XML and plain text, 
uses Manjavacas and Fonteyn's historical BERT model [MacBERTh](https://aclanthology.org/2021.nlp4dh-1.4/) 
and Google Colab to create embeddings that are stored in and searched through Lance via a Python FastAPI/SolidJS 
application.

A sample dataset, and indeed Lance indexes, are available upon request.

## Usage Synopsis

To add a doc to the corpus:

    python src/tier0/tier0_0_text2db.py --file enoch_charles_1917.xml --corpus misc
    python src/passage_search_pipeline/ingest/passages_1_export_full.py --force-doc-id enoch_charles_1917
    # Run on Colab passages_2_0_colab_embed_passages.py
    python src/passage_search_pipeline/ingest/passages_3_passages_parquet_to_lance.py

Run the search servers:

    start-servers.sh

## Motivation

> We all declare for liberty but in using the same word we do not all mean the same thing
> -- Abraham Lincoln, Address at the Sanitary Fair in Baltimore, Maryland, on April 18, 1864

**How can historical references be found to the people - like yours truly - who modern clinicians refer to as albinos, when the term was not coined until at earliest the 1650s?**

## A research demonstration using contextual embeddings

### Research problem

How can researchers find historically significant passages when the language used to describe a subject changes over time?

A search for a modern term can be effective when that term was also used in the period being studied. It is much less effective when the terminology is recent, when earlier writers described the same phenomena in different language, or when a concept appears indirectly through metaphor, religious imagery or narrative.

This project explores whether contextual language models can help researchers discover such material. The demonstration uses representations of extreme bodily paleness in literary and religious texts, with the modern term *albino* providing a starting point for investigating earlier descriptions. Disclosure: the author has Oculocutaneous albinism.

The objective is not to establish that historical figures described as white, pale or extraordinary had albinism. It is to develop a research instrument that can retrieve potentially relevant passages beyond the limits of exact-word search, while preserving enough textual and bibliographic information for researchers to assess the evidence.

### Worked reverse diachronic example: from a modern medical text to medieval literature

**Step 1 — Begin with modern terminology.**

![From an initial search for the term 'albino', find the top result, a 1972 medical text, and select 'find similar'](./README/albino_1970-2000AD.png)

I searched passages dated 1900–2000 using the query `albino` and the `l8` representation (the eighth layer of the MacBERTh model). The system returned 30 results. I selected the highest-ranked passage, from A. J. Psaila’s *Albinism – A Case Report* (1972).

![Adjust the date range to find historical matches, 0 AD to 1400, and scroll to view references from (translated) Welsh and Judeo-Christian mythology:](./README/albino_0-1400AD.png)

![More results](./README/albino_0-1400AD_b.png)

The selected passage discusses forms of albinism, including a description of partial albinism in which hair is yellow or light brown. This provides a modern medical context from which to explore historical descriptions, although the selected passage is only one fragment of a larger text.

**Step 2 — Use the passage as a semantic query.**

Rather than searching for the word *albino* again, I selected the system’s “find similar” function. This uses the stored vector representation of the selected passage to retrieve other passages with similar representations.

I restricted the search to the period 1000–1500. The system returned 21 results from the available corpus and date range.

Among the highest-ranked results were passages from two very different literary and religious sources.

**The English Apocalypse (approximately 1350 in the dataset)**

One result describes the Son of Man:

> and the heed of hym and his heeris weren whyte as whyte wolle and as snow, and the iyen of hym as flawme of fier

This is a Middle English rendering of the vision in Revelation 1:14, in which the figure's head and hair are described as white like wool and snow. The passage combines extraordinary paleness with a striking description of the eyes.

For a study of the cultural representation of extreme bodily paleness, this is a promising lead. It provides an opportunity to investigate how pal functions in a theological vision and how such descriptions relate to broader traditions of divine appearance, majesty and otherness.

It is not evidence that the figure has albinism in a modern clinical sense. The value of the retrieval is that it identifies a historically situated representation worth investigating, not that it supplies a retrospective diagnosis.

**The Mabinogi: *Pwyll, Prince of Dyfed* (dated approximately 1100 in the dataset)**

Other highly ranked passages describe hunting dogs of dazzling palidity, including dogs with red ears. Further results from the *Mabinogi* describe a shining white boar and a woman riding a pale white horse.

These passages are not equivalent to the description in *The English Apocalypse*: most concern animals or a narrative figure rather than a medical description of human appearance. Nevertheless, they suggest a possible comparative line of enquiry into the literary use of conspicuous paleness, including its association with unusual or significant beings.

The results also illustrate a limitation. Semantic similarity does not guarantee that passages address the same subject. Some results will be relevant to the research question; others will be useful only as contextual comparisons, and some will be false positives.

### What the demonstration establishes

The example illustrates a practical form of semantic discovery:

1. Start with a passage that expresses a modern concept.
1. Retrieve semantically similar passages from an earlier period, without requiring the same terminology.
1. Inspect the retrieved texts in their bibliographic and historical context.
1. Evaluate their relevance and develop further questions from the evidence.

The researcher remains responsible for interpretation. The system helps locate material that might otherwise be missed; it does not determine historical meaning or establish conceptual continuity by itself.

The distinction between retrieval and interpretation is central. A passage about divine paleness, an unusually coloured animal and a clinical description of albinism may share features in the model's representation without expressing the same concept, or they may uncover a shared conceptual field as yet unrecognised by a researcher. The relationship is a question for historical and literary analysis.

### Technical approach

The demonstration combines established language-modelling and vector-search components in a working research application.

- **Corpus and metadata:** Texts are represented in a PostgreSQL database, with document metadata and token-level information extracted from TEI XML and plain-text sources.
- **Passage construction:** Text is divided into overlapping windows of 40 words, with a 20-word hop. Token offsets and document metadata are retained so retrieved passages can be traced back to their sources.
- **Embeddings:** Passages are encoded using MacBERTh, a BERT model developed for historical language. The current demonstration uses 768-dimensional representations derived from the model's eighth hidden layer.
- **Indexing and retrieval:** Passage vectors are stored in Lance, supporting vector search alongside chronological filtering and retrieval by an existing passage vector.
- **Application:** A Python retrieval layer is exposed through FastAPI and a command-line interface, with a SolidJS search interface for interactive exploration.

The embedding workflow runs separately in Google Colab, with per-document checkpoints and validation to support resumable processing. The resulting vectors can then be incorporated into the local search index.

The implementation is designed to retain source identity, dates and passage offsets throughout retrieval. These are not incidental details: they allow computational results to be inspected as documentary evidence rather than treated as an opaque list of similarity scores.

### Discovery through unexpected semantic connections

The semantic proximity observed by the model does not establish historical equivalence, and as with all texts, results must be evaluated in their textual and historical contexts. Yet unexpected matches are not merely false positives. A search initiated with a modern clinical term can retrieve medieval theological descriptions, mythological narratives and literary representations of extraordinary paleness. These may not describe the same phenomenon, but their proximity can expose connections between bodies of material that are conventionally studied separately.

The value of the system lies partly in this capacity to generate research leads beyond the vocabulary of the original query. Rather than simply locating known instances of a concept, it can help researchers discover unfamiliar representations, formulate new comparative questions and follow connections across disciplinary boundaries. The resulting hypotheses still require close reading and historical verification; the computational method assists discovery rather than determining interpretation.

### Limitations and next steps

This is a working proof of concept, not a validated claim that semantic retrieval consistently outperforms conventional search. The example demonstrates that the system can retrieve plausible historical leads from a modern starting passage. It does not yet measure recall, precision or the proportion of results that researchers judge useful.

Several issues require further investigation:

- **Retrieval design:** Different passage lengths, embedding representations and ranking strategies produce materially different results. This project's parent project build ensemble embeddings across a larger corpus with a consequentially larger footprint and cost.
- **Evaluation:** The method needs systematic comparison with keyword-based retrieval and assessment of results by a human researcher.

The next stage would be to construct a curated set of relevant and irrelevant passages, compare retrieval methods, and examine how results vary across periods and genres. The broader research objective is to use computational diachronic semantic search to support rather than replace close reading and historically grounded interpretation.

To that end, the system can be extended to add further models trained on further periods and languages to support a much wider corpus, so that for example the above query could discover John of Patmos' original language, or Snorri's depiction of Baldr.

### Summary

This project demonstrates an end-to-end research tool for exploring historical texts through contextual semantic search. Its contribution at this stage is a working, inspectable retrieval workflow and a concrete example of how a modern query can lead to potentially relevant material in medieval literature.

The wider methodological question is how computational retrieval can help researchers find evidence when terminology changes, concepts are expressed indirectly, or relevant passages do not share obvious keywords. Answering that question requires both technical evaluation and substantive interpretation of the retrieved texts.

This repo is extracted from the full project  at [github.com/leegee/mutatis-mutandis](https://github.com/leegee/mutatis-mutandis).

