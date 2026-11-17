---
type: comparative-survey
language: Old English
period: "late seventh to eleventh century (composition and witness dates vary)"
status: working note
tags:
  - research/transmission
  - research/corpus
  - topic/colour-language
  - topic/whiteness
  - topic/human-appearance
  - language/old-english
related_notes:
  - "[[Middle English whiteness and human appearance]]"
  - "[[Texts to add to the Old English corpus]]"
  - "[[Open questions]]"
  - "[[Transmission diagrams - Scriptural sources to Bede]]"
---

# Old English whiteness and human appearance

## Scope and present state

This is a working summary of the Old English evidence assembled so far, with a note on the next corpus addition. It distinguishes bodily or hair colour from sacred radiance, moral symbolism, illness, and supernatural description. The local search is useful for finding candidates, but it is not yet a complete survey of the Old English canon.

The local YCOE collection contains 100 prose texts or samples. The available CLASP snapshot is partial and weighted toward selected poetry. A literal search for forms of *hwit* found relevant material in both, but spelling variants and other colour terms still need systematic review. MacBERTh semantic search is also expected to be much less reliable before its training period, so early examples need corpus concordance and edition checks.

## Current high-value evidence

| Example                            | What it contributes                                 | Qualification                                    |
| ---------------------------------- | --------------------------------------------------- | ------------------------------------------------ |
| Old English Bede, Anglian boys     | White bodies, fair faces, excellent hair            | Vernacular transmission of Bede                  |
| Old English Bede, two **Heawalds** | **Direct contrast between _blaca_ and _hwita**_     | **Exact colour distinction needs investigation** |
| Ælfric, Benedict                   | White hair                                          | Hagiographic context                             |
| Ælfric, Mary of Egypt              | White hair against sun-darkened skin                | Particularly interesting bodily contrast         |
| Ælfric, Cecilia                    | Blood, whitening body, rose and lily                | Martyrdom imagery                                |
| _Christ A, B, C_                   | Several descriptions of Christ and visionary beings | Needs contextual classification                  |

### Bede, V.11, the two Heawalds

Old English OCR: https://archive.org/stream/oldenglishversio02bede/oldenglishversio02bede_djvu.txt

Book V, Chapter XI One is called *se blaca Heawald*, the other *se hwita Heawald*, with the distinction explained by the appearance of their hair. After being martyred their bodies cast into the river are illuminated by a shaft of light.

This is a direct hair-colour contrast; whether *hwita* means white, grey, or another light shade remains open.

Thomas Miller’s _The Old English Version of Bede’s Ecclesiastical History of the English People_ (Early English Text Society, 1890–98):

> Wæs ðis tosceaden hweðre, þætte for hiora missenlice feaxes hiwe oðer wæs cueden se **blaca** Heawald, oðer se **hwita** Heawald.

Literally: "This was distinguished, however, in that, because of the different appearance/colour of their hair, one was called the Black Hewald, the other the White Hewald." The Latin underlying it is _unus Niger Heuuald, alter Albus Heuuald diceretur_. 

The Old English wording is quoted in the _Oxford English Dictionary_ under **black**, with its source identified as Bede, _Ecclesiastical History_ (Old English translation, Tanner manuscript), V.xi, p. 414. The edition’s textual apparatus also records manuscript variants.

> Þam rǣse þæs forðgeotendan strēames geborene wǣron þurh eall fēowertig mīla oð ða stōwe, þe hiora cūðe menn 7 hiora gefēran on wǣron. Swylce ēac se mǣsta **scīma heofonlīces lēohtes** ūfan æghwylcre nihte ofer ða stōwe scān, þær þæt gelamp þæt ða līchoman cōmon; 7 þæt ēac swylce ða hǣðnan gesāwon 7 beheoldon, þe hīe slōgon.

> Āh ða ōðer þāra martīra in neahtlīcere gesihðe ǣteowde sumum hiora gefēran, þæs nama wæs Tilmon. Wæs þæt mǣre wer 7 for worulde ēac swylce æþelre gebyrde; wæs hē ǣrest from cyninges þegn, 7 þā wæs eft munuc geworden. Wæs hē him secgende, þæt hē meahte hiora līchoman in ðǣre stōwe gemǣtan, þær hē gesāwe þæt lēoht of heofonum on eorðan scīnan.


## To Investigate

- **Old English Bede, Gregory's Anglian boys:** the Old English translation describes the boys as having *hwites lichoman* (white bodies), fair faces, and noble or excellent hair. This is a vernacular transmission of Bede's account, not independent evidence for a pre-Christian English appearance ideal.
- **Aelfric's saints' lives:** Benedict is described with white hair. In the Life of Mary of Egypt, white hair is set beside a body darkened by the sun. These are valuable descriptions of human hair and skin, but they occur in hagiographic and ascetic narratives.
- **Aelfric's Life of Cecilia:** red blood and a whitening body are compared with a rose and a lily. The colours are explicit, but this is a martyrdom image rather than a direct gloss on the Hebrew red-and-white passages.
- **Biblical and miraculous bodies:** Moses' hand becomes white as snow in the Old English Exodus; the survivors in the Life of Eustace have bodies whiter than snow. These are bodily colour references, but their contexts are affliction and miracle, not ordinary complexion.
- **Poetic *aelfscyne*:** Alaric Hall's contextual reading emphasizes elf-like beauty. Brightness may remain a possible resonance, but the word alone does not establish luminous bodies, pale skin, or a general phenotype.

These cases should be read alongside the distinct Christian images in which whiteness belongs to clothing, transformed sin, sanctity, or visionary beings. See the relevant primary-text and transmission notes before treating any example as evidence of ordinary appearance.

## ECHOE: promising Old English corpus addition

The Electronic Corpus of Anonymous Homilies in Old English (ECHOE) is a promising addition for religious prose and manuscript transmission. Its public repository includes TEI XML with manuscript-level encoding and text alternatives: [ECHOE GitHub repository](https://github.com/ECHOEProject/echoe). It can add anonymous homilies and related prose beyond the current local YCOE and CLASP coverage. Compare work identities and witnesses against the local corpora before counting results as new evidence.

The local input folder is `G:\corpus\echoe_main`. The ingester now has a dedicated ECHOE path in `backend/src/mutatis_mutandis/ingest/ingest.py`:

- It preserves Unicode letters, combining marks, symbols, and MUFI private-use characters rather than converting the transcription to ASCII.
- It reads the manuscript `origDate`, including dates nested inside `msFrag`, rather than treating the digital edition's publication statement as the historical date.
- Where several manuscript fragments are described, it uses their combined date span and stores the midpoint in `pub_year`; `source_date_raw` retains the span. This is a search-indexing convention, not a claim that the work was composed in that midpoint year.
- It renders one textual form from parallel TEI alternatives, preferring expansions or regularized readings where available. Other parallel readings are not currently indexed as separate records, so searches will not cover every encoded variant.

Two inspected headers illustrate the date handling:

| ECHOE item | Title | Manuscript date in header | Search `pub_year` |
|---|---|---:|---:|
| `018.40` | Luiselli Fadda VII / *Sermo Augustini* | 1163-1187 | 1175 |
| `73.1` | *Invention of the Cross* (Napier) | 1038-1062, repeated for two fragments | 1050 |

These are manuscript-witness dates. The headers do not establish the works' original composition dates. The handler has been updated but the corpus has not yet been ingested, so text extraction, token boundaries, and database metadata still need a one-file review.

## Middle English comparison

The Middle English survey is underway in [[Middle English whiteness and human appearance]]. Current leads include a milk-white face in *Libeaus Desconus*, Chaucer's red *rode* beside golden hair and a white garment, and the ambiguous *white syde* in *Floris and Blauncheflour*. These examples differ in referent and certainty; they do not by themselves demonstrate continuity from Old English or a direct response to Hebrew.

The local CME collection is available for semantic searching. MEC searches and edition checks have produced candidates, but the MEC is selective and raw hit counts include duplicates, devotional metaphors, textiles, editorial matter, and non-human referents. METS TEI editions and PCMEP are possible additions for targeted Middle English religious prose and poetry.

## Working conclusions and next steps

1. There are clear Old English references to white hair and bodily whiteness, but they occur in different genres and narrative settings. They should not be collapsed into one stable symbolic meaning.
2. Bede is a useful starting point for tracing biblical and Christian interpretation into England. The Old English Bede and Aelfric provide later vernacular transmission evidence; they do not prove that the same symbolism was already established in pre-Christian England.
3. YCOE plus the available CLASP snapshot is not enough to claim complete Old English coverage. ECHOE is the strongest immediate prose addition; fuller poetic coverage remains a separate need.
4. Before broad ECHOE ingestion, inspect one record end to end, confirm that the selected reading and dates are suitable for the research questions, then compare its witness and work IDs with existing corpora.
5. Keep composition, textual redaction, manuscript witness, digital edition, and search-index date distinct in notes and search interpretation.

## References

- [ECHOE project repository](https://github.com/ECHOEProject/echoe)
- [Official YCOE text inventory](https://penn-historical-corpora.uni-mannheim.de/ycoe/info/YcoeTextFile.htm)
- [York-Helsinki Parsed Corpus of Old English Poetry](https://www-users.york.ac.uk/~lang18/pcorpus.html)
- [Alaric Hall, *The Meanings of Elf and Elves in Medieval England*](https://www.alarichall.org.uk/ahphdful.pdf)
- [Middle English Compendium](https://quod.lib.umich.edu/m/mec/)
- [METS Editions GitHub organization and edition repositories](https://github.com/mets-editions)
- [Parsed Corpus of Middle English Poetry access](https://www.pcmep.net/download.php)