"""
Reading audioBlast for the browse build.

Everything here is a targeted query: one taxon's worth. Pages are assembled per taxon rather
than from harvested tables, because the API charges roughly three seconds for any page of a large
module beyond the first, whatever the page size, so pulling recordingstaxa whole costs about
fifteen minutes while the first page of a filtered query costs a quarter of a second.

An id filter takes a list and taxa has a classification endpoint, so a set of records is one
request rather than one each: a page costs seventeen requests where it once cost forty-four.

The API refuses a parameter it does not recognise with a 400 naming what the module accepts, so a
mistyped filter fails here rather than silently returning an unfiltered table.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.audioblast.org"
AGENT = "browse.acousti.cloud build (+https://browse.acousti.cloud)"
COL = "CoL"
EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"


class ApiError(Exception):
    pass


def get(url, tries=3):
    headers = {"User-Agent": AGENT}
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # A 400 is the API saying the query is wrong; retrying will not help
            if error.code == 400:
                raise ApiError("%s\n  %s" % (url, error.read().decode("utf-8", "replace").strip()))
            if attempt == tries - 1:
                raise ApiError("%s -> HTTP %s" % (url, error.code))
        except Exception as error:
            if attempt == tries - 1:
                raise ApiError("%s -> %s" % (url, error))
        time.sleep(1 + attempt * 2)


def rows(module, limit=None, **filters):
    """Rows of a data module matching the filters. Stops at `limit` rather than paging forever."""
    size = min(limit or 1000, 1000)
    query = dict(filters, page=1, page_size=size, output="nakedJSON")
    got = get("%s/data/%s/?%s" % (API, module, urllib.parse.urlencode(query)))
    return got if isinstance(got, list) else []


def count(module, **filters):
    """How many rows match, without pulling them."""
    query = dict(filters, page_size=1)
    got = get("%s/data/%s/?%s" % (API, module, urllib.parse.urlencode(query)))
    return got.get("last_page", 0) if isinstance(got, dict) else 0


# --- the Catalogue of Life spine -------------------------------------------------------------

def col_by_name(name):
    """The CoL node for a name, or None. CoL holds one row per taxon, so this is unambiguous."""
    found = rows("taxa", source=COL, taxon=name)
    exact = [r for r in found if r["taxon"] == name]
    return (exact or found or [None])[0]


def col_by_id(col_id):
    found = rows("taxa", source=COL, id=col_id)
    return found[0] if found else None


def lineage(col_id):
    """
    Root first, this taxon last. One request: the API walks parent_id itself, which it has to do
    anyway and can do without fourteen round trips.
    """
    got = rows("taxa/classification", source=COL, id=col_id)
    return got if isinstance(got, list) else []


def children(col_id, limit=1000):
    return rows("taxa", source=COL, parent_id=col_id, limit=limit)


# --- what each source says this taxon is -----------------------------------------------------

# Sources whose rows a page does not show. taxonBot is being retired, so its content is left
# out rather than shown and then explained. Excluded here, at the one place source rows are
# read, so nothing downstream sees them: not the table of what each source calls a taxon, not
# the names records are looked up by, not the images, descriptions or references hanging off
# them.
EXCLUDED_SOURCES = {"taxonBot"}


def source_rows(col_id):
    """The rows of other sources that skos:exactMatch this CoL taxon."""
    links = rows("links", object_type="taxa", object_source=COL, object_id=col_id)
    wanted, remarks = {}, {}
    for link in links:
        if link.get("predicate") != EXACT_MATCH:
            continue
        if link["subject_source"] in EXCLUDED_SOURCES:
            continue
        wanted.setdefault(link["subject_source"], []).append(link["subject_id"])
        remarks[(link["subject_source"], link["subject_id"])] = link.get("remarks")
    out = []
    # Grouped by source rather than asked for in one call: an id is only unique within its source,
    # so source=a,b with id=x,y would match x from b as readily as from a
    for source, ids in wanted.items():
        for row in rows("taxa", source=source, id=",".join(ids)):
            row["_remarks"] = remarks.get((row["source"], row["id"]))
            out.append(row)
    return out


# --- the records a taxon has -----------------------------------------------------------------

def recordings(name, rank, limit=200):
    """
    Recordings of a taxon, through the join view. recordings.taxon is a full-text field, so
    filtering it would return anything sharing a word: 921 rows for Gryllotalpa vineae where the
    join gives the 536 that are actually of it.
    """
    field = (rank or "").lower()
    if field not in ("kingdom", "class", "order", "suborder", "family", "subfamily", "tribe", "genus", "species"):
        return [], 0
    return rows("recordingstaxa", limit=limit, **{field: name}), count("recordingstaxa", **{field: name})


def traits(name, limit=200):
    return rows("traits", taxon=name, limit=limit)


def annotations(name, limit=50):
    return rows("annomate", taxon=name, limit=limit)


# --- records that reach a taxon only through the links table ---------------------------------

ABOUT = "http://purl.obolibrary.org/obo/IAO_0000136"
DENOTES = "http://purl.obolibrary.org/obo/IAO_0000219"
TO_TAXON = "http://rs.tdwg.org/dwc/iri/toTaxon"

LINKED_KINDS = {
    "images": ABOUT,
    "descriptions": ABOUT,
    "references": ABOUT,
    "specimens": TO_TAXON,
    "vernacularnames": DENOTES,
}


def linked(source, taxon_id, cap=12):
    """
    Records that point at a source's taxon row, one request per kind rather than per record now
    that an id filter takes a list. Capped: a page shows a handful and the rest are a link away.
    """
    out = {kind: [] for kind in LINKED_KINDS}
    links = rows("links", object_type="taxa", object_source=source, object_id=taxon_id, limit=1000)
    wanted = {}
    for link in links:
        kind = link.get("subject_type")
        if kind not in LINKED_KINDS or link.get("predicate") != LINKED_KINDS[kind]:
            continue
        ids = wanted.setdefault((kind, link["subject_source"]), [])
        if len(ids) < cap:
            ids.append(link["subject_id"])
    for (kind, held_by), ids in wanted.items():
        out[kind].extend(rows(kind, source=held_by, id=",".join(ids), limit=cap))
    return out
