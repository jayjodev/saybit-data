#!/usr/bin/env bash
# 단어장 기기 안 사전 셋(Vocab/Resources/Lexicon/*.sqlite)과 무료 묶음(Vocab/Resources/Packs/*.json)을 만든다.
# CI(vocab-ios.yml · vocab-ios-release.yml)와 로컬 맥에서 xcodegen 전에 돈다. 만든 파일은 커밋하지 않는다(.gitignore).
# 명세 = docs/claude/roadmap/vocab/02-engineering.md 5.2 · 6절 · 원장 D21(사전은 실행 파일 밖 자원 파일) · D22 · D38.
# ios/madi/fetch-models.sh 를 본떴다: 원자료와 만든 결과는 저장소 밖 캐시에 둔다(맥 러너는 checkout 때 무시 파일을 지우므로
# 매번 받지 않게). 캐시에 결과가 있으면 복사만(1초), 없으면 원자료를 받아 Tools/build_lexicon.py · build_packs.py 를 돌린다(1~2분).
#
# 원자료(판 · 해시를 바꾸면 DATA_VERSION 도 올린다):
#   CC-CEDICT        MDBG 최신 파일만 공개(판 주소 없음) = 처음 받은 파일을 캐시에 두고 계속 쓴다. 해시가 다르면 경고만.
#   JMdict 흔한 말   jmdict-simplified GitHub 릴리스(판 고정 + sha256). EDRDG FTP 는 끊겨 이 길을 쓴다(02-engineering 5.2).
#   한국어기초사전   krdict.korean.go.kr 전체 내려받기 JSON(최신만). 2026-10-28 이 노드의 curl 은 400 을 받았다 = 못 받으면
#                    브라우저로 받은 zip 을 "$SRC/krdict-json.zip" 에 두면 다음 실행부터 쓴다(그때까지 한국어 사전 없이 빌드).
#   학습용 어휘      국립국어원 누리집 파일(고정 이름 + sha256), NGSL 1.2 통계 · 교수용 낱말 꼴 CSV(고정 + sha256), wordfreq 3.1.1 휠(PyPI, 고정 + sha256).
#   시험 목록        TSL 1.2 · BSL 1.2 · NAWL 1.2(newgeneralservicelist.com, CC BY-SA 4.0, 고정 + sha256) · HSK 2.0 급별(complete-hsk-vocabulary, MIT,
#                    GitHub 커밋 고정 + sha256) · JLPT N5~N1(Jonathan Waller tanos.co.uk CC BY 의 JSON 사본 Bluskyo/JLPT_Vocabulary, 커밋 고정 + sha256).
#   자막 빈도        hermitdave FrequencyWords 2018(OpenSubtitles, CC BY-SA 4.0) en · zh_cn · ja · ko(GitHub 커밋 고정 + sha256) = 회화 묶음 순서.
#   예문             Tatoeba 주간 내보내기(per_language 문장 · 표시 · 번역 연결 + 사용자 언어 + 일본어 색인, CC BY 2.0 FR). 최신만 공개라
#                    CC-CEDICT 처럼 처음 받은 판을 $SRC/tatoeba 에 두고 계속 쓴다(해시가 다르면 경고만, 받은 날 = 자료 출처 판).
#   덧쓰기           Tools/pack_overrides/*.tsv = 사람이 검토한 뜻 · 읽기 · 빼기(저장소 안, 바뀌면 캐시 열쇠가 바뀐다).
#   묶음 목록        Vocab/Packs/PackManifest.json = 앱이 보이는 묶음 40개(자주 쓰는 단어 12 · 회화 8 · 시험 20)의 단일 소스. build_packs.py PACK_IDS 와
#                    같아야 하고(--check-manifest 가 먼저 막는다), 바뀌면 캐시 열쇠가 바뀐다.
#
# 못 받거나 못 만들면 그 자원 없이 빌드된다(앱은 사전 찾기가 비고 묶음 줄을 숨긴다, 단위 시험은 VocabTests/Fixtures 고정판만 쓴다).
# 출시 빌드는 VOCAB_REQUIRE_LEXICON=1 = 사전 셋 · 예문 사전 · 매니페스트의 묶음 전부 중 하나라도 없으면 여기서 멈춘다.
# 캐시 자리 = VOCAB_LEXICON_CACHE(기본 ~/Library/Caches/vocab-lexicon). 원자료를 새로 받으려면 VOCAB_LEXICON_REFRESH=1.
set -euo pipefail
cd "$(dirname "$0")"

DATA_VERSION="2026-10-30.2"
ROOT="${VOCAB_LEXICON_CACHE:-$HOME/Library/Caches/vocab-lexicon}"
SRC="$ROOT/src"
PY="${PYTHON:-python3}"
OUT_LEXICON="Vocab/Resources/Lexicon"
OUT_PACKS="Vocab/Resources/Packs"

CEDICT_FILE="cedict_1_0_ts_utf-8_mdbg.txt.gz"
CEDICT_URL="https://www.mdbg.net/chinese/export/cedict/$CEDICT_FILE"
CEDICT_SHA="347499200f7eb34a922993fc71397d4033845096a8ca070b760ec200ff9be2ed"   # 2026-10-27T01:55:52Z 판(125,326 항목)
JMDICT_FILE="jmdict-eng-common-3.6.2+20261026175559.json.tgz"
JMDICT_URL="https://github.com/scriptin/jmdict-simplified/releases/download/3.6.2%2B20261026175559/jmdict-eng-common-3.6.2%2B20261026175559.json.tgz"
JMDICT_SHA="b5468172549cdc5b0be5ab49320805bc594d11344593fca66aaf59d11242983a"
KRDICT_FILE="krdict-json.zip"
KRDICT_URL="https://krdict.korean.go.kr/dicBatchDownload?seq=220"
KRDICT_SHA="c8f9ffbf7e9be1f1ec86fa29e4160a75eee8044fc081c27788dadf3ceb66d34e"   # 20261019 판(표제어 56,555)
NIKL_FILE="nikl-learner-vocabulary-2003.txt"
NIKL_URL="https://www.korean.go.kr/common/download.do?file_path=etcData&c_file_name=b73a8438-4713-4436-8481-ec26fd0dce2a_0.txt&o_file_name=nikl.txt"
NIKL_SHA="3b49681f05d6a7490c13da2a2847e433effdf65da409fd295792d6ee33685064"
NGSL_FILE="NGSL_1.2_stats.csv"
NGSL_URL="https://www.newgeneralservicelist.com/s/NGSL_12_stats.csv"
NGSL_SHA="2098bab8955a120a9766c6282a51d7d578c6cb0a7d946600d2ffb73ba25a0b44"
NGSL_FORMS_FILE="NGSL_1.2_lemmatized_for_teaching.csv"
NGSL_FORMS_URL="https://www.newgeneralservicelist.com/s/NGSL_12_lemmatized_for_teaching.csv"
NGSL_FORMS_SHA="b54e297244988237457e04f823aa8dca68e3d646938dc76d383e099f04cb7666"
TATOEBA_URL="https://downloads.tatoeba.org/exports"
# 2026-10-24 주간 내보내기(이 판으로 묶음 예문을 검토했다). 파일 이름 · 경로 · sha256.
TATOEBA_FILES="
eng_sentences_detailed.tsv.bz2 per_language/eng c39d2fab0cc5bc2b798b539134b83abaf5dec723a059ce55496907d08e3e9030
cmn_sentences_detailed.tsv.bz2 per_language/cmn 7af009b234bbb21ed6a254c2b55fa7c81c9dd53509d0982cd92c1097573f9af5
jpn_sentences_detailed.tsv.bz2 per_language/jpn e305ecf638ab24cd57b0b5f9fcdc342267ef4a3fdb19c71621f1a49baaf6d84f
kor_sentences_detailed.tsv.bz2 per_language/kor 46fbeaa3cd0b2f140b303149e10881bc49978a3a822efe944b0c4ebabb3ea371
eng_tags.tsv.bz2 per_language/eng e598d4dd5da41beffddc551e37b4ecd28660aac0e633ad0bf54a432ffdbd9ea4
cmn_tags.tsv.bz2 per_language/cmn 86a70f7f4a1204ede54c2a09a1c74b3609c341ed75a8086d88cf6dcd76de7ac9
jpn_tags.tsv.bz2 per_language/jpn 51f869f544d7f0dd7cf227e952fcee29b8f0cadd1f1a3c2dfbcb72e71e2bc229
kor_tags.tsv.bz2 per_language/kor f30931b05381ace5e464bd3dc1a4f494349a1bbc1dc676708665d732a109978b
cmn-eng_links.tsv.bz2 per_language/cmn 3c996fc24421df363f8b17dfb689698ead9bb3ba2be207fc415fda2823da333a
cmn-kor_links.tsv.bz2 per_language/cmn acd1d178e452c8ebe6a71b013001799e28a4d918be134b55c1184f36bf2ef376
jpn-eng_links.tsv.bz2 per_language/jpn ec6f09d686111dae93274600e8ee202c9d4cbba02bab91f73ae1a578aaca492a
jpn-kor_links.tsv.bz2 per_language/jpn 52f4da341dcd2d6cb437f01f4c7ad93195392dbf94c26b44a452733dc42c51ec
eng-kor_links.tsv.bz2 per_language/eng e26199c28a29a56c07e28785ee798fa32798672324937fcb4fc380fde89bdc61
user_languages.tar.bz2 . c62f97356d3266198cfbe2fdad6d640e16998b228fe801ec29e9ad76e536cafb
jpn_indices.tar.bz2 . 3e4fb8ad85fb71ed939091432c7b74c6951560c85c20cbd4738823cd83797880
"
WORDFREQ_FILE="wordfreq-3.1.1-py3-none-any.whl"
WORDFREQ_URL="https://files.pythonhosted.org/packages/24/61/62835c475d69872d30689f284497853fe33fe1d6dd18f57346d13305861d/$WORDFREQ_FILE"
WORDFREQ_SHA="4b1c6ecffc6198be3396d5cf871c4423ca71c907c231348d352dd54d62b97473"
# 시험 · 회화 묶음 원자료(D46 · D47). 전부 pinned(해시가 다르면 실패). GitHub 원자료는 커밋 SHA 주소 = 파일이 바뀌지 않는다.
MANIFEST="Vocab/Packs/PackManifest.json"
NGSL_SITE="https://www.newgeneralservicelist.com/s"
TSL_FILE="TSL_12_stats.csv"
TSL_SHA="2259df25a1077b04067ef0c0e9e4c98b46c91e4d539741dfaceba88651ff486d"             # TOEIC Service List 1.2, 1,250 표제어 · 순위
TSL_FORMS_FILE="TSL_12_lemmatized_for_teaching.csv"
TSL_FORMS_SHA="aca322f1e8b55c9c85e8b9f04ea384a2fcb069019e6e77fff3eb141ee2b67929"
BSL_FILE="BSL_120_stats.csv"
BSL_SHA="45055265eb4e74c65f5d26edabbc1a0da38c45bbb924cd9bd01fd391b74ff157"             # Business Service List 1.2, 1,700 표제어 · 순위
BSL_FORMS_FILE="BSL_120_lemmatized_for_teaching.csv"
BSL_FORMS_SHA="0073a91b4186dc0bba0960f2ed9486bd117177403f4e0ac9f3738474f2b2a3c9"
NAWL_FILE="NAWL_12_lemmatized_for_teaching.csv"
NAWL_SHA="1790b0fa22c5815ebf5a9a15c9363c03a6e906c77bf217f99033734f1459137b"            # New Academic Word List 1.2, 957 표제어(순위 없음 = wordfreq 순)
HSK_COMMIT="7ac65bf1a6387d35f1ade478906172a19311c7f9"                                      # drkameleon/complete-hsk-vocabulary main 2026-03-23
HSK_FILE="complete-hsk-vocabulary-${HSK_COMMIT:0:7}.min.json"
HSK_URL="https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/$HSK_COMMIT/complete.min.json"
HSK_SHA="52d8e64ba65a6db4a38ea34302c6de5df53cdb5145254b25edcbf93b80676434"
JLPT_COMMIT="4358f932937ad0232194a36e9f4f875094910c6b"                                     # Bluskyo/JLPT_Vocabulary main 2026-07-15(tanos.co.uk 사본)
JLPT_FILE="JLPT_vocab_ALL-${JLPT_COMMIT:0:7}.json"
JLPT_URL="https://raw.githubusercontent.com/Bluskyo/JLPT_Vocabulary/$JLPT_COMMIT/data/vocab/results/JLPT_vocab_ALL.json"
JLPT_SHA="7cccbbc9559d056526f122dff17c24dc80cfc4c607bdd1b26db0dc5238baabca"
SUBS_COMMIT="525f9b560de45753a5ea01069454e72e9aa541c6"                                     # hermitdave/FrequencyWords master 2022-02-07
SUBS_URL="https://raw.githubusercontent.com/hermitdave/FrequencyWords/$SUBS_COMMIT/content/2018"
# 파일 이름 · 폴더 · sha256(build_packs.py SUBS_FILES 와 같은 이름). 일본어는 50k 판이 없어 full.
SUBS_FILES="
en_50k.txt en 5351ff405b1126ef555791dd4d9798a48e3e9a501a9fc481a9da957752cfb458
zh_cn_50k.txt zh_cn 25599e00347b893e55c3058a748819b3fe19403291cd12f7c03af128e7f3fe45
ja_full.txt ja 581dd106a134ff9f2706e23cde9fe95cd24d96ead6357cd3bd3bba9e166a764e
ko_50k.txt ko 8d00401b6728c8d6feeaa5455583c1a33408dd020aae4aa55609b25004d1d99d
"

if command -v shasum >/dev/null 2>&1; then
  SHA=(shasum -a 256)
else
  SHA=(sha256sum)
fi
hash_of() { "${SHA[@]}" "$1" | cut -d' ' -f1; }
warn() { echo "::warning::$*" >&2; }

# get <파일 이름> <주소> <sha256> <pinned|latest>. 있으면 그대로(최신만 공개된 원자료도 처음 받은 판을 계속 쓴다).
# pinned = 해시가 다르면 실패 · latest = 해시가 다르면 경고만(새 판). 실패하면 1.
get() {
  local name="$1" url="$2" want="$3" mode="$4" path="$SRC/$1"
  mkdir -p "$(dirname "$path")"
  if [ -f "$path" ] && [ "${VOCAB_LEXICON_REFRESH:-0}" != 1 ]; then
    if [ "$mode" = pinned ] && [ "$(hash_of "$path")" != "$want" ]; then
      rm -f "$path"
    else
      return 0
    fi
  fi
  echo "받기: $name"
  if ! curl -fsSL --retry 3 --connect-timeout 20 --max-time 900 -o "$path.part" "$url"; then
    rm -f "$path.part"
    return 1
  fi
  local got
  got="$(hash_of "$path.part")"
  if [ "$got" != "$want" ]; then
    if [ "$mode" = pinned ]; then
      echo "::error::$name 해시가 다르다(받은 것 $got, 고정 $want)" >&2
      rm -f "$path.part"
      return 1
    fi
    warn "$name 이 고정판과 다른 새 판이다(해시 $got). 그대로 쓰고 판 날짜는 사전 meta 에 적힌다"
  fi
  mv "$path.part" "$path"
}

have_cedict=1; have_jmdict=1; have_krdict=1; have_packs=1
get "$CEDICT_FILE" "$CEDICT_URL" "$CEDICT_SHA" latest || { warn "CC-CEDICT 를 받지 못했다"; have_cedict=0; }
get "$JMDICT_FILE" "$JMDICT_URL" "$JMDICT_SHA" pinned || { warn "JMdict 를 받지 못했다"; have_jmdict=0; }
# 한국어기초사전 원본 누리집은 자동 요청에 400 을 준다(2026-10-28). 그래서 설계 때 내려받기 안내 화면을 거쳐 받은 같은 판(20261019)을
# 이 저장소의 비공개 릴리스 첨부로 두었다(CC BY-SA 2.0 KR, 상업 허용 · 출처 표시). 누리집에서 못 받으면 그 첨부를 받는다(GH_TOKEN 필요).
KRDICT_RELEASE_TAG="vocab-data-krdict-20261019"
get_release_asset() {
  local name="$1" tag="$2" want="$3" path="$SRC/$1"
  [ -n "${GH_TOKEN:-}" ] || return 1
  [ -n "${GITHUB_REPOSITORY:-}" ] || return 1
  mkdir -p "$SRC"
  echo "받기(저장소 릴리스 $tag): $name"
  "$PYTHON_FOR_FETCH" -I - "$GITHUB_REPOSITORY" "$tag" "$name" "$path.part" <<'PY' || { rm -f "$path.part"; return 1; }
import json, os, sys, urllib.request
repo, tag, name, out = sys.argv[1:5]
headers = {"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28"}
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=headers)
release = json.load(urllib.request.urlopen(req, timeout=60))
asset = next(a for a in release["assets"] if a["name"] == name)
req = urllib.request.Request(asset["url"], headers={**headers, "Accept": "application/octet-stream"})
with urllib.request.urlopen(req, timeout=900) as resp, open(out, "wb") as fh:
    while True:
        chunk = resp.read(1 << 20)
        if not chunk:
            break
        fh.write(chunk)
PY
  if [ "$(hash_of "$path.part")" != "$want" ]; then
    echo "::error::$name(릴리스 첨부) 해시가 고정판과 다르다" >&2
    rm -f "$path.part"
    return 1
  fi
  mv "$path.part" "$path"
}
PYTHON_FOR_FETCH="$(command -v python3)"
if ! get "$KRDICT_FILE" "$KRDICT_URL" "$KRDICT_SHA" latest && ! get_release_asset "$KRDICT_FILE" "$KRDICT_RELEASE_TAG" "$KRDICT_SHA"; then
  warn "한국어기초사전을 받지 못했다(누리집 400 · 릴리스 첨부도 실패). $SRC/$KRDICT_FILE 에 두면 다음 실행부터 쓴다. 이번 빌드는 한국어 뜻 후보 · 한국어 묶음 없이"
  have_krdict=0
fi
get "$NIKL_FILE" "$NIKL_URL" "$NIKL_SHA" pinned || { warn "학습용 어휘 목록을 받지 못했다"; have_packs=0; }
get "$NGSL_FILE" "$NGSL_URL" "$NGSL_SHA" pinned || { warn "NGSL 을 받지 못했다"; have_packs=0; }
get "$NGSL_FORMS_FILE" "$NGSL_FORMS_URL" "$NGSL_FORMS_SHA" pinned || { warn "NGSL 낱말 꼴을 받지 못했다"; have_packs=0; }
get "$WORDFREQ_FILE" "$WORDFREQ_URL" "$WORDFREQ_SHA" pinned || { warn "wordfreq 를 받지 못했다"; have_packs=0; }
# 시험 목록 · 자막 빈도(전부 pinned). 하나라도 없으면 묶음 전체를 만들지 않는다(매니페스트 묶음 40개는 한 번에 만든다).
get "$TSL_FILE" "$NGSL_SITE/$TSL_FILE" "$TSL_SHA" pinned || { warn "TSL 을 받지 못했다"; have_packs=0; }
get "$TSL_FORMS_FILE" "$NGSL_SITE/$TSL_FORMS_FILE" "$TSL_FORMS_SHA" pinned || { warn "TSL 낱말 꼴을 받지 못했다"; have_packs=0; }
get "$BSL_FILE" "$NGSL_SITE/$BSL_FILE" "$BSL_SHA" pinned || { warn "BSL 을 받지 못했다"; have_packs=0; }
get "$BSL_FORMS_FILE" "$NGSL_SITE/$BSL_FORMS_FILE" "$BSL_FORMS_SHA" pinned || { warn "BSL 낱말 꼴을 받지 못했다"; have_packs=0; }
get "$NAWL_FILE" "$NGSL_SITE/$NAWL_FILE" "$NAWL_SHA" pinned || { warn "NAWL 을 받지 못했다"; have_packs=0; }
get "$HSK_FILE" "$HSK_URL" "$HSK_SHA" pinned || { warn "HSK 목록을 받지 못했다"; have_packs=0; }
get "$JLPT_FILE" "$JLPT_URL" "$JLPT_SHA" pinned || { warn "JLPT 목록을 받지 못했다"; have_packs=0; }
while read -r name dir sha; do
  [ -n "$name" ] || continue
  get "subs/$name" "$SUBS_URL/$dir/$name" "$sha" pinned || { warn "자막 빈도 $name 을 받지 못했다"; have_packs=0; }
done <<< "$SUBS_FILES"
# 묶음 목록(앱 자원)이 build_packs.py 의 묶음 id 와 같은지 = 다르면 여기서 멈춘다(앱이 없는 묶음을 보이거나 만든 묶음을 숨기지 않게).
"$PY" -I Tools/build_packs.py --check-manifest "$MANIFEST"
# Tatoeba: 한 폴더(src/tatoeba)에 처음 받은 주간 판을 두고 계속 쓴다. 판 날짜 = 처음 받은 날(VERSION).
have_tatoeba=1
while read -r name dir sha; do
  [ -n "$name" ] || continue
  get "tatoeba/$name" "$TATOEBA_URL/$dir/$name" "$sha" latest || { warn "Tatoeba $name 을 받지 못했다"; have_tatoeba=0; }
done <<< "$TATOEBA_FILES"
mkdir -p "$SRC/tatoeba"
[ -f "$SRC/tatoeba/VERSION" ] || date -u +%Y-%m-%d > "$SRC/tatoeba/VERSION"
[ "$have_tatoeba" = 1 ] || have_packs=0

# 결과 캐시 열쇠 = 판 + 두 스크립트 + 받은 원자료 해시(최신만 공개된 원자료가 바뀌면 다시 만든다).
KEY="$({
  echo "$DATA_VERSION"
  hash_of Tools/build_lexicon.py
  hash_of Tools/build_packs.py
  hash_of "$MANIFEST"
  for f in Tools/pack_overrides/*.tsv; do hash_of "$f"; done
  for f in "$CEDICT_FILE" "$JMDICT_FILE" "$KRDICT_FILE" "$NIKL_FILE" "$NGSL_FILE" "$NGSL_FORMS_FILE" "$WORDFREQ_FILE" \
           "$TSL_FILE" "$TSL_FORMS_FILE" "$BSL_FILE" "$BSL_FORMS_FILE" "$NAWL_FILE" "$HSK_FILE" "$JLPT_FILE"; do
    if [ -f "$SRC/$f" ]; then hash_of "$SRC/$f"; else echo "없음 $f"; fi
  done
  while read -r name dir sha; do
    [ -n "$name" ] || continue
    if [ -f "$SRC/subs/$name" ]; then hash_of "$SRC/subs/$name"; else echo "없음 subs/$name"; fi
  done <<< "$SUBS_FILES"
  while read -r name dir sha; do
    [ -n "$name" ] || continue
    if [ -f "$SRC/tatoeba/$name" ]; then hash_of "$SRC/tatoeba/$name"; else echo "없음 $name"; fi
  done <<< "$TATOEBA_FILES"
} | "${SHA[@]}" | cut -c1-16)"
BUILD="$ROOT/build-$DATA_VERSION-$KEY"

# 매니페스트의 묶음 id 전부(한 줄, 공백 구분). 출시 빌드 필수 목록 · 캐시 완성 판정이 쓴다.
manifest_ids() {
  "$PY" -I -c 'import json, sys; print(" ".join(p["id"] for p in json.load(open(sys.argv[1], encoding="utf-8"))["packs"]))' "$MANIFEST"
}

if [ ! -f "$BUILD/.done" ]; then
  STAGE="$BUILD.part"
  rm -rf "$STAGE"
  mkdir -p "$STAGE/Lexicon" "$STAGE/Packs"
  if [ "$have_cedict" = 1 ] && [ "$have_jmdict" = 1 ]; then
    # 한국어기초사전이 없으면 빈 자리 대신 그 파일만 빠진다(build_lexicon.py 는 셋을 다 받는다 = 없으면 가짜 zip 대신 건너뛴다).
    if [ "$have_krdict" = 1 ]; then
      "$PY" -I Tools/build_lexicon.py --cedict "$SRC/$CEDICT_FILE" --jmdict "$SRC/$JMDICT_FILE" --krdict "$SRC/$KRDICT_FILE" \
        --out "$STAGE/Lexicon" || { warn "사전을 만들지 못했다"; rm -rf "$STAGE/Lexicon"; mkdir -p "$STAGE/Lexicon"; }
    else
      "$PY" -I Tools/build_lexicon.py --cedict "$SRC/$CEDICT_FILE" --jmdict "$SRC/$JMDICT_FILE" \
        --out "$STAGE/Lexicon" || { warn "사전을 만들지 못했다"; rm -rf "$STAGE/Lexicon"; mkdir -p "$STAGE/Lexicon"; }
    fi
  fi
  # 묶음 · 예문 사전 = 원자료(사전 셋 + 목록 + 자막 + Tatoeba)와 덧쓰기가 다 있어야 만든다(뜻 · 예문이 묶음 파일 안에 있다, 형식 2).
  if [ "$have_packs" = 1 ] && [ "$have_cedict$have_jmdict$have_krdict" = 111 ]; then
    "$PY" -I Tools/build_packs.py --cedict "$SRC/$CEDICT_FILE" --jmdict "$SRC/$JMDICT_FILE" --krdict "$SRC/$KRDICT_FILE" \
      --nikl "$SRC/$NIKL_FILE" --ngsl "$SRC/$NGSL_FILE" --ngsl-forms "$SRC/$NGSL_FORMS_FILE" --wordfreq "$SRC/$WORDFREQ_FILE" \
      --tsl "$SRC/$TSL_FILE" --tsl-forms "$SRC/$TSL_FORMS_FILE" --bsl "$SRC/$BSL_FILE" --bsl-forms "$SRC/$BSL_FORMS_FILE" \
      --nawl "$SRC/$NAWL_FILE" --hsk "$SRC/$HSK_FILE" --jlpt "$SRC/$JLPT_FILE" --subs "$SRC/subs" --manifest "$MANIFEST" \
      --tatoeba "$SRC/tatoeba" --tatoeba-version "$(cat "$SRC/tatoeba/VERSION" 2>/dev/null || echo "")" \
      --overrides Tools/pack_overrides --out "$STAGE/Packs" --examples-out "$STAGE/Lexicon" \
      || { warn "묶음을 만들지 못했다"; rm -rf "$STAGE/Packs" "$STAGE/Lexicon/examples.sqlite"; mkdir -p "$STAGE/Packs"; }
  fi
  # 다 받아 만든 판만 캐시로 남긴다(빠진 원자료가 있으면 다음 실행이 다시 시도한다). 묶음은 매니페스트 전부가 있어야 한다.
  packs_complete=1
  for id in $(manifest_ids); do
    [ -f "$STAGE/Packs/$id.json" ] || packs_complete=0
  done
  if [ "$have_cedict$have_jmdict$have_krdict$have_packs" = 1111 ] && [ -f "$STAGE/Lexicon/krdict.sqlite" ] \
     && [ -f "$STAGE/Lexicon/examples.sqlite" ] && [ "$packs_complete" = 1 ]; then
    touch "$STAGE/.done"
  fi
  rm -rf "$BUILD"
  mv "$STAGE" "$BUILD"
  # 지난 판 결과는 지운다(원자료 src/ 는 남긴다).
  for old in "$ROOT"/build-*; do
    [ "$old" = "$BUILD" ] || rm -rf "$old"
  done
fi

rm -rf "$OUT_LEXICON" "$OUT_PACKS"
mkdir -p "$OUT_LEXICON" "$OUT_PACKS"
cp "$BUILD"/Lexicon/*.sqlite "$OUT_LEXICON"/ 2>/dev/null || true
cp "$BUILD"/Packs/*.json "$OUT_PACKS"/ 2>/dev/null || true
echo "사전: $(ls "$OUT_LEXICON" | tr '\n' ' ')($(du -sh "$OUT_LEXICON" | cut -f1)) · 묶음 $(ls "$OUT_PACKS" | wc -l | tr -d ' ')개($(du -sh "$OUT_PACKS" | cut -f1))"

if [ "${VOCAB_REQUIRE_LEXICON:-0}" = 1 ]; then
  for f in cedict.sqlite jmdict.sqlite; do
    [ -f "$OUT_LEXICON/$f" ] || { echo "::error::출시 빌드에 $f 가 없다" >&2; exit 1; }
  done
  # 한국어기초사전은 저장소 릴리스 첨부로 늘 받을 수 있다(2026-10-28) = 출시 빌드에서는 필수. 매니페스트의 묶음 전부 · 예문 사전도 필수.
  for f in cedict.sqlite jmdict.sqlite krdict.sqlite examples.sqlite; do
    [ -f "$OUT_LEXICON/$f" ] || { echo "::error::출시 빌드에 $f 가 없다" >&2; exit 1; }
  done
  for id in $(manifest_ids); do
    [ -f "$OUT_PACKS/$id.json" ] || { echo "::error::출시 빌드에 묶음 $id 가 없다" >&2; exit 1; }
  done
fi
