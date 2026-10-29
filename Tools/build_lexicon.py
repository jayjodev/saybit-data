#!/usr/bin/env python3
"""단어장(ios/vocab) 기기 안 사전 셋을 만든다. 파이썬 표준 라이브러리만(맥 러너의 /usr/bin/python3 3.9 에서도 돈다).

명세 = docs/claude/roadmap/vocab/02-engineering.md 5절(뜻 · 읽기 채우기 · 싣는 사전 · 한국어기초사전) · 원장 D20 · D21 · D33 · D38.
측정 원본 = docs/claude/roadmap/vocab/tools/lexicon/{cedict_pack,jmdict_pack,krdict_measure,pack_coverage}.py.

  cedict.sqlite  CC-CEDICT(MDBG, CC BY-SA 4.0)  간체 · 번체 · 숫자 성조 병음 · 영어 풀이
  jmdict.sqlite  JMdict 흔한 말(EDRDG, CC BY-SA 4.0, jmdict-simplified)  표기 · 가나 · 영어 풀이 · 항목 번호
  krdict.sqlite  국립국어원 한국어기초사전(CC BY-SA 2.0 KR)  표제어 · 발음 · 등급 · 영 · 일 · 중 대역 + 거꾸로 찾기 표

판마다 meta 표에 원천 이름 · 판(날짜) · 라이선스 · 주소 · 원본 sha256 을 적는다(설정 '자료 출처' 화면이 읽는다).
만든 파일은 저장소에 넣지 않는다 = ios/vocab/fetch-lexicon.sh 가 CI 맥의 캐시에서 Vocab/Resources/Lexicon/ 에 둔다.
--fixture <단어 목록> = 단위 시험용 작은 판(VocabTests/Fixtures/fixture-*.sqlite, 수십 항목, 이것만 커밋한다).

실행: python3 -I build_lexicon.py --cedict cedict.txt.gz --jmdict jmdict-eng-common.json.tgz [--krdict krdict-json.zip] --out DIR
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import zipfile

# 표 모양이 바뀌면 올린다(앱 LexiconDB 가 meta format 을 본다).
FORMAT = "1"
# 중국어 풀이는 항목마다 앞에서 셋까지(02-engineering 5.2 '풀이 3개 이하로 줄이는 판은 M3 에서 다시 잼' = 이 판).
CEDICT_MAX_GLOSS = 3
# 일본어 풀이 = 읽기마다 뜻 셋까지 · 뜻마다 풀이 셋까지(jmdict_pack.py 와 같다).
JMDICT_MAX_SENSES = 3
JMDICT_MAX_GLOSS = 3

CEDICT_LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\] /(.*)/\s*$")
CEDICT_DATE = re.compile(r"^#! date=(\d{4}-\d{2}-\d{2})")
# 뜻이 아니라 다른 항목을 가리키는 풀이(이체자 · 참조 · 성씨). 이것만 있는 읽기는 뒤로 보낸다.
CEDICT_WEAK = re.compile(r"^((old|archaic|ancient|Japanese|Taiwan|unofficial|erhua|non-standard|incorrect) )*variant of "
                         r"|^see (also )?|^used in |^also written |^abbr\. for ")
CEDICT_SURNAME = re.compile(r"^surname ")
HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
KANA = re.compile(r"^[ぁ-ヿー]+$")
KRDICT_DATE = re.compile(r"_(\d{8})\.json$")

# 한국어기초사전 등급(후보 줄 순서 = 초급 → 중급 → 고급 → 없음, 02-engineering 5.3).
KR_LEVEL = {"초급": 1, "중급": 2, "고급": 3}
# 거꾸로 찾기 표의 언어 번호(앱 KoreanCandidates 와 같은 값).
REV_LANG = {"en": 1, "ja": 2, "zh": 3}


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def open_text(path: str) -> io.TextIOBase:
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, encoding="utf-8")


def new_db(path: str, schema: str, meta: dict) -> sqlite3.Connection:
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.execute("PRAGMA page_size = 4096")
    db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID")
    db.executescript(schema)
    db.executemany("INSERT INTO meta VALUES(?, ?)", [(k, str(v)) for k, v in meta.items()])
    return db


def finish(db: sqlite3.Connection, path: str, counts: dict) -> None:
    db.executemany("INSERT OR REPLACE INTO meta VALUES(?, ?)", [(k, str(v)) for k, v in counts.items()])
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"{os.path.basename(path)}: {', '.join(f'{k}={v}' for k, v in counts.items())} · {os.path.getsize(path) / 1e6:.2f}MB")


# ── 고정판(단위 시험) 단어 목록 ─────────────────────────────────────────────

def read_fixture(path: str) -> dict:
    """줄마다 '언어 단어'(zh 学习 · ja 今日 · ko 공부). 'rev 언어 낱말' = 그 낱말을 대역어로 가진 한국어 항목까지(거꾸로 찾기 시험).
    # 뒤는 주석."""
    words = {"zh": set(), "ja": set(), "ko": set(), "en": set(), "rev": {"en": set(), "zh": set(), "ja": set()}}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            lang, _, word = line.partition(" ")
            if lang == "rev":
                lang, _, word = word.strip().partition(" ")
                words["rev"][lang].add(word.strip())
            else:
                words[lang].add(word.strip())
    return words


# ── CC-CEDICT ──────────────────────────────────────────────────────────────

def no_dash(text: str) -> str:
    """화면 글에 줄표(U+2014)를 쓰지 않는다(카피 규칙). 사전 풀이 몇 줄에 있는 것을 쌍점 · 쉼표로 바꾼다."""
    return text.replace(" \u2014 ", ": ").replace("\u2014", ", ")


def cedict_glosses(body: str) -> tuple:
    items = [no_dash(g.strip()) for g in body.split("/") if g.strip()]
    kept = [g for g in items if not g.startswith("CL:")] or items[:1]
    flags = 0
    if kept and all(CEDICT_WEAK.match(g) for g in kept):
        flags |= 2
    if kept and all(CEDICT_SURNAME.match(g) for g in kept):
        flags |= 4
    return kept[:CEDICT_MAX_GLOSS], flags


def build_cedict(src: str, out: str, only: set | None) -> None:
    version = ""
    rows = []
    with open_text(src) as handle:
        for line in handle:
            if line.startswith("#"):
                match = CEDICT_DATE.match(line)
                if match:
                    version = match.group(1)
                continue
            match = CEDICT_LINE.match(line)
            if not match:
                continue
            trad, simp, raw_pinyin, body = match.groups()
            if only is not None and simp not in only and trad not in only:
                continue
            glosses, flags = cedict_glosses(body)
            if raw_pinyin[:1].isupper():
                flags |= 1  # 고유 명사(대문자 병음)
            rows.append((simp, trad, raw_pinyin, "/".join(glosses), flags))
    meta = {
        "format": FORMAT, "source": "CC-CEDICT", "publisher": "MDBG", "version": version,
        "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "url": "https://www.mdbg.net/chinese/dictionary?page=cc-cedict", "source_sha256": sha256(src),
    }
    db = new_db(out, """
        -- 한 줄 = CC-CEDICT 한 항목. pinyin = 원본 그대로(대문자 = 고유 명사, u: = ü). 앱이 저장 꼴("nü3 er2")로 바꾸고,
        -- 원본 머리 '번체 간체 [병음]' 을 항목 열쇠로 쓴다(판이 바뀌어도 같은 항목을 가리킨다).
        -- gloss = 풀이를 / 로 이은 것. flags 1 = 고유 명사 · 2 = 이체자 · 참조 풀이만 · 4 = 성씨 풀이만.
        CREATE TABLE entry(id INTEGER PRIMARY KEY, simp TEXT NOT NULL, trad TEXT NOT NULL, pinyin TEXT NOT NULL,
                           gloss TEXT NOT NULL, flags INTEGER NOT NULL);
        -- 표기(간체 · 번체) → 항목. 색인 둘 대신 표 하나(크기).
        CREATE TABLE form(text TEXT NOT NULL, entry INTEGER NOT NULL, PRIMARY KEY(text, entry)) WITHOUT ROWID;
    """, meta)
    db.executemany("INSERT INTO entry(simp, trad, pinyin, gloss, flags) VALUES(?, ?, ?, ?, ?)", rows)
    forms = set()
    for index, (simp, trad, _, _, _) in enumerate(rows, 1):
        forms.add((simp, index))
        forms.add((trad, index))
    db.executemany("INSERT INTO form VALUES(?, ?)", sorted(forms))
    finish(db, out, {"entries": len(rows), "forms": len(forms)})


# ── JMdict 흔한 말 (jmdict-simplified) ──────────────────────────────────────

def load_jmdict(src: str) -> dict:
    if src.endswith((".tgz", ".tar.gz")):
        with tarfile.open(src, "r:gz") as archive:
            member = next(m for m in archive.getmembers() if m.name.endswith(".json"))
            return json.load(archive.extractfile(member))
    if src.endswith(".zip"):
        with zipfile.ZipFile(src) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".json"))
            return json.load(archive.open(name))
    with open(src, encoding="utf-8") as handle:
        return json.load(handle)


def applies(values: list, text: str) -> bool:
    return "*" in values or text in values


def build_jmdict(src: str, out: str, only: set | None) -> None:
    data = load_jmdict(src)
    readings = []   # (rid, seq, kana, gloss, pos, flags)
    forms = {}      # (text, rid) → ord
    rid = 0
    entries = 0
    for word in data["words"]:
        kanji = [k for k in word.get("kanji", []) if "sK" not in k.get("tags", [])]
        if any(k.get("common") for k in kanji):
            kanji = [k for k in kanji if k.get("common")]
        kana = [k for k in word.get("kana", []) if "sk" not in k.get("tags", [])]
        if any(k.get("common") for k in kana):
            kana = [k for k in kana if k.get("common")]
        if not kana:
            continue
        if only is not None:
            texts = {k["text"] for k in kanji} | {k["text"] for k in kana}
            if not texts & only:
                continue
        entries += 1
        senses = word.get("sense", [])
        usually_kana = any("uk" in s.get("misc", []) for s in senses) or not kanji
        for kana_index, reading in enumerate(kana):
            mine = [s for s in senses if applies(s.get("appliesToKana", ["*"]), reading["text"])]
            if not mine:
                continue
            gloss = no_dash("\n".join("; ".join(g["text"] for g in s.get("gloss", [])[:JMDICT_MAX_GLOSS])
                                      for s in mine[:JMDICT_MAX_SENSES]))
            pos = []
            for sense in mine:
                for tag in sense.get("partOfSpeech", []):
                    if tag not in pos:
                        pos.append(tag)
            rid += 1
            readings.append((rid, int(word["id"]), reading["text"], gloss, ",".join(pos), 1 if usually_kana else 0))
            # 표기 → 읽기. 한자 표기 = 그 가나가 붙는 한자 표기마다, 가나 표기 = 가나 자체.
            # ord = 표기 안 순서(작을수록 앞): 흔한 가나 · 첫 가나 먼저, 가나 표기는 '보통 가나로 씀' 항목 먼저.
            common = 0 if reading.get("common") else 5
            for k in kanji:
                if applies(reading.get("appliesToKanji", ["*"]), k["text"]):
                    forms.setdefault((k["text"], rid), common + kana_index)
            forms.setdefault((reading["text"], rid), (0 if usually_kana else 10) + common + kana_index)
    meta = {
        "format": FORMAT, "source": "JMdict", "publisher": "Electronic Dictionary Research and Development Group",
        "version": data.get("dictDate", ""), "converter": f"jmdict-simplified {data.get('version', '')}",
        "license": "CC BY-SA 4.0", "license_url": "https://www.edrdg.org/edrdg/licence.html",
        "url": "https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project", "source_sha256": sha256(src),
        "common_only": "1",
    }
    db = new_db(out, """
        -- reading = JMdict 항목 하나의 가나 하나(같은 표기 다른 읽기 = 다른 줄 = 다른 단어, D33 · 02-engineering 4.4).
        -- seq = JMdict 항목 번호(판이 바뀌어도 같다). gloss = 뜻을 줄바꿈으로, 뜻 안 풀이를 ; 로. flags 1 = 보통 가나로 씀.
        CREATE TABLE reading(id INTEGER PRIMARY KEY, seq INTEGER NOT NULL, kana TEXT NOT NULL, gloss TEXT NOT NULL,
                             pos TEXT NOT NULL, flags INTEGER NOT NULL);
        -- 표기 한 줄 한 행(r1 의 | 잇기 + LIKE 3.3ms 를 버린 꼴, 02-engineering 5.1).
        CREATE TABLE form(text TEXT NOT NULL, reading INTEGER NOT NULL, ord INTEGER NOT NULL,
                          PRIMARY KEY(text, reading)) WITHOUT ROWID;
    """, meta)
    db.executemany("INSERT INTO reading VALUES(?, ?, ?, ?, ?, ?)", readings)
    db.executemany("INSERT INTO form VALUES(?, ?, ?)", [(t, r, o) for (t, r), o in forms.items()])
    finish(db, out, {"entries": entries, "readings": len(readings), "forms": len(forms)})


# ── 한국어기초사전 ──────────────────────────────────────────────────────────

def feats(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        value = [value]
    out = {}
    for feat in value:
        if isinstance(feat, dict) and "att" in feat:
            out.setdefault(feat["att"], feat.get("val"))
    return out


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def clean_equivalent(text: str) -> str:
    text = (text or "").replace("\t", " ").strip()
    if not text or text.startswith("(対訳語無し)") or text in ("-", "."):
        return ""
    return no_dash(" ".join(text.split()))


def en_keys(text: str) -> list:
    """'study; learn' → study · learn(소문자, 괄호 풀이 · 'to ' 빼고). 네 낱말 넘는 풀이는 열쇠로 쓰지 않는다."""
    keys = []
    for part in re.split(r"[;,]", text):
        key = re.sub(r"\s*\([^)]*\)", "", part).strip().strip(".").lower()
        if key.startswith("to ") and len(key) > 3:
            key = key[3:]
        if key and len(key.split()) <= 4:
            keys.append(key)
    return keys


def zh_keys(text: str) -> list:
    keys = []
    for part in re.split(r"[，,、；;／/]", text):
        key = "".join(part.split())
        if key and HAN.search(key) and len(key) <= 8:
            keys.append(key)
    return keys


def ja_keys(text: str) -> list:
    """'しずめる【沈める】。しずませる【沈ませる】' → 沈める · しずめる · 沈ませる · しずませる. 〜する 는 줄기도."""
    keys = []
    for part in re.split(r"[。、；;，,]", text):
        part = part.strip()
        if not part or part.startswith("("):
            continue
        match = re.match(r"^(.*?)【(.*?)】", part)
        # 한자 표기가 있으면 그것만(가나 열쇠는 한자 없는 말에만 = 크기 · 동음 충돌).
        found = [match.group(2).strip()] if match else [part]
        for key in found:
            if not key or len(key) > 12:
                continue
            keys.append(key)
            if key.endswith("する") and len(key) > 2:
                keys.append(key[:-2])
    return keys


def build_krdict(src: str, out: str, only: dict | None) -> None:
    version = ""
    words = []    # (id, form, hom, pos, level, pron, origin)
    senses = []   # (sid, word, ord, en)
    rev = {}      # (lang, key, sid) → 대역어 안 자리(0 = 맨 앞 대역어)
    sid = 0
    skipped_units = 0
    with zipfile.ZipFile(src) as archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            match = KRDICT_DATE.search(info.filename)
            if match:
                version = max(version, match.group(1))
            with archive.open(info) as handle:
                data = json.load(handle)
            for entry in as_list(data["LexicalResource"]["Lexicon"]["LexicalEntry"]):
                ef = feats(entry.get("feat"))
                # 단어만(구 · 관용구 · 속담 · 문법 형태는 단어 뜻 후보로 쓰지 않는다).
                if ef.get("lexicalUnit") != "단어":
                    skipped_units += 1
                    continue
                lemmas = as_list(entry.get("Lemma"))
                form = next((feats(l.get("feat")).get("writtenForm") for l in lemmas
                             if feats(l.get("feat")).get("writtenForm")), None)
                if not form:
                    continue
                form = form.strip()
                pron = ""
                for wf in as_list(entry.get("WordForm")):
                    wff = feats(wf.get("feat"))
                    if wff.get("type") == "발음" and wff.get("pronunciation"):
                        pron = wff["pronunciation"].strip()
                        break
                sense_rows = []
                keys = {}
                for order, sense in enumerate(as_list(entry.get("Sense"))):
                    eq = {}
                    for item in as_list(sense.get("Equivalent")):
                        qf = feats(item.get("feat"))
                        lang = {"영어": "en", "일본어": "ja", "중국어": "zh"}.get(qf.get("language", ""))
                        if lang and lang not in eq:
                            eq[lang] = clean_equivalent(qf.get("lemma", ""))
                    sid += 1
                    sense_rows.append((sid, int(entry["val"]), order, eq.get("en", "")))
                    for lang, split in (("en", en_keys), ("ja", ja_keys), ("zh", zh_keys)):
                        for position, key in enumerate(split(eq.get(lang, ""))):
                            keys.setdefault((REV_LANG[lang], key, sid), min(position, 9))
                if only is not None:
                    wanted = form in only["ko"] or any(
                        key in only["rev"][lang] for (code, key, _) in keys for lang in ("en", "ja", "zh") if REV_LANG[lang] == code)
                    if not wanted:
                        continue
                level = KR_LEVEL.get(ef.get("vocabularyLevel", ""))
                hom = int(ef.get("homonym_number") or 0)
                words.append((int(entry["val"]), form, hom, ef.get("partOfSpeech", ""), level, pron, ef.get("origin") or ""))
                senses.extend(sense_rows)
                # 접사 · 어미 · 조사(-가 · -씨 …)는 뜻 후보로 쓰지 않는다(표제어 찾기에는 남긴다).
                affix = form.startswith("-") or form.endswith("-") or ef.get("partOfSpeech") in ("접사", "어미", "조사")
                if not affix:
                    rev.update(keys)
    meta = {
        "format": FORMAT, "source": "한국어기초사전", "source_en": "Basic Korean Dictionary",
        "publisher": "국립국어원(National Institute of Korean Language)", "version": version,
        "license": "CC BY-SA 2.0 KR", "license_url": "https://creativecommons.org/licenses/by-sa/2.0/kr/",
        "url": "https://krdict.korean.go.kr", "terms_url": "https://krdict.korean.go.kr/kor/kboardPolicy/copyRightTermsInfo",
        "source_sha256": sha256(src),
    }
    db = new_db(out, """
        -- word = 표제어(id = 한국어기초사전 항목 번호, 판이 바뀌어도 같다). level 1 초급 · 2 중급 · 3 고급 · NULL 없음.
        CREATE TABLE word(id INTEGER PRIMARY KEY, form TEXT NOT NULL, hom INTEGER NOT NULL, pos TEXT NOT NULL,
                          level INTEGER, pron TEXT NOT NULL, origin TEXT NOT NULL);
        -- sense = 뜻 하나와 영어 대역어(lemma 원문). 일 · 중 대역어는 거꾸로 찾기 열쇠로만 싣는다(크기).
        CREATE TABLE sense(id INTEGER PRIMARY KEY, word INTEGER NOT NULL, ord INTEGER NOT NULL, en TEXT NOT NULL);
        -- 거꾸로 찾기(D38: 한국어 뜻 후보 줄의 첫 원천) = 대역어 낱말(lang 1 영 · 2 일 · 3 중, 영어는 소문자) → 뜻.
        -- pos = 그 뜻의 대역어 줄에서 몇째인가(0 = 맨 앞 = 대표 대역어).
        CREATE TABLE revkey(lang INTEGER NOT NULL, text TEXT NOT NULL, id INTEGER NOT NULL,
                            PRIMARY KEY(lang, text)) WITHOUT ROWID;
        CREATE TABLE rev(key INTEGER NOT NULL, sense INTEGER NOT NULL, pos INTEGER NOT NULL,
                         PRIMARY KEY(key, sense)) WITHOUT ROWID;
    """, meta)
    db.executemany("INSERT INTO word VALUES(?, ?, ?, ?, ?, ?, ?)", words)
    db.executemany("INSERT INTO sense VALUES(?, ?, ?, ?)", senses)
    key_ids = {}
    for (code, key, _) in sorted(rev):
        key_ids.setdefault((code, key), len(key_ids) + 1)
    db.executemany("INSERT INTO revkey VALUES(?, ?, ?)", [(c, k, i) for (c, k), i in key_ids.items()])
    db.executemany("INSERT INTO rev VALUES(?, ?, ?)",
                   sorted((key_ids[(c, k)], s, p) for (c, k, s), p in rev.items()))
    db.execute("CREATE INDEX word_form ON word(form)")
    db.execute("CREATE INDEX sense_word ON sense(word)")
    finish(db, out, {"entries": len(words), "senses": len(senses), "reverse_keys": len(key_ids),
                     "reverse_rows": len(rev), "skipped_phrases": skipped_units})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cedict", required=True)
    parser.add_argument("--jmdict", required=True)
    parser.add_argument("--krdict", help="없으면 krdict.sqlite 만 빼고 만든다(앱은 한국어 뜻 후보 없이 돈다)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixture", help="단위 시험용 단어 목록(이 단어만 담은 fixture-*.sqlite)")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    only = read_fixture(args.fixture) if args.fixture else None
    prefix = "fixture-" if only is not None else ""
    build_cedict(args.cedict, os.path.join(args.out, prefix + "cedict.sqlite"), only["zh"] if only else None)
    build_jmdict(args.jmdict, os.path.join(args.out, prefix + "jmdict.sqlite"), only["ja"] if only else None)
    if args.krdict:
        build_krdict(args.krdict, os.path.join(args.out, prefix + "krdict.sqlite"), only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
