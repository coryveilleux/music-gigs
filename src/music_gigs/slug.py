import re


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"['']", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
