"""MAC CSV decoding: Big5 for most files, UTF-8 with a BOM for some.

7888's 2026-07 snapshot (uploaded 2026-09-07) arrived as UTF-8 with a BOM.
The old decode tried Big5 with errors='replace', which never raises, so the
UTF-8 fallback never ran: the file decoded to mojibake, its first row was
not 臺灣, and the snapshot was dropped as a failure on every tick.
"""
from scraper.scrapers.mac_economic_scraper import decode_csv

SNAPSHOT = (
    '項    目,國內生產毛額(GDP) 年(月)別,GDP(億美元)\r\n'
    '臺灣,115年4-6月,"2,544.37"\r\n'
    '中國大陸,115年4-6月,"53,078.3"\r\n'
)


def test_big5_file():
    assert decode_csv(SNAPSHOT.encode('big5')) == SNAPSHOT


def test_utf8_file_with_bom():
    assert decode_csv(b'\xef\xbb\xbf' + SNAPSHOT.encode('utf-8')) == SNAPSHOT


def test_utf8_file_without_bom():
    assert decode_csv(SNAPSHOT.encode('utf-8')) == SNAPSHOT


def test_7887_header_in_big5():
    header = '項         目,兩岸貿易 年(月)別,  貿易總額(億美元),  對中國大陸出口(億美元)'
    assert decode_csv(header.encode('big5')) == header
