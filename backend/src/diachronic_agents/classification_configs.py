from diachronic_agents.llm.passage_classifier import ClassificationConfig

ALBINISM_CONFIG = ClassificationConfig(
    search_term="white hair",
    target_description=(
        "Descriptions of unusually white or pale human hair, "
        "human complexion, or animal bodily coverings. "
        "Human hair and complexion are primary categories. "
        "Animal hair, fur, feathers and flaxen hair are retained "
        "as distinct secondary categories."
    ),
    include=[
        "Human hair, including scalp hair and facial hair",
        "Human complexion, including unusually pale complexion",
        "Animal hair, fur, coats and manes",
        "Feathers and plumage as animal bodily coverings",
        "Mythological, symbolic and allegorical animals",
        "Descriptions of hair or bodily-covering colour even when "
        "the creature is fictional",
        "Flaxen or similarly pale hair, recorded separately from white hair",
    ],
    exclude=[
        "White garments, clothing and robes",
        "White fabric, wool as a material, silk and textiles",
        "White paint, stone, buildings and other objects",
        "White light and radiance without a bodily description",
    ],
    categories={
        "human_hair": "Scalp or facial hair of human beings (primary).",
        "complexion": "Human skin colour or pallor; separate from hair (primary).",
        "animal_fur": "Hair, fur, coats or manes of animals (secondary).",
        "feathers": "Feathers and plumage; distinct from hair (secondary).",
        "flaxen_hair": "Flaxen or similarly pale hair; do not equate with white (secondary).",
    },
    rules=[
        "Clothing, textiles, materials, objects and light are not bodily features.",
    ],
)


LIBERTY_CONFIG = ClassificationConfig(
    search_term="liberty",
    target_description=(
        "Passages in which liberty or freedom is invoked, defined, "
        "claimed, denied or contested as a political, legal or moral concept."
    ),
    include=[
        "Liberty or freedom claimed for an individual, group or nation",
        "Arguments that liberty is threatened, lost or being defended",
        "Definitions or theories of what liberty consists of",
        "Liberty of enslaved people, including emancipation and manumission",
    ],
    exclude=[
        "Liberty as a personal, place or institutional name",
        "Casual 'at liberty to' meaning merely 'permitted'",
        "Allegorical statues or coins bearing the word, without discussion",
    ],
    categories={
        "emancipation": "Liberty of enslaved people; abolition, manumission, freedom from bondage.",
        "constitutional": "Liberty as a constitutional or legal right or guarantee.",
        "civil_liberties": "Speech, press, habeas corpus, conscription, arbitrary arrest.",
        "national": "Liberty of a nation, section or government; independence, self-government.",
        "moral_religious": "Liberty of conscience, religion or the soul.",
    },
    rules=[
        "Record how the passage uses the term, not whether the usage is sincere.",
    ],
)
