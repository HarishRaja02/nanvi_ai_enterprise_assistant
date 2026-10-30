import re

def extract_target(q):
    cleaned = re.sub(r'(?i)\b(?:can\s+you\s+)?(?:please\s+)?(?:help\s+me\s+)?(?:i\s+)?(?:need\s+to\s+|want\s+to\s+|would\s+like\s+to\s+)?(?:find|search\s+for|search|look\s+for|locate|get|fetch|show|open|pull\s+up)\b', '', q)
    cleaned = re.sub(r'(?i)\b(?:a\s+|an\s+|the\s+|one\s+)?(?:file|document|files|documents|pdf|record|records)\s*(?:named|called|containing|contain|contains|with|for)?\b', '', cleaned)
    cleaned = re.sub(r'(?i)\b(?:in\s+)?(?:local\s+storage|database|db|emails?|google\s+drive|cloud)\b', '', cleaned)
    cleaned = re.sub(r'(?i)\b(?:this\s+i|this\s+one|please)\b', '', cleaned)
    cleaned = cleaned.strip(" :,-'\"?.")
    if cleaned.lower() in ('', 'a', 'the', 'one', 'it', 'this', 'that'):
        return ''
    return cleaned

test_queries = [
    'i need to find the file',
    'i need to find one file',
    'i need one file',
    'i want to find a document',
    'file contain INV-2026-0042 this i',
    'INV-2026-0042',
    'invoice_022.pdf',
    'find contracts with Acme',
    'Search in Local Storage',
    'Search in Database',
]
for t in test_queries:
    print(f'{t!r} -> {extract_target(t)!r}')

