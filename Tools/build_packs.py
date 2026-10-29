#!/usr/bin/env python3
"""단어장(ios/vocab) 무료 묶음과 예문 사전을 만든다. 파이썬 표준 라이브러리만(맥 러너의 /usr/bin/python3 3.9 에서도 돈다).

명세 = docs/claude/roadmap/vocab/02-engineering.md 6절 · 원장 D20 · D22 · D33 · 01-memory L22 · L23 · N1.

묶음 = 언어마다 셋(1 = 자주 쓰는 첫 500 · 2 = 다음 1,000 · 3 = 그다음 1,500), 시험 이름 없음(D22).
  en-1/2/3  NGSL 1.2(Browne · Culligan · Phillips, CC BY-SA 4.0) SFI 순, 영어 학습자용 = 한국어 뜻
  zh-1/2/3  wordfreq 3.1.1 zh 빈도 × Tatoeba 일상 문장 빈도, CC-CEDICT 에 있는 말 = 한국어 · 영어 뜻
  ja-1/2/3  wordfreq 3.1.1 ja 빈도 × Tatoeba 일본어 색인(사전형) 빈도, JMdict 흔한 말 = 한국어 · 영어 뜻
  ko-1/2/3  국립국어원 한국어 학습용 어휘 목록(2003, 공공누리 제1유형) 등급 · 순위, 한국어기초사전 항목 = 영어 뜻(한국어 학습자용)

묶음 한 줄 = 단어 하나 = 뜻 하나(읽기 · 사전 항목이 정해져 있다, 추정 읽기 없음 D33):
  {id, term, alt?, reading?, dictRef, pos, ko?, en?, ex?, exKo?, exEn?, exRef?, cat?, ov?}
  reading = zh 숫자 성조 병음(CC-CEDICT 그 항목) · ja 히라가나(JMdict 그 읽기, 가나만 된 말은 없음) · ko 표준 발음(표기와 다를 때만)
  ko · en = 짧은 뜻 1~3개('; ' 로 잇는다, 쓰는 뜻 먼저). 사전 후보를 순위 매겨 고르고(뜻_고르기), 틀린 것은 덧쓰기 파일이 고친다.
  ex = 예문 한 줄(Tatoeba CC BY 2.0 FR, 한국어 단어는 Tatoeba 또는 한국어기초사전), exKo · exEn = 그 번역(없으면 빈다, 지어내지 않는다).
  ov = 덧쓰기로 고친 칸(감사용). 묶음 파일 = {"format": 2, "id", "lang", "sources", "items"}.
예문 사전 = examples.sqlite(묶음 밖 단어도, 넣기 시트가 사전에 예문이 있으면 제안한다).
덧쓰기 = Tools/pack_overrides/*.tsv(사람이 검토한 고침, 줄마다 근거 주석). 표 · 표본 = --report 폴더.

실행: python3 -I build_packs.py --cedict … --jmdict … --krdict … --nikl … --ngsl … --ngsl-forms … --wordfreq … --tatoeba DIR
                                 --overrides Tools/pack_overrides --out DIR --examples-out DIR [--report DIR]
      python3 -I build_packs.py --fixture lexicon_fixture.txt --fixture-lexicon FIXTURES --out FIXTURES  (fixture-pack-zh.json)
"""
from __future__ import annotations

import argparse
import bz2
import collections
import csv
import gzip
import hashlib
import io
import json
import math
import os
import random
import re
import sqlite3
import struct
import sys
import tarfile
import zipfile

FORMAT = 2
# 묶음 크기(1 · 2 · 3). 하루 새 단어 상한은 엔진(10)이 지킨다 = 1 은 약 50일 치.
PACK_SIZES = (500, 1000, 1500)
# 예문 길이(L23 '한 문장'): 영어 = 낱말 10개까지 · 중 · 일 = 글자 20개까지(문장 부호 빼고) · 한국어 = 어절 8개 · 글자 24개까지.
MAX_WORDS_EN = 10
MAX_CHARS_CJK = 20
MAX_EOJEOL_KO = 8
MAX_CHARS_KO = 24
# 예문 사전에 싣는 말 수(언어마다, 쓰임 순).
EXAMPLE_TERMS = 12000

HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆]")
ZH_WORD = re.compile(r"^[㐀-䶿一-鿿豈-﫿]+$")
KANA_ONLY = re.compile(r"^[ぁ-ゟァ-ヿー]+$")
HANGUL = re.compile(r"[가-힣]")
LATIN_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)
EM_DASH = "\u2014"

# 품사 표시 꼴(앱 PackEntry.pos 와 같은 값). 사전마다 다른 이름을 이 열둘로 모은다.
POS_CODES = ("n", "v", "adj", "adv", "pron", "num", "cl", "prep", "conj", "intj", "det", "phr")


def log(*parts) -> None:
    print(*parts, flush=True)


def no_dash(text: str) -> str:
    """화면 글에 줄표(U+2014)를 쓰지 않는다(카피 규칙). 원자료의 줄표는 쉼표 · 쌍점으로 바꾼다."""
    return text.replace(" \u2014 ", ": ").replace("\u2014", ", ").replace("\u2015", ", ")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ── 작은 msgpack 읽개(wordfreq cBpack · 간체 표만 읽으면 된다) ─────────────────

def unpack(data: bytes, at: int = 0):
    code = data[at]
    at += 1
    if code <= 0x7F:
        return code, at
    if 0x80 <= code <= 0x8F:
        return unpack_map(data, at, code & 0x0F)
    if 0x90 <= code <= 0x9F:
        return unpack_array(data, at, code & 0x0F)
    if 0xA0 <= code <= 0xBF:
        size = code & 0x1F
        return data[at:at + size].decode("utf-8"), at + size
    if code >= 0xE0:
        return code - 0x100, at
    if code == 0xC0:
        return None, at
    if code in (0xC2, 0xC3):
        return code == 0xC3, at
    fixed = {0xCC: ">B", 0xCD: ">H", 0xCE: ">I", 0xCF: ">Q", 0xD0: ">b", 0xD1: ">h", 0xD2: ">i", 0xD3: ">q",
             0xCA: ">f", 0xCB: ">d"}
    if code in fixed:
        fmt = fixed[code]
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, data[at:at + size])[0], at + size
    lengths = {0xD9: ">B", 0xDA: ">H", 0xDB: ">I", 0xC4: ">B", 0xC5: ">H", 0xC6: ">I"}
    if code in lengths:
        fmt = lengths[code]
        width = struct.calcsize(fmt)
        size = struct.unpack(fmt, data[at:at + width])[0]
        at += width
        chunk = data[at:at + size]
        return (chunk.decode("utf-8") if code >= 0xD9 else chunk), at + size
    if code in (0xDC, 0xDD):
        fmt = ">H" if code == 0xDC else ">I"
        width = struct.calcsize(fmt)
        return unpack_array(data, at + width, struct.unpack(fmt, data[at:at + width])[0])
    if code in (0xDE, 0xDF):
        fmt = ">H" if code == 0xDE else ">I"
        width = struct.calcsize(fmt)
        return unpack_map(data, at + width, struct.unpack(fmt, data[at:at + width])[0])
    raise ValueError(f"msgpack 형식 0x{code:02x} 은 읽지 않는다")


def unpack_array(data: bytes, at: int, count: int):
    items = []
    for _ in range(count):
        item, at = unpack(data, at)
        items.append(item)
    return items, at


def unpack_map(data: bytes, at: int, count: int):
    out = {}
    for _ in range(count):
        key, at = unpack(data, at)
        value, at = unpack(data, at)
        out[key] = value
    return out, at


# wordfreq numbers.MULTI_DIGIT_RE(앞에서 맞춤) = 여러 자리 숫자로 시작하는 말은 top_n_list 가 뺀다.
MULTI_DIGIT = re.compile(r"\d[\d.,]+")


class WordFreq:
    """wordfreq 3.1.1 휠 안의 자료(설치하지 않고 읽는다). rank = top_n_list 순서(1부터), band = cB 띠 번호(작을수록 흔함)."""

    def __init__(self, wheel: str) -> None:
        self.wheel = wheel
        self.archive = zipfile.ZipFile(wheel)

    def ranks(self, lang: str) -> dict:
        raw = gzip.decompress(self.archive.read(f"wordfreq/data/large_{lang}.msgpack.gz"))
        data, _ = unpack(raw)
        header = data[0]
        if not isinstance(header, dict) or header.get("format") != "cB" or header.get("version") != 1:
            raise ValueError("wordfreq cBpack 머리가 아니다")
        out = {}
        for band in data[1:]:
            for word in band:
                if not MULTI_DIGIT.match(word) and word not in out:
                    out[word] = len(out) + 1
        return out

    def jieba(self) -> tuple:
        """(wordfreq 분절 사전 {말: 빈도}, jieba 원 사전 {말: 품사})."""
        freq = {}
        for line in self.archive.read("wordfreq/data/jieba_zh.txt").decode("utf-8").splitlines():
            parts = line.split(" ")
            if len(parts) >= 2 and parts[1].isdigit():
                freq[parts[0]] = int(parts[1])
        pos = {}
        for line in self.archive.read("wordfreq/data/jieba_zh_orig.txt").decode("utf-8").splitlines():
            parts = line.split(" ")
            if len(parts) >= 3:
                pos.setdefault(parts[0], parts[2])
        return freq, pos

    def simplify_map(self) -> dict:
        data, _ = unpack(gzip.decompress(self.archive.read("wordfreq/data/_chinese_mapping.msgpack.gz")))
        return data


# ── CC-CEDICT ──────────────────────────────────────────────────────────────

CEDICT_LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\] /(.*)/\s*$")
CEDICT_DATE = re.compile(r"^#! date=(\d{4}-\d{2}-\d{2})")
# 다른 항목을 가리킬 뿐인 풀이(이체자 · 참조). build_lexicon.py CEDICT_WEAK 와 같다.
CEDICT_WEAK = re.compile(r"^((old|archaic|ancient|Japanese|Taiwan|unofficial|erhua|non-standard|incorrect) )*variant of "
                         r"|^see (also )?|^used in |^also written |^abbr\. for |^also pr\. ")
CEDICT_SURNAME = re.compile(r"^surname ")
# 묶음에 넣지 않는 풀이 꼴(말씨 · 분야 · 지역 표시만 남은 말).
CEDICT_NOT_EVERYDAY = re.compile(r"^\((vulgar|slang|coarse|offensive|derog\.|literary|archaic|old|dialect|Cantonese|Tw|Buddhism|Taoism|"
                                 r"chemistry|physics|math\.|mathematics|medicine|biology|botany|zoology|anatomy|geology|astronomy|"
                                 r"computing|linguistics|music|law|finance|military)\)")
CEDICT_BAD = re.compile(r"\b(vulgar|obscene|coarse|offensive|derog\.|pejorative|sexual|penis|vagina|fuck|semen|prostitute)\b", re.I)


class CedictEntry:
    __slots__ = ("trad", "simp", "raw", "glosses", "flags")

    def __init__(self, trad, simp, raw, glosses, flags):
        self.trad, self.simp, self.raw, self.glosses, self.flags = trad, simp, raw, glosses, flags

    @property
    def key(self) -> str:
        """앱 LexiconDB.ChineseEntry.key 와 같은 꼴 = 묶음 dictRef."""
        return f"{self.trad} {self.simp} [{self.raw}]"

    @property
    def pinyin(self) -> str:
        """저장 꼴(소문자 · ü). 앱 Pinyin.fromCEDICT 와 같다."""
        return " ".join(self.raw.replace("u:", "ü").replace("U:", "Ü").lower().split())

    @property
    def proper(self) -> bool:
        return self.raw[:1].isupper()

    @property
    def weak(self) -> bool:
        kept = [g for g in self.glosses if not g.startswith("CL:")]
        return bool(kept) and all(CEDICT_WEAK.match(g) for g in kept)

    @property
    def surname_only(self) -> bool:
        kept = [g for g in self.glosses if not g.startswith("CL:")]
        return bool(kept) and all(CEDICT_SURNAME.match(g) for g in kept)


def load_cedict(path: str) -> tuple:
    """({간체: [항목]}, 판 날짜)."""
    version = ""
    by_simp = collections.defaultdict(list)
    opener = gzip.open if path.endswith(".gz") else open
    with io.TextIOWrapper(opener(path, "rb"), encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                match = CEDICT_DATE.match(line)
                if match:
                    version = match.group(1)
                continue
            match = CEDICT_LINE.match(line)
            if not match:
                continue
            trad, simp, raw, body = match.groups()
            glosses = [no_dash(g.strip()) for g in body.split("/") if g.strip()]
            by_simp[simp].append(CedictEntry(trad, simp, raw, glosses, 0))
    return by_simp, version


# ── JMdict 흔한 말 (jmdict-simplified) ──────────────────────────────────────

# 묶음에서 뺄 품사 · 말씨(조사 · 조동사 · 접사 · 접속사 · 조수사 · 표현 · 비속어).
JA_EXCLUDED_POS = {"prt", "aux", "aux-v", "aux-adj", "pref", "suf", "conj", "cop", "ctr", "n-suf", "n-pref", "exp",
                   "unc", "n-pr"}
JA_BAD_MISC = {"vulg", "X", "derog", "sens", "arch", "obs", "rare", "dated", "poet", "male-sl", "joc"}
JA_POS = {"n": "n", "n-adv": "n", "n-t": "n", "adj-i": "adj", "adj-ix": "adj", "adj-na": "adj", "adj-no": "adj", "adj-pn": "det",
          "adj-t": "adj", "adj-f": "adj", "adv": "adv", "adv-to": "adv", "int": "intj", "pn": "pron", "num": "num", "ctr": "cl",
          "conj": "conj", "prt": "phr", "exp": "phr"}


def ja_pos_code(tags: list) -> str:
    for tag in tags:
        if tag.startswith("v") and tag not in ("vs-c",):
            return "v"
        if tag in JA_POS:
            return JA_POS[tag]
    return "n"


def hiragana(kana: str) -> str:
    """가타카나 → 히라가나(글자 자리만, ー 는 그대로) = 앱 CompareRules.katakanaToHiragana 꼴."""
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 or ord(c) in (0x30FD, 0x30FE) else c for c in kana)


def applies(values: list, text: str) -> bool:
    return "*" in values or text in values


def load_jmdict(path: str) -> dict:
    if path.endswith((".tgz", ".tar.gz")):
        with tarfile.open(path, "r:gz") as archive:
            member = next(m for m in archive.getmembers() if m.name.endswith(".json"))
            return json.load(archive.extractfile(member))
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


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


KR_LEVEL = {"초급": 1, "중급": 2, "고급": 3}
KR_LANGS = {"영어": "en", "일본어": "ja", "중국어": "zh"}


class KrSense:
    __slots__ = ("order", "eq", "en_def", "examples", "ko_def", "phrases")

    def __init__(self, order, eq, en_def, examples, ko_def="", phrases=()):
        self.order, self.eq, self.en_def, self.examples = order, eq, en_def, examples
        self.ko_def, self.phrases = ko_def, phrases


class KrWord:
    __slots__ = ("id", "form", "hom", "pos", "level", "pron", "origin", "category", "senses")

    def __init__(self, id, form, hom, pos, level, pron, origin, category, senses):
        self.id, self.form, self.hom, self.pos, self.level = id, form, hom, pos, level
        self.pron, self.origin, self.category, self.senses = pron, origin, category, senses


def clean_kr_text(text: str) -> str:
    text = (text or "").replace("&apos;", "'").replace("&quot;", '"').replace("&amp;", "&").replace("\t", " ")
    return no_dash(" ".join(text.split()))


def load_krdict(path: str) -> tuple:
    """({항목 번호: KrWord}, 판). 단어만(구 · 관용구 · 속담 · 문법 형태 제외). 대역어는 영 · 일 · 중만, 예문은 문장 · 대화만."""
    words = {}
    version = ""
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            match = re.search(r"_(\d{8})\.json$", info.filename)
            if match:
                version = max(version, match.group(1))
            with archive.open(info) as handle:
                data = json.load(handle)
            for entry in as_list(data["LexicalResource"]["Lexicon"]["LexicalEntry"]):
                ef = feats(entry.get("feat"))
                if ef.get("lexicalUnit") != "단어":
                    continue
                form = next((feats(l.get("feat")).get("writtenForm") for l in as_list(entry.get("Lemma"))
                             if feats(l.get("feat")).get("writtenForm")), None)
                if not form:
                    continue
                pron = ""
                for wf in as_list(entry.get("WordForm")):
                    wff = feats(wf.get("feat"))
                    if wff.get("type") == "발음" and wff.get("pronunciation"):
                        pron = wff["pronunciation"].strip()
                        break
                senses = []
                for order, sense in enumerate(as_list(entry.get("Sense"))):
                    eq = {}
                    en_def = ""
                    for item in as_list(sense.get("Equivalent")):
                        qf = feats(item.get("feat"))
                        lang = KR_LANGS.get(qf.get("language", ""))
                        if lang and lang not in eq:
                            eq[lang] = clean_kr_text(qf.get("lemma", ""))
                            if lang == "en":
                                en_def = clean_kr_text(qf.get("definition", ""))
                    examples = []
                    phrases = []
                    for example in as_list(sense.get("SenseExample")):
                        xf = example.get("feat")
                        kind = feats(xf).get("type")
                        texts = [f.get("val") for f in as_list(xf) if isinstance(f, dict) and f.get("att") == "example"]
                        for text in texts:
                            text = clean_kr_text(text)
                            if text and kind in ("문장", "대화"):
                                examples.append(text)
                            elif text and kind == "구":
                                phrases.append(text)
                    ko_def = clean_kr_text(feats(sense.get("feat")).get("definition", ""))
                    senses.append(KrSense(order, eq, en_def, examples, ko_def, tuple(phrases)))
                wid = int(entry["val"])
                words[wid] = KrWord(wid, form.strip(), int(ef.get("homonym_number") or 0), ef.get("partOfSpeech", ""),
                                    KR_LEVEL.get(ef.get("vocabularyLevel", "")), pron, ef.get("origin") or "",
                                    ef.get("semanticCategory") or "", senses)
    return words, version


KR_POS = {"명사": "n", "의존 명사": "n", "대명사": "pron", "수사": "num", "동사": "v", "형용사": "adj", "보조 동사": "v",
          "보조 형용사": "adj", "관형사": "det", "부사": "adv", "감탄사": "intj", "조사": "phr", "어미": "phr", "접사": "phr"}


# ── Tatoeba ────────────────────────────────────────────────────────────────

TATOEBA_FILES = (
    "eng_sentences_detailed.tsv.bz2", "cmn_sentences_detailed.tsv.bz2", "jpn_sentences_detailed.tsv.bz2",
    "kor_sentences_detailed.tsv.bz2", "eng_tags.tsv.bz2", "cmn_tags.tsv.bz2", "jpn_tags.tsv.bz2", "kor_tags.tsv.bz2",
    "cmn-eng_links.tsv.bz2", "cmn-kor_links.tsv.bz2", "jpn-eng_links.tsv.bz2", "jpn-kor_links.tsv.bz2",
    "eng-kor_links.tsv.bz2", "user_languages.tar.bz2", "jpn_indices.tar.bz2",
)
# 예문으로 쓰지 않는 표시(고칠 것 · 문장 아님 · 사투리 · 옛말 · 인용 · 속담 · 시 · 뉴스 · 저작권 의심).
TATOEBA_BAD_TAG = re.compile(r"^@|not a sentence|non-sentence|dialect|kansai|classical|bungo|old-fashioned|old kana|archaic|"
                             r"poetry|poem|quote|proverb|idiom|成语|by |voanews|extra-long|copyright|vulgar|slang|profan|"
                             r"insult|rude|sex|offensive|wwwjdic|incorrect|wrong|ambiguous|maths|mathematics|programming", re.I)
TATOEBA_GOOD_TAG = re.compile(r"^OK$")
# 문장에 들면 예문으로 쓰지 않는 사람 이름(Tatoeba 영어 기본 문장의 Tom · Mary 를 피한다, 못 피하면 쓴다).
NAME_HINT = re.compile(r"\b(Tom|Mary|John|Jack|Ken|Mike|Bill|Bob|Jane|Lucy|Tony|Mr|Mrs|Ms)\b|トム|メアリー|ケン|汤姆|玛丽|톰|메리")


class Sentence:
    __slots__ = ("id", "lang", "text", "owner", "good", "en", "ko")

    def __init__(self, id, lang, text, owner):
        self.id, self.lang, self.text, self.owner = id, lang, text, owner
        self.good = False
        self.en = []   # 영어 번역 문장 번호
        self.ko = []   # 한국어 번역 문장 번호


class Tatoeba:
    """per_language 내보내기 파일(판 = 받은 날의 주간 내보내기). 문장 = CC BY 2.0 FR(일부 CC0)."""

    def __init__(self, folder: str, keep_eng: callable) -> None:
        self.folder = folder
        self.block = {}
        self.natives = collections.defaultdict(set)
        with tarfile.open(os.path.join(folder, "user_languages.tar.bz2"), "r:bz2") as archive:
            member = next(m for m in archive.getmembers() if m.name.endswith(".csv"))
            for line in archive.extractfile(member).read().decode("utf-8", "replace").splitlines():
                parts = line.split("\t")
                if len(parts) >= 3 and parts[1] == "5":
                    self.natives[parts[0]].add(parts[2])
        self.bad = set()
        good = set()
        for lang in ("eng", "cmn", "jpn", "kor"):
            for line in self.lines(f"{lang}_tags.tsv.bz2"):
                parts = line.split("\t")
                if len(parts) == 2:
                    if TATOEBA_BAD_TAG.search(parts[1]):
                        self.bad.add(int(parts[0]))
                    elif TATOEBA_GOOD_TAG.match(parts[1]):
                        good.add(int(parts[0]))
        self.links = collections.defaultdict(list)
        for pair in ("cmn-eng", "cmn-kor", "jpn-eng", "jpn-kor", "eng-kor"):
            for line in self.lines(f"{pair}_links.tsv.bz2"):
                a, _, b = line.partition("\t")
                if a.isdigit() and b.strip().isdigit():
                    self.links[int(a)].append(int(b))
                    self.links[int(b)].append(int(a))
        self.sentences = {}
        for lang in ("cmn", "jpn", "kor", "eng"):
            for line in self.lines(f"{lang}_sentences_detailed.tsv.bz2"):
                parts = line.split("\t")
                if len(parts) < 4 or not parts[0].isdigit():
                    continue
                sid = int(parts[0])
                if sid in self.bad:
                    continue
                text = no_dash(parts[2].strip())
                # 영어는 번역으로 쓰이거나 짧은 것만(전부 들면 메모리 · 시간).
                if lang == "eng" and not (sid in self.links or keep_eng(text)):
                    continue
                sentence = Sentence(sid, lang, text, parts[3])
                sentence.good = sid in good
                self.sentences[sid] = sentence
        for sentence in self.sentences.values():
            for other in self.links.get(sentence.id, ()):
                target = self.sentences.get(other)
                if target is None or target.lang == sentence.lang:
                    continue
                if target.lang == "eng":
                    sentence.en.append(other)
                elif target.lang == "kor":
                    sentence.ko.append(other)
        self.ja_index = []   # (일본어 문장 번호, 영어 번역 번호, 색인 줄)
        with tarfile.open(os.path.join(folder, "jpn_indices.tar.bz2"), "r:bz2") as archive:
            member = next(m for m in archive.getmembers() if m.name.endswith(".csv"))
            for line in archive.extractfile(member).read().decode("utf-8", "replace").splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                    self.ja_index.append((int(parts[0]), int(parts[1]), parts[2]))

    def lines(self, name: str):
        with bz2.open(os.path.join(self.folder, name), "rt", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line.rstrip("\n")

    def blocked(self, sentence: Sentence) -> bool:
        """금칙어(Tools/pack_overrides/block.tsv)가 든 번역 문장은 쓰지 않는다. block 은 Examples 가 채운다."""
        words = self.block.get({"eng": "en", "cmn": "zh", "jpn": "ja", "kor": "ko"}.get(sentence.lang, ""), ())
        if not words:
            return False
        if sentence.lang == "eng":
            return bool(set(w.lower() for w in LATIN_WORD.findall(sentence.text)) & words)
        return any(word in sentence.text for word in words)

    def native(self, sentence: Sentence) -> bool:
        return sentence.owner in self.natives.get(sentence.lang, ())

    def translation(self, sentence: Sentence, lang: str, prefer: callable = None):
        """그 말 번역 하나(원어민 · 표시 좋음 · 짧은 것 먼저). 한국어는 직접 번역이 없으면 영어 번역의 한국어 번역(간접, 둘 다 사람 번역)."""
        ids = sentence.en if lang == "eng" else sentence.ko
        found = [self.sentences[i] for i in ids if i in self.sentences and not self.blocked(self.sentences[i])]
        indirect = False
        if not found and lang == "kor" and sentence.lang != "eng":
            for eid in sentence.en:
                english = self.sentences.get(eid)
                if english is not None:
                    found += [self.sentences[i] for i in english.ko if i in self.sentences and not self.blocked(self.sentences[i])]
            indirect = bool(found)
        if not found:
            return None, False
        def key(s):
            return (-(prefer(s.text) if prefer else 0), not self.native(s), not s.good, bool(NAME_HINT.search(s.text)),
                    len(s.text), s.id)
        return min(found, key=key), indirect


# ── 중국어 낱말 나누기(jieba 와 같은 DAG + 최대 확률 길, HMM 없음 = wordfreq 와 같은 꼴) ──

class ZhSegmenter:
    def __init__(self, freq: dict) -> None:
        self.freq = freq
        self.total = float(sum(freq.values()))
        self.logtotal = math.log(self.total)
        self.prefixes = set()
        self.maxlen = 1
        for word in freq:
            self.maxlen = max(self.maxlen, len(word))
            for end in range(1, len(word)):
                self.prefixes.add(word[:end])

    def cut(self, text: str) -> list:
        n = len(text)
        dag = []
        for start in range(n):
            ends = []
            for end in range(start + 1, min(n, start + self.maxlen) + 1):
                piece = text[start:end]
                if piece in self.freq:
                    ends.append(end)
                elif piece not in self.prefixes:
                    break
            dag.append(ends or [start + 1])
        route = [(0.0, n)] * (n + 1)
        for start in range(n - 1, -1, -1):
            route[start] = max((math.log(self.freq.get(text[start:end]) or 1) - self.logtotal + route[end][0], end)
                               for end in dag[start])
        out = []
        start = 0
        while start < n:
            end = route[start][1]
            out.append(text[start:end])
            start = end
        return out


def cjk_length(text: str) -> int:
    """문장 부호 · 공백을 뺀 글자 수."""
    return len(PUNCT.sub("", text))


# ── 한국어 뜻 고르기(한국어기초사전 거꾸로 찾기, D38 의 묶음 판) ──────────────────

def en_keys(text: str) -> list:
    """build_lexicon.py en_keys 와 같다: 'study; learn' → study · learn(소문자, 괄호 풀이 · 'to ' 빼고, 네 낱말까지)."""
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
    """'しずめる【沈める】。しずませる【沈ませる】' → 沈める · 沈ませる(한자 표기가 없으면 가나). 〜する 는 줄기도."""
    keys = []
    for part in re.split(r"[。、；;，,]", text):
        part = part.strip()
        if not part or part.startswith("("):
            continue
        match = re.match(r"^(.*?)【(.*?)】", part)
        found = [match.group(2).strip(), match.group(1).strip()] if match else [part]
        for key in found:
            if not key or len(key) > 12:
                continue
            keys.append(key)
            if key.endswith("する") and len(key) > 2:
                keys.append(key[:-2])
    return keys


# 영어 풀이 낱말 맞추기에서 빼는 흔한 말.
EN_STOP = set("a an the to of in on at for by with from and or be is are was were been am it its one's oneself someone "
              "something sb sth etc as into about this that these those which".split())


def en_words(text: str) -> set:
    """풀이 · 대역어 · 번역 문장의 내용 낱말(소문자, 흔한 말 빼고, 끝 s · ed · ing 를 덜어 낸 꼴도)."""
    out = set()
    for word in re.findall(r"[a-z]+", re.sub(r"\([^)]*\)", " ", text.lower())):
        if word in EN_STOP or len(word) < 2:
            continue
        out.add(word)
        for suffix in ("ing", "ed", "es", "s", "ly"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                out.add(word[:-len(suffix)])
    return out


class KoIndex:
    """대역어 낱말 → 한국어기초사전 뜻(언어마다). 행 = (항목 번호, 뜻 순서, 대역어 안 자리)."""

    def __init__(self, kr: dict, nikl_rank: dict) -> None:
        self.kr = kr
        self.nikl_rank = nikl_rank   # 항목 번호 → 학습용 어휘 순위(작을수록 흔함)
        self.index = {"en": collections.defaultdict(list), "zh": collections.defaultdict(list),
                      "ja": collections.defaultdict(list)}
        splitters = {"en": en_keys, "zh": zh_keys, "ja": ja_keys}
        for word in kr.values():
            if word.form.startswith("-") or word.form.endswith("-") or word.pos in ("접사", "어미", "조사", "품사 없음"):
                continue
            for sense in word.senses:
                for lang, split in splitters.items():
                    seen = set()
                    for position, key in enumerate(split(sense.eq.get(lang, ""))):
                        if key not in seen:
                            seen.add(key)
                            self.index[lang][key].append((word.id, sense.order, position))

    def candidates(self, lang: str, keys: list, gloss_words: set, pos: str = "", origin_forms: tuple = ()) -> list:
        """[(점수, 항목 번호, 근거)] 높은 순. 근거 = 사람이 읽는 짧은 글(검토 표)."""
        best = {}
        hits = collections.Counter()
        for key in keys:
            for wid, order, position in self.index[lang].get(key, ()):
                word = self.kr[wid]
                sense = word.senses[order]
                score = 1.0
                score += {0: 1.0, 1: 0.5}.get(position, 0.2)
                score += {0: 1.0, 1: 0.6, 2: 0.35, 3: 0.2}.get(order, 0.0)
                score += {1: 0.8, 2: 0.45, 3: 0.1}.get(word.level, 0.0)
                rank = self.nikl_rank.get(wid)
                if rank is not None:
                    score += 0.6 if rank <= 1500 else 0.4 if rank <= 4000 else 0.2
                agree = gloss_words & en_words(sense.eq.get("en", "")) if lang != "en" else set()
                if agree:
                    score += 1.2 + 0.2 * min(len(agree), 3)
                kpos = KR_POS.get(word.pos, "")
                if pos and kpos:
                    if kpos == pos or (pos == "adj" and kpos == "v" and word.form.endswith("하다")):
                        score += 0.6
                    elif {pos, kpos} <= {"n", "v", "adj", "adv"}:
                        score -= 0.6
                if origin_forms and word.origin and word.origin in origin_forms and (agree or position == 0):
                    score += 0.5
                # 다른 뜻 여럿이 같은 낱말을 대역어로 가지면(가다 = go) 그 말이 대표 뜻일 가능성이 크다.
                hits[wid] += 1
                why = f"{word.form}/{word.pos}/L{word.level or '-'}/s{order}p{position}" + ("/en" if agree else "")
                if wid not in best or score > best[wid][0]:
                    best[wid] = (score, why)
        out = []
        for wid, (score, why) in best.items():
            out.append((score + 0.25 * min(hits[wid] - 1, 4), wid, why))
        out.sort(key=lambda row: (-row[0], self.kr[row[1]].form))
        return out


# ── 덧쓰기(사람이 검토한 고침) ─────────────────────────────────────────────────

OVERRIDE_FIELDS = {"drop", "keep", "ko", "en", "reading", "pos", "ex", "ref"}


class Overrides:
    """Tools/pack_overrides/<언어>.tsv = 표기[@사전 항목] <TAB> 칸 <TAB> 값 <TAB> 근거. block.tsv = 언어 <TAB> 낱말(묶음 · 예문에서 뺀다)."""

    def __init__(self, folder: str | None) -> None:
        self.rows = {"en": {}, "zh": {}, "ja": {}, "ko": {}}
        self.block = {"en": set(), "zh": set(), "ja": set(), "ko": set()}
        self.used = set()
        if not folder:
            return
        for lang in self.rows:
            path = os.path.join(folder, f"{lang}.tsv")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if not line.strip() or line.startswith("#"):
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 2 or parts[1] not in OVERRIDE_FIELDS:
                        raise ValueError(f"{path}:{number} 칸 이름이 틀렸다: {line!r}")
                    if EM_DASH in line:
                        raise ValueError(f"{path}:{number} 줄표 금지")
                    value = parts[2].strip() if len(parts) > 2 else ""
                    self.rows[lang].setdefault(parts[0].strip(), {})[parts[1]] = value
        path = os.path.join(folder, "block.tsv")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    if line.strip() and not line.startswith("#"):
                        lang, _, word = line.rstrip("\n").partition("\t")
                        word = word.split("\t")[0].strip()
                        if lang in self.block and word:
                            self.block[lang].add(word)

    def get(self, lang: str, term: str, ref: str | None = None) -> dict:
        rows = self.rows[lang]
        out = {}
        if term in rows:
            out.update(rows[term])
            self.used.add((lang, term))
        if ref and f"{term}@{ref}" in rows:
            out.update(rows[f"{term}@{ref}"])
            self.used.add((lang, f"{term}@{ref}"))
        return out

    def unused(self) -> list:
        return [(lang, key) for lang, rows in self.rows.items() for key in rows if (lang, key) not in self.used]


def split_meanings(value: str) -> list:
    return [part.strip() for part in value.split(";") if part.strip()]


# ── 묶음 한 줄 ─────────────────────────────────────────────────────────────

class Item:
    def __init__(self, lang: str, term: str) -> None:
        self.lang = lang
        self.term = term
        self.alt = None
        self.reading = None
        self.ref = None          # dictRef
        self.pos = ""
        self.ko = []
        self.en = []
        self.gloss_words = set()   # 예문 뜻 맞추기(그 뜻의 영어 낱말)
        self.ko_stems = []         # 예문 뜻 맞추기(한국어 뜻 줄기)
        self.forms = set()         # 문장에서 이 말로 보는 꼴(영 · 한)
        self.category = ""
        self.useful = 0.0          # 작을수록 먼저
        self.example = None        # (문장, 한국어 번역 글, 영어 번역 글, 원천 열쇠, 간접 여부)
        self.overridden = []
        self.why = ""              # 검토 표 근거
        self.ex_pick = None        # 덧쓰기 예문 번호(None = 자동, 0 = 없음)

    def meaning_line(self, lang: str) -> str:
        return "; ".join(self.ko if lang == "ko" else self.en)

    def as_json(self, number: int) -> dict:
        out = {"id": f"{self.lang}:{self.ref or self.term}" if self.lang != "en" else f"en:{self.term}",
               "term": self.term}
        if self.alt:
            out["alt"] = self.alt
        if self.reading:
            out["reading"] = self.reading
        out["dictRef"] = self.ref
        out["rank"] = number
        out["pos"] = self.pos or "n"
        if self.ko:
            out["ko"] = "; ".join(self.ko)
        if self.en:
            out["en"] = "; ".join(self.en)
        if self.example:
            sentence, ko, en, source, _ = self.example
            out["ex"] = sentence
            if ko:
                out["exKo"] = ko
            if en:
                out["exEn"] = en
            out["exRef"] = source
        if self.category:
            out["cat"] = self.category
        if self.overridden:
            out["ov"] = sorted(set(self.overridden))
        return out


def apply_override(item: Item, row: dict) -> bool:
    """덧쓰기 한 줄을 그 줄에 붙인다. 빼라는 줄이면 False."""
    if "drop" in row:
        return False
    for field in ("ko", "en"):
        if field in row:
            setattr(item, field, split_meanings(row[field]))
            item.overridden.append(field)
    if "pos" in row:
        item.pos = row["pos"]
        item.overridden.append("pos")
    if "ex" in row:
        item.ex_pick = 0 if row["ex"] in ("", "none") else int(row["ex"])
        item.overridden.append("ex")
    return True


# ── 한국어 활용 꼴(예문 찾기용, 대충 맞추고 뜻 맞추기로 거른다) ──────────────────

def ko_split(syllable: str) -> tuple:
    code = ord(syllable) - 0xAC00
    return code // 588, (code % 588) // 28, code % 28


def ko_join(cho: int, jung: int, jong: int) -> str:
    return chr(0xAC00 + cho * 588 + jung * 28 + jong)


# 중성 번호: ㅏ0 ㅐ1 ㅑ2 ㅒ3 ㅓ4 ㅔ5 ㅕ6 ㅖ7 ㅗ8 ㅘ9 ㅙ10 ㅚ11 ㅛ12 ㅜ13 ㅝ14 ㅞ15 ㅟ16 ㅠ17 ㅡ18 ㅢ19 ㅣ20
# 종성 번호: ㄴ4 ㄷ7 ㄹ8 ㅁ16 ㅂ17 ㅅ19 ㅆ20 ㅎ27
KO_CONTRACT = {8: (9,), 13: (14,), 20: (6,), 18: (4, 0), 11: (10,), 0: (0,), 4: (4,), 1: (1,), 5: (5,), 6: (6,), 16: (16,)}
KO_PARTICLES = ("", "이", "가", "은", "는", "을", "를", "에", "에서", "에게", "한테", "께", "의", "도", "만", "와", "과", "로", "으로",
                "부터", "까지", "보다", "처럼", "이나", "나", "랑", "이랑", "요", "이에요", "예요", "이야", "야", "입니다", "이다", "다",
                "이고", "고", "들", "들이", "들은", "들을", "들도", "에는", "에도", "으로는", "로는", "이라고", "라고", "인", "이면", "면")
KO_ENDING_START = set("고는니다요서세시지게기면며도자야라러려어아았었을은겠던든네나냐죠군구거걸께습셨십실신길겼잖세실셔시ㅂ")


def ko_forms(lemma: str, pos: str) -> set:
    """활용하는 말(동사 · 형용사)이면 문장 어절 앞에 올 수 있는 꼴들. 아니면 표기 하나."""
    if pos not in ("v", "adj") or not lemma.endswith("다") or len(lemma) < 2:
        return {lemma}
    stem = lemma[:-1]
    head, last = stem[:-1], stem[-1]
    forms = {stem}
    if not ("가" <= last <= "힣"):
        return forms
    cho, jung, jong = ko_split(last)
    if last == "하":
        forms |= {head + "해", head + "했", head + "한", head + "할", head + "함", head + "합"}
        return forms
    if jong == 0:
        for batchim in (4, 8, 16, 17, 20):
            forms.add(head + ko_join(cho, jung, batchim))
        vowels = KO_CONTRACT.get(jung, ())
        if jung == 18:   # ㅡ 탈락: 앞 모음이 ㅏ · ㅗ 면 ㅏ(바빠), 아니면 ㅓ(써)
            bright = bool(head) and "가" <= head[-1] <= "힣" and ko_split(head[-1])[1] in (0, 8)
            vowels = () if last == "르" else ((0,) if bright else (4,))
        for vowel in vowels:
            forms.add(head + ko_join(cho, vowel, 0))
            forms.add(head + ko_join(cho, vowel, 20))
        if last == "르" and head:
            pc, pj, pjong = ko_split(head[-1])
            if pjong == 0:
                vowel = 0 if pj in (0, 8) else 4
                forms.add(head[:-1] + ko_join(pc, pj, 8) + ko_join(5, vowel, 0))
                forms.add(head[:-1] + ko_join(pc, pj, 8) + ko_join(5, vowel, 20))
        if jung == 20 and cho == 11 and last == "이":
            forms.add(head + "여")
    else:
        bare = head + ko_join(cho, jung, 0)
        if jong == 8:   # ㄹ 탈락: 살다 → 사는 · 삽니다
            forms |= {bare, head + ko_join(cho, jung, 4), head + ko_join(cho, jung, 17)}
        elif jong == 17:   # ㅂ 불규칙: 춥다 → 추워 · 돕다 → 도와
            forms |= {bare + "워", bare + "웠", bare + "와", bare + "왔", bare + "운", bare + "울"}
        elif jong == 7:   # ㄷ 불규칙: 듣다 → 들어
            forms.add(head + ko_join(cho, jung, 8))
        elif jong == 19:   # ㅅ 불규칙: 짓다 → 지어
            forms.add(bare)
        elif jong == 27:   # ㅎ 불규칙: 빨갛다 → 빨개 · 그렇다 → 그래
            forms |= {head + ko_join(cho, 1, 0), head + ko_join(cho, 1, 20), bare, head + ko_join(cho, jung, 4)}
    return forms


def ko_matches(eojeol: str, forms: set, pos: str) -> bool:
    word = eojeol.strip(".,!?\"'“”‘’…()~·")
    for form in forms:
        if not word.startswith(form):
            continue
        rest = word[len(form):]
        if pos in ("v", "adj"):
            if not rest or rest[0] in KO_ENDING_START or (len(form) >= 2 and rest[:1] in ("어", "아", "여")):
                return True
        elif rest in KO_PARTICLES:
            return True
    return False


# ── 영어 꼴 ────────────────────────────────────────────────────────────────

def en_inflections(lemma: str) -> set:
    """NGSL 교수용 표의 꼴이 없을 때 쓰는 규칙 꼴(복수 · 3인칭 · 과거 · 진행). 세 글자 미만 말(I · a · he)은 그 꼴 하나."""
    word = lemma.lower()
    if len(word) < 3:
        return {word}
    forms = {word, word + "s", word + "es", word + "ed", word + "ing", word + "d"}
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        forms |= {word[:-1] + "ies", word[:-1] + "ied"}
    if word.endswith("e"):
        forms.add(word[:-1] + "ing")
    if len(word) >= 3 and word[-1] not in "aeiouwxy" and word[-2] in "aeiou" and word[-3] not in "aeiou":
        forms |= {word + word[-1] + "ed", word + word[-1] + "ing"}
    return forms


# ── 예문 고르기 ────────────────────────────────────────────────────────────

JA_TOKEN = re.compile(r"^(?P<head>[^(\[{~]+)(?:\((?P<paren>[^)]*)\))?(?:\[(?P<sense>\d+)\])?(?:\{(?P<surf>[^}]*)\})?(?P<good>~)?$")


class Examples:
    """언어마다 문장 찾기 색인 + 점수(02-engineering L23: 짧은 한 문장 · 번역 한 줄). 문장 하나는 묶음 단어 하나에만 쓴다."""

    def __init__(self, tat: Tatoeba, block: dict, zh_seg: ZhSegmenter, zh_simplify: dict, ja_forms: dict) -> None:
        self.tat = tat
        self.block = block
        tat.block = block
        self.used = set()
        self.zh = collections.defaultdict(list)
        self.ja = collections.defaultdict(list)   # 항목 번호 → [(문장 번호, 가나, 뜻 번호, 검증 표시, 영어 번역 번호)]
        self.en = collections.defaultdict(list)
        self.ko = collections.defaultdict(list)   # 어절 첫 글자 → [문장 번호]
        self.zh_tokens = {}
        en_cap = collections.Counter()
        for sentence in tat.sentences.values():
            if self.blocked(sentence.text, sentence.lang):
                continue
            if sentence.lang == "cmn":
                if not sentence.en or cjk_length(sentence.text) > MAX_CHARS_CJK or sentence.text.translate(zh_simplify) != sentence.text:
                    continue
                tokens = zh_seg.cut(sentence.text)
                self.zh_tokens[sentence.id] = tokens
                for token in set(tokens):
                    self.zh[token].append(sentence.id)
            elif sentence.lang == "eng":
                words = LATIN_WORD.findall(sentence.text)
                if not 3 <= len(words) <= MAX_WORDS_EN:
                    continue
                # 한국어 번역이 있는 문장은 다 · 없는 문장은 원어민 것만 낱말마다 80개까지(메모리).
                if not sentence.ko and not tat.native(sentence):
                    continue
                for token in set(w.lower() for w in words):
                    if sentence.ko or en_cap[token] < 80:
                        self.en[token].append(sentence.id)
                        en_cap[token] += 1
            elif sentence.lang == "kor":
                eojeols = sentence.text.split()
                if not sentence.en or len(eojeols) > MAX_EOJEOL_KO or len(sentence.text) > MAX_CHARS_KO:
                    continue
                for first in set(e.strip("\"'“”‘(")[:1] for e in eojeols):
                    if first:
                        self.ko[first].append(sentence.id)
        for jid, eid, line in tat.ja_index:
            sentence = tat.sentences.get(jid)
            if sentence is None or cjk_length(sentence.text) > MAX_CHARS_CJK or self.blocked(sentence.text, "jpn"):
                continue
            for token in line.split():
                match = JA_TOKEN.match(token)
                if not match:
                    continue
                head = match.group("head")
                paren = match.group("paren") or ""
                seq = int(paren[1:]) if paren.startswith("#") and paren[1:].isdigit() else None
                kana = paren if paren and not paren.startswith("#") else None
                for entry_seq, default_kana, kana_all in ja_forms.get(head, ()):
                    if seq is not None and entry_seq != seq:
                        continue
                    if kana and hiragana(kana) not in kana_all:
                        continue
                    self.ja[entry_seq].append((jid, hiragana(kana or default_kana), int(match.group("sense") or 1),
                                               bool(match.group("good")), eid))
                    break

    def blocked(self, text: str, lang: str) -> bool:
        return self.tat.blocked(Sentence(0, lang, text, ""))

    # 점수: 번역(한국어 직접 > 간접) · 뜻 맞음 · 원어민 · 검증 표시 · 사람 이름 없음 · 알맞은 길이 · 아직 안 쓴 문장.
    def score(self, sentence: Sentence, ko_text, ko_indirect: bool, en_text, agree: bool, length: float, ideal: tuple,
              checked: bool = False) -> float:
        score = 0.0
        if ko_text:
            score += 3.0 if ko_indirect else 4.0
        if agree:
            score += 2.5
        if self.tat.native(sentence):
            score += 1.0
        if sentence.good or checked:
            score += 0.8
        if NAME_HINT.search(sentence.text):
            score -= 1.2
        low, high = ideal
        if length < low:
            score -= 0.6 * (low - length)
        elif length > high:
            score -= 0.35 * (length - high)
        if not re.search(r"[.!?。！？]$", sentence.text.strip()):
            score -= 0.5
        if sentence.id in self.used:
            score -= 4.0
        return score

    def finish(self, sentence: Sentence, ko_target: bool, item: Item) -> tuple:
        """(문장, 한국어 번역, 영어 번역, 원천, 간접) = 고른 문장의 번역 줄."""
        ko_text, indirect, en_text = None, False, None
        if sentence.lang != "kor" and ko_target:
            found, indirect = self.tat.translation(sentence, "kor", prefer=lambda t: ko_agree(t, item.ko_stems))
            ko_text = found.text if found else None
        if sentence.lang != "eng":
            found, _ = self.tat.translation(sentence, "eng", prefer=lambda t: bool(item.gloss_words & en_words(t)))
            en_text = found.text if found else None
        return sentence.text, ko_text, en_text, f"tatoeba:{sentence.id}", indirect

    def best(self, item: Item, candidates: list, ideal: tuple, length, ko_target: bool, checked: dict = None):
        """후보 문장 가운데 가장 나은 것(없으면 None). 영어 아닌 문장은 영어 번역이 있어야 한다.
        번역이 그 뜻과 맞는 문장(번역 문장에 뜻 낱말이 든다)이 하나라도 있으면 그 가운데서만 고른다(다른 뜻 예문 막기)."""
        scored = []
        for sid in candidates:
            sentence = self.tat.sentences.get(sid)
            if sentence is None:
                continue
            ko_found, ko_indirect = (None, False)
            if ko_target and sentence.lang != "kor":
                ko_found, ko_indirect = self.tat.translation(sentence, "kor", prefer=lambda t: ko_agree(t, item.ko_stems))
            en_found = None
            if sentence.lang != "eng":
                en_found, _ = self.tat.translation(sentence, "eng", prefer=lambda t: bool(item.gloss_words & en_words(t)))
                if en_found is None:
                    continue
            if sentence.lang == "eng":
                agree = bool(ko_found and ko_agree(ko_found.text, item.ko_stems))
            else:
                agree = bool(en_found and item.gloss_words & en_words(en_found.text))
            score = self.score(sentence, ko_found.text if ko_found else None, ko_indirect, en_found, agree,
                               length(sentence.text), ideal, bool(checked and checked.get(sid)))
            if sentence.lang == "eng":
                # 기본 꼴(run)이 든 문장 먼저 · 숫자 · 따옴표 문장은 뒤로.
                if item.term.lower() in (w.lower() for w in LATIN_WORD.findall(sentence.text)):
                    score += 1.0
            if re.search(r"\d", sentence.text) or (en_found and re.search(r"\d", en_found.text)):
                score -= 1.0
            if re.search(r"[\"“”「」『』]", sentence.text):
                score -= 0.5
            scored.append((agree, score, -sid, sentence, bool(ko_found)))
        if not scored:
            return None
        if any(row[0] for row in scored):
            scored = [row for row in scored if row[0]]
        best = max(scored, key=lambda row: (row[1], row[2]))[3]
        self.used.add(best.id)
        return self.finish(best, ko_target, item)

    def find(self, item: Item, ko_target: bool = True):
        if item.ex_pick == 0:
            return None
        if item.ex_pick:
            sentence = self.tat.sentences.get(item.ex_pick)
            if sentence is None:
                raise ValueError(f"덧쓰기 예문 {item.ex_pick} 이 Tatoeba 판에 없다({item.lang} {item.term})")
            self.used.add(sentence.id)
            return self.finish(sentence, ko_target, item)
        if item.lang == "zh":
            return self.best(item, self.zh.get(item.term, ()), (6, 14), cjk_length, ko_target)
        if item.lang == "en":
            ids = sorted(set(sid for form in item.forms for sid in self.en.get(form, ())))
            return self.best(item, ids, (4, 8), lambda t: len(LATIN_WORD.findall(t)), ko_target)
        if item.lang == "ja":
            rows = [r for r in self.ja.get(int(item.ref), ()) if item.reading is None or r[1] == hiragana(item.reading or "")
                    or not HAN.search(item.term)]
            checked = {r[0]: r[3] for r in rows}
            return self.best(item, sorted(checked), (6, 14), cjk_length, ko_target, checked)
        if item.lang == "ko":
            forms = item.forms
            firsts = set(f[:1] for f in forms)
            ids = set()
            for first in firsts:
                for sid in self.ko.get(first, ()):
                    sentence = self.tat.sentences[sid]
                    if any(ko_matches(e, forms, item.pos) for e in sentence.text.split()):
                        ids.add(sid)
            # 한 글자 줄기(가다 · 보다 …)는 영어 번역이 뜻과 맞는 문장만(가방 · 보통 같은 헛짚기를 거른다).
            if min(len(f) for f in forms) <= 1:
                ids = {sid for sid in ids if any(item.gloss_words & en_words(self.tat.sentences[e].text)
                                                 for e in self.tat.sentences[sid].en if e in self.tat.sentences)}
            return self.best(item, sorted(ids), (2, 5), lambda t: len(t.split()), False)
        return None


def ko_agree(text: str, stems: list) -> bool:
    return any(stem and stem in text for stem in stems)


def ko_stem(meaning: str) -> str:
    """한국어 뜻 → 번역 문장에서 찾을 줄기(달리다 → 달리 · 공부하다 → 공부 · 은행 → 은행)."""
    word = re.sub(r"\([^)]*\)|~|\s.*$", "", meaning).strip()
    if word.endswith("하다") and len(word) > 2:
        return word[:-2]
    if word.endswith("다") and len(word) >= 3:
        return word[:-1]
    return word if len(word) >= 2 else ""


# ── 뜻 다듬기 ──────────────────────────────────────────────────────────────

def short_gloss(text: str, limit: int = 32) -> str:
    """사전 풀이 하나를 카드 뜻 꼴로(괄호 설명 · CL: · 끝 마침표 빼기). 너무 길면 빈 글."""
    text = no_dash(text)
    text = re.sub(r"\s*\((?:[^()]|\([^)]*\))*\)", "", text)
    text = re.sub(r"\s*\[[^\]]*\]", "", text)
    text = re.sub(r"\b[^\s|]+\|([^\s\[]+)", r"\1", text)   # CC-CEDICT 번체|간체 → 간체
    text = " ".join(text.split()).strip(" .;,")
    if not text or len(text) > limit:
        return ""
    return text


def pick_glosses(glosses: list, count: int = 3, total: int = 48) -> list:
    out = []
    for gloss in glosses:
        if gloss.startswith("CL:") or CEDICT_WEAK.match(gloss):
            continue
        short = short_gloss(gloss)
        if not short or short.lower() in (g.lower() for g in out):
            continue
        if out and sum(len(g) + 2 for g in out) + len(short) > total:
            break
        out.append(short)
        if len(out) == count:
            break
    return out


def kr_english(sense: KrSense, count: int = 3) -> list:
    """한국어 단어의 영어 뜻 = 한국어기초사전 그 뜻의 영어 대역어(쉼표 · 쌍반점으로 나뉜 것 앞에서부터)."""
    parts = []
    text = sense.eq.get("en", "")
    if text.lower().startswith("(no equivalent"):
        return []
    for part in re.split(r"[;,]", text):
        # 한국어기초사전은 '-적' 명사를 'being economic' 꼴로 옮긴다 = 'economic'.
        part = re.sub(r"^\s*being\s+", "", part)
        short = short_gloss(part, 28)
        if short and short.lower() not in (p.lower() for p in parts):
            parts.append(short)
        if len(parts) == count:
            break
    return parts


def choose_korean(cands: list, kr: dict, limit: int = 2) -> tuple:
    """후보 점수 줄 → (한국어 뜻들, 고른 항목). 둘째는 첫째와 거의 같은 점수이고 뿌리가 다른 말일 때만."""
    if not cands:
        return [], None
    top_score, top_id, _ = cands[0]
    chosen = [kr[top_id].form]
    for score, wid, _ in cands[1:]:
        if len(chosen) >= limit or score < top_score - 0.35:
            break
        form = kr[wid].form
        root = chosen[0][:-2] if chosen[0].endswith("하다") else chosen[0]
        if form.startswith(root) or chosen[0].startswith(form[:-2] if form.endswith("하다") else form):
            continue
        if form not in chosen:
            chosen.append(form)
    return chosen, kr[top_id]


def ko_attributive(word: str) -> str:
    """한국어 형용사 기본형 → 꾸미는 꼴(영어 형용사 뜻은 영어 단어장 관례대로 '큰 · 중요한'). 크다 → 큰 · 어렵다 → 어려운 · 길다 → 긴."""
    if not word.endswith("다") or len(word) < 2:
        return word
    stem = word[:-1]
    last = stem[-1]
    if not "가" <= last <= "힣":
        return word
    if stem.endswith(("있", "없")):
        return stem + "는"
    cho, jung, jong = ko_split(last)
    head = stem[:-1]
    if jong == 0:
        return head + ko_join(cho, jung, 4)
    if jong == 8:   # 길다 → 긴
        return head + ko_join(cho, jung, 4)
    if jong == 17 and word not in ("좁다", "굽다", "뽑다", "씹다"):   # ㅂ 불규칙: 어렵다 → 어려운
        return head + ko_join(cho, jung, 0) + "운"
    if jong == 27 and word not in ("좋다", "놓다", "낳다", "넣다"):   # ㅎ 불규칙: 하얗다 → 하얀
        return head + ko_join(cho, jung, 4)
    return stem + "은"


def ko_translation_vote(cands: list, texts: list, kr: dict, top: int = 15) -> list:
    """후보 점수에 사람 번역(Tatoeba 한국어 번역 문장) 투표를 더한다: 그 낱말이 든 문장의 한국어 번역에 후보의 줄기가 몇 번 나오나.
    instead → 대신(도리어 아님) · depend → 달려 있다. 한 글자 줄기(가다 = 가)는 아무 데나 맞아 세지 않는다."""
    if not texts or not cands:
        return cands
    out = []
    for score, wid, why in cands[:top]:
        stem = ko_stem(kr[wid].form)
        count = sum(1 for t in texts if stem and len(stem) >= 2 and stem in t)
        if count:
            score += min(2.4, 0.9 * math.log2(1 + count))
            why += f"/tr{count}"
        out.append((score, wid, why))
    out.sort(key=lambda row: (-row[0], kr[row[1]].form))
    return out + cands[top:]


def ko_texts_for(ids, tat: Tatoeba, limit: int = 300) -> list:
    """문장 번호들 → 한국어 번역 문장 글(직접 번역만)."""
    texts = []
    for sid in list(ids)[:limit]:
        sentence = tat.sentences.get(sid)
        if sentence is None:
            continue
        for kid in sentence.ko:
            korean = tat.sentences.get(kid)
            if korean is not None:
                texts.append(korean.text)
    return texts


def kr_category(word) -> str:
    if word is None or not word.category:
        return ""
    parts = [p.strip() for p in word.category.split(">")]
    return " > ".join(parts[:2])


def declump(items: list, window: int = 10, most: int = 2) -> list:
    """L22: 같은 범주 낱말이 열 개 안에 셋 이상 몰리지 않게 뒤로 조금 민다(빈도 순서는 거의 그대로)."""
    out = []
    waiting = []
    for item in items:
        waiting.append(item)
        progressed = True
        while waiting and progressed:
            progressed = False
            for index, candidate in enumerate(waiting):
                recent = [i.category for i in out[-(window - 1):] if i.category]
                if not candidate.category or recent.count(candidate.category) < most or len(waiting) > 6:
                    out.append(waiting.pop(index))
                    progressed = True
                    break
    out.extend(waiting)
    return out


# ── 영어 묶음 ──────────────────────────────────────────────────────────────

def read_ngsl(stats: str, forms_path: str | None) -> tuple:
    with open(stats, encoding="utf-8-sig") as handle:
        # 표 프로그램이 true · false 를 TRUE · FALSE 로 바꿔 둔 줄이 있다(NGSL 1.2 stats).
        rows = sorted((int(r["SFI Rank"]), r["Lemma"].strip().lower() if r["Lemma"].strip() in ("TRUE", "FALSE") else r["Lemma"].strip())
                      for r in csv.DictReader(handle) if r.get("Lemma", "").strip())
    forms = collections.defaultdict(set)
    if forms_path:
        with open(forms_path, encoding="utf-8-sig") as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    continue
                parts = [p.strip().lower() for p in line.strip().split(",") if p.strip()]
                if parts:
                    forms[parts[0]].update(parts)
    return rows, forms


def build_en(rows: list, forms: dict, koidx: KoIndex, kr: dict, ov: Overrides, examples: Examples = None) -> list:
    items = []
    seen = set()
    for rank, lemma in rows:
        key = lemma.lower()
        if key in seen:
            continue
        seen.add(key)
        item = Item("en", lemma)
        row = ov.get("en", lemma)
        if "drop" in row or key in ov.block["en"]:
            continue
        cands = koidx.candidates("en", [key], set())
        if examples is not None:
            word_forms = (forms.get(key) or set()) | en_inflections(key)
            ids = sorted(set(sid for form in word_forms for sid in examples.en.get(form, ()) if examples.tat.sentences[sid].ko))
            cands = ko_translation_vote(cands, ko_texts_for(ids, examples.tat), kr)
        item.ko, chosen = choose_korean(cands, kr)
        forms_of = {kr[w].form: kr[w] for _, w, _ in cands}
        item.ko = [ko_attributive(m) if forms_of.get(m) is not None and forms_of[m].pos == "형용사"
                   else m + "인" if m.endswith("적") and len(m) >= 3 and forms_of.get(m) is not None and forms_of[m].pos in ("관형사", "명사")
                   else m for m in item.ko]
        item.why = " | ".join(f"{s:.1f} {w}" for s, _, w in cands[:4])
        item.pos = KR_POS.get(chosen.pos, "n") if chosen else "n"
        item.category = kr_category(chosen)
        if not apply_override(item, row):
            continue
        if "ko" in row and chosen is not None and row["ko"].split(";")[0].strip() != chosen.form:
            first = next((kr[w] for _, w, _ in cands if kr[w].form == split_meanings(row["ko"])[0]), None)
            item.category = kr_category(first)
            if first is not None and "pos" not in row:
                item.pos = KR_POS.get(first.pos, item.pos)
        item.forms = (forms.get(key) or set()) | en_inflections(key)
        item.ko_stems = [ko_stem(m) for m in item.ko]
        item.useful = rank
        item.ref = None
        items.append(item)
    return items


# ── 중국어 묶음 ────────────────────────────────────────────────────────────

ZH_NUMERAL = set("〇零一二三四五六七八九十百千万亿两几半第")
# jieba 품사 → 묶음 품사(풀이가 'to …' 면 동사가 먼저).
ZH_POS = {"n": "n", "nr": "n", "ns": "n", "nt": "n", "nz": "n", "ng": "n", "vn": "n", "an": "n", "s": "n", "f": "n", "t": "n",
          "tg": "n", "v": "v", "vd": "v", "vg": "v", "vi": "v", "a": "adj", "ad": "adj", "ag": "adj", "b": "adj", "z": "adj",
          "d": "adv", "df": "adv", "dg": "adv", "r": "pron", "rr": "pron", "rz": "pron", "m": "num", "mq": "num", "q": "cl",
          "p": "prep", "c": "conj", "e": "intj", "o": "intj", "l": "phr", "i": "phr"}
ZH_BOUND = re.compile(r"^\((bound form|suffix|prefix|particle|literary|classical|archaic|old)\b")


def zh_pos(entry: CedictEntry, tag: str, chosen: list = ()) -> str:
    first = chosen[0] if chosen else next((g for g in entry.glosses if not g.startswith("CL:")), "")
    if first.startswith("to ") or re.match(r"^\((coll\.|Tw|of [^)]*)\) to ", first):
        return "v"
    if re.match(r"^classifier for ", first):
        return "cl"
    return ZH_POS.get(tag, "n")


def zh_useful_entries(entries: list) -> list:
    plain = [e for e in entries if not e.proper and not e.weak and not e.surname_only]
    return [e for e in plain if not all(CEDICT_BAD.search(g) or ZH_BOUND.match(g) for g in e.glosses if not g.startswith("CL:"))]


ZH_LABEL = re.compile(r"^\((bound form|literary|classical|archaic|old|dialect|Cantonese|Tw|onom\.|slang|vulgar|derog\.|"
                      r"Buddhism|Taoism|math\.|chemistry|physics|medicine|biology|botany|zoology|computing|linguistics|law|"
                      r"finance|military|music|sports|loanword|neologism|Internet slang|honorific|polite|written)\)")


def zh_senses(entry: CedictEntry) -> list:
    """CC-CEDICT 풀이 = '/' 로 뜻, ';' 로 같은 뜻의 다른 말. [(표시 붙은 뜻인가, [작은 풀이들])]. 분류사 · 참조 풀이는 뺀다."""
    out = []
    for gloss in entry.glosses:
        if gloss.startswith("CL:") or CEDICT_WEAK.match(gloss):
            continue
        labelled = bool(ZH_LABEL.match(gloss))
        parts = []
        depth = 0
        current = ""
        for char in gloss:
            depth += {"(": 1, ")": -1}.get(char, 0)
            if char == ";" and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += char
        parts.append(current)
        subs = [p.strip() for p in parts if p.strip()]
        if subs:
            out.append((labelled, subs))
    return out


def zh_english_sets(word: str, examples: Examples, tat: Tatoeba) -> list:
    """이 말이 낱말로 든 Tatoeba 문장의 영어 번역 낱말 모음들(뜻 · 풀이 순서 투표 재료)."""
    sets = []
    for sid in examples.zh.get(word, ())[:400]:
        sentence = tat.sentences.get(sid)
        if sentence is None:
            continue
        english = set()
        for eid in sentence.en:
            if eid in tat.sentences:
                english |= en_words(tat.sentences[eid].text)
        if english:
            sets.append(english)
    return sets


# 번역 문장 거의 어디에나 드는 영어 낱말(like · other · have …)은 뜻 투표에 쓰지 않는다. build_all 이 Tatoeba 번역으로 채운다.
EN_COMMON = set()


def votes_for(text: str, sets: list) -> int:
    words = en_words(text)
    content = {w for w in words if w not in EN_COMMON} or words
    return sum(1 for english in sets if content & english) if content else 0


def common_english(tat: Tatoeba, share: float = 0.012) -> set:
    """중 · 일 문장의 영어 번역에서 1.2% 넘는 문장에 드는 낱말."""
    counts = collections.Counter()
    total = 0
    for sentence in tat.sentences.values():
        if sentence.lang in ("cmn", "jpn") and sentence.en:
            english = tat.sentences.get(sentence.en[0])
            if english is not None:
                total += 1
                counts.update(en_words(english.text))
    return {w for w, c in counts.items() if c > share * max(1, total)}


def zh_choose_entry(word: str, entries: list, sets: list, wanted: str | None) -> tuple:
    """같은 표기의 다른 병음 = 다른 뜻. 덧쓰기 병음 → 그 병음, 아니면 Tatoeba 번역에 풀이 낱말이 많이 든 항목.
    같은 병음 항목이 둘 이상이면(后 = 왕후 · 後 뒤) 그 안에서도 같은 투표로 고른다."""
    groups = collections.OrderedDict()
    for entry in entries:
        groups.setdefault(entry.pinyin, []).append(entry)
    if wanted and wanted not in groups:
        raise ValueError(f"덧쓰기 병음 {wanted} 가 CC-CEDICT {word} 에 없다(있는 것 {list(groups)})")
    pool = groups[wanted] if wanted else entries
    if len(pool) == 1:
        return pool[0], "덧쓰기" if wanted else ""
    votes = {id(e): votes_for(" ".join(" ".join(sub) for labelled, sub in zh_senses(e) if not labelled), sets) for e in pool}
    best = max(pool, key=lambda e: (votes[id(e)], len(e.glosses), -pool.index(e)))
    return best, ("덧쓰기 " if wanted else "") + "투표 " + " ".join(f"{e.pinyin}/{e.trad}:{votes[id(e)]}" for e in pool)


def zh_pick_glosses(entry: CedictEntry, sets: list, count: int = 3, total: int = 44) -> list:
    """영어 뜻 1~3개 = 자주 쓰는 뜻 먼저(사전 풀이 순서는 빈도 순이 아니다: 幹 = tree trunk … to do).
    뜻 순서 = 표시 없는 뜻 → Tatoeba 번역 투표(두 표 넘게 앞서야 자리를 바꾼다) → 사전 순서. 첫 뜻에서 둘, 다음 뜻에서 하나."""
    senses = zh_senses(entry)
    if not senses:
        return []
    def promoted(votes: list) -> list:
        """사전 순서를 지키되, 뒤 것이 첫째의 두 배 + 2 표를 넘을 때만 앞으로(幹 tree trunk < to do)."""
        first = votes[0]
        order = sorted(range(len(votes)), key=lambda i: (0 if i == 0 or votes[i] < 2 * first + 2 else -votes[i], i))
        return order

    rows = []
    for index, (labelled, subs) in enumerate(senses):
        sub_votes = [votes_for(sub, sets) for sub in subs]
        rows.append((labelled, index, [subs[i] for i in promoted(sub_votes)], max(sub_votes)))
    plain = [r for r in rows if not r[0]] or rows
    rest = [r for r in rows if r[0] and r in rows and r not in plain]
    order = promoted([r[3] for r in plain])
    ranked = [(r[0], 0, r[1], r[2], r[3]) for r in [plain[i] for i in order] + rest]
    out = []
    top_votes = None
    for labelled, _, _, subs, votes in ranked:
        if out and (len(out) >= count or votes < max(2, top_votes * 0.3)):
            break
        take = 2 if not out else 1
        for sub in subs:
            short = short_gloss(sub, 30)
            if not short or short.lower() in (g.lower() for g in out):
                continue
            if out and sum(len(g) + 2 for g in out) + len(short) > total:
                break
            out.append(short)
            if top_votes is None:
                top_votes = votes
            take -= 1
            if take == 0 or len(out) == count:
                break
    return out


def build_zh(wf: WordFreq, cedict: dict, jieba_pos: dict, examples: Examples, tat: Tatoeba, koidx: KoIndex, kr: dict,
             ov: Overrides, limit: int) -> list:
    ranks = wf.ranks("zh")
    counts = collections.Counter()
    for sid, tokens in examples.zh_tokens.items():
        for token in set(tokens):
            counts[token] += 1
    pool = []
    for word, rank in ranks.items():
        if rank > 60000 or len(pool) >= limit * 3:
            break
        if not ZH_WORD.match(word) or len(word) > 4:
            continue
        row = ov.get("zh", word)
        if "drop" in row or word in ov.block["zh"]:
            continue
        tag = jieba_pos.get(word, "")
        if "keep" not in row:
            if tag[:1] in ("u", "y", "k", "h", "x") or tag in ("e", "o"):
                continue
            if len(word) > 1 and all(c in ZH_NUMERAL for c in word):
                continue
            if word[0] == "第" and all(c in ZH_NUMERAL for c in word[1:]):
                continue
        entries = zh_useful_entries(cedict.get(word, []))
        if not entries:
            continue
        pool.append((word, rank, counts.get(word, 0), tag, entries, row))
    by_count = sorted(range(len(pool)), key=lambda i: (-pool[i][2], pool[i][1]))
    count_rank = {}
    for position, index in enumerate(by_count, 1):
        count_rank[index] = position if pool[index][2] > 0 else len(pool)
    order = sorted(range(len(pool)), key=lambda i: (math.log(i + 1) + math.log(count_rank[i]), pool[i][1]))
    items = []
    for index in order:
        word, rank, count, tag, entries, row = pool[index]
        sets = zh_english_sets(word, examples, tat)
        entry, how = zh_choose_entry(word, entries, sets, row.get("reading"))
        item = Item("zh", word)
        item.ref = entry.key
        item.reading = entry.pinyin
        item.alt = entry.trad if entry.trad != word else None
        item.en = zh_pick_glosses(entry, sets)
        if not item.en:
            continue
        item.gloss_words = en_words(" ".join(g for g in entry.glosses if not g.startswith("CL:")))
        item.pos = zh_pos(entry, tag, item.en)
        cands = koidx.candidates("zh", [word], en_words(" ".join(item.en)), item.pos, (entry.trad, word))
        cands = ko_translation_vote(cands, ko_texts_for(examples.zh.get(word, ()), tat), kr)
        item.ko, chosen = choose_korean(cands, kr)
        item.category = kr_category(chosen)
        item.why = f"wf{rank} tat{count} {tag} {how} || " + " | ".join(f"{s:.1f} {w}" for s, _, w in cands[:4])
        if "reading" in row:
            item.overridden.append("reading")
        if not apply_override(item, row):
            continue
        item.ko_stems = [ko_stem(m) for m in item.ko]
        item.useful = len(items)
        items.append(item)
        if len(items) >= limit:
            break
    return items


# ── 일본어 묶음 ────────────────────────────────────────────────────────────

GODAN_STEMS = {"う": "わいっえお", "く": "かきいけこ", "ぐ": "がぎいげご", "す": "さしせそ", "つ": "たちってと", "ぬ": "なにんねの",
               "ぶ": "ばびんべぼ", "む": "まみんめも", "る": "らりっれろ"}


def ja_surfaces(term: str, tags: list) -> set:
    """wordfreq(MeCab 표면형) 에서 이 말을 찾을 꼴: 사전형 + 활용 줄기(思う → 思っ · 思い · 思わ)."""
    out = {term}
    # 가나만 된 활용어의 줄기(それる → それ)는 다른 말과 겹쳐 빈도를 부풀린다 = 한자 든 말만 줄기를 센다.
    if not HAN.search(term):
        return out
    if any(t.startswith("v1") for t in tags) and term.endswith("る"):
        out.add(term[:-1])
    if any(t.startswith("v5") for t in tags) and term[-1:] in GODAN_STEMS:
        for kana in GODAN_STEMS[term[-1]]:
            out.add(term[:-1] + kana)
    if "adj-i" in tags and term.endswith("い"):
        out |= {term[:-1], term[:-1] + "く", term[:-1] + "かっ"}
    if "vs-i" in tags and term.endswith("する"):
        out |= {term[:-2] + "し", term[:-2] + "さ"}
    if "vk" in tags:
        out |= {"来", "き", "こ"}
    return out


class JaEntry:
    __slots__ = ("seq", "kanji", "kana", "senses")

    def __init__(self, seq, kanji, kana, senses):
        self.seq, self.kanji, self.kana, self.senses = seq, kanji, kana, senses


def ja_entries(data: dict) -> list:
    out = []
    for word in data["words"]:
        kanji = [(k["text"], bool(k.get("common")), k.get("tags", [])) for k in word.get("kanji", []) if "sK" not in k.get("tags", [])]
        kana = [(k["text"], bool(k.get("common")), k.get("tags", []), k.get("appliesToKanji", ["*"]))
                for k in word.get("kana", []) if "sk" not in k.get("tags", [])]
        senses = []
        for sense in word.get("sense", []):
            senses.append((sense.get("partOfSpeech", []), sense.get("misc", []),
                           [no_dash(g["text"]) for g in sense.get("gloss", [])],
                           sense.get("appliesToKanji", ["*"]), sense.get("appliesToKana", ["*"])))
        if kana:
            out.append(JaEntry(int(word["id"]), kanji, kana, senses))
    return out


def ja_form_index(entries: list) -> dict:
    """표기 → [(항목 번호, 그 표기의 기본 가나, 그 항목의 가나 전부)]. 흔한 항목 · 그 표기가 대표 표기인 항목 먼저
    (색인 줄의 は = 조사 は 이지 歯 가 아니고, 本 = ほん 이지 元 의 다른 표기가 아니다)."""
    index = collections.defaultdict(list)
    for entry in entries:
        kana_all = frozenset(hiragana(k[0]) for k in entry.kana)
        for position, (text, common, tags) in enumerate(entry.kanji):
            kana = next((k[0] for k in entry.kana if applies(k[3], text) and k[1]), None) or \
                   next((k[0] for k in entry.kana if applies(k[3], text)), entry.kana[0][0])
            index[text].append((not common, position, entry.seq, kana, kana_all))
        for position, (text, common, tags, _) in enumerate(entry.kana):
            # 가나 표기는 한자 표기가 없는 말 · 보통 가나로 쓰는 말이 그 가나의 주인이다.
            usually = not entry.kanji or any("uk" in s[1] for s in entry.senses[:1])
            index[text].append((not common, position + (0 if usually else 10), entry.seq, text, kana_all))
    return {form: [(seq, kana, kana_all) for _, _, seq, kana, kana_all in sorted(rows, key=lambda r: r[:3])]
            for form, rows in index.items()}


def build_ja(wf: WordFreq, entries: list, examples: Examples, koidx: KoIndex, kr: dict, ov: Overrides, limit: int) -> list:
    ranks = wf.ranks("ja")
    pool = []
    for entry in entries:
        rows = examples.ja.get(entry.seq, ())
        by_kana = collections.Counter(r[1] for r in rows)
        common_kana = [k for k in entry.kana if k[1]] or entry.kana
        kana = by_kana.most_common(1)[0][0] if by_kana else hiragana(common_kana[0][0])
        kana_form = next((k for k in entry.kana if hiragana(k[0]) == kana), common_kana[0])
        senses = [s for s in entry.senses if applies(s[4], kana_form[0])]
        if not senses:
            continue
        # 색인 줄의 뜻 번호(번호 없음 = 첫 뜻). 다른 뜻이 첫 뜻보다 두 배 넘게 쓰였을 때만 그 뜻을 대표로.
        sense_votes = collections.Counter(r[2] for r in rows if r[1] == kana)
        primary = senses[0]
        if sense_votes:
            top, votes = sense_votes.most_common(1)[0]
            if 1 <= top <= len(entry.senses) and votes >= 2 * max(1, sense_votes.get(1, 0)) and entry.senses[top - 1] in senses:
                primary = entry.senses[top - 1]
        pos_tags = primary[0] or next((s[0] for s in senses if s[0]), [])
        misc = set(primary[1])
        usually_kana = "uk" in misc or not entry.kanji
        kanji_ok = [k for k in entry.kanji if applies(kana_form[3], k[0]) and not set(k[2]) & {"rK", "iK", "oK", "ateji"}]
        kanji_ok = [k for k in kanji_ok if k[1]] or kanji_ok
        term = kana_form[0] if usually_kana or not kanji_ok else kanji_ok[0][0]
        surfaces = ja_surfaces(term, pos_tags)
        rank = min((ranks.get(s, 10 ** 6) for s in surfaces), default=10 ** 6)
        if not rows and rank > 30000:
            continue
        pool.append((entry, term, kana, primary, pos_tags, misc, len(rows), rank, senses))
    by_count = sorted(range(len(pool)), key=lambda i: (-pool[i][6], pool[i][7]))
    count_rank = {index: (position if pool[index][6] else len(pool)) for position, index in enumerate(by_count, 1)}
    by_rank = sorted(range(len(pool)), key=lambda i: pool[i][7])
    freq_rank = {index: position for position, index in enumerate(by_rank, 1)}
    order = sorted(range(len(pool)), key=lambda i: math.log(freq_rank[i]) + math.log(count_rank[i]))
    items = []
    seen_terms = set()
    for index in order:
        entry, term, kana, primary, pos_tags, misc, count, rank, senses = pool[index]
        row = ov.get("ja", term, str(entry.seq))
        if "drop" in row or term in ov.block["ja"]:
            continue
        if "reading" in row:
            wanted = hiragana(row["reading"])
            form = next((k for k in entry.kana if hiragana(k[0]) == wanted), None)
            if form is None:
                raise ValueError(f"덧쓰기 가나 {wanted} 가 JMdict {entry.seq} {term} 에 없다")
            kana = wanted
            senses = [s for s in entry.senses if applies(s[4], form[0])] or senses
            primary = senses[0]
            pos_tags = primary[0] or pos_tags
        if "keep" not in row:
            if not pos_tags or set(pos_tags) <= JA_EXCLUDED_POS or pos_tags[0] in JA_EXCLUDED_POS:
                continue
            if misc & JA_BAD_MISC or any(CEDICT_BAD.search(g) for g in primary[2]):
                continue
            # 고유 명사(풀이가 다 대문자로 시작: Japan · Tokyo) · 숫자만 · 한 글자 가나.
            if primary[2] and all(g[:1].isupper() and g not in ("I",) for g in primary[2]):
                continue
            if re.match(r"^[〇一二三四五六七八九十百千万億]{2,}$", term) or (KANA_ONLY.match(term) and len(term) == 1):
                continue
        if (term, kana) in seen_terms:
            continue
        seen_terms.add((term, kana))
        item = Item("ja", term)
        item.ref = str(entry.seq)
        item.reading = kana if HAN.search(term) else None
        item.en = pick_glosses(primary[2])
        if not item.en:
            continue
        item.gloss_words = en_words(" ".join(primary[2]))
        item.pos = ja_pos_code(pos_tags)
        keys = [k[0] for k in entry.kanji] + [k[0] for k in entry.kana]
        if term.endswith("する"):
            keys.append(term[:-2])
        cands = koidx.candidates("ja", keys, item.gloss_words, item.pos, tuple(k[0] for k in entry.kanji))
        cands = ko_translation_vote(cands, ko_texts_for([r[0] for r in examples.ja.get(entry.seq, ()) if r[1] == kana], examples.tat), kr)
        item.ko, chosen = choose_korean(cands, kr)
        item.category = kr_category(chosen)
        item.why = f"wf{rank} tat{count} {','.join(pos_tags)} || " + " | ".join(f"{s:.1f} {w}" for s, _, w in cands[:4])
        if "reading" in row:
            item.overridden.append("reading")
        if not apply_override(item, row):
            continue
        item.ko_stems = [ko_stem(m) for m in item.ko]
        item.useful = len(items)
        items.append(item)
        if len(items) >= limit:
            break
    return items


# ── 한국어 묶음(한국어를 배우는 사람, 뜻 = 영어) ──────────────────────────────────

# 학습용 어휘 목록 품사 줄임 → 한국어기초사전 품사. 고(고유 명사) · 보(보조 용언)는 싣지 않는다.
NIKL_POS = {
    "명": ("명사",), "동": ("동사",), "형": ("형용사",), "부": ("부사",), "대": ("대명사",), "수": ("수사",),
    "관": ("관형사",), "감": ("감탄사",), "의": ("의존 명사",), "불": ("부사", "감탄사", "대명사", "명사"),
}


def read_nikl(path: str) -> list:
    with open(path, encoding="cp949") as handle:
        lines = handle.read().splitlines()
    rows = []
    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) < 5 or not cols[0].strip().isdigit():
            continue
        rows.append((int(cols[0]), cols[1].strip(), cols[2].strip(), cols[3].strip(), cols[4].strip()))
    return rows


def nikl_entry(term: str, pos: str, hint: str, by_form: dict) -> object:
    """학습용 어휘 한 줄 → 한국어기초사전 항목 하나(품사 · 원어 · 풀이 힌트로 고른다)."""
    rows = by_form.get(term, [])
    wanted = NIKL_POS.get(pos)
    if wanted:
        rows = [w for w in rows if w.pos in wanted] or ([] if pos != "불" else rows)
    if not rows:
        return None
    if HAN.search(hint):
        han = "".join(HAN.findall(hint))
        rows = [w for w in rows if w.origin and "".join(HAN.findall(w.origin)) == han] or rows
    elif hint and len(rows) > 1:
        # 풀이 힌트('버스에 ~' · '~를 띄우다' · '10시 20~')의 낱말을 조사를 떼고 그 항목 뜻풀이 · 구 · 예문에서 찾는다.
        needles = []
        for token in re.split(r"[\s~.,·]+", hint):
            token = re.sub(r"(에서|으로|에게|에|를|을|이|가|은|는|와|과|로|의|도)$", "", token)
            if token and token != term:
                needles.append(token)
        def overlap(word):
            score = 0
            for sense in word.senses[:4]:
                text = " ".join((sense.ko_def,) + tuple(sense.phrases) + tuple(sense.examples[:8]))
                score += sum((3 if sense.order == 0 else 1) for n in needles if n in text)
            return score
        best = max(overlap(w) for w in rows)
        if best:
            rows = [w for w in rows if overlap(w) == best]
    rows.sort(key=lambda w: (w.level or 9, w.hom, w.id))
    return rows[0]


def ko_reading(word) -> str | None:
    """표준 발음(장음 표시 ː 빼고). 표기와 같으면 없음(카드에 같은 글이 두 번 보이지 않게)."""
    pron = (word.pron or "").split("/")[0].replace("ː", "").replace(":", "").strip()
    return pron if pron and pron != word.form.replace(" ", "") and pron != word.form else None


def build_ko(rows: list, kr: dict, ov: Overrides) -> list:
    by_form = collections.defaultdict(list)
    for word in kr.values():
        by_form[word.form].append(word)
    grade_order = {"A": 0, "B": 1, "C": 2}
    rows = sorted((r for r in rows if r[4] in grade_order), key=lambda r: (grade_order[r[4]], r[0]))
    items = []
    seen_ids = set()
    seen_terms = collections.defaultdict(list)
    for rank, raw, pos, hint, grade in rows:
        term = re.sub(r"\d+$", "", raw)
        if pos in ("고", "보", "조") or not term or term.startswith("-") or term.endswith("-"):
            continue
        word = nikl_entry(term, pos, hint, by_form)
        # 덧쓰기 키 = 표기 · 학습용 어휘 원래 꼴(배02 = 동형어 번호까지) · 표기@항목 번호. ref = 한국어기초사전 항목을 바꿔 고른다.
        row = dict(ov.get("ko", raw))
        if word is not None:
            row.update(ov.get("ko", term, str(word.id)))
        if "ref" in row:
            word = kr[int(row["ref"])]
            row.update(ov.get("ko", term, str(word.id)))
        if word is None or word.id in seen_ids or not word.senses:
            continue
        if "drop" in row or term in ov.block["ko"]:
            continue
        item = Item("ko", term)
        item.ref = str(word.id)
        item.reading = ko_reading(word)
        item.pos = KR_POS.get(word.pos, "n")
        item.en = kr_english(word.senses[0])
        if not item.en:
            item.en = next((kr_english(s) for s in word.senses[1:] if kr_english(s)), [])
        item.category = kr_category(word)
        item.why = f"{raw}/{pos}/{grade}/{hint} → {word.form}{word.hom}/{word.pos}/L{word.level or '-'}"
        if "ref" in row:
            item.overridden.append("ref")
        if not apply_override(item, row):
            continue
        if not item.en:
            continue
        # 같은 표기 다른 품사(가까이 부 · 명)는 영어 뜻이 겹치면 앞 것만.
        overlap = any(set(e.lower() for e in item.en) & set(e.lower() for e in other.en) for other in seen_terms[term])
        if overlap and "keep" not in row:
            continue
        seen_ids.add(word.id)
        seen_terms[term].append(item)
        item.gloss_words = en_words(" ".join(item.en))
        item.forms = ko_forms(term, item.pos)
        item.useful = len(items)
        item.kr_word = word
        items.append(item)
    return items


def ko_dictionary_example(item: Item) -> tuple | None:
    """Tatoeba 에 맞는 문장이 없을 때 = 한국어기초사전 그 항목의 예문(번역 없음). 짧고 이 말이 든 것."""
    word = getattr(item, "kr_word", None)
    if word is None:
        return None
    best = None
    for sense in word.senses[:2]:
        for text in sense.examples:
            if len(text) > MAX_CHARS_KO or len(text.split()) > MAX_EOJEOL_KO:
                continue
            if not any(ko_matches(e, item.forms, item.pos) for e in text.split()):
                continue
            key = (sense.order, abs(len(text) - 14), text)
            if best is None or key < best[0]:
                best = (key, text)
    if best is None:
        return None
    return best[1], None, None, f"krdict:{word.id}", False


# ── 영어 예문 사전용 말(NGSL 밖, 넣기 시트 제안) ───────────────────────────────

def en_extra_terms(wf: WordFreq, have: set, koidx: KoIndex, kr: dict, ov: Overrides, limit: int) -> list:
    out = []
    for word, rank in wf.ranks("en").items():
        if len(out) >= limit:
            break
        if not re.match(r"^[a-z]{3,}$", word) or word in have or word in ov.block["en"]:
            continue
        item = Item("en", word)
        item.ko, _ = choose_korean(koidx.candidates("en", [word], set()), kr)
        item.ko_stems = [ko_stem(m) for m in item.ko]
        item.forms = en_inflections(word)
        out.append(item)
    return out


# ── 쓰기 ───────────────────────────────────────────────────────────────────

PACK_TITLES = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean"}


def write_pack(out: str, pack_id: str, lang: str, items: list, sources: dict) -> None:
    payload = {"format": FORMAT, "id": pack_id, "lang": lang, "sources": sources,
               "items": [item.as_json(index + 1) for index, item in enumerate(items)]}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if EM_DASH in text:
        raise ValueError(f"{pack_id} 에 줄표가 남았다")
    path = os.path.join(out, f"{pack_id}.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    log(f"{pack_id}.json: {len(items)}개 · {os.path.getsize(path) / 1e3:.0f}KB")


def write_examples(path: str, rows: list, meta: dict) -> None:
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.execute("PRAGMA page_size = 4096")
    db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID")
    db.executescript("""
        -- 한 줄 = 말 하나의 예문 하나(lang en · zh · ja · ko, reading = zh 숫자 성조 병음 · ja 히라가나, 영 · 한은 빈 글).
        -- ko · en = 그 문장의 한국어 · 영어 번역(사람 번역만, 없으면 빈 글). source = tatoeba:<문장 번호> · krdict:<항목 번호>.
        CREATE TABLE example(lang TEXT NOT NULL, term TEXT NOT NULL, reading TEXT NOT NULL, text TEXT NOT NULL,
                             ko TEXT NOT NULL, en TEXT NOT NULL, source TEXT NOT NULL,
                             PRIMARY KEY(lang, term, reading)) WITHOUT ROWID;
    """)
    db.executemany("INSERT INTO meta VALUES(?, ?)", [(k, str(v)) for k, v in meta.items()])
    db.executemany("INSERT OR IGNORE INTO example VALUES(?, ?, ?, ?, ?, ?, ?)", rows)
    db.commit()
    db.execute("VACUUM")
    db.close()
    log(f"examples.sqlite: {len(rows)}줄 · {os.path.getsize(path) / 1e6:.2f}MB")


def coverage_row(pack_id: str, lang: str, items: list) -> dict:
    n = len(items) or 1
    def pct(count):
        return round(100.0 * count / n, 1)
    needs_reading = [i for i in items if lang == "zh" or (lang == "ja" and HAN.search(i.term))]
    reading = "n/a" if lang in ("en", "ko") else round(100.0 * sum(1 for i in needs_reading if i.reading) / max(1, len(needs_reading)), 1)
    has_ex = [i for i in items if i.example]
    return {
        "pack": pack_id, "words": len(items), "reading%": reading,
        "ko%": "n/a" if lang == "ko" else pct(sum(1 for i in items if i.ko)),
        "en%": "n/a" if lang == "en" else pct(sum(1 for i in items if i.en)),
        "ex%": pct(len(has_ex)),
        "exKo%": "n/a" if lang == "ko" else pct(sum(1 for i in has_ex if i.example[1])),
        "exEn%": "n/a" if lang == "en" else pct(sum(1 for i in has_ex if i.example[2])),
        "ov": sum(1 for i in items if i.overridden),
    }


def write_report(folder: str, lang: str, packs: list) -> list:
    os.makedirs(folder, exist_ok=True)
    rows = []
    with open(os.path.join(folder, f"review-{lang}.tsv"), "w", encoding="utf-8") as handle:
        handle.write("pack\trank\tterm\treading\tpos\tko\ten\tex\texKo\texEn\tcat\tov\twhy\n")
        for pack_id, items in packs:
            rows.append(coverage_row(pack_id, lang, items))
            for number, item in enumerate(items, 1):
                ex = item.example or ("", None, None, "", False)
                handle.write("\t".join([pack_id, str(number), item.term, item.reading or "", item.pos, "; ".join(item.ko),
                                        "; ".join(item.en), ex[0], ex[1] or "", ex[2] or "", item.category,
                                        ",".join(item.overridden), item.why]) + "\n")
    return rows


def print_table(rows: list) -> str:
    keys = ["pack", "words", "reading%", "ko%", "en%", "ex%", "exKo%", "exEn%", "ov"]
    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for row in rows:
        lines.append("| " + " | ".join(str(row[k]) for k in keys) + " |")
    return "\n".join(lines)


def split_packs(lang: str, items: list) -> list:
    out = []
    start = 0
    for index, size in enumerate(PACK_SIZES):
        chunk = items[start:start + size]
        start += size
        if chunk:
            out.append((f"{lang}-{index + 1}", chunk))
    return out


def build_all(args) -> int:
    ov = Overrides(args.overrides)
    log("사전 읽기")
    cedict, cedict_version = load_cedict(args.cedict)
    jm = load_jmdict(args.jmdict)
    jm_entries = ja_entries(jm)
    ja_forms = ja_form_index(jm_entries)
    kr, kr_version = load_krdict(args.krdict)
    nikl_rows = read_nikl(args.nikl)
    by_form = collections.defaultdict(list)
    for word in kr.values():
        by_form[word.form].append(word)
    nikl_rank = {}
    for rank, raw, pos, hint, grade in nikl_rows:
        word = nikl_entry(re.sub(r"\d+$", "", raw), pos, hint, by_form)
        if word is not None:
            nikl_rank[word.id] = min(rank, nikl_rank.get(word.id, rank))
    koidx = KoIndex(kr, nikl_rank)
    wf = WordFreq(args.wordfreq)
    jieba_freq, jieba_pos = wf.jieba()
    segmenter = ZhSegmenter(jieba_freq)
    simplify = wf.simplify_map()
    log("Tatoeba 읽기")
    tat = Tatoeba(args.tatoeba, lambda text: len(text.split()) <= MAX_WORDS_EN)
    examples = Examples(tat, ov.block, segmenter, simplify, ja_forms)
    EN_COMMON.update(common_english(tat))
    log(f"흔한 영어 낱말(투표 제외) {len(EN_COMMON)}개")
    ngsl_rows, ngsl_forms = read_ngsl(args.ngsl, args.ngsl_forms)
    total = sum(PACK_SIZES)
    log("묶음 고르기")
    built = {
        "en": build_en(ngsl_rows, ngsl_forms, koidx, kr, ov, examples),
        "zh": build_zh(wf, cedict, jieba_pos, examples, tat, koidx, kr, ov, EXAMPLE_TERMS),
        "ja": build_ja(wf, jm_entries, examples, koidx, kr, ov, EXAMPLE_TERMS),
        "ko": build_ko(nikl_rows, kr, ov),
    }
    if len(kr_version) == 8 and kr_version.isdigit():
        kr_version = f"{kr_version[:4]}-{kr_version[4:6]}-{kr_version[6:]}"
    sources = {
        "en": {"list": "NGSL 1.2", "meaning": f"krdict {kr_version}", "examples": "Tatoeba"},
        "zh": {"list": "wordfreq 3.1.1 + Tatoeba", "dict": f"CC-CEDICT {cedict_version}", "meaning": f"krdict {kr_version}",
               "examples": "Tatoeba"},
        "ja": {"list": "wordfreq 3.1.1 + Tatoeba", "dict": f"JMdict {jm.get('dictDate', '')}", "meaning": f"krdict {kr_version}",
               "examples": "Tatoeba"},
        "ko": {"list": "NIKL 2003", "dict": f"krdict {kr_version}", "examples": "Tatoeba + krdict"},
    }
    os.makedirs(args.out, exist_ok=True)
    table = []
    example_rows = []
    for lang, items in built.items():
        # 영어 묶음은 한국어 뜻이 곧 카드 뜻이다 = 한국어 뜻이 없는 말은 싣지 않는다(영어 뜻으로 대신할 수 없다).
        if lang == "en":
            items = [i for i in items if i.ko]
        pack_items = items[:total]
        # 예문은 묶음 단어부터(쓰임 순 = 앞 단어가 좋은 문장을 먼저 가진다), 그다음 예문 사전용 나머지.
        for item in pack_items:
            item.example = examples.find(item, ko_target=lang != "ko")
            if item.example is None and lang == "ko":
                item.example = ko_dictionary_example(item)
        ordered = declump(pack_items)
        packs = split_packs(lang, ordered)
        for pack_id, chunk in packs:
            write_pack(args.out, pack_id, lang, chunk, sources[lang])
        if args.report:
            table += write_report(args.report, lang, packs)
        rest = items[total:]
        if lang == "en":
            rest = en_extra_terms(wf, {f for i in items for f in i.forms}, koidx, kr, ov, EXAMPLE_TERMS - len(items))
        for item in rest:
            item.example = examples.find(item, ko_target=lang != "ko")
            if item.example is None and lang == "ko":
                item.example = ko_dictionary_example(item)
        for item in pack_items + rest:
            if item.example:
                text, ko, en, source, _ = item.example
                example_rows.append((lang, item.term, (item.reading or "") if lang in ("zh", "ja") else "", text, ko or "",
                                     en or "", source))
    if args.examples_out:
        os.makedirs(args.examples_out, exist_ok=True)
        tatoeba_dates = sorted({os.path.getmtime(os.path.join(args.tatoeba, f)) for f in TATOEBA_FILES})
        write_examples(os.path.join(args.examples_out, "examples.sqlite"), example_rows, {
            "format": "1", "source": "Tatoeba", "license": "CC BY 2.0 FR",
            "license_url": "https://creativecommons.org/licenses/by/2.0/fr/", "url": "https://tatoeba.org",
            "version": args.tatoeba_version or "", "also": f"한국어기초사전 {kr_version} 예문(CC BY-SA 2.0 KR)",
        })
    unused = ov.unused()
    if unused:
        log(f"쓰이지 않은 덧쓰기 {len(unused)}줄: " + ", ".join(f"{l}:{k}" for l, k in unused[:40]))
        if args.strict:
            return 1
    log(print_table(table))
    if args.report:
        with open(os.path.join(args.report, "coverage.md"), "w", encoding="utf-8") as handle:
            handle.write(print_table(table) + "\n")
    return 0


def build_fixture(args) -> int:
    """단위 시험용 작은 묶음 = 만든 묶음에서 고정 단어만 골라 VocabTests/Fixtures 에(커밋한다)."""
    wanted = collections.defaultdict(list)
    with open(args.fixture, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            lang, _, term = line.partition(" ")
            if lang and term:
                wanted[lang].append(term.strip())
    for lang, terms in wanted.items():
        found = {}
        sources = {}
        for index in range(len(PACK_SIZES)):
            path = os.path.join(args.from_packs, f"{lang}-{index + 1}.json")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            sources = data["sources"]
            for row in data["items"]:
                found.setdefault(row["term"], row)
        items = []
        for number, term in enumerate(terms, 1):
            if term not in found:
                raise ValueError(f"고정 단어 {lang} {term} 가 묶음에 없다")
            row = dict(found[term])
            row["rank"] = number
            items.append(row)
        payload = {"format": FORMAT, "id": f"fixture-pack-{lang}", "lang": lang, "sources": sources, "items": items}
        with open(os.path.join(args.out, f"fixture-pack-{lang}.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        log(f"fixture-pack-{lang}.json: {len(items)}개")
    if args.from_examples:
        source = sqlite3.connect(os.path.join(args.from_examples, "examples.sqlite"))
        rows = []
        for lang, terms in wanted.items():
            for term in terms:
                rows += source.execute("SELECT * FROM example WHERE lang = ? AND term = ?", (lang, term)).fetchall()
        meta = dict(source.execute("SELECT key, value FROM meta").fetchall())
        write_examples(os.path.join(args.out, "fixture-examples.sqlite"), rows, meta)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cedict")
    parser.add_argument("--jmdict")
    parser.add_argument("--krdict")
    parser.add_argument("--nikl")
    parser.add_argument("--ngsl")
    parser.add_argument("--ngsl-forms", help="NGSL_12_lemmatized_for_teaching.csv(낱말 꼴)")
    parser.add_argument("--wordfreq", help="wordfreq-3.1.1-py3-none-any.whl")
    parser.add_argument("--tatoeba", help="Tatoeba 내보내기 파일 폴더(TATOEBA_FILES)")
    parser.add_argument("--tatoeba-version", help="Tatoeba 내보내기 날짜(자료 출처 화면)")
    parser.add_argument("--overrides", help="Tools/pack_overrides")
    parser.add_argument("--out", required=True, help="묶음 json 폴더")
    parser.add_argument("--examples-out", help="examples.sqlite 를 둘 폴더(사전 폴더)")
    parser.add_argument("--report", help="검토 표 · 범위 표를 둘 폴더")
    parser.add_argument("--strict", action="store_true", help="쓰이지 않은 덧쓰기가 있으면 실패")
    parser.add_argument("--fixture", help="단위 시험용 단어 목록(Tools/pack_fixture.txt)")
    parser.add_argument("--from-packs", help="--fixture: 만든 묶음 폴더")
    parser.add_argument("--from-examples", help="--fixture: 만든 examples.sqlite 폴더")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.fixture:
        return build_fixture(args)
    needed = ("cedict", "jmdict", "krdict", "nikl", "ngsl", "wordfreq", "tatoeba")
    missing = [n for n in needed if not getattr(args, n)]
    if missing:
        parser.error("다 있어야 한다: " + ", ".join("--" + n for n in missing))
    return build_all(args)


if __name__ == "__main__":
    sys.exit(main())
