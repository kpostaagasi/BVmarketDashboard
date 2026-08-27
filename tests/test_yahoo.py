from datetime import datetime, timezone

from ingest.yahoo import gun_yuvarla, noktalari_ayikla, sembol_kodla


def ts(yil, ay, gun, saat):
    return int(datetime(yil, ay, gun, saat, tzinfo=timezone.utc).timestamp())


def test_sembol_kodla_esittir_isaretini_kodlar():
    assert sembol_kodla("BZ=F") == "BZ%3DF"


def test_sembol_kodla_sade_sembole_dokunmaz():
    assert sembol_kodla("AAPL") == "AAPL"


def test_gun_yuvarla_yaz_saatinde_dogru_gunu_verir():
    # NY Mercantile yaz saati: borsa yerel gece yarısı 04:00 UTC
    assert gun_yuvarla(ts(2026, 8, 27, 4)) == "2026-08-27"


def test_gun_yuvarla_kis_saatinde_dogru_gunu_verir():
    # kış saati: borsa yerel gece yarısı 05:00 UTC
    assert gun_yuvarla(ts(2026, 1, 15, 5)) == "2026-01-15"


def test_gun_yuvarla_utc_onundeki_borsayi_ileri_yuvarlar():
    # UTC+2 borsası: yerel gece yarısı bir önceki günün 22:00 UTC'sidir
    assert gun_yuvarla(ts(2026, 3, 10, 22)) == "2026-03-11"


def test_noktalari_ayikla_nulllari_atar():
    yanit = {
        "chart": {
            "result": [
                {
                    "timestamp": [ts(2026, 1, 5, 5), ts(2026, 1, 6, 5), ts(2026, 1, 7, 5)],
                    "indicators": {"quote": [{"close": [80.5, None, 82.25]}]},
                }
            ]
        }
    }
    assert noktalari_ayikla(yanit) == [("2026-01-05", 80.5), ("2026-01-07", 82.25)]


def test_noktalari_ayikla_ardisik_ayni_tarihi_tekillestirir():
    yanit = {
        "chart": {
            "result": [
                {
                    "timestamp": [ts(2026, 1, 5, 4), ts(2026, 1, 5, 6)],
                    "indicators": {"quote": [{"close": [80.5, 81.0]}]},
                }
            ]
        }
    }
    assert noktalari_ayikla(yanit) == [("2026-01-05", 80.5)]


def test_noktalari_ayikla_bos_yanitta_bos_liste():
    assert noktalari_ayikla({}) == []
    assert noktalari_ayikla({"chart": {"result": []}}) == []
