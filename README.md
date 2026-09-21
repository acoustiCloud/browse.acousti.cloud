# browse.acousti.cloud

Static pages for the records held in [audioBlast](https://audioblast.org), one page per taxon,
built from the [audioBlast API](https://api.audioblast.org) and served from GitHub Pages.

A page here is a document: no script, no runtime call to the API, nothing that has to succeed
after it is served. Whatever it knows was settled when it was built.

This is not [view.audioblast.org](https://view.audioblast.org), which is a workbench for analysing
one recording. These pages are the citable, indexable record of a taxon, and they link out to the
viewer for the analysis.

## Building

Needs Python 3 and nothing else.

```
cd build
py build.py "Gryllotalpa vineae"              one taxon
py build.py "Gryllotalpidae" --deep           that taxon and everything below it
```

Pages are written to `docs/taxon/<slug>/index.html`, and `docs/sitemap.xml` lists what was built.
A page costs about 40 requests and three seconds, so a large build is bounded by the number of
requests rather than by anything complicated.

## How a page is put together

The Catalogue of Life rows in the API are the spine. Each is one taxon, with `parent_id` giving a
tree that runs to the domain and carries ranks the flattened columns cannot hold — *Gryllidea*
(infraorder) and *Gryllotalpoidea* (superfamily) appear in the classification of a mole cricket and
in no column.

Every other source's rows hang off that spine through `skos:exactMatch`, so a taxon held twice by
one source, or under two names by two sources, is one page here. Each source keeps its own
classification, and where they disagree the page shows both rather than choosing.

Records reach a taxon by name, because that is how `recordingstaxa`, `traits` and `annomate` hold
them. The names come from the source rows, so the join is name → source row → CoL node, never a
name on its own.

## Two things the build does deliberately

**Recordings come from `recordingstaxa`, not `recordings`.** The `taxon` field on `recordings` is
full-text, so filtering it returns anything sharing a word: 921 rows for *Gryllotalpa vineae*
where the join view gives the ones actually of it.

**Image files are checked before they are shown.** audioBlast holds metadata for images whose
source no longer serves the file — four of seven for *Gryllotalpa vineae* answer 403. A build is
the one chance to notice before a reader meets a broken figure.

## URLs

`/taxon/<slug>/`, where the slug folds diacritics and collapses punctuation. A hybrid sign becomes
an `x` rather than vanishing, because the sources write hybrids both ways and dropping it would
make `Anaxyrus americanus × fowleri` look like a trinomial.

Checked against all 20,180 distinct names in audioBlast: four slugs collide, each a pair of rows
differing only in a capital letter or a question mark.

## Layout

```
build/   api.py      reading audioBlast
         render.py   one taxon page, and the sitemap
         build.py    what to build, and writing it out
docs/    the built site. GitHub Pages serves a branch from its root or from /docs,
         and nowhere else, so that is the name.
```

`docs/` is committed: GitHub Pages serves what is in the repository, so the build output belongs
in it.
