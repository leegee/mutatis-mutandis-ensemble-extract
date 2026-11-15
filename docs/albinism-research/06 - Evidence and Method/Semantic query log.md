---
type: research-method
status: active log
tags:
  - research/method
  - research/semantic-search
  - research/corpus
  - topic/whiteness
  - topic/human-appearance
related_notes:
  - "[[Evidence protocol]]"
  - "[[Old English whiteness and human appearance]]"
  - "[[Middle English whiteness and human appearance]]"
  - "[[Daniel 7 - Ancient of Days]]"
  - "[[Revelation 1 - Son of Man vision]]"
---

# Semantic query log

## Purpose

Record semantic searches for white-haired, pale, ruddy, bright, and otherwise visually striking human figures. Queries are exploratory prompts to a vector model: a close-ranked result is a lead to inspect, not evidence that the text contains the queried phrase or meaning.

## Record for each run

Capture the date, interface or command, embedding model, corpus and year filters, query text exactly as submitted, search scale and representation settings, result count, and useful ranked hits. For each hit, verify the underlying text, witness/edition, date type, and source path before adding it to a research claim. Keep failed metadata lookups visible in the log.

MacBERTh is expected to be less dependable for material substantially earlier than its training period (approximately the mid-fifteenth century). Treat early English semantic results as discovery aids and check them with spelling-aware lexical searches and concordances. Do not merge semantic ranking with exact-text evidence.

## Seed query bank

Run these as separate queries first, then try paraphrases and combinations. Preserve spelling exactly so results can be compared between runs.

### Scriptural figures and intertexts

- `son of man`
- `Ancient of Days`
- `ancient as days` (retain this wording as a separate vector prompt; compare with the conventional phrase above)
- `son of man`
- `the Son of Man with white hair`
- `the Ancient of Days with hair like wool`
- `a heavenly man whose hair is white`

### Hair and snow / wool comparisons

- `white as wool`
- `hair white as wool`
- `white as snow`
- `hair white as snow`
- `his head and hair were white as wool and snow`

### Human complexion and bodily colour

- `white body and ruddy appearance`
- `white skin, red cheeks`
- `white as milk and ruddy as coral`
- `a fair body with red or rosy or ruddy colour`
- `white hair and a sun-darkened body`
- `a pale person with bright hair`

### Radiance and symbolic appearance

- `a luminous human figure with shining white hair`
- `a beautiful person whose body shines white`
- `white-haired saint or holy man`
- `a person whose whiteness signals holiness`
- `white-haired supernatural being`

These prompts are starting points, not a fixed vocabulary. Add plausible paraphrases, genre-specific descriptions, biblical wording, and spelling variants; log each query as submitted. Search translated biblical phrases separately from independent narrative descriptions.

## Recorded run

### R-001 - `hair as white as snow`

- **Interface:** search GUI; semantic/broad search, based on the returned distance-ranked results.
- **Run date / embedding model:** not captured in the conversation; record on the next repeat.
- **Filters:** 1200-1600; broad scale; representation `last`; limit 10.
- **Useful leads:**
  - *Merlin*, Herry Lovelich (CME, c. 1450): the returned passage describes the woman's flesh as white as snow and then red as drops of blood in snow. This is a strong human-appearance lead; verify the passage and lineation in the CME item before citing.
  - Wycliffite Later Version, Apocalypse 1 (misc, c. 1390): the Son of Man's hair is rendered white as wool and snow. This is a scriptural/theological figure and a useful transmission lead, not an ordinary human-complexion example.
  - *The Faerie Queene* (1596) appeared in the ranked response with null title/source path/text. The user confirmed that this record remains in Lance but had been removed from PostgreSQL and the source corpus as a presumed duplicate. Do not cite the blank result; restore/re-ingest and verify provenance before using it.
- **Assessment:** the run surfaced one promising human description and one close biblical-transmission result, alongside a corpus metadata problem. It did not establish a frequency or a general English convention.

## Pending runs

- [ ] Run the scriptural figure seeds (`son of man`, `Ancient of Days`, `ancient as days`) separately, with the same corpus and year filters; compare biblical translations, commentaries, and independent descriptions.
- [ ] Run `white as wool`, `hair white as wool`, `white as snow`, and `hair white as snow` separately; inspect exact phrase hits and semantic neighbors as distinct evidence types.
- [ ] Search paraphrases for white/ruddy bodies and white hair with darkened skin, checking Old and Middle English spelling variants in lexical searches.
- [ ] Repeat key queries in the CLI and GUI where possible; record model, corpus scope, and settings so differences can be explained.
- [ ] Reconcile results with null or stale metadata against PostgreSQL, Lance, and the source corpus before citation.

## Interpretation safeguards

- Separate literal complexion or hair from garments, sacred light, moral whiteness, illness, miracle, and non-human bodies.
- Distinguish source-language wording, translation, editorial normalization, and modern paraphrase.
- Record composition date separately from manuscript witness date and edition/publication date.
- A semantic neighbor is not proof of intertextuality, lexical equivalence, or historical influence.