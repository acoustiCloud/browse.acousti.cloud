"""
Who each source is, and the mark that stands for it.

Every module gives its records a `source`, but it is a bare string: nothing in the API says that
"unp" is the Urban Nature Project or where to find it, so each consumer has kept its own table of
that. When api.audioblast.org grows a sources module this reads it and the table below goes away.

Until then the table carries only what can be checked: display names are the API's own words for
them, and a homepage is given only where the data itself points at one.
"""

import os
import re
import shutil
import urllib.error
import urllib.request

import api

# What the API would need to serve, keyed by the string the other modules put in `source`.
# `url` is left empty rather than guessed: an empty one shows a mark with nothing behind it,
# a wrong one sends a reader somewhere that is not the source.
KNOWN = {
    "CoL":              {"name": "Catalogue of Life",  "url": "https://www.catalogueoflife.org", "initials": "CoL"},
    "bio.acousti.ca":   {"name": "BioAcoustica",       "url": "http://bio.acousti.ca"},
    "iNaturalist":      {"name": "iNaturalist",        "url": "https://www.inaturalist.org"},
    "xeno-canto":       {"name": "xeno-canto",         "url": "https://xeno-canto.org", "initials": "XC"},
    "Plazi":            {"name": "Plazi",              "url": "https://plazi.org"},
    # Small ingests (github.com/audioblast/small_ingests) are a route in, not an
    # organisation with a mark of its own, so they are named and left unbadged.
    "sounds_of_norway": {"name": "Sounds of Norway",   "url": "", "badge": False},
    "unp":              {"name": "Urban Nature Project",
                         "url": "https://www.nhm.ac.uk/about-us/urban-nature-project.html",
                         "initials": "UNP"},
    "ColinBirds":       {"name": "ColinBirds",
                         "url": "https://github.com/audioblast/small_ingests",
                         "badge": False},
    "Mikula_etal_2020": {"name": "Mikula et al. 2020",
                         "url": "https://github.com/audioblast/small_ingests",
                         "badge": False},
    # Taxon sources, which show in the table of what each source calls this taxon
    "taxonBot":         {"name": "taxonBot",         "url": "", "initials": "tB"},
    "osf":              {"name": "Orthoptera Species File",
                         "url": "https://orthoptera.speciesfile.org", "initials": "OSF"},
}

# The file extensions a logo may arrive as, and nothing else: a build writes what it fetches into
# the published site, so it decides what it is willing to publish rather than trusting a URL.
SERVABLE = {
    "image/svg+xml": ".svg", "image/png": ".png",
    "image/jpeg": ".jpg", "image/webp": ".webp",
}
MAX_LOGO = 96 * 1024

# Logos held here rather than fetched, for sources whose own site publishes nothing usable at the
# size these are shown. Named for the source's slug. An API logo still wins over one of these.
HELD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos")


# Words that carry no identity, so "Sounds of Norway" is SN rather than SO
MINOR = {"of", "the", "and", "for", "de", "des", "et", "al", "van", "von"}


def initials(name, given=None):
    """
    Two letters to stand in for a source with no logo. A mark that is plainly a fallback is
    better than a generic icon that pretends every source looks the same.

    Sources name themselves in run-together words as often as in separate ones, so BioAcoustica
    and ColinBirds are read as two words each. The first letter keeps the case it was written
    with, because iNaturalist is not IN.
    """
    if given:
        return given
    words = [part for chunk in re.split(r"[^A-Za-z0-9]+", name)
             for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+|[A-Z]", chunk)
             if part and part.lower() not in MINOR]
    if len(words) >= 2:
        return words[0][0] + words[1][0].upper()
    return (words[0][:2].title() if words else "?")


def slug(source):
    """A filename for a source, since a source string may hold dots and underscores."""
    return re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-") or "source"


def register():
    """
    Every source, as the API describes them if it can and as the table above does if it cannot.
    The API is the authority wherever it answers: a name it gives wins over a name here.
    """
    known = {source: dict(entry, source=source) for source, entry in KNOWN.items()}
    try:
        rows = api.rows("sources", limit=200)
    except api.ApiError:
        # No sources module yet, so every source falls back to its initials
        rows = []
    for row in rows:
        source = row.get("source")
        if not source:
            continue
        entry = known.setdefault(source, {"source": source})
        for field, value in (("name", row.get("name")), ("url", row.get("url")),
                             ("logo", row.get("logo"))):
            if isinstance(value, str) and value.strip():
                entry[field] = value.strip()
    for source, entry in known.items():
        entry.setdefault("name", source)
        entry.setdefault("url", "")
        entry["initials"] = initials(entry["name"], entry.get("initials"))
    return known


def fetch_logo(url, into, name):
    """
    Copy a logo into the site once, so a page needs nothing but this site to render. The file is
    named for the source and typed by what the server says it sent, not by what the URL ends in.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": api.AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            if not 200 <= response.status < 300:
                return None
            kind = (response.headers.get_content_type() or "").lower()
            if kind not in SERVABLE:
                return None
            body = response.read(MAX_LOGO + 1)
    except Exception:
        return None
    if not body or len(body) > MAX_LOGO:
        return None
    os.makedirs(into, exist_ok=True)
    filename = name + SERVABLE[kind]
    with open(os.path.join(into, filename), "wb") as handle:
        handle.write(body)
    return "/logo/" + filename


def held_logo(name, into):
    """A logo kept in the repo, copied into the site beside the fetched ones."""
    for ext in (".svg", ".png", ".webp", ".jpg"):
        path = os.path.join(HELD, name + ext)
        if os.path.exists(path):
            os.makedirs(into, exist_ok=True)
            shutil.copyfile(path, os.path.join(into, name + ext))
            return "/logo/" + name + ext
    return None


def resolve(out):
    """
    The register with every logo placed under `out`/logo. A source whose logo is missing, too big,
    or not an image keeps its initials: a broken image next to every record would be worse than
    the plain text this replaces.
    """
    known = register()
    into = os.path.join(out, "logo")
    for source, entry in sorted(known.items()):
        url = entry.get("logo")
        name = slug(source)
        entry["mark"] = (fetch_logo(url, into, name) if url else None) or held_logo(name, into)
    return known
