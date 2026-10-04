import pytest

from extraction.normalize import law_key, normalize_citation

CASES = [
    ("M.G.L. c. 186, § 15B(3)(a)", "G.L. c. 186, § 15B(3)(a)"),
    ("M.G.L. c. 40P, § 4", "G.L. c. 40P, § 4"),
    ("Mass. Gen. Laws ch. 186 § 15B", "G.L. c. 186, § 15B"),
    ("N.J.S.A. 46:8-21.2", "N.J.S.A. 46:8-21.2"),
    ("NJSA 2A:18-61.1(f)", "N.J.S.A. 2A:18-61.1(f)"),
    ("P.L. 2025, c. 405", "P.L.2025, c.405"),
    ("Cal. Civ. Code §1947.12", "Cal. Civ. Code § 1947.12"),
    ("California Civil Code § 1950.5(g)", "Cal. Civ. Code § 1950.5(g)"),
    ("Cal. Bus. & Prof. Code § 16729(a)", "Cal. Bus. & Prof. Code § 16729(a)"),
    ("LAMC 151.06", "L.A. Mun. Code § 151.06"),
    ("BMC 13.63.030", "Berkeley Mun. Code § 13.63.030"),
    ("San Francisco Rent Ordinance § 37.9(a)", "S.F. Admin. Code § 37.9(a)"),
    ("S.F. Administrative Code chapter 37", "S.F. Admin. Code ch. 37"),
    ("Jersey City Municipal Code § 218-12", "Jersey City Code § 218-12"),
    ("Cambridge Municipal Code chapter 8.71", "Cambridge Mun. Code ch. 8.71"),
    ("S.2983", "S.2983"),
    ("Initiative Petition 25-21", "Initiative Petition 25-21"),
    (None, None),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_normalize(raw, expected):
    assert normalize_citation(raw) == expected


def test_idempotent():
    for raw, _ in CASES:
        once = normalize_citation(raw)
        assert normalize_citation(once) == once


@pytest.mark.parametrize("a,b", [
    ("M.G.L. c. 186, § 15B(3)(a)", "G.L. c. 186, § 15B(6), (7)"),
    ("Cal. Civ. Code § 1950.5(c)(1)", "California Civil Code § 1950.5(h)(2)-(5)"),
    ("LAMC 151.09.A, 165.03", "L.A. Mun. Code § 151.09"),
    ("N.J.S.A. 2A:18-61.1 et seq.", "N.J.S.A. 2A:18-61.1(f)"),
])
def test_law_key_groups_subsections(a, b):
    assert law_key(a) == law_key(b)


def test_law_key_separates_laws():
    assert law_key("Cal. Civ. Code § 1950.5") != law_key("Cal. Civ. Code § 1950.6")
