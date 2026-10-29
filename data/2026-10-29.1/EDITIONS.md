# Data version 2026-10-29.1

Shipped in Saybit 1.0.0 (11) for iPhone. Built by the app's `fetch-lexicon.sh` from the sources below.

| Source | Edition | Source file sha256 |
|---|---|---|
| CC-CEDICT (MDBG) | 2026-10-27 export, 125,326 entries | `347499200f7eb34a922993fc71397d4033845096a8ca070b760ec200ff9be2ed` |
| JMdict common words (EDRDG), via jmdict-simplified 3.6.2 | 2026-10-26, 22,649 entries | `b5468172549cdc5b0be5ab49320805bc594d11344593fca66aaf59d11242983a` |
| Basic Korean Dictionary (National Institute of Korean Language) | 20261019 JSON export, 51,555 entries used | `c8f9ffbf7e9be1f1ec86fa29e4160a75eee8044fc081c27788dadf3ceb66d34e` |
| Tatoeba | weekly per-language export, downloaded 2026-10-29 | listed in `fetch-lexicon.sh` (`TATOEBA_FILES`) |
| New General Service List 1.2 | 1.2 | listed in `fetch-lexicon.sh` (`NGSL_SHA`, `NGSL_FORMS_SHA`) |
| Korean Learner Vocabulary List (National Institute of Korean Language) | 2003 | listed in `fetch-lexicon.sh` (`NIKL_SHA`) |
| wordfreq | 3.1.1 | listed in `fetch-lexicon.sh` (`WORDFREQ_SHA`) |

Word lists: `en-*` 500 / 1,000 / 1,302 words, `zh-*`, `ja-*` and `ko-*` 500 / 1,000 / 1,500 words each.
Licenses and what we changed: see the repository [README](../../README.md).
