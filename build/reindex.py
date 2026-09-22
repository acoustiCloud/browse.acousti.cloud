"""
Rewrite docs/index.html and docs/sitemap.xml from the pages already built.

The index is the one part of the site that depends on the whole of it rather than on one taxon,
so it is also the part most likely to need changing after a long build. Reading it back off the
pages costs seconds, where rebuilding them to regenerate it costs the whole run again.

  py reindex.py
"""

import datetime
import os
import re
import sys

import api
import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs")
TAXA = os.path.join(OUT, "taxon")

TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RANK = re.compile(r'<p class="rank">(.*?)</p>', re.S)
COL_ID = re.compile(r'/taxon/CoL/([A-Za-z0-9]+)')
RECORDINGS = re.compile(r'<b>([\d,]+)</b> <span>recordings</span>')
# The last link in the breadcrumb is the taxon immediately above this one
CRUMB = re.compile(r'<nav class="crumb".*?</nav>', re.S)
CRUMB_HREF = re.compile(r'href="(/taxon/[^"]+)"')


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def scan():
    """What each built page says about itself."""
    pages = {}
    for slug in os.listdir(TAXA):
        page = os.path.join(TAXA, slug, "index.html")
        if not os.path.exists(page):
            continue
        html = read(page)
        title = TITLE.search(html)
        col = COL_ID.search(html)
        if not (title and col):
            print("  ! %s: not a taxon page" % slug, file=sys.stderr)
            continue
        rank = RANK.search(html)
        recordings = RECORDINGS.search(html)
        crumb = CRUMB.search(html)
        above = CRUMB_HREF.findall(crumb.group(0)) if crumb else []
        pages["/taxon/%s/" % slug] = {
            "id": col.group(1),
            # A title now reads "Gryllotalpa vineae - Vineyard Mole-cricket"; the taxon is the
            # part before the dash, and everything downstream matches on that
            "taxon": title.group(1).split("—")[0].strip(),
            "rank": (rank.group(1).strip() if rank else ""),
            "count": int(recordings.group(1).replace(",", "")) if recordings else 0,
            "parent_path": above[-1] if above else None,
        }
    return pages


def main():
    if not os.path.isdir(TAXA):
        sys.exit("nothing built at %s" % TAXA)
    print("Reading built pages:", file=sys.stderr)
    pages = scan()
    print("  %s pages" % format(len(pages), ","), file=sys.stderr)
    if not pages:
        sys.exit("no pages to index")

    # A page whose parent was not built is a way in
    built = [(dict(id=p["id"], taxon=p["taxon"], rank=p["rank"]), p["count"])
             for p in pages.values()]
    roots = [(dict(id=p["id"], taxon=p["taxon"], rank=p["rank"]), p["count"])
             for p in pages.values()
             if not p["parent_path"] or p["parent_path"] not in pages]
    roots.sort(key=lambda pair: -pair[1])

    counts = api.get(api.API + "/standalone/data/fetch_data_counts/?output=nakedJSON")
    held = counts.get("counts", {}) if isinstance(counts, dict) else {}
    stats = [(len(built), "pages built"),
             (int(held.get("recordings", 0)), "recordings in audioBlast"),
             (int(held.get("traits", 0)), "trait measurements"),
             (api.count("taxa", source=api.COL), "taxa in the Catalogue of Life spine")]

    changed = datetime.date.today().isoformat()
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as handle:
        handle.write(render.sitemap(sorted(pages) + ["/"], changed))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(render.index(built, roots, stats, changed))
    size = os.path.getsize(os.path.join(OUT, "index.html")) / 1024
    print("  %d root%s, index %.1fkB, sitemap %s urls"
          % (len(roots), "" if len(roots) == 1 else "s", size, format(len(pages) + 1, ",")),
          file=sys.stderr)


if __name__ == "__main__":
    main()
