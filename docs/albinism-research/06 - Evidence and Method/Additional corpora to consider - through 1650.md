---
type: research-resource-list
period: "through 1650"
status: working checklist
tags:
  - research/corpus
  - research/semantic-search
  - topic/whiteness
  - topic/human-appearance
  - topic/hair
related_notes:
  - "[[Evidence protocol]]"
  - "[[Middle English whiteness and human appearance]]"
  - "[[Transmission chronology]]"
---
## Specific Texts to Examine
	
For Jewish tradition, see **Chagigah 14a**
# Additional corpora to consider — through 1650

## Current scope

At least the current phase, include only texts whose publication dates are no later than **1650**. Where a corpus spans a later period, filter its records by the publication date of the text or edition being ingested; do not use an older work’s composition date to pull a later edition into scope. Preserve composition and witness dates separately where available.

These are possible additions to the existing printed-book and medieval-text collections, chosen to add different genres or to provide a historical baseline. More texts may yield few direct white-hair descriptions; their value is also in supplying medical, social, and interpretive contexts.

The 1650 cutoff defines the principal English survey, not the ultimate chronological endpoint of the research. Material from 1650–1914 is reserved for comparative investigation against Thomas White's findings and is not intended to constitute an equally comprehensive corpus.

## Religious writing and poetry

The project should deliberately include ecclesiastical writing and poetry alongside prose and printed books. These genres were central to literate culture before the novel became a major vehicle for representing people. Sermons, homilies, biblical commentary, devotional works, liturgical writing, religious controversy, and verse can show how appearance was framed through scripture, doctrine, allegory, and devotional practice.

Religious writing can document the authority and presence of religious institutions in the textual culture of the period, but the number of surviving or digitized texts does not by itself measure ordinary people's belief or compliance. Keep normative teaching, devotional practice, literary representation, and evidence of readership/circulation distinct.

### Religious prose: first priority

The **Corpus of English Religious Prose (COERP)** is a direct fit for a focused religious-writing strand. Its present Early Modern English sample covers 1500-1700, about one million words in c. 250 files, with pragmatic annotation and a web interface offering search and download. For the current project, use only texts published through 1650. The corpus description page was last updated in 2014, so confirm that the interface and download route still work and check the permitted reuse terms.

EEBO already contains sermons, homilies, biblical commentary, devotional prose, and theological works. Before adding a separate COERP copy, compare its records with the local EEBO inventory and prefer distinct texts or keep clear source/version identifiers. A metadata-filtered religious subset of the existing EEBO store may be a useful first comparison.

- [COERP description, period and availability](https://varieng.helsinki.fi/CoRD/corpora/COERP/)

### Poetry: fill the identified gaps

- **Middle English poetry:** the **Parsed Corpus of Middle English Poetry (PCMEP)** contains 57 poems and about 235,000 words from c. 1150-1420. It offers a poetry-focused, annotated selection that complements CME, especially for comparing verse with prose around 1250-1350. Download access requires an account from the corpus compiler; its terms prohibit redistribution and reserve rights in both source editions and annotation. Obtain permission before ingesting it into a shared or redistributable store. [PCMEP overview](https://www.pcmep.net/) · [download and use conditions](https://www.pcmep.net/download.php)
- **Selected scholarly editions:** the **Middle English Texts Series (METS)** provides metadata-filtered texts by form and genre, including poetry, religious verse, biblical exegesis, and devotional writing. New editions have TEI-XML; the legacy backlist is still being encoded, so choose individual TEI-XML editions rather than assuming the whole series is uniformly TEI. Its XML is CC BY-NC-SA 4.0; check compatibility with the project's intended use and avoid duplicating CME texts without a reason. [METS text catalogue](https://metseditions.org/texts) · [METS Editions GitHub organization and edition repositories](https://github.com/mets-editions) · [copyright and licence](https://metseditions.org/copyright-citation). Some has now been added.
- **Early Modern poetry (1500-1650):** start with poetry already in EEBO/ECCO and classify it as a distinct genre/subset. Consider additional individually selected editions only when the current corpus lacks a text or witness; this avoids adding large duplicate runs of printed verse.

For Old and Middle English poetry, most texts fall before MacBERTh's approximate c. 1450 training horizon. Vector retrieval can still suggest leads, but use spelling-variant and lexical searches plus contextual reading to assess coverage; do not interpret few vector hits as absence.

### Search distinctions within these genres

Tag and review separately: scriptural quotation/exegesis; sermons and homilies; saints' lives; liturgical and devotional works; theological controversy; allegorical or biblical poetry; lyric and romance; and secular poetry. A white-haired divine figure in a commentary, an elderly person in a lyric, and white clothing in a devotional poem are different kinds of evidence.

## Correspondence and everyday description

The **Corpus of Early English Correspondence family (CEEC)** is the strongest next trial for personal and social descriptions. Across its versions, it covers about 1402–1800, with approximately 5.26 million words, 11,700 letters, and 1,180 writers. For the present cutoff, retain only eligible letters dated through 1650.

- The **CEECS sampler** covers 1418–1680 and contains about 450,000 words; it is a practical small pilot, filtered to 1650.
- The larger **PCEEC** covers 1410–1681 and has about 2.16 million words; it is a possible expansion if the sampler proves useful and the access terms permit ingestion.
- Other CEEC-family extensions cover later periods and should be excluded for this phase.

The corpus was designed for sociolinguistic research, with information about writers and audiences; private letters may provide more everyday references to people than printed literary texts. The CEEC project page describes the sampler as publicly available, while ICAME’s current delivery route states academic-use access through CLARINO/Corpuscle. Check the applicable version’s licence and download terms before redistributing or embedding the full text.

- [CEEC family overview and version sizes](https://varieng.helsinki.fi/CoRD/corpora/CEEC/)
- [ICAME access information](https://icame.info/icame-corpora/)

## Medical and bodily descriptions

The **Corpus of Early English Medical Writing (CEEM)** provides targeted medical context that general literary and print corpora may underrepresent.

- **Middle English Medical Texts (MEMT):** c. 1375–1500; about 500,000 words across 86 texts, including academic and surgical writing, remedies, and materia medica.
- **Early Modern English Medical Texts (EMEMT):** 1500–1700; about two million words and c. 230 texts, including general treatises, disease and treatment works, recipes, health guides, surgery/anatomy, and *Philosophical Transactions* samples. For this project phase, retain only texts published through 1650.

These are promising for historical descriptions of bodily conditions, age, hair, complexion, and albinism. They were distributed with books on CD-ROM and purpose-built presenter software; confirm library availability, licence, and permitted text reuse before attempting ingestion. The early medical corpora predate or straddle MacBERTh’s approximate training horizon, so use lexical searches and contextual reading alongside vector retrieval, especially for MEMT.

- [CEEM overview and corpus contents](https://varieng.helsinki.fi/series/volumes/14/taavitsainen_pahta/)
- [EMEMT publication and distribution details](https://benjamins.com/catalog/z.160)
- [MEMT description](https://benjamins.com/catalog/z.131)

Alternatively:

- [Málaga Late Middle English corpus (1350–1500)](https://hunter.uma.es/?utm_source=chatgpt.com)
    
- [Málaga Early Modern corpus (1500–1700)](https://modernmss.uma.es/?utm_source=chatgpt.com)
    
- [Manuscript corpus and downloads](https://modernmss.uma.es/thecorpus/?utm_source=chatgpt.com)
    
- [Online CQPweb search](https://modernmss.uma.es/cqpweb?utm_source=chatgpt.com)
    
- [CoRD overview and documentation](https://varieng.helsinki.fi/CoRD/corpora/SciProse/?utm_source=chatgpt.com)

## Historical baseline across periods

The **Helsinki Corpus of English Texts** is a structured, multi-genre sample of about 1.57 million words and 450 texts, spanning Old, Middle, and Early Modern English (c. 730–1710). It has a TEI XML edition. Restrict the current ingestion to texts published by 1650. Its sampling makes it useful as a diagnostic comparison corpus, not as a comprehensive source or a basis for absence claims.

Much of its earlier material predates MacBERTh’s approximate training range. For those records, lexical/concordance searches are likely to be more dependable than semantic retrieval. It will also overlap with local YCOE, CME, and other collections, so compare text identifiers before embedding to avoid duplicate passages.

- [Helsinki Corpus description, scope, and XML edition](https://varieng.helsinki.fi/CoRD/corpora/HelsinkiCorpus/)
- [ICAME/CLARINO access information](https://icame.info/icame-corpora/)

## Deferred beyond the current cutoff

- **Corpus of English Dialogues (CED), 1560–1760:** potentially useful for social rank, gender, and speech-like interaction, but only its 1560–1650 material fits the current scope. Consider later if correspondence and medical writing leave important genre gaps. The full corpus is about 1.18 million words across 177 text files. [CED description](https://varieng.helsinki.fi/CoRD/corpora/CED/)
- **Old Bailey Corpus, 1720–1913:** outside the current period and therefore not an addition for this phase. Reconsider only if the project expands into late modern English. [Corpus record and access link](https://registry.text-plus.org/doc/collection/52085cd3-4fbd-4ecb-a1cb-530fe778dc4d?lang=en)
- **CLMET:** its late-modern period is beyond the 1650 cutoff. The project’s code already defines a local CLMET input directory, so first check whether it is present in the passage store rather than acquiring another corpus. That existing location is configured in [`corpus_config.py`](D:/src/mutatis-mutandis-ensemble-extract/backend/src/mutatis_mutandis/lib/corpus_config.py).

## Suggested order

1. Pilot the through-1650 COERP material, comparing its religious texts against EEBO and separating prose, verse, and genre.
2. Complete the relevant gaps in the existing CLASP poetry snapshot; then test selected PCMEP or METS poems whose texts and rights are not already covered by CME.
3. Pilot the through-1650 subset of CEECS for personal descriptions and social commentary.
4. If licensing permits, test MEMT and the through-1650 portion of EMEMT for medical and bodily language.
5. Add the through-1650 Helsinki Corpus as a small, metadata-rich baseline, with duplicate checks against current corpora.
6. Keep the dialogue and Old Bailey corpora deferred unless the project scope or genre needs expand.

For every addition, record version, date basis, genre, coverage, identifiers, annotation, and licence. Keep publication date, composition date, and witness date distinct. Use direct spelling-variant searches to audit important vector-search findings.
