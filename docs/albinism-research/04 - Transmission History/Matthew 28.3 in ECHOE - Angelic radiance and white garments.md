---
type: transmission-record
passage: "Matthew 28:2-5, with an intertextual citation of Revelation 6:11"
language: "Latin and Old English"
status: working transcription checked against ECHOE XML
tags:
  - research/transmission
  - topic/whiteness
  - topic/radiance
  - topic/white-garments
  - language/old-english
related_notes:
  - "[[Old English whiteness and human appearance]]"
  - "[[Semantic query log]]"
  - "[[Daniel 7 - Ancient of Days]]"
  - "[[Revelation 1 - Son of Man vision]]"
---

# Matthew 28:3 in ECHOE: angelic radiance and white garments

## Why this passage matters

ECHOE search surfaced an Old English homiletic rendering of Matthew 28:3. It is useful background for the project because the snow-white garment is explicitly interpreted as a sign of the blessed, then connected to Revelation's white robes. The passage documents scriptural and homiletic symbolism in England; it is not evidence for ordinary human complexion or white hair.

## Text and witnesses

The Latin quotation in both records reads:

> *Erat autem aspectus eius sicut fulgur, et vestimenta eius sicut nix.*

"His appearance was like lightning, and his garments were like snow." The biblical source is identified in the TEI with `source="mt28.3"`.

A readable rendering of the Old English transcription is:

> *Þæs engles ansyn wæs swa beorht ⁊ swa egeslic swa ligetum, ⁊ his hrægl wæron swa hwite swa snaw.*

"The angel's appearance was as bright and awe-inspiring as lightning, and his garments were as white as snow."

Here *ansyn* is appearance/face, *beorht* is bright, *egeslic* is awe-inspiring or fearsome, and *hrægl* means garment. The whiteness belongs expressly to the angel's clothing. ECHOE encodes manuscript letterforms and expansions with TEI and MUFI entities; the readable line above is not a diplomatic reproduction of every glyph.

Two ECHOE records preserve this passage:

| ECHOE item | ECHOE file | Witness date in `origDate` | Indexed midpoint | Text locus |
|---|---|---:|---:|---|
| `48.26` | `G:\corpus\echoe_main\048.26.xml` | 1013-1037 | 1025 | `s48.26.17-18` |
| `309.26` | `G:\corpus\echoe_main\309.26.xml` | 996-1020 | 1008 | `s309.26.17-18` |

These are manuscript-witness dates, not dates of composition. The same homily and reading recur in both records; compare the XML variants before counting them as independent textual formulations.

## Homiletic interpretation and intertext

The homily explains that the angel does not need bodily clothing because angels are spiritual. It then says that the angel's bright garment signifies how beautiful and wondrous the blessed souls will be after leaving mortal life. The interpretation therefore makes the garment's brightness an eschatological sign.

The explanation is followed by a Latin quotation identified as Revelation 6:11:

> *Datae sunt illis stolae albae, et dictum est illis ut requiescerent.*

"White robes were given to them, and they were told to rest." This links Matthew's angelic garment to the white robes given to the dead/elect in Revelation. The sequence is a particularly useful example of how a biblical clothing image can become an image of the blessed after death.

## Interpretative limits

- Matthew 28:3 describes an angel's appearance and garments; it does not describe a human's skin, hair, or complexion.
- The homilist explicitly reads the bright clothing symbolically, as a sign of the blessed souls' future state.
- The Revelation 6:11 citation strengthens the eschatological reading, but it does not show that every white garment in Old English texts carries that meaning.
- The two ECHOE records are manuscript witnesses of the same homily; witness dates should not be mistaken for the date the homily was composed.

## Semantic search seeds

Use each as a separate vector prompt, then verify results against the text:

- `an angel whose appearance is like lightning and whose garments are white as snow`
- `a bright garment signifies the beauty of blessed souls after death`
- `white robes are given to souls who are told to rest`
- `the elect clothed in white after death`
- `white garments as a sign of holy souls`
- `radiant angels and the white robes of the blessed`
- `heavenly beings clothed in white robes`
- `lightning-like appearance and snow-white clothing`

## Sources and local records

- ECHOE XML, *Schaefer III*, item 48.26: `G:\corpus\echoe_main\048.26.xml`, especially `s48.26.17-19` and `s48.26.106-111`.
- ECHOE XML, *Schaefer III*, item 309.26: `G:\corpus\echoe_main\309.26.xml`, especially `s309.26.17-19` and the repeated later passage around `s309.26.101-109`.
- [ECHOE repository](https://github.com/ECHOEProject/echoe)
- [[Semantic query log]]