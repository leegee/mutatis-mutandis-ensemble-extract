from pathlib import Path

from mutatis_mutandis.lib.cannonical_rules import CanonicalRule, CanonicalRules

CORPUS_MIN_YEAR = 1600
CORPUS_MAX_YEAR = 1650
FILTER_DOCUMENT_SIZE = False
MIN_TOKENS_IN_DOC = 200
MAX_TOKENS_IN_DOC = 400_000

def get_lance_indexes_dir(indexes_dir: str | Path) -> Path:
    return Path(indexes_dir) / "lance_pamphlets"

# "bone fei", "bonne foy", "bonne foy", "bone fei", "bonne foi", "good faith", "bonne foi", "bona fidēs"

CONCEPT_SETS: CanonicalRules = {
    "LIBERTY": {
        "forms": {
            "liberty",
            "freedom",
        },
        "expected": {
            "rights",
            "right",
            "property",
            "privilege",
            "immunity",
            "freeborn",
            "free-born",
            "franchise",
        },
        "false_positives": set(),
    },

    "LEGITIMACY": {
        "forms": {
            "lawful",
            "right",
            "authority",
        },
        "expected": {
            "consent",
            "trust",
            "commission",
            "constitution",
            "fundamental",
            "custom",
            "law",
            "obedience",
            "jurisdiction",
            "title",
        },
        "false_positives": set(),
    },

    "TYRANNY": {
        "forms": {
            "tyranny",
            "oppression",
        },
        "expected": {
            "arbitrary",
            "bondage",
            "yoke",
            "usurpation",
            "usurper",
            "encroachment",
            "enslave",
            "slavery",
            "tyrannical",
            "tyrant",
        },
        "false_positives": set(),
    },

    "PEOPLE": {
        "forms": {
            "people",
            "commons",
            "multitude",
        },
        "expected": {
            "public",
            "nation",
            "community",
            "inhabitants",
            "subjects",
            "voice",
            "commonwealth",
            "populous",
            "general",
        },
        "false_positives": set(),
    },

    "PREROGATIVE": {
        "forms": {
            "prerogative",
        },
        "expected": {
            "sovereignty",
            "sovereign",
            "royal",
            "kingly",
            "majesty",
            "privilege",
            "dominion",
            "power",
            "authority",
            "arbitrary",
        },
        "false_positives": set(),
    },
}

CIVIL_WAR_CONCEPT_SETS: CanonicalRules = {
    "PREROGATIVE": {
        "forms": {
            "prerogative", # "prerogatiue", "prerogatives", "prerogatiues",
        },
        "false_positives": set(),
    },
    "LAW": {
        "forms": {
            "law", # "laws", "lawe", "lawes",
        },
        "false_positives": {
            "clawes", "claw", "flaw", "lawne",
            "thlaw", # welsh
            "laz", "layt", "layen",
            },
    },
    "LIBERTY": {
        "forms": {
            "liberty",
            # "libe_ty", "liberry", "libertie", "libertye", "liberte", "liliberty", "libertv", "libertty", "lyliberty", "libertyes", "libert", "liberties", "libery", "libertly", "fulliberty", "lilibertyis", "thliberties", "libertyby", "iberty", "libertle", "libertles", "libertys", "iiberty", "iberties", "libety", "liberts", "libertynow", "libertees", "libetty", "libertee", "libertes", "lyberty", "lberty", "libertis", "leberty", "liberrie", "lliberty"

            # Keep for now then remove after re-ingestion which will normalise:
            # "aliberty", "liberti", "berty",
            # Need to pre-ingest fix "lib erty" etc
            # "generalliberty",
            # "understandingliberty",
        },
        "false_positives": {
            "libertine", "libertin", "libertins", "libertinage", "libertinism",
            "libertind", "libertyin", "liberality",  "libertinisme", "liberallity",
            "libertism", "libertines", "liberta",
            # "liberal", "liberall",
            "libels",
            "libertate", "libertates", "liberabit", "libero","deliberates", "deliberated",
            "liberto","liberabo","liberall","liberalytie","liberaui","liberally","liberates","liberalitie",
            "libera", "deliberate", "liberando", "libya", "liberi", "liberior"

        },
    },


    "DIVINE": {
        "forms": {
            "divine",
            # "god",  "heaven", "heavens", "eternal", "grace", "providence", "sacred", "holy", "lord", "almighty", "creator", "eternity"
        },
        "false_positives": {
             "good", "goods", "gold", "glad" # "godly",
        }
    },
    "TEMPORAL": {
        "forms": {
            "temporal", # "state", "civil", "political",  "commonwealth", "kingdom", "government", "authority", "prince", "realm"
        },
        "false_positives": set(), # { "statue", "station", "temple" }
    },


    # Rough political/legal
    "KING": {
        "forms": {"king", }, # "kings", "kinges",  # "monarch", "sovereign"
        "false_positives": {"kin", "kine", "sink", "sing"}
    },
    "PARLIAMENT": {
        "forms": {"parliament", }, # "parliment", "parliaments"
        "false_positives": { "parlour"} # "parliamentary",
    },
    "OBEDIENCE": {
        "forms": {"obedience"}, # , "obedient", "obedienc", "obey"
        "false_positives": {"obscene", "obeyed", "obed"}
    },
    "PEOPLE": {
        "forms": {"people"}, #  "peoples", "peple",   "populace", "subjects"
        "false_positives": {"peep", "peeps", "pepla"}
    },
    "COMMONWEALTH": {
        "forms": {"commonwealth", "common-wealth", "common weal"},
        "false_positives": {"common", "wealth"}
    },

    # Rough theology
    "CHURCH": {
        "forms": {"church"}, # , "churches", "clergy", "ecclesia", "congregation"
        "false_positives": set(), # {"churchyard", "churchman"}
    },
    "RELIGION": {
        "forms": {"religion"}, # , "religions", "faith", "doctrine", "creed"
        "false_positives": set(),  # {"religious", "religionist"}
    },

    # Neutral baselines
    "MAN": {
        "forms": {"man"},
        "false_positives": set()  # {"woman"},
    },

    "HOUSE": {
        "forms": {"house"},
        "false_positives": {},
    },

    "PROPERTY": {
        "forms": {
            "property", #  "propertie", "propriety"
        },
        "false_positives": set() # { "properly" }
    },

    # May 2026
    "REVOLUTION": {
        "forms": {
            "revolution" # , "revolucion", "revolutio", "revolutions", "revolutión", "revolucon", "revolucionary", "revolucioners", "revolutioners",
            # "rebellion", "insurrection"
        },
        "false_positives": set(), # { "astronomical", "planetary", "celestial", "orb", "circle" }
    },
    "INTEREST": {
        "forms": {
            "interest", # "interesse", "intrest", "intrests", "interests", "interestes", "interessed",
        },
        "false_positives": set(),
        # { "usury", "usance", "money", "profit", "compound" }
    },
    "FANATIC": {
        "forms": {
            "fanatic", #  "fanatick", "fanatique", # "fanaticism", "fanaticisme", "phanatic", "phanatique"
        },
        "false_positives": set(),
    },
    "ANABAPTIST": {
        "forms": {"anabaptist"},
        "false_positives": set(),
    },
    "ENTHUSIASM": {
        "forms": {
            "enthusiasm",
            # "enthusiasme", "enthousiasm", "enthusiast", "enthusiasts", "enthusiastick", "enthusiastical", "enthusiasms", "enthusiastical"
        },
        "false_positives": set(),
    },

    "HEBREW REPUBLIC": {
        "forms": {
            "hebrew", "jewish", "mosaic",
            "Hebraism",
            "commonwealth of israel", "israelite commonwealth", "israelitish republic",
            "polity of the Jews"
        },
    }
}
