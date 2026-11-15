---
type: transmission-record
tags:
  - research/transmission
  - research/diagram
  - reception/ancient-and-medieval
related_notes:
  - "[[Transmission chronology]]"
  - "[[Bede's Expositio Apocalypseos]]"
  - "[[Gildas on Lamentations]]"
  - "[[Daniel 7 - Ancient of Days]]"
  - "[[Revelation 1 - Son of Man vision]]"
  - "[[Song of Songs 5 - Bright and ruddy]]"
---

# Transmission diagrams — scriptural sources to Bede

These diagrams map the transmission and reception evidence currently recorded in this vault. They distinguish a text’s literary source, surviving textual witnesses, quotations, and later interpretation. A manuscript witness is not automatically an ancestor of another witness.

**Arrow key:** solid arrows mark a direct quotation, explicit use, or attested textual presence; dashed arrows mark a proposed literary or exegetical connection whose exact route is not established; no arrow means the vault currently records no transmission link.

## 1. Daniel 7:9 → Revelation 1:14 → Bede on Revelation

Daniel 7:9’s white clothing and wool-like hair are closely echoed in Revelation 1:14. The vault records Jerome’s explicit comparison of Daniel’s vision with John’s Apocalypse. The diagram therefore marks the Daniel-to-Revelation relationship as an intertextual echo, not as a demonstrated manuscript chain.

```mermaid
flowchart LR
    D[Daniel 7:9<br/>Aramaic vision<br/>snow-white clothing; hair like wool]
    R[Revelation 1:14–15<br/>Greek apocalypse<br/>white head and hair; wool / snow]
    G[Greek Revelation witnesses<br/>P98, 3rd c.; Sinaiticus, 4th c.;<br/>Alexandrinus and Ephraemi, 5th c.]
    C[Cyprian, Testimonia II.26<br/>c. 248–250<br/>early Latin literary quotation]
    F[Fleury Palimpsest, VL 55<br/>5th c.<br/>physical Latin witness; text provisional]
    P[Primasius<br/>6th c. Latin commentary]
    B[Bede, Explanatio Apocalypseos<br/>c. 703<br/>white head and hair read as divine antiquity / immortality;<br/>wool and snow applied to sheep and the whitened elect]
    M[Matthew 25<br/>sheep at Christ's right hand<br/>Bede's stated association for wool]

    D -. "close imagery; literary relationship, not a manuscript stemma" .-> R
    R --> G
    R --> C
    R --> F
    R --> B
    M --> B
    P -. "commentary background; specific borrowing for Bede's colour gloss not established" .-> B

    classDef text fill:#edf4ff,stroke:#345,stroke-width:1px;
    classDef witness fill:#f2f2f2,stroke:#555,stroke-width:1px;
    classDef reception fill:#fff2d8,stroke:#754,stroke-width:1px;
    class D,R text;
    class G,C,F witness;
    class P,B,M reception;
```

### Reading this diagram

- Daniel 7 and Revelation 1 share the white-head/hair and wool/snow imagery, and the vault records Jerome drawing the comparison. The diagram does not claim that a particular Daniel manuscript was copied into Revelation.
- P98, the Greek codices, Cyprian’s quotation, and Fleury are separate evidence points. Cyprian is a dated literary quotation, not a surviving copy of Revelation; Fleury is a surviving Latin manuscript, not a demonstrated copy of Cyprian.
- Bede’s commentary directly interprets Revelation 1:14. His explanation of wool invokes the sheep at the right hand; his snow imagery evokes the multitude of the elect made white. The vault records a Primasius connection for Bede’s exposition of the feet, but does not establish that Bede borrowed his white-hair interpretation from Primasius.

## 2. Song of Songs 5:10 → Bede on the Song

This is the clearest direct route from one of the project’s red-and-white passages to Bede: Bede quotes the Latin verse and interprets the colour pair allegorically.

```mermaid
flowchart LR
    H[Song of Songs 5:10<br/>Hebrew: צַח וְאָדֹם<br/>bright / white and ruddy]
    L[Latin biblical text<br/>Dilectus meus candidus et rubicundus<br/>white and ruddy]
    B[Bede, Expositio in Cantica Canticorum<br/>on Song 5:10]
    V[candidus → Christ's virginity / sinlessness]
    P[rubicundus → Christ's Passion and blood]
    I[Isaiah 63:2 and Revelation 1:5<br/>cited in Bede's Passion reading]

    H -. "Latin translation route not traced here" .-> L --> B
    B --> V
    B --> P
    I --> P

    classDef source fill:#edf4ff,stroke:#345,stroke-width:1px;
    classDef reception fill:#fff2d8,stroke:#754,stroke-width:1px;
    class H,L source;
    class B,V,P,I reception;
```

The dashed edge marks the untraced Latin translation history; the solid edge records Bede’s quotation of the Latin wording and his own commentary. The final nodes are reception, not alternate lexical translations: Bede reads *candidus* and *rubicundus* Christologically, with the red linked to the Passion rather than to a literal complexion.

## 3. Lamentations 4:7 → Gildas; no recorded continuation to Bede

The vault records Gildas quoting Lamentations 4:7 in the sixth century and applying the lament to the Church. It does not record Bede commenting on this verse or a link from Gildas’s use to Bede.

```mermaid
flowchart LR
    H[Lamentations 4:7<br/>Hebrew poem<br/>snow, milk, ruddy / red, precious material]
    L[Latin biblical wording<br/>exact versional route not established here]
    G[Gildas, De excidio<br/>c. 540<br/>candidiores ... nive;<br/>rubicundiores ...; sapphiro ...]
    E[Gildas applies the lament to the Church]
    B[Bede<br/>No direct treatment of Lam 4:7<br/>recorded in this vault]

    H -. "translation route not yet traced" .-> L
    L --> G
    G --> E

    classDef source fill:#edf4ff,stroke:#345,stroke-width:1px;
    classDef reception fill:#fff2d8,stroke:#754,stroke-width:1px;
    classDef gap fill:#fff,stroke:#777,stroke-dasharray: 4 4;
    class H source;
    class G,E reception;
    class L,B gap;
```

Gildas is therefore a reception endpoint for Lamentations in the evidence assembled so far, not a proven link in Bede’s reading of Song of Songs or Revelation. The Lamentations and Song passages can be compared as Hebrew red-and-white imagery, but the vault does not establish literary dependence between them.

## Limits and next evidence to collect

- Collate the Latin biblical lemma in Bede against the Latin witnesses actually available to him; a shared wording does not identify the specific exemplar.
- Compare Bede’s Revelation exposition line-by-line with Primasius and other Latin commentators before extending a source arrow to the white-hair gloss.
- Verify the Greek and Latin textual forms and manuscript dates from the editions listed in the linked witness notes.
- Do not extend Gildas’s Lamentations quotation to Bede without evidence of Bede’s use of Gildas or the verse.

## Sources in this vault

- [[Daniel 7 - Ancient of Days]]
- [[Revelation 1 - Son of Man vision]]
- [[Cyprian - Revelation]]
- [[Fleury Palimpsest - VL 55 - Revelation]]
- [[Bede's Expositio Apocalypseos]]
- [[Song of Songs 5 - Bright and ruddy]]
- [[Lamentations 4 - Nazirites like snow]]
- [[Gildas on Lamentations]]
- [[Transmission chronology]]
