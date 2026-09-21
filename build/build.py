"""
Build taxon pages for browse.acousti.cloud.

  py build.py "Gryllotalpa vineae"          one taxon
  py build.py "Gryllotalpa vineae" --deep   that taxon and everything below it

Output goes to site/taxon/<slug>/index.html, with site/sitemap.xml listing what was built.
Nothing in the output calls the API: a page is finished when it is written.
"""

import argparse
import datetime
import os
import sys
import time
import urllib.error
import urllib.request

import api
import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
# Recordings roll up by rank in the join view, so a count against a rank is the count at or below
COUNTABLE = ("kingdom", "class", "order", "suborder", "family", "subfamily", "tribe", "genus", "species")


def image_is_live(url, timeout=15):
    """
    Whether an image can actually be fetched. Worth asking at build time: audioBlast holds the
    metadata for images whose files its source no longer serves, and a static build is the one
    chance to notice before a reader meets a broken figure.
    """
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": api.AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def gather(node, seen_counts):
    """Everything one page needs. Each call is small; there are simply a lot of them."""
    chain = api.lineage(node["id"])
    kids = api.children(node["id"])
    parent_id = node.get("parent_id")
    siblings = [c for c in api.children(parent_id) if c["id"] != node["id"]] if parent_id else []

    sources = api.source_rows(node["id"])
    release = next((s["_remarks"].rsplit(";", 1)[-1].strip()
                    for s in sources if s.get("_remarks") and ";" in s["_remarks"]), None)

    names = list(dict.fromkeys([node["taxon"]] + [s["taxon"] for s in sources]))
    rank = (node.get("rank") or "").lower()

    recordings, total = ([], 0)
    for name in names:
        got, n = api.recordings(name, rank)
        recordings.extend(got)
        total += n
    traits, annotations = [], []
    for name in names:
        traits.extend(api.traits(name))
        annotations.extend(api.annotations(name))

    linked = {kind: [] for kind in api.LINKED_KINDS}
    for source in sources:
        for kind, rows in api.linked(source["source"], source["id"]).items():
            linked[kind].extend(rows)
    for image in linked["images"]:
        image["_live"] = image_is_live(image.get("url", ""))

    child_counts = {}
    for child in kids:
        child_rank = (child.get("rank") or "").lower()
        if child_rank in COUNTABLE:
            key = (child_rank, child["taxon"])
            if key not in seen_counts:
                seen_counts[key] = api.count("recordingstaxa", **{child_rank: child["taxon"]})
            child_counts[child["id"]] = seen_counts[key]
    for ancestor in chain[:-1]:
        ancestor_rank = (ancestor.get("rank") or "").lower()
        if ancestor_rank in COUNTABLE:
            key = (ancestor_rank, ancestor["taxon"])
            if key not in seen_counts:
                seen_counts[key] = api.count("recordingstaxa", **{ancestor_rank: ancestor["taxon"]})
            child_counts[ancestor["id"]] = seen_counts[key]
    for sibling in siblings:
        sibling_rank = (sibling.get("rank") or "").lower()
        if sibling_rank in COUNTABLE:
            key = (sibling_rank, sibling["taxon"])
            if key not in seen_counts:
                seen_counts[key] = api.count("recordingstaxa", **{sibling_rank: sibling["taxon"]})
            child_counts[sibling["id"]] = seen_counts[key]

    return {
        "node": node, "lineage": chain, "children": kids, "siblings": siblings,
        "sources": sources, "release": release,
        "records": {"recordings": recordings, "traits": traits, "annotations": annotations},
        "linked": linked,
        "counts": {"recordings": total, "traits": len(traits), "annotations": len(annotations)},
        "child_counts": child_counts,
    }


def write(node, data):
    path = render.path_of(node["taxon"])
    folder = os.path.join(SITE, path.strip("/").replace("/", os.sep))
    os.makedirs(folder, exist_ok=True)
    html = render.page(node, data["lineage"], data["children"], data["siblings"], data["sources"],
                       data["records"], data["linked"], data["counts"], data["child_counts"],
                       data["release"])
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(html)
    return path, len(html.encode("utf-8"))


def build(names, deep=False):
    built = []
    seen_counts = {}
    queue = list(names)
    done = set()
    while queue:
        name = queue.pop(0)
        if name in done:
            continue
        done.add(name)
        node = api.col_by_name(name)
        if node is None:
            sys.stderr.write("  ! no Catalogue of Life node for %r\n" % name)
            continue
        started = time.time()
        data = gather(node, seen_counts)
        path, size = write(node, data)
        built.append(path)
        broken = sum(1 for i in data["linked"]["images"] if not i["_live"])
        sys.stderr.write("  %-34s %6.1fkB  %5.1fs  %s recordings%s\n" % (
            path, size / 1024, time.time() - started, format(data["counts"]["recordings"], ","),
            "  (%d image files missing)" % broken if broken else ""))
        if deep:
            queue.extend(c["taxon"] for c in data["children"])
    return built


def main():
    parser = argparse.ArgumentParser(description="Build taxon pages for browse.acousti.cloud")
    parser.add_argument("taxon", nargs="+", help="taxon name, as the Catalogue of Life spells it")
    parser.add_argument("--deep", action="store_true", help="also build everything below it")
    args = parser.parse_args()

    sys.stderr.write("Building:\n")
    started = time.time()
    built = build(args.taxon, deep=args.deep)

    if built:
        changed = datetime.date.today().isoformat()
        os.makedirs(SITE, exist_ok=True)
        with open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8") as handle:
            handle.write(render.sitemap(built, changed))
        sys.stderr.write("\n%d page%s in %.1fs, sitemap.xml written\n"
                         % (len(built), "" if len(built) == 1 else "s", time.time() - started))
    else:
        sys.stderr.write("\nNothing built\n")


if __name__ == "__main__":
    main()
