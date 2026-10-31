WHITENESS = {
    "white",
    "whiteness",
    "whiten",
    "whitened",
    "whitening",

    "pale",
    "paleness",
    "pallid",
    "pallor",

    "wan",
    "wanly",
    "wanness",
    "bloodless",
    "colourless",
    "colorless",
    "colourlessness",
    "colorlessness",

    "hoary",
    "grey",
    "gray",
    "greyness",
    "grayness",

    "bleach",
    "bleached",
    "bleaching",

    "albino",
    "albinos",
    "albinoes",
    "albinism",
    "albinotic",
    "albinistic",

    "ghostly",
    "cadaverous",
    "livid",
}


WEAK_WHITENESS_PATTERNS = (
    {"white", "grey", "gray"},
    {"hoary", "grey", "gray"},
    {"pale"},
    {"pale", "grey"},
)


WHITENESS_WEIGHTS = {
    # Strong/direct whiteness
    "white": 1.0,
    "whiteness": 1.5,
    "whiten": 1.0,
    "whitened": 1.0,
    "whitening": 1.0,

    # Pallor
    "pale": 1.0,
    "paleness": 1.5,
    "pallid": 1.5,
    "pallor": 1.5,

    # Related bodily whiteness/pallor
    "wan": 1.0,
    "wanly": 1.0,
    "wanness": 1.5,
    "bloodless": 1.5,
    "colourless": 1.5,
    "colorless": 1.5,
    "colourlessness": 5.0,
    "colorlessness": 5.0,

    # Hair / ageing whiteness
    "hoary": 0.8,
    "grey": 0.75,
    "gray": 0.75,
    "greyness": 1.0,
    "grayness": 1.0,

    # Bleaching
    "bleach": 1.0,
    "bleached": 1.0,
    "bleaching": 1.0,

    # Diagnostic extreme whiteness
    "albino": 10.0,
    "albinos": 10.0,
    "albinoes": 10.0,
    "albinism": 10.0,
    "albinotic": 10.0,
    "albinistic": 10.0,

    # Figurative / potentially bodily
    "ghostly": 1.0,
    "cadaverous": 1.5,
    "livid": 1.0,
}
