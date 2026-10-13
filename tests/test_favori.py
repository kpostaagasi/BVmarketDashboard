from core.favori import FAVORI_TAVANI, favori_degistir, favorileri_coz


def test_bos_metin_bos_liste():
    assert favorileri_coz(None, {"a"}) == []
    assert favorileri_coz("  ", {"a"}) == []


def test_bilinmeyen_ve_tekrar_elenir_sira_korunur():
    assert favorileri_coz("b, a,a, yok, b", {"a", "b"}) == ["b", "a"]


def test_tavan_keser():
    ham = ",".join(f"s{i}" for i in range(50))
    assert len(favorileri_coz(ham, {f"s{i}" for i in range(50)})) == FAVORI_TAVANI


def test_varsa_cikarir_yoksa_ekler():
    assert favori_degistir(["a", "b"], "a") == ["b"]
    assert favori_degistir(["a"], "b") == ["a", "b"]


def test_tavan_doluyken_eklemez_cikarmayi_engellemez():
    dolu = [f"s{i}" for i in range(FAVORI_TAVANI)]
    assert favori_degistir(dolu, "yeni") == dolu
    assert favori_degistir(dolu, dolu[0]) == dolu[1:]
