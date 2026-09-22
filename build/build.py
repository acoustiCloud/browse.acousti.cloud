"""
Build taxon pages for browse.acousti.cloud.

  py build.py "Gryllotalpa vineae"                  one taxon
  py build.py "Gryllotalpidae" --deep               that taxon and everything below it
  py build.py "Orthoptera" --deep --workers 16      ... harder

Output goes to docs/taxon/<slug>/index.html, with docs/index.html and docs/sitemap.xml covering
what was built. Nothing in the output calls the API: a page is finished when it is written.

A page is seventeen requests and almost no work, so the build is bound by waiting. It builds
pages concurrently and shares what it has already asked for.
"""

import argparse
import concurrent.futures
import datetime
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import api
import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# GitHub Pages serves a branch from its root or from /docs, and nowhere else
OUT = os.path.join(ROOT, "docs")
# Recordings roll up by rank in the join view, so a count against a rank is the count at or below
COUNTABLE = ("kingdom", "class", "order", "suborder", "family", "subfamily", "tribe", "genus", "species")
# How many parents to ask about at once while walking down the tree
PARENTS_PER_CALL = 20

_lock = threading.Lock()
_counts = {}
_children = {}


def shared(cache, key, produce):
    """
    Ask once for something several pages need. A genus and each of its species all want the same
    sibling list and the same counts, so without this a deep build asks again for every page.

    Two threads can still race to produce the same value. That costs one extra request rather
    than a wrong answer, which is the right way round.
    """
    with _lock:
        if key in cache:
            return cache[key]
    value = produce()
    with _lock:
        return cache.setdefault(key, value)


def count_at_or_below(rank, name):
    rank = (rank or "").lower()
    if rank not in COUNTABLE:
        return None
    return shared(_counts, (rank, name), lambda: api.count("recordingstaxa", **{rank: name}))


def children_of(col_id):
    return shared(_children, col_id, lambda: api.children(col_id))


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


def discover(names, deep):
    """
    The taxa to build. Going down the tree asks about a whole level at once, since parent_id takes
    a list: a family costs a handful of requests rather than one per taxon in it.
    """
    found = {}
    frontier = []
    for name in names:
        node = api.col_by_name(name)
        if node is None:
            print("  ! no Catalogue of Life node for %r" % name, file=sys.stderr)
            continue
        found[node["id"]] = node
        frontier.append(node["id"])
    while deep and frontier:
        below = []
        for at in range(0, len(frontier), PARENTS_PER_CALL):
            chunk = frontier[at:at + PARENTS_PER_CALL]
            got = api.rows("taxa", source=api.COL, parent_id=",".join(chunk), limit=1000)
            if len(got) >= 1000:
                # Wider than one response holds, so ask parent by parent rather than truncate
                got = [row for one in chunk for row in children_of(one)]
            below.extend(got)
        frontier = []
        for row in below:
            if row["id"] not in found:
                found[row["id"]] = row
                frontier.append(row["id"])
    return list(found.values())


def resolve_paths(nodes):
    """
    Where each page goes, decided for the whole set at once.

    Two taxa can share a name: the Catalogue of Life carries monotypic higher taxa named after
    the genus inside them, so Metrioptera is both an infratribe and the genus beneath it. Deriving
    a path from a name gave both the same one, and under a thread pool which survived depended on
    which finished last.

    Where names collide the deepest keeps the plain slug, since someone typing metrioptera wants
    the genus rather than the rank above it, and the rest carry their rank.
    """
    known = {node["id"]: node for node in nodes}

    def depth(node):
        seen, below, parent = set(), 0, node.get("parent_id")
        while parent in known and parent not in seen:
            seen.add(parent)
            below += 1
            parent = known[parent].get("parent_id")
        return below

    sharing = {}
    for node in nodes:
        sharing.setdefault(render.slug(node["taxon"]), []).append(node)

    paths, clashed = {}, 0
    for slug, together in sharing.items():
        if len(together) > 1:
            clashed += len(together) - 1
            together = sorted(together, key=lambda one: (-depth(one), one["id"]))
        paths[together[0]["id"]] = "/taxon/%s/" % slug
        for other in together[1:]:
            rank = render.slug(other.get("rank") or "") or "taxon"
            paths[other["id"]] = "/taxon/%s-%s/" % (slug, rank)

    # Silently losing a page is the bug this exists to prevent, so a path still wanted twice stops
    # the build rather than letting one win
    taken = {}
    for col_id, path in paths.items():
        if path in taken:
            sys.exit("two taxa want %s: %s and %s" % (path, taken[path], col_id))
        taken[path] = col_id
    if clashed:
        print("  %d name%s shared, given their rank in the path"
              % (clashed, "" if clashed == 1 else "s"), file=sys.stderr)
    return paths


def gather(node):
    """Everything one page needs."""
    chain = api.lineage(node["id"])
    kids = children_of(node["id"])
    parent_id = node.get("parent_id")
    siblings = [c for c in children_of(parent_id) if c["id"] != node["id"]] if parent_id else []

    sources = api.source_rows(node["id"])
    release = next((s["_remarks"].rsplit(";", 1)[-1].strip()
                    for s in sources if s.get("_remarks") and ";" in s["_remarks"]), None)

    names = list(dict.fromkeys([node["taxon"]] + [s["taxon"] for s in sources]))
    rank = (node.get("rank") or "").lower()

    recordings, total = [], 0
    traits, annotations = [], []
    for name in names:
        got, n = api.recordings(name, rank)
        recordings.extend(got)
        total += n
        traits.extend(api.traits(name))
        annotations.extend(api.annotations(name))

    linked = {kind: [] for kind in api.LINKED_KINDS}
    for source in sources:
        for kind, rows in api.linked(source["source"], source["id"]).items():
            linked[kind].extend(rows)
    for image in linked["images"]:
        image["_live"] = image_is_live(image.get("url", ""))

    counts = {}
    for other in kids + siblings + chain[:-1]:
        at_or_below = count_at_or_below(other.get("rank"), other["taxon"])
        if at_or_below is not None:
            counts[other["id"]] = at_or_below

    return {
        "node": node, "lineage": chain, "children": kids, "siblings": siblings,
        "sources": sources, "release": release,
        "records": {"recordings": recordings, "traits": traits, "annotations": annotations},
        "linked": linked,
        "counts": {"recordings": total, "traits": len(traits), "annotations": len(annotations)},
        "child_counts": counts,
    }


def write(node, data):
    path = render.path_for(node)
    folder = os.path.join(OUT, path.strip("/").replace("/", os.sep))
    os.makedirs(folder, exist_ok=True)
    html = render.page(node, data["lineage"], data["children"], data["siblings"], data["sources"],
                       data["records"], data["linked"], data["counts"], data["child_counts"],
                       data["release"])
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(html)
    return path, len(html.encode("utf-8"))


def one_page(node):
    started = time.time()
    data = gather(node)
    path, size = write(node, data)
    broken = sum(1 for i in data["linked"]["images"] if not i["_live"])
    print("  %-38s %6.1fkB  %4.1fs  %s recordings%s" % (
        path, size / 1024, time.time() - started,
        format(data["counts"]["recordings"], ","),
        "  (%d image files missing)" % broken if broken else ""), file=sys.stderr)
    return path, node, data["counts"]["recordings"]


def build(nodes, workers):
    built = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one_page, node): node for node in nodes}
        for future in concurrent.futures.as_completed(futures):
            node = futures[future]
            try:
                built.append(future.result())
            except Exception as error:
                print("  ! %-36s %s" % (node["taxon"], error), file=sys.stderr)
    # Sorted, so the sitemap and index do not depend on which thread finished first
    built.sort(key=lambda made: made[0])
    return built


def main():
    parser = argparse.ArgumentParser(description="Build taxon pages for browse.acousti.cloud")
    parser.add_argument("taxon", nargs="+", help="taxon name, as the Catalogue of Life spells it")
    parser.add_argument("--deep", action="store_true", help="also build everything below it")
    parser.add_argument("--workers", type=int, default=8, help="pages to build at once (default 8)")
    args = parser.parse_args()

    started = time.time()
    print("Finding what to build:", file=sys.stderr)
    nodes = discover(args.taxon, args.deep)
    print("  %d taxa in %.1fs" % (len(nodes), time.time() - started), file=sys.stderr)
    render.set_paths(resolve_paths(nodes))
    print("Building, %d at a time:" % args.workers, file=sys.stderr)
    built = build(nodes, args.workers)

    print("", file=sys.stderr)
    if not built:
        print("Nothing built", file=sys.stderr)
        return

    ids = {node["id"] for _, node, _ in built}
    roots = [(node, count) for _, node, count in built if node.get("parent_id") not in ids]
    roots.sort(key=lambda pair: -pair[1])
    counts = api.get(api.API + "/standalone/data/fetch_data_counts/?output=nakedJSON")
    held = counts.get("counts", {}) if isinstance(counts, dict) else {}
    stats = [(len(built), "pages built"),
             (int(held.get("recordings", 0)), "recordings in audioBlast"),
             (int(held.get("traits", 0)), "trait measurements"),
             (api.count("taxa", source=api.COL), "taxa in the Catalogue of Life spine")]
    changed = datetime.date.today().isoformat()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as handle:
        handle.write(render.sitemap([path for path, _, _ in built] + ["/"], changed))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(render.index([(node, count) for _, node, count in built], roots, stats, changed))
    print("%d page%s in %.1fs, index and sitemap written"
          % (len(built), "" if len(built) == 1 else "s", time.time() - started), file=sys.stderr)


if __name__ == "__main__":
    main()
