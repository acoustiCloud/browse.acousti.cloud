"""
Rendering a taxon page.

The page is a document, not an application: no script, no runtime call to the API, nothing that
has to succeed after it is served. What it knows was settled when it was built.
"""

import html
import json
import re
import unicodedata

SITE = "https://browse.acousti.cloud"
API = "https://api.audioblast.org"
VIEWER = "https://view.audioblast.org"

ITALIC_RANKS = ("genus", "species", "subgenus", "subspecies")

# A page shows this many measurements and links out for the rest
TRAIT_ROW_CAP = 60

# While the site is small enough to read whole, the index lists every page. Past that it offers
# entry points instead: a front page that is two megabytes of links is not a way in.
SHOW_ALL_BELOW = 200
# The ranks worth offering as a way in. A kingdom is not one: Animalia is everything audioBlast
# holds and Plantae is nothing, so neither gets a reader anywhere. Someone looking for frogs wants
# Anura, and someone looking for crickets wants Gryllidae.
ENTRY_RANKS = ("class", "order", "family")
ENTRIES = 30

# What the groups are called by people who are not taxonomists, in the order they are worth
# offering. Only the ones actually built are shown, so this can name more than the site holds.
# Hylidae and Tettigoniidae are deliberately absent: they sit inside Anura and Orthoptera, and a
# way in should not offer the same recordings twice under two names.
HUMAN_GROUPS = [
    ("Anura", "Frogs and toads"),
    ("Orthoptera", "Crickets, katydids and grasshoppers"),
    ("Hemiptera", "Cicadas, hoppers and other true bugs"),
    ("Chiroptera", "Bats"),
    ("Rodentia", "Rodents"),
    ("Carnivora", "Carnivores"),
    ("Artiodactyla", "Hoofed mammals"),
    ("Primates", "Primates"),
    ("Hymenoptera", "Bees, wasps and ants"),
    ("Squamata", "Lizards and snakes"),
    ("Coleoptera", "Beetles"),
    ("Lepidoptera", "Moths and butterflies"),
    ("Crocodylia", "Crocodiles and alligators"),
    ("Diptera", "Flies"),
    ("Cetacea", "Whales and dolphins"),
    ("Aves", "Birds"),
    ("Testudines", "Turtles and tortoises"),
    ("Caudata", "Salamanders and newts"),
]


def slug(name):
    """
    A hybrid sign becomes an x rather than vanishing: the sources write hybrids both ways, and
    dropping it would make `Anaxyrus americanus x fowleri` a trinomial.
    """
    text = str(name).replace("×", " x ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")


# Where each taxon's page went, by Catalogue of Life id, settled before any page is written.
# A path cannot be derived from a name: the Catalogue of Life carries monotypic higher taxa named
# after the genus inside them, so Metrioptera is both an infratribe and the genus beneath it.
_paths = {}


def set_paths(paths):
    """Fixed once, before the build starts, and only read after."""
    global _paths
    _paths = dict(paths)


def path_for(node):
    """The page of a taxon, by id. Falls back to its name for anything built on its own."""
    return _paths.get(node.get("id")) or path_of(node["taxon"])


def e(value):
    return html.escape("" if value is None else str(value))


def has(value):
    return value is not None and str(value).strip() != ""


def shares_name(node):
    """
    Whether another taxon in this build is called the same thing. Only true of the one that gave
    up the plain slug, so the page someone means by the bare name is left titled by it alone.
    """
    path = _paths.get(node.get("id"))
    return path is not None and path != path_of(node["taxon"])


def path_of(name):
    return "/taxon/%s/" % slug(name)


def common_name(vernacular):
    """
    The name to lead with, preferring English where a taxon has one. A page titled only with a
    binomial answers a question almost nobody types.
    """
    if not vernacular:
        return None
    english = [v for v in vernacular if (v.get("language") or "").lower().startswith("en")]
    return (english or vernacular)[0].get("vernacularName")


# Who each source is, set once before the build starts. Empty until then, which is what a page
# built on its own gets: the source's name, printed as it always was, with no mark beside it.
_sources = {}


def set_sources(known):
    global _sources
    _sources = dict(known)


def source_mark(source):
    """
    A source's name with its mark before it. The logo is decorative beside the name it labels, so
    it is hidden from a screen reader rather than read out twice, and the source's full name is
    on the wrapper for anyone who does not recognise the mark.
    """
    shown = e(source or "")
    entry = _sources.get(source or "")
    # A source with no mark of its own is named and left alone: a badge that stands for nothing
    # is noise beside the sources that have one.
    if entry is None or entry.get("badge") is False:
        return shown
    if entry.get("mark"):
        mark = ("<img class=\"mk\" src=\"%s\" alt=\"\" width=\"16\" height=\"16\" loading=\"lazy\">"
                % e(entry["mark"]))
    else:
        mark = "<span class=\"mk mono\" aria-hidden=\"true\">%s</span>" % e(entry["initials"])
    return "<span class=\"srcof\" title=\"%s\">%s%s</span>" % (e(entry["name"]), mark, shown)


def record(kind, row, text=None, id_field="id"):
    """
    A link to a record's own address in the API. Everything audioBlast holds dereferences at
    /{kind}/{source}/{id}, so a page that shows a record can always reach the record.
    """
    ident = row.get(id_field)
    label = e(text if text is not None else ident)
    if not (has(row.get("source")) and has(ident)):
        return label
    return "<a href=\"%s/%s/%s/%s\">%s</a>" % (API, kind, e(row["source"]), e(ident), label)


def at_source(row, text="at source"):
    """Where the source keeps its own page for a record, if it does."""
    url = row.get("info_url")
    return (" <a href=\"%s\">%s</a>" % (e(url), e(text))) if has(url) else ""


def name_html(name, rank):
    tag = "i" if (rank or "").lower() in ITALIC_RANKS else "span"
    return "<%s>%s</%s>" % (tag, e(name), tag)


STYLE = """
:root{
  --paper:#f4f6f7; --surface:#ffffff; --sunk:#eceff2;
  --ink:#121a20; --muted:#5b6b78; --rule:#dbe1e6;
  --accent:#a8480c; --accent-soft:#f3e3d8; --signal:#14595f;
  --display:"Spectral",Georgia,"Times New Roman",serif;
  --body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --data:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  --gut:clamp(16px,4vw,40px);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0d1216; --surface:#141c22; --sunk:#19232a;
  --ink:#e4ebf0; --muted:#94a5b2; --rule:#25313a;
  --accent:#e5945c; --accent-soft:#2e2019; --signal:#63b6bc;
}}
:root[data-theme="dark"]{
  --paper:#0d1216; --surface:#141c22; --sunk:#19232a;
  --ink:#e4ebf0; --muted:#94a5b2; --rule:#25313a;
  --accent:#e5945c; --accent-soft:#2e2019; --signal:#63b6bc;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
     font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding-inline:var(--gut)}
a{color:var(--signal);text-underline-offset:2px}
a:hover{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}

.masthead{border-bottom:1px solid var(--rule);background:var(--surface)}
.masthead .wrap{padding-block:clamp(22px,4vw,40px) clamp(18px,3vw,28px)}
.crumb{margin:0 0 14px;font-family:var(--data);font-size:12.5px;color:var(--muted);
       display:flex;flex-wrap:wrap;gap:3px 7px;align-items:baseline;line-height:1.7}
.crumb i{font-style:italic}
.crumb .sep{color:var(--rule)}
.crumb a{color:var(--muted);text-decoration:none;display:inline-flex;flex-direction:column;
         gap:1px;padding-bottom:1px;border-bottom:1px solid transparent}
.crumb a:hover{color:var(--accent);border-bottom-color:currentColor}
.crumb .rk{font-size:9px;letter-spacing:.11em;text-transform:uppercase;opacity:.62;line-height:1.3}
.crumb .sep{align-self:flex-end;padding-bottom:2px}
h1{margin:0;font-family:var(--display);font-weight:600;
   font-size:clamp(2rem,6vw,3.2rem);line-height:1.05;letter-spacing:-.01em;text-wrap:balance}
h1 i{font-style:italic}
.lede{margin:18px 0 0;max-width:62ch;font-family:var(--display);font-size:1.12rem;
      line-height:1.65;color:var(--ink)}
.groups{margin:0;padding:0;list-style:none;display:grid;
        grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:0 28px}
.groups li{border-bottom:1px solid var(--rule)}
.groups a{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:2px 14px;
          padding:11px 0;text-decoration:none;color:var(--ink)}
.groups a:hover{color:var(--accent)}
.groups .what{font-family:var(--display);font-size:1.12rem;line-height:1.3}
.groups .sci{grid-row:2;font-family:var(--data);font-size:11.5px;color:var(--muted)}
.groups .n{grid-row:1;font-family:var(--data);font-size:12.5px;
           font-variant-numeric:tabular-nums;color:var(--muted)}
.groups a:hover .n,.groups a:hover .sci{color:var(--accent)}
.srcof{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;vertical-align:baseline}
.mk{width:16px;height:16px;flex:none;border-radius:3px;object-fit:contain}
.mk.mono{display:inline-flex;align-items:center;justify-content:center;background:var(--muted);
         color:var(--surface);font-family:var(--data);font-size:9px;font-weight:600;line-height:1}
.tiles{margin:0 0 6px;padding:0;list-style:none;display:grid;
       grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:0 24px}
.tiles li{border-bottom:1px solid var(--rule)}
.tiles a{display:flex;justify-content:space-between;gap:12px;padding:7px 0;align-items:baseline;
         text-decoration:none;color:var(--ink)}
.tiles a:hover{color:var(--accent)}
.tiles .n{font-family:var(--data);font-size:12px;font-variant-numeric:tabular-nums;color:var(--muted)}
.tiles a:hover .n{color:var(--accent)}
.rank{margin:9px 0 0;font-family:var(--data);font-size:12px;letter-spacing:.1em;
      text-transform:uppercase;color:var(--accent)}
.vern{margin:16px 0 0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:7px 18px;
      font-family:var(--display);font-size:1.06rem}
.vern li{display:flex;align-items:baseline;gap:7px}
.vern code{font-family:var(--data);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
           color:var(--muted);border:1px solid var(--rule);border-radius:3px;padding:1px 5px}

.glance{background:var(--sunk);border-bottom:1px solid var(--rule)}
.glance .wrap{padding-block:15px;display:flex;flex-wrap:wrap;gap:9px 28px}
.glance div{display:flex;align-items:baseline;gap:7px}
.glance b{font-family:var(--data);font-weight:500;font-variant-numeric:tabular-nums}
.glance span{font-size:12.5px;color:var(--muted)}

section{border-bottom:1px solid var(--rule)}
section .wrap{padding-block:clamp(28px,4.5vw,44px)}
h2{margin:0 0 6px;font-family:var(--data);font-size:11.5px;font-weight:500;letter-spacing:.16em;
   text-transform:uppercase;color:var(--accent)}
.note{margin:0 0 22px;font-size:13.5px;color:var(--muted);max-width:68ch}
.prose{max-width:72ch;font-family:var(--display);font-size:1.1rem;line-height:1.72}
.prose p{margin:0 0 1em}
.src{margin:-.4em 0 1.6em;font-family:var(--data);font-size:11.5px;color:var(--muted)}
.src a{color:var(--muted)}
.src a:hover{color:var(--accent)}
.topic{margin:0 0 7px;font-family:var(--data);font-size:11px;letter-spacing:.12em;
       text-transform:uppercase;color:var(--muted)}

.traits{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1px;
        background:var(--rule);border:1px solid var(--rule)}
.trait{background:var(--surface);padding:15px 17px;display:flex;flex-direction:column;gap:6px}
.trait h3{margin:0;font-size:13.5px;font-weight:600;line-height:1.35}
.trait h3 a{color:inherit;text-decoration:none;border-bottom:1px dotted var(--rule)}
.vals{margin:0;font-family:var(--data);font-size:1.15rem;font-variant-numeric:tabular-nums;
      color:var(--signal);line-height:1.3;word-break:break-word}
.qual{margin:0;font-size:11.5px;color:var(--muted)}
.vals a{color:inherit;text-decoration:none;border-bottom:1px solid var(--rule)}
.vals a:hover{color:var(--accent);border-bottom-color:currentColor}
h3.sub{margin:30px 0 6px;font-family:var(--data);font-size:11.5px;font-weight:500;
       letter-spacing:.16em;text-transform:uppercase;color:var(--accent)}
tr:target td{background:var(--accent-soft)}

.recs{border:1px solid var(--rule);background:var(--surface)}
.rec{display:grid;grid-template-columns:1fr auto;gap:3px 18px;padding:13px 17px;
     border-bottom:1px solid var(--rule);align-items:baseline}
.rec:last-child{border-bottom:none}
.rec .t{font-weight:500;font-size:14.5px}
.rec .d{font-family:var(--data);font-size:13px;font-variant-numeric:tabular-nums;color:var(--signal)}
.rec .m{grid-column:1/-1;font-family:var(--data);font-size:11.5px;color:var(--muted);
        display:flex;flex-wrap:wrap;gap:3px 13px}
.more{margin:14px 0 0;font-size:13px;color:var(--muted)}

.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px}
figure{margin:0;background:var(--surface);border:1px solid var(--rule);overflow:hidden;
       display:flex;flex-direction:column}
figure img{display:block;width:100%;height:auto;background:var(--sunk)}
figcaption{padding:10px 13px;font-size:12px;color:var(--muted);font-family:var(--data);
           display:flex;flex-direction:column;gap:3px;border-top:1px solid var(--rule)}
figcaption b{color:var(--ink);font-weight:500;letter-spacing:.06em;text-transform:uppercase;font-size:10.5px}

.nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:26px}
.nav h3{margin:0 0 10px;font-family:var(--data);font-size:11px;letter-spacing:.12em;
        text-transform:uppercase;color:var(--muted);font-weight:500}
.nav ul{margin:0;padding:0;list-style:none;display:flex;flex-direction:column}
.nav li{border-bottom:1px solid var(--rule)}
.nav li:last-child{border-bottom:none}
.nav a{display:flex;justify-content:space-between;gap:14px;padding:8px 0;text-decoration:none;
       align-items:baseline;color:var(--ink)}
.nav a:hover{color:var(--accent)}
.nav .n{font-family:var(--data);font-size:12px;font-variant-numeric:tabular-nums;color:var(--muted)}
.nav a:hover .n{color:var(--accent)}
.nav .none{color:var(--muted);font-size:12.5px;padding:8px 0}

table.grid{width:100%;border-collapse:collapse;font-size:14px}
table.grid th{text-align:left;font-family:var(--data);font-size:10.5px;letter-spacing:.1em;
      text-transform:uppercase;color:var(--muted);font-weight:500;
      padding:0 18px 9px 0;border-bottom:1px solid var(--rule);white-space:nowrap}
table.grid td{padding:10px 18px 10px 0;border-bottom:1px solid var(--rule);vertical-align:top}
table.grid td.n{font-family:var(--data);font-variant-numeric:tabular-nums;white-space:nowrap}
.scroll{overflow-x:auto}

.refs{margin:0;padding:0;list-style:none;max-width:78ch;display:flex;flex-direction:column;gap:15px}
.refs li{padding-left:15px;border-left:2px solid var(--rule);font-size:14.5px;line-height:1.55}
.refs .who{font-weight:500}
.refs .where{color:var(--muted);font-size:13.5px}

details{border:1px solid var(--rule);background:var(--surface)}
summary{padding:13px 17px;cursor:pointer;font-family:var(--data);font-size:12.5px;color:var(--ink)}
summary::marker{color:var(--accent)}
pre{margin:0;padding:17px;background:var(--sunk);border-top:1px solid var(--rule);
    overflow-x:auto;font-family:var(--data);font-size:11.5px;line-height:1.6}

footer .wrap{padding-block:30px 40px;font-size:12.5px;color:var(--muted);
             display:flex;flex-direction:column;gap:8px}
footer a{color:var(--muted)}
footer .iri{font-family:var(--data);font-size:11.5px;word-break:break-all}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def schema_for(node, vernacular, lineage):
    parent = lineage[-2] if len(lineage) > 1 else None
    data = {
        "@context": ["https://schema.org/", {"dwc": "http://rs.tdwg.org/dwc/terms/"}],
        "@type": "Taxon",
        "@id": SITE + path_for(node),
        "name": node["taxon"],
        "taxonRank": (node.get("rank") or "").lower(),
        "url": SITE + path_for(node),
        "sameAs": "%s/taxon/%s/%s" % (API, "CoL", node["id"]),
    }
    if vernacular:
        data["alternateName"] = [v["vernacularName"] for v in vernacular]
    if parent:
        data["parentTaxon"] = {"@type": "Taxon", "name": parent["taxon"],
                               "taxonRank": (parent.get("rank") or "").lower(),
                               "url": SITE + path_for(parent)}
    return data


def breadcrumbs_for(lineage):
    """
    The classification as a BreadcrumbList. It says to a search engine what the nav at the top of
    the page says to a reader, and is what puts the hierarchy in a result instead of a bare URL.
    """
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": at + 1, "name": step["taxon"],
             "item": SITE + path_for(step)}
            for at, step in enumerate(lineage)
        ],
    }


def page(node, lineage, children, siblings, sources, records, linked, counts, child_counts, release):
    """One taxon page. Everything passed in is already fetched; nothing here calls the API."""
    out = []
    w = out.append
    name = node["taxon"]
    rank = (node.get("rank") or "").lower()
    vernacular = linked.get("vernacularnames", [])

    w("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">")
    w("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    common = common_name(vernacular)
    # A name shared with another taxon needs its rank to tell the two pages apart
    called = name if not shares_name(node) else "%s (%s)" % (name, (node.get("rank") or "taxon").lower())
    # What the page is: the sound of a taxon, not the taxon. It says so in the one line a
    # search result gives it, and the share card says the same, because a page has one title.
    titled = "Bioacoustics of %s" % (
        called if common is None else "%s \u2014 %s" % (called, common))
    w("<title>%s</title>" % e(titled))
    said = called if common is None else "%s (%s)" % (common, called)
    summary = "%s in audioBlast: %s recordings, %s trait measurements, and the sources that hold them." % (
        e(said), format(counts.get("recordings", 0), ","), format(counts.get("traits", 0), ","))
    w("<meta name=\"description\" content=\"%s\">" % summary)
    w("<link rel=\"canonical\" href=\"%s%s\">" % (SITE, path_for(node)))
    w("<meta property=\"og:title\" content=\"%s\">" % e(titled))
    w("<meta property=\"og:description\" content=\"%s\">" % summary)
    w("<meta property=\"og:type\" content=\"article\">")
    w("<link rel=\"alternate\" type=\"application/ld+json\" href=\"%s/taxon/%s/%s\">" % (API, "CoL", node["id"]))
    w("<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>")
    w("<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
      "family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&"
      "family=Spectral:ital,wght@0,400;0,600;1,400;1,600&display=swap\">")
    w("<style>%s</style>" % STYLE)
    w("<script type=\"application/ld+json\">%s</script>" %
      json.dumps(schema_for(node, vernacular, lineage), ensure_ascii=False))
    if len(lineage) > 1:
        w("<script type=\"application/ld+json\">%s</script>" %
          json.dumps(breadcrumbs_for(lineage), ensure_ascii=False))
    w("</head>\n<body>")

    # masthead ---------------------------------------------------------------------------------
    w("<header class=\"masthead\"><div class=\"wrap\">")
    # Each step carries its rank: the chain runs through ranks the flat columns never held, and
    # Gryllidea or Gryllotalpoidea tells a reader nothing without the word infraorder or superfamily
    crumb = []
    for step in lineage[:-1]:
        crumb.append("<a href=\"%s\"><span class=\"rk\">%s</span>%s</a>" % (
            path_for(step), e(step.get("rank") or ""),
            name_html(step["taxon"], step.get("rank"))))
    w("<nav class=\"crumb\" aria-label=\"Classification\">%s</nav>" %
      "<span class=\"sep\">›</span>".join(crumb))
    w("<h1>Bioacoustics of %s</h1>" % name_html(name, rank))
    w("<p class=\"rank\">%s</p>" % e(node.get("rank") or ""))
    if vernacular:
        w("<ul class=\"vern\">")
        for v in vernacular:
            lang = v.get("language")
            w("<li>%s%s</li>" % (record("vernacular-name", v, v["vernacularName"]),
                                 (" <code>%s</code>" % e(lang)) if has(lang) else ""))
        w("</ul>")
    w("</div></header>")

    # glance -----------------------------------------------------------------------------------
    tiles = [(counts.get("recordings", 0), "recordings"), (counts.get("traits", 0), "trait measurements"),
             (counts.get("annotations", 0), "annotations"), (len(linked.get("images", [])), "images"),
             (len(linked.get("references", [])), "references"), (len(linked.get("specimens", [])), "specimens")]
    w("<div class=\"glance\"><div class=\"wrap\">")
    for n, label in tiles:
        if n:
            w("<div><b>%s</b> <span>%s</span></div>" % (format(n, ","), label))
    w("</div></div>")

    # account ----------------------------------------------------------------------------------
    descriptions = [d for d in linked.get("descriptions", []) if has(d.get("value"))]
    if descriptions:
        w("<section><div class=\"wrap\"><h2>Account</h2>")
        w("<p class=\"note\">What the sources say about this taxon, as written.</p><div class=\"prose\">")
        for d in descriptions:
            w("<p class=\"topic\">%s · %s</p><p>%s</p><p class=\"src\">%s%s</p>" % (
                e(d.get("topic") or "general"), source_mark(d.get("source")), e(d["value"]),
                record("description", d, "this account"), at_source(d, "at %s" % d.get("source"))))
        w("</div></div></section>")

    # traits -----------------------------------------------------------------------------------
    by_trait = {}
    for row in records.get("traits", []):
        by_trait.setdefault(row["trait"], []).append(row)
    if by_trait:
        w("<section><div class=\"wrap\"><h2>Acoustic traits</h2>")
        w("<p class=\"note\">%d measurements across %d traits. Each name links to its term in the "
          "audioBlast vocabulary.</p><div class=\"traits\">" % (len(records.get("traits", [])), len(by_trait)))
        for trait, group in sorted(by_trait.items(), key=lambda kv: -len(kv[1])):
            values = [r["value"] for r in group if has(r.get("value"))]
            numbers = []
            for v in values:
                try:
                    numbers.append(float(v))
                except (TypeError, ValueError):
                    numbers = None
                    break
            if numbers and len(numbers) > 2:
                shown = "%g–%g" % (min(numbers), max(numbers))
            else:
                shown = ", ".join(list(dict.fromkeys(values))[:3])
            ontology = group[0].get("trait_ontology")
            label = ("<a href=\"%s\">%s</a>" % (e(ontology), e(trait))) if has(ontology) else e(trait)
            calls = sorted({r["call_type"] for r in group if has(r.get("call_type"))})
            bits = [b for b in ("%d measurements" % len(group) if len(group) > 1 else "",
                                ", ".join(calls)) if b]
            w("<div class=\"trait\"><h3>%s</h3><p class=\"vals\"><a href=\"#t-%s\">%s</a></p>%s</div>" %
              (label, slug(trait), e(shown),
               ("<p class=\"qual\">%s</p>" % e(" · ".join(bits))) if bits else ""))
        w("</div>")

        # the measurements themselves, which the cards only summarise
        rows = records.get("traits", [])
        w("<h3 class=\"sub\">Measurements</h3>")
        w("<p class=\"note\">Every value behind the summaries above. Each links to its own record "
          "in the API, which carries the reference it was taken from.</p>")
        w("<div class=\"scroll\"><table class=\"grid\"><thead><tr><th>Trait</th><th>Value</th>"
          "<th>Call</th><th>Part</th><th>Sex</th><th>Temp.</th><th>Source</th></tr></thead><tbody>")
        shown_rows = 0
        for trait, group in sorted(by_trait.items(), key=lambda kv: -len(kv[1])):
            for i, r in enumerate(group):
                if shown_rows >= TRAIT_ROW_CAP:
                    break
                anchor = (" id=\"t-%s\"" % slug(trait)) if i == 0 else ""
                w("<tr%s><td>%s</td><td class=\"n\"><a href=\"%s/trait/%s/%s\">%s</a></td>"
                  "<td>%s</td><td>%s</td><td>%s</td><td class=\"n\">%s</td><td>%s</td></tr>" % (
                    anchor, e(trait) if i == 0 else "",
                    API, e(r.get("source")), e(r.get("id")), e(r.get("value") or "—"),
                    e(r.get("call_type") or ""), e(r.get("call_part") or ""),
                    e(r.get("sex") or ""), e(r.get("temperature") or ""),
                    source_mark(r.get("source"))))
                shown_rows += 1
        w("</tbody></table></div>")
        if len(rows) > shown_rows:
            w("<p class=\"more\">%s more measurements in the "
              "<a href=\"https://audioblast.org/?page=traitstaxa&amp;%s=%s\">audioBlast browser</a>.</p>"
              % (format(len(rows) - shown_rows, ","), e(rank), e(name)))
        w("</div></section>")

    # recordings -------------------------------------------------------------------------------
    recordings = records.get("recordings", [])
    if recordings:
        named = [r for r in recordings if has(r.get("name"))][:12]
        w("<section><div class=\"wrap\"><h2>Recordings</h2>")
        w("<p class=\"note\">%s in audioBlast.</p><div class=\"recs\">" % format(counts.get("recordings", 0), ","))
        for r in named:
            w("<div class=\"rec\"><div class=\"t\">%s</div><div class=\"d\">%s</div><div class=\"m\">" %
              (e(r["name"]), (e(r.get("duration")) + " s") if has(r.get("duration")) else ""))
            for bit in [e(r.get("author")) if has(r.get("author")) else "",
                        e(r.get("date")) if has(r.get("date")) else "",
                        source_mark(r.get("source"))]:
                if bit:
                    w("<span>%s</span>" % bit)
            w("<span><a href=\"%s/?source=%s&amp;id=%s\">listen ›</a></span>" %
              (VIEWER, e(r.get("source")), e(r.get("id"))))
            w("<span>%s</span>" % record("recording", r, "record"))
            if has(r.get("info_url")):
                w("<span>%s</span>" % at_source(r, "at source").strip())
            w("</div></div>")
        w("</div>")
        if counts.get("recordings", 0) > len(named):
            w("<p class=\"more\">%s more in the <a href=\"https://audioblast.org/?page=recordingstaxa&amp;%s=%s\">"
              "audioBlast browser</a>.</p>" % (format(counts["recordings"] - len(named), ","), e(rank), e(name)))
        w("</div></section>")

    # annotations -------------------------------------------------------------------------------
    annotations = records.get("annotations", [])
    if annotations:
        w("<section><div class=\"wrap\"><h2>Annotations</h2>")
        w("<p class=\"note\">Regions of a recording marked as this taxon, by a person or by an "
          "algorithm.</p>")
        w("<div class=\"scroll\"><table class=\"grid\"><thead><tr><th>Recording</th><th>From</th>"
          "<th>To</th><th>Type</th><th>Annotator</th><th>Record</th></tr></thead><tbody>")
        for a in annotations[:25]:
            w("<tr><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td>"
              "<td>%s</td><td>%s</td><td class=\"n\">%s</td></tr>" % (
                e(a.get("source_id") or "—"), e(a.get("time_start") or "—"),
                e(a.get("time_end") or "—"), e(a.get("type") or "—"),
                e(a.get("annotator") or "—"),
                record("annotation", a, "view", id_field="annotation_id")))
        w("</tbody></table></div></div></section>")

    # figures ----------------------------------------------------------------------------------
    images = [i for i in linked.get("images", []) if i.get("_live")]
    if images:
        w("<section><div class=\"wrap\"><h2>Figures</h2>")
        w("<p class=\"note\">Oscillograms, traces and photographs held against this taxon.</p><div class=\"figs\">")
        for i in images:
            w("<figure><img src=\"%s\" alt=\"%s\" loading=\"lazy\" width=\"%s\" height=\"%s\">"
              "<figcaption><b>%s</b><span>%s</span></figcaption></figure>" %
              (e(i.get("url")), e("%s: %s" % (i.get("kind"), i.get("title"))),
               e(i.get("width")), e(i.get("height")), e(i.get("kind")),
               record("image", i, i.get("title"))))
        w("</div></div></section>")

    # navigation -------------------------------------------------------------------------------
    w("<section><div class=\"wrap\"><h2>Browse</h2>")
    w("<p class=\"note\">Counts are recordings at or below each taxon, so an empty branch shows as "
      "empty before you click it. A dash means the join view holds no column for that rank and "
      "cannot roll up to it.</p><div class=\"nav\">")
    # Up as well as down and across: the breadcrumb is chrome at the top of the page, and someone
    # reading the browse section should be able to climb from it without going back up there
    ancestors = list(reversed(lineage[:-1]))
    groups = (("Higher classification", ancestors, "This is the root of the classification."),
              ("Contains", children, "Nothing below this taxon in audioBlast."),
              ("Alongside", siblings, "No sibling taxa held."))
    for heading, group, empty in groups:
        w("<div><h3>%s</h3>" % heading)
        if group:
            w("<ul>")
            for child in group:
                n = child_counts.get(child["id"])
                w("<li><a href=\"%s\">%s <span class=\"n\">%s</span></a></li>" %
                  (path_for(child), name_html(child["taxon"], child.get("rank")),
                   format(n, ",") if n else "—"))
            w("</ul>")
        else:
            w("<p class=\"none\">%s</p>" % e(empty))
        w("</div>")
    w("</div></div></section>")

    # specimens and references -----------------------------------------------------------------
    specimens = linked.get("specimens", [])
    if specimens:
        w("<section><div class=\"wrap\"><h2>Specimens</h2>")
        w("<p class=\"note\">Occurrences the recordings are of, in Darwin Core terms.</p>")
        w("<div class=\"scroll\"><table class=\"grid\"><thead><tr><th>Catalogue</th><th>Institution</th>"
          "<th>Basis</th><th>Sex</th><th>Life stage</th></tr></thead><tbody>")
        for sp in specimens:
            w("<tr><td class=\"n\">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                record("specimen", sp, sp.get("catalogNumber") or sp.get("id")),
                e(sp.get("institutionCode") or "—"), e(sp.get("basisOfRecord") or "—"),
                e(sp.get("sex") or "—"), e(sp.get("lifeStage") or "—")))
        w("</tbody></table></div></div></section>")

    references = linked.get("references", [])
    if references:
        w("<section><div class=\"wrap\"><h2>References</h2>")
        w("<p class=\"note\">Publications audioBlast links to this taxon.</p><ul class=\"refs\">")
        for r in sorted(references, key=lambda x: str(x.get("year") or "")):
            where = ", ".join(str(x) for x in (r.get("journal") or r.get("booktitle"),
                                               r.get("volume"), r.get("pages")) if has(x))
            w("<li><span class=\"who\">%s (%s)</span> %s%s%s</li>" % (
                e(r.get("author") or "Anon."), e(r.get("year") or "n.d."),
                record("reference", r, r.get("title") or "untitled"),
                ("<br><span class=\"where\">%s</span>" % e(where)) if where else "",
                ("<br><a href=\"https://doi.org/%s\">doi:%s</a>" % (e(r["doi"]), e(r["doi"])))
                if has(r.get("doi")) else ""))
        w("</ul></div></section>")

    # sources ----------------------------------------------------------------------------------
    w("<section><div class=\"wrap\"><h2>Sources</h2>")
    w("<p class=\"note\">The rows audioBlast holds for this taxon, each matched to the same Catalogue of "
      "Life node. Where a source classifies it differently, its own classification is kept.</p>")
    w("<div class=\"scroll\"><table class=\"grid\"><thead><tr><th>Source</th><th>Its name</th><th>Its rank</th>"
      "<th>Its family</th><th>Record</th></tr></thead><tbody>")
    for s in sources:
        w("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
          "<td class=\"n\"><a href=\"%s/taxon/%s/%s\">%s/%s</a></td></tr>" %
          (source_mark(s["source"]), name_html(s["taxon"], s.get("rank")), e(s.get("rank") or "—"),
           e(s.get("family") or "—"), API, e(s["source"]), e(s["id"]), e(s["source"]), e(s["id"])))
    w("</tbody></table></div></div></section>")

    # machine-readable -------------------------------------------------------------------------
    w("<section><div class=\"wrap\"><h2>Machine-readable</h2>")
    w("<p class=\"note\">Bioschemas is in the head of this page. The Darwin Core RDF lives at the API "
      "address below, which negotiates JSON-LD and Turtle.</p>")
    w("<details><summary>Bioschemas Taxon, as embedded</summary><pre>%s</pre></details>" %
      e(json.dumps(schema_for(node, vernacular, lineage), indent=2, ensure_ascii=False)))
    w("</div></section>")

    # footer -----------------------------------------------------------------------------------
    w("<footer><div class=\"wrap\">")
    w("<p>Built from the <a href=\"%s\">audioBlast API</a>. Classification from the Catalogue of Life%s, "
      "records from the sources listed above.</p>" % (API, (" (%s)" % e(release)) if release else ""))
    w("<p class=\"iri\">%s/taxon/CoL/%s</p>" % (API, e(node["id"])))
    w("</div></footer>\n</body>\n</html>")
    return "\n".join(out)


def index(pages, roots, stats, changed):
    """
    The way in. It lists only taxa that have been built, so the front of the site can never point
    at a page that does not exist: the roots of whatever has been built, and, while the site is
    small enough to show whole, everything else grouped by rank.
    """
    out = []
    w = out.append
    w("<!doctype html>" + chr(10) + "<html lang=\"en\">" + chr(10) + "<head>" + chr(10) + "<meta charset=\"utf-8\">")
    w("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    w("<title>browse.acousti.cloud</title>")
    w("<meta name=\"description\" content=\"A page for each taxon audioBlast holds recordings, "
      "traits and annotations of, built from the audioBlast API.\">")
    w("<link rel=\"canonical\" href=\"%s/\">" % SITE)
    w("<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>")
    w("<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?"
      "family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&"
      "family=Spectral:ital,wght@0,400;0,600;1,400;1,600&display=swap\">")
    w("<style>%s</style>" % STYLE)
    w("</head>" + chr(10) + "<body>")

    w("<header class=\"masthead\"><div class=\"wrap\">")
    w("<p class=\"rank\">browse.acousti.cloud</p>")
    w("<h1>The sounds we hold, by taxon</h1>")
    w("<p class=\"lede\">A page for every taxon <a href=\"https://audioblast.org\">audioBlast</a> "
      "holds recordings, traits or annotations of. Classification follows the "
      "<a href=\"https://www.catalogueoflife.org\">Catalogue of Life</a>; the records come from the "
      "collections audioBlast draws on, each keeping its own account of what a taxon is.</p>")
    w("</div></header>")

    w("<div class=\"glance\"><div class=\"wrap\">")
    for n, label in stats:
        w("<div><b>%s</b> <span>%s</span></div>" % (format(n, ","), e(label)))
    w("</div></div>")

    held = {node["taxon"]: (node, count) for node, count in pages}
    groups = [(label,) + held[taxon] for taxon, label in HUMAN_GROUPS if taxon in held]
    if groups:
        w("<section><div class=\"wrap\"><h2>Listen to</h2>")
        w("<p class=\"note\">Recordings at or below each group.</p><ul class=\"groups\">")
        for label, node, count in groups:
            w("<li><a href=\"%s\"><span class=\"what\">%s</span>"
              "<span class=\"sci\">%s</span><span class=\"n\">%s</span></a></li>"
              % (path_for(node), e(label), name_html(node["taxon"], node.get("rank")),
                 format(count, ",")))
        w("</ul></div></section>")

    w("<section><div class=\"wrap\"><h2>%s</h2>" % ("The whole tree" if groups else "Start here"))
    w("<p class=\"note\">%s</p>" % ("Every taxon audioBlast holds, from the top."
                                     if groups else "Counts are recordings at or below each taxon."))
    w("<div class=\"nav\"><div><ul>")
    for node, count in roots:
        w("<li><a href=\"%s\">%s <span class=\"n\">%s</span></a></li>" % (
            path_for(node), name_html(node["taxon"], node.get("rank")),
            format(count, ",") if count else "—"))
    w("</ul></div></div></div></section>")

    if len(pages) < SHOW_ALL_BELOW:
        w("<section><div class=\"wrap\"><h2>Every page</h2>")
        w("<p class=\"note\">%d built so far. The <a href=\"/sitemap.xml\">sitemap</a> lists "
          "them all.</p>" % len(pages))
        by_rank = {}
        for node, count in pages:
            by_rank.setdefault((node.get("rank") or "").lower(), []).append((node, count))
        order = ["domain", "kingdom", "phylum", "subphylum", "class", "order", "suborder",
                 "infraorder", "superfamily", "family", "subfamily", "tribe", "genus",
                 "species", "subspecies"]
        for rank in sorted(by_rank, key=lambda r: (order.index(r) if r in order else 99, r)):
            group = sorted(by_rank[rank], key=lambda pair: pair[0]["taxon"])
            w("<h3 class=\"sub\">%s</h3><ul class=\"tiles\">" % e(rank or "unranked"))
            for node, count in group:
                w("<li><a href=\"%s\">%s <span class=\"n\">%s</span></a></li>" % (
                    path_for(node), name_html(node["taxon"], node.get("rank")),
                    format(count, ",") if count else "\u2014"))
            w("</ul>")
        w("</div></section>")
    elif pages and not groups:
        already = set()
        for node, _ in roots:
            already.add(node["id"])
        picked = [(node, count) for node, count in pages
                  if (node.get("rank") or "").lower() in ENTRY_RANKS
                  and node["id"] not in already and count]
        picked.sort(key=lambda pair: -pair[1])
        w("<section><div class=\"wrap\"><h2>Major groups</h2>")
        w("<p class=\"note\">Where most of the recordings are, of %s pages built. Every one is "
          "in the <a href=\"/sitemap.xml\">sitemap</a>, and each page leads to what sits above, "
          "below and beside it.</p>" % format(len(pages), ","))
        w("<ul class=\"tiles\">")
        for node, count in picked[:ENTRIES]:
            w("<li><a href=\"%s\">%s <span class=\"n\">%s</span></a></li>" % (
                path_for(node), name_html(node["taxon"], node.get("rank")),
                format(count, ",")))
        w("</ul></div></section>")

    w("<footer><div class=\"wrap\">")
    w("<p>Built %s from the <a href=\"%s\">audioBlast API</a>. "
      "Source at <a href=\"https://github.com/acoustiCloud/browse.acousti.cloud\">GitHub</a>.</p>"
      % (e(changed), API))
    w("</div></footer>" + chr(10) + "</body>" + chr(10) + "</html>")
    return chr(10).join(out)


def sitemap(paths, changed):
    """A sitemap of every page built, which is what a static site can offer in place of a crawl."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in sorted(paths):
        out.append("  <url><loc>%s%s</loc><lastmod>%s</lastmod></url>" % (SITE, path, changed))
    out.append("</urlset>")
    return "\n".join(out)
