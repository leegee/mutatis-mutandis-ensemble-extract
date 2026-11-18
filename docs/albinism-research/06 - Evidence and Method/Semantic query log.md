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

### Garments, radiance, and the blessed

- `an angel whose appearance is like lightning and whose garments are white as snow`
- `a bright garment signifies the beauty of blessed souls after death`
- `white robes are given to souls who are told to rest`
- `the elect clothed in white after death`
- `white garments as a sign of holy souls`
- `radiant angels and the white robes of the blessed`
- `Erat autem aspectus eius sicut fulgur et vestimenta eius sicut nix`
- `Datae sunt illis stolae albae et dictum est illis ut requiescerent`
- `þæs engles ansyn wæs swa beorht and his hrægl wæron swa hwite swa snaw`

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

### R-002 - Global semantic seed sweep

- **Date:** 2026-11-15.
- **Interface / model:** backend CLI; MacBERTh; representation `l8`; passage scale `broad`; exact vector search (`--exact`, bypasses the approximate vector index).
- **Filters:** 0-1650. Queries were `son of man` and `ancient as days` (limit 6), then `white as wool`, `white as snow`, and `white body ruddy as coral` (limit 3).
- **Useful leads:**
  - `son of man` returned EEBO item `A41020`, *A fountaine of teares* (1646). A devotional prayer calls God the “Ancient of dayes” and joins Daniel/Revelation wording: garment white as snow, hair like pure wool. This is a strong early modern reception lead, not a new biblical witness.
  - `white as snow` returned CME item `CME00134`, Lovelich's *Merlin* (c. 1450): the woman's flesh is compared with snow and described as red as drops of blood in snow. This remains a strong human-appearance candidate; verify lineation and the edition before citation. Two returned windows overlap the same passage and are not separate occurrences.
  - The same query returned EEBO `A78070`, *The little Bible of the man* (1649), interpreting the Song of Songs hair image (“thy hair is like a flock of goats, as white as snow”) as old age and righteousness. This is allegorical reception, not a literal portrait.
  - `ancient as days` ranked a personification of Old Christmas (`A75608`, 1646), described as hoary-headed and white as snow. Interesting personification, but not evidence for an ordinary person's appearance.
  - `white body ruddy as coral` mostly retrieved red-and-white flower descriptions and medical discussion of urine: useful false positives, not human complexion evidence.
- **Assessment:** results are strongest for biblical reception and a Middle English literary complexion description. Semantic rankings need confirmation by exact text and context; these searches do not measure prevalence.

### R-003 - ECHOE-only semantic search

- **Date:** 2026-11-15.
- **Interface / model:** MacBERTh, `l8`, `broad`, exact vector search, with a Lance corpus filter for `echoe` and witness years 800-1250. ECHOE currently has 1,160 `l8` rows in the 950-1199 year buckets.
- **Queries:** `white as wool`; `white as snow`; `a holy man with white hair`; `a white body and fair appearance`; `the Son of Man with hair white as wool`; `the Ancient of Days with white hair`; `a man with white hair`; `the white hair of an elderly saint`; `hair became white with age`; `a white-haired monk`; `a man's body white as snow`.
- **Verified lead:** ECHOE's *Schaefer III* appears in two manuscript items: `048.26` (witness date 1013-1037; indexed midpoint 1025) and `309.26` (996-1020; midpoint 1008). The XML marks the passage `quote source="mt28.3"`. Its Latin reads *Erat autem aspectus eius sicut fulgur et vestimenta eius sicut nix*; the Old English describes the angel's appearance as bright and fearsome as lightning and his garments as white as snow. The homily then explains the bright garment as signifying the beauty of the blessed after mortal life. This is a useful English witness to Matthew 28:3 and to sacred whiteness as clothing/radiance, not white hair or ordinary complexion.
- **Other close ranks:** *Verba seniorum* and *Vercelli XXI* passages about fire, light, and heavenly joy ranked repeatedly, but the inspected excerpts did not describe white hair or human complexion. Treat them as semantic neighbors/false positives unless a fuller context proves otherwise.
- **Assessment:** no direct ECHOE example of a white-haired human or a white/ruddy complexion surfaced in these prompts. This is not a negative finding for the whole corpus. The clear result so far is scriptural transmission of angelic radiance and white clothing; comparing the two *Schaefer III* witnesses may be worthwhile.
### R-004 - Garment and afterlife symbolism in ECHOE

- **Date:** 2026-11-15.
- **Interface / model:** corpus-filtered Lance search; MacBERTh, `l8`, `broad`, exact vector search; ECHOE only; witness-year filter 800-1250.
- **Queries:** `an angel whose appearance is like lightning and whose garments are white as snow`; `a bright garment signifies the beauty of blessed souls after death`; `white robes are given to souls who are told to rest`; `the elect clothed in white after death`; `white garments as a sign of holy souls`; `radiant angels and the white robes of the blessed`.
- **Results:** the Schaefer III Matthew 28:3 passage continued to appear in the top ranks, including ECHOE items 48.26 and 309.26. The afterlife/bright-garment prompt retrieved it within the top three, but other prompts frequently ranked *Verba seniorum* (182.2a, fire and spiritual light) and *Vercelli XXI* (394.26, eternal heavenly light) above it. Those are broad religious-light neighbors, not white-clothing or human-appearance examples in the inspected snippets.
- **Assessment:** the context-based prompts help retrieve the verified ECHOE passage, but they also expose a cluster of thematic false positives. Keep the ECHOE source loci (`mt28.3`, `apc6.11`) and exact Latin/Old English wording alongside any semantic rank. Follow up with source-language prompts and exact-text/concordance checks; the run produced no new direct white-hair or complexion example.
## Pending runs

- [x] Run `son of man` and `ancient as days`, plus the ECHOE prompt `the Ancient of Days with white hair`; see R-002 and R-003. [ ] Still run the exact global prompt `Ancient of Days` and compare biblical translations, commentaries, and independent descriptions.
- [x] Run `white as wool` and `white as snow`; see R-002 and the ECHOE-filtered variants in R-003. Still run hair-specific phrase variants and verify candidates lexically.
- [ ] Search paraphrases for white/ruddy bodies and white hair with darkened skin, checking Old and Middle English spelling variants in lexical searches.
- [x] Repeat key queries in the CLI and run ECHOE-filtered Lance searches; see R-002 and R-003. Compare with a GUI run when convenient.
- [ ] Reconcile results with null or stale metadata against PostgreSQL, Lance, and the source corpus before citation.

## Interpretation safeguards

- Separate literal complexion or hair from garments, sacred light, moral whiteness, illness, miracle, and non-human bodies.
- Distinguish source-language wording, translation, editorial normalization, and modern paraphrase.
- Record composition date separately from manuscript witness date and edition/publication date.
- A semantic neighbor is not proof of intertextuality, lexical equivalence, or historical influence.