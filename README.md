# Saybit converted data

Dictionary and word-list files converted for **Saybit**, an iPhone vocabulary notebook by Vivory Lab
(English, Chinese, Japanese and Korean). The app ships these files as separate resource files next to the app binary.
They are published here so that anyone can get, read, change and share the converted files under the licenses of the
data they come from, without the App Store.

This is a good-faith step to follow the license terms. It is not a claim that every licensing question about App
Store distribution is settled.

## Download

The data files are in [`data/`](data), one folder per data version, with the same layout the app uses
(`Lexicon/*.sqlite`, `Packs/*.json`). Each folder has `SHA256SUMS.txt` (sha256, size in bytes, path) and
`EDITIONS.md` (the edition of each source).

| Data version | Shipped in | Folder |
|---|---|---|
| 2026-10-29.2 | Saybit 1.0.0 (21) (also TestFlight (18) to (20)) | [`data/2026-10-29.2`](data/2026-10-29.2) |
| 2026-10-29.1 | TestFlight builds 1.0.0 (11) to (17) only | [`data/2026-10-29.1`](data/2026-10-29.1) |

## Sources, licenses and what we changed

| File | Source | License | What we changed |
|---|---|---|---|
| `Lexicon/cedict.sqlite` | [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict), MDBG | [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt) | Converted to SQLite: simplified and traditional forms, numbered-tone pinyin and English glosses, plus a lookup table of written forms |
| `Lexicon/jmdict.sqlite` | [JMdict](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project) common words, Electronic Dictionary Research and Development Group, via [jmdict-simplified](https://github.com/scriptin/jmdict-simplified) | [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt) and the [EDRDG licence](licenses/EDRDG-licence.txt) | Converted to SQLite: written forms, kana readings, English glosses and JMdict entry numbers, plus a lookup table of written forms |
| `Lexicon/krdict.sqlite` | [Basic Korean Dictionary](https://krdict.korean.go.kr), National Institute of Korean Language | [CC BY-SA 2.0 KR](licenses/CC-BY-SA-2.0-KR.txt) ([terms](https://krdict.korean.go.kr/kor/kboardPolicy/copyRightTermsInfo)) | Converted to SQLite: headwords, pronunciations, levels and English, Japanese and Chinese equivalents, plus a reverse-lookup table. Text only: no sound or picture files |
| `Lexicon/examples.sqlite` | [Tatoeba](https://tatoeba.org) sentences and human translations; Korean examples also from the Basic Korean Dictionary | Tatoeba parts: [CC BY 2.0 FR](licenses/CC-BY-2.0-FR.txt). Basic Korean Dictionary parts: [CC BY-SA 2.0 KR](licenses/CC-BY-SA-2.0-KR.txt) | One example per word with its Korean and English translation when a human translation exists. Each row keeps its source number (`tatoeba:<sentence>` or `krdict:<entry>`), so the author of each Tatoeba sentence can be found on tatoeba.org |
| `Packs/*.json` (everyday-word lists `xx-1..3`) | English: [New General Service List 1.2](https://www.newgeneralservicelist.com/new-general-service-list) (Browne, C., Culligan, B., & Phillips, J.). Korean: [Korean Learner Vocabulary List](https://www.korean.go.kr) (National Institute of Korean Language, 2003). Chinese and Japanese order: [wordfreq](https://github.com/rspeer/wordfreq) data (Robyn Speer) including the sources wordfreq credits. Meanings, readings and examples from the dictionaries and Tatoeba above | NGSL and wordfreq: [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt). Korean list: [KOGL Type 1](licenses/KOGL-Type-1.txt). Dictionary and Tatoeba parts: as above | Chose and ordered words, joined meanings, readings and example sentences; applied the hand-reviewed corrections in `Tools/pack_overrides/` |
| `Packs/*-conv-*.json` (conversation lists) | Order: [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (Hermit Dave), word counts from the [OpenSubtitles 2018](https://opus.nlpl.eu/OpenSubtitles.php) corpus via OPUS, combined with how often words appear in Tatoeba sentences. Korean: the Korean Learner Vocabulary List in that order. Meanings, readings and examples from the dictionaries and Tatoeba above | FrequencyWords content: [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt). Korean list: [KOGL Type 1](licenses/KOGL-Type-1.txt). Dictionary and Tatoeba parts: as above | Turned subtitle word forms back into dictionary forms, dropped names, swear words and function-word fragments, and dropped rows with no Korean or English meaning. No subtitle text is included |
| `Packs/en-toeic-*.json`, `Packs/en-toefl-*.json` (TOEIC and TOEFL prep lists) | [TOEIC Service List 1.2](https://www.newgeneralservicelist.com/toeic-service-list) and [Business Service List 1.2](https://www.newgeneralservicelist.com/business-service-list) (Browne, C. & Culligan, B.); [New Academic Word List 1.2](https://www.newgeneralservicelist.com/new-academic-word-list) (Browne, C., Culligan, B., & Phillips, J.), ordered by wordfreq | [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt) | Split into levels by rank, joined meanings and example sentences as above |
| `Packs/zh-hsk-*.json` (HSK prep lists) | HSK 2.0 level vocabulary as compiled in [complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (Yanis Zafirópulos) | [MIT](licenses/MIT-complete-hsk-vocabulary.txt). Readings and English from CC-CEDICT: as above | Took the level of each word and its in-level frequency; readings and English glosses were looked up again in CC-CEDICT |
| `Packs/ja-jlpt-*.json` (JLPT prep lists, N5 to N1 level) | The unofficial JLPT level lists by Jonathan Waller ([tanos.co.uk](https://www.tanos.co.uk/jlpt/sharing/)), via the JSON copy [Bluskyo/JLPT_Vocabulary](https://github.com/Bluskyo/JLPT_Vocabulary) | Lists: [CC BY 4.0](licenses/CC-BY-4.0.txt) as credited in the app. JSON copy: [MIT](licenses/MIT-JLPT_Vocabulary.txt). Readings and English from JMdict: as above | Took the level of each word; readings and English glosses were looked up again in JMdict |
| `Packs/ko-topik-*.json` (TOPIK prep lists) | Grades A, B and C of the Korean Learner Vocabulary List (National Institute of Korean Language, 2003), shown as TOPIK I level, TOPIK II intermediate and advanced. There is no official TOPIK word list | [KOGL Type 1](licenses/KOGL-Type-1.txt). Dictionary and Tatoeba parts: as above | Grouped by grade, joined meanings and example sentences as above |

The exam-prep lists are built from open word lists. They are not official lists and are not affiliated with any exam
provider; exam names are trademarks of their owners.

Our adaptations of CC BY-SA material are released under CC BY-SA 4.0, and the original licenses above keep applying to
the parts that come from each source. Please keep the attributions when you share the files.

The files are provided as they are, without warranties of any kind. The original authors do not endorse Saybit or this
repository.

## Rebuild

`fetch-lexicon.sh` and `Tools/` are the scripts the app build runs (copied from the app source tree, same relative
layout). `fetch-lexicon.sh` downloads each source, checks it against a pinned sha256 where the source publishes fixed
versions, and runs `Tools/build_lexicon.py` and `Tools/build_packs.py`. Outputs land in `Vocab/Resources/Lexicon` and
`Vocab/Resources/Packs`. `Vocab/Packs/PackManifest.json` is the list of word lists the app shows.

The scripts here match the newest data version. The scripts for an earlier version are in this repository's git
history (2026-10-29.1 = commit `4b22d6a`).

- CC-CEDICT and Tatoeba publish only their latest export, so a rebuild today may differ from a release here. The
  editions used are listed above.
- The Basic Korean Dictionary site may refuse scripted downloads. Download the JSON export from krdict.korean.go.kr in
  a browser and place it at `$VOCAB_LEXICON_CACHE/src/krdict-json.zip` (default cache `~/Library/Caches/vocab-lexicon`).

The scripts are under the [MIT license](licenses/MIT.txt). They contain no dictionary data.

## Contact

contact@vivory.app
