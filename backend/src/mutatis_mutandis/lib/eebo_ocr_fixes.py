import re

OCR_FIXES = {
    r'[\|¦∣]': '',                 # remove OCR bars
    r'\bberty\b': 'liberty',
    r'\btoliberty\b': 'to liberty',
    r'\bvnjustice\b': 'unjustice',
    r'\bdinjustice\b': 'injustice',
    r'\biujustice\b': 'injustice',
    r'\bofjustice\b': 'of justice',
    r'\bdojustice\b': 'do justice',

}

def apply_ocr_fixes(text: str) -> str:
    for pattern, replacement in OCR_FIXES.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
