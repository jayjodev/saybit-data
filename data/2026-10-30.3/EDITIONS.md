# Data version 2026-10-30.3

First shipped in Saybit 1.0.0 (26) for iPhone (TestFlight) and 1.0.0 (3) for Android (internal test). Built by the app's
`fetch-lexicon.sh` from the same sources and editions as 2026-10-29.2. The dictionaries (`cedict`, `jmdict`, `krdict`) are the
same files. Compared with 2026-10-30.2, reviewed corrections in `Tools/pack_overrides` changed 36 entries after a check of
examples that do not contain their headword: 8 Korean examples that belonged to another word were removed (갈다, 놓다, 낳다,
벌다, 낫다, 고르다, 긋다, 두르다), 22 Japanese Korean-meanings were corrected or filled in (for example しゃべる, 温まる, ぐらい,
まいる, 就く, 湧く, 九つ, よす) and 6 Japanese examples that belonged to another word were removed. One more Korean entry
(신중하다) picked up a freed example that fits it. 57 lines changed across the lists; word counts are unchanged.

| Source | Edition | Source file sha256 |
|---|---|---|
| CC-CEDICT (MDBG) | 2026-10-27 export, 125,326 entries | `347499200f7eb34a922993fc71397d4033845096a8ca070b760ec200ff9be2ed` |
| JMdict common words (EDRDG), via jmdict-simplified 3.6.2 | 2026-10-26, 22,649 entries | `b5468172549cdc5b0be5ab49320805bc594d11344593fca66aaf59d11242983a` |
| Basic Korean Dictionary (National Institute of Korean Language) | 20261019 JSON export, 51,555 entries used | `c8f9ffbf7e9be1f1ec86fa29e4160a75eee8044fc081c27788dadf3ceb66d34e` |
| Tatoeba | weekly per-language export, downloaded 2026-10-29 | listed in `fetch-lexicon.sh` (`TATOEBA_FILES`) |
| New General Service List 1.2 | 1.2 | listed in `fetch-lexicon.sh` (`NGSL_SHA`, `NGSL_FORMS_SHA`) |
| TOEIC Service List 1.2 | 1.2 | listed in `fetch-lexicon.sh` (`TSL_SHA`, `TSL_FORMS_SHA`) |
| Business Service List 1.2 | 1.2 | listed in `fetch-lexicon.sh` (`BSL_SHA`, `BSL_FORMS_SHA`) |
| New Academic Word List 1.2 | 1.2 | listed in `fetch-lexicon.sh` (`NAWL_SHA`) |
| complete-hsk-vocabulary (HSK 2.0 levels 1 to 6) | commit `7ac65bf1a6387d35f1ade478906172a19311c7f9` | listed in `fetch-lexicon.sh` (`HSK_SHA`) |
| JLPT level vocabulary (Jonathan Waller), JSON copy Bluskyo/JLPT_Vocabulary | commit `4358f932937ad0232194a36e9f4f875094910c6b` | listed in `fetch-lexicon.sh` (`JLPT_SHA`) |
| FrequencyWords (hermitdave), OpenSubtitles 2018 | commit `525f9b560de45753a5ea01069454e72e9aa541c6` | listed in `fetch-lexicon.sh` (`SUBS_FILES`) |
| Korean Learner Vocabulary List (National Institute of Korean Language) | 2003 | listed in `fetch-lexicon.sh` (`NIKL_SHA`) |
| wordfreq | 3.1.1 | listed in `fetch-lexicon.sh` (`WORDFREQ_SHA`) |

Word lists (40, the list of record is `Vocab/Packs/PackManifest.json`):

| Lists | Words |
|---|---|
| Everyday words `en-1..3` | 500 / 1,000 / 1,302 |
| Everyday words `zh-1..3`, `ja-1..3`, `ko-1..3` | 500 / 1,000 / 1,500 each |
| Conversation `en-conv-1..2`, `zh-conv-1..2`, `ja-conv-1..2`, `ko-conv-1..2` | 500 / 1,000 each |
| TOEIC prep `en-toeic-1..4` (Basic, Intermediate, Advanced, Business) | 343 / 324 / 335 / 822 |
| TOEFL prep `en-toefl-1..2` | 374 / 373 |
| HSK prep `zh-hsk-1..6` (HSK 2.0 levels 1 to 6) | 146 / 146 / 297 / 591 / 1,288 / 2,461 |
| JLPT prep `ja-jlpt-1..5` (N5 to N1 level) | 621 / 591 / 1,562 / 1,619 / 2,593 |
| TOPIK prep `ko-topik-1..3` (TOPIK I level, TOPIK II level intermediate, advanced) | 894 / 2,005 / 2,737 |

The exam-prep lists are built from open word lists. They are not official lists and are not affiliated with any exam
provider; exam names are trademarks of their owners.

Licenses and what we changed: see the repository [README](../../README.md).
