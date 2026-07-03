"""Testy jednostkowe logiki zapytań (``exif_query``) i aliasów pól.

Uruchomienie:
    python3 -m pytest              # jeśli zainstalowany pytest
    python3 -m unittest            # bez dodatkowych zależności
"""

import unittest

from exif_query import (
    And,
    Condition,
    Or,
    QueryError,
    field_names,
    matches_all,
    parse_condition,
    parse_query,
)
from exif_reader import gps_to_decimal, resolve_field


class TestParseCondition(unittest.TestCase):
    def test_basic_operators(self):
        self.assertEqual(
            parse_condition("ISOSpeedRatings>=400"),
            Condition("ISOSpeedRatings", ">=", "400"),
        )
        self.assertEqual(
            parse_condition("FNumber<3.5"), Condition("FNumber", "<", "3.5")
        )
        self.assertEqual(
            parse_condition("Model~HX9"), Condition("Model", "~", "HX9")
        )

    def test_longer_operator_wins_over_prefix(self):
        # '>=' nie może zostać potraktowane jako '>' + '=...'
        cond = parse_condition("ISO>=400")
        self.assertEqual(cond.op, ">=")
        self.assertEqual(cond.value, "400")

    def test_value_with_spaces(self):
        cond = parse_condition("Camera=SONY DSC-HX9V")
        self.assertEqual(cond.value, "SONY DSC-HX9V")

    def test_whitespace_is_trimmed(self):
        self.assertEqual(
            parse_condition("  ISO  >=  400 "),
            Condition("ISO", ">=", "400"),
        )

    def test_invalid_raises(self):
        for bad in ["bezoperatora", "=400", ">100", ""]:
            with self.assertRaises(QueryError):
                parse_condition(bad)


class TestNumericMatching(unittest.TestCase):
    def setUp(self):
        self.fields = {"ISOSpeedRatings": 640, "FNumber": 3.3}

    def test_ge_le_gt_lt(self):
        self.assertTrue(parse_condition("ISOSpeedRatings>=640").matches(self.fields))
        self.assertTrue(parse_condition("ISOSpeedRatings>=400").matches(self.fields))
        self.assertFalse(parse_condition("ISOSpeedRatings>640").matches(self.fields))
        self.assertTrue(parse_condition("ISOSpeedRatings<=640").matches(self.fields))
        self.assertTrue(parse_condition("FNumber<3.5").matches(self.fields))
        self.assertFalse(parse_condition("FNumber<3.0").matches(self.fields))

    def test_equality_numeric(self):
        # 640 (int) == "640" oraz 3.3 == "3.3"
        self.assertTrue(parse_condition("ISOSpeedRatings=640").matches(self.fields))
        self.assertTrue(parse_condition("FNumber=3.3").matches(self.fields))
        self.assertTrue(parse_condition("ISOSpeedRatings!=800").matches(self.fields))
        self.assertFalse(parse_condition("ISOSpeedRatings!=640").matches(self.fields))


class TestStringAndDateMatching(unittest.TestCase):
    def setUp(self):
        self.fields = {
            "Camera": "SONY DSC-HX9V",
            "Model": "DSC-HX9V",
            "DateTime": "2025:02:12 18:13:27",
        }

    def test_case_insensitive_equality(self):
        self.assertTrue(parse_condition("Camera=sony dsc-hx9v").matches(self.fields))

    def test_substring(self):
        self.assertTrue(parse_condition("Model~hx9").matches(self.fields))
        self.assertFalse(parse_condition("Model~nikon").matches(self.fields))

    def test_date_range_lexicographic(self):
        # Format EXIF sortuje się chronologicznie jako tekst.
        self.assertTrue(parse_condition("DateTime>=2025:01:01").matches(self.fields))
        self.assertTrue(parse_condition("DateTime<2026:01:01").matches(self.fields))
        self.assertFalse(parse_condition("DateTime>=2025:03:01").matches(self.fields))

    def test_missing_field_never_matches(self):
        self.assertFalse(parse_condition("Nieistnieje=cos").matches(self.fields))
        self.assertFalse(parse_condition("Nieistnieje!=cos").matches(self.fields))


class TestMatchesAll(unittest.TestCase):
    def test_conjunction(self):
        fields = {"ISOSpeedRatings": 250, "FNumber": 3.3}
        conds = [parse_condition("ISOSpeedRatings<400"), parse_condition("FNumber<=3.5")]
        self.assertTrue(matches_all(fields, conds))
        conds.append(parse_condition("FNumber<3.0"))
        self.assertFalse(matches_all(fields, conds))


class TestAliases(unittest.TestCase):
    def test_known_aliases(self):
        self.assertEqual(resolve_field("ISO"), "ISOSpeedRatings")
        self.assertEqual(resolve_field("iso"), "ISOSpeedRatings")
        self.assertEqual(resolve_field("Date"), "DateTime")
        self.assertEqual(resolve_field("F"), "FNumber")

    def test_unknown_passes_through(self):
        self.assertEqual(resolve_field("ExposureBiasValue"), "ExposureBiasValue")


class TestQueryGrouping(unittest.TestCase):
    def test_and_or_precedence(self):
        # AND wiąże silniej niż OR: A OR B AND C  ==  A OR (B AND C)
        node = parse_query("ISO=100 OR ISO=200 AND FNumber=3.3")
        self.assertIsInstance(node, Or)
        self.assertTrue(node.matches({"ISO": 100, "FNumber": 9.0}))   # lewy człon
        self.assertTrue(node.matches({"ISO": 200, "FNumber": 3.3}))   # prawy człon
        self.assertFalse(node.matches({"ISO": 200, "FNumber": 9.0}))  # B bez C

    def test_parentheses_override_precedence(self):
        node = parse_query("(ISO=100 OR ISO=200) AND FNumber=3.3")
        self.assertIsInstance(node, And)
        self.assertTrue(node.matches({"ISO": 100, "FNumber": 3.3}))
        self.assertFalse(node.matches({"ISO": 100, "FNumber": 9.0}))

    def test_value_with_spaces_in_expression(self):
        node = parse_query("Camera=SONY DSC-HX9V OR ISO=100")
        self.assertTrue(node.matches({"Camera": "SONY DSC-HX9V", "ISO": 999}))

    def test_alias_resolution_in_query(self):
        node = parse_query("ISO>=400", resolver=resolve_field)
        self.assertEqual(field_names(node), ["ISOSpeedRatings"])

    def test_field_names_dedup(self):
        node = parse_query("DateTime>=2025:01:01 AND DateTime<2026:01:01")
        self.assertEqual(field_names(node), ["DateTime"])

    def test_syntax_errors(self):
        for bad in ["(ISO=100", "ISO=100 AND", "AND ISO=100", "()", ""]:
            with self.assertRaises(QueryError):
                parse_query(bad)


class TestGpsToDecimal(unittest.TestCase):
    def test_north_east_positive(self):
        # 52°13'56.4\"N, 21°00'30\"E  (okolice Warszawy)
        lat = gps_to_decimal((52, 13, 56.4), "N")
        lon = gps_to_decimal((21, 0, 30), "E")
        self.assertAlmostEqual(lat, 52.2323333, places=5)
        self.assertAlmostEqual(lon, 21.0083333, places=5)

    def test_south_west_negative(self):
        self.assertAlmostEqual(gps_to_decimal((33, 51, 54), "S"), -33.865, places=4)
        self.assertAlmostEqual(gps_to_decimal((70, 40, 0), "W"), -70.6667, places=3)

    def test_incomplete_returns_none(self):
        self.assertIsNone(gps_to_decimal(None, "N"))
        self.assertIsNone(gps_to_decimal((52, 13), "N"))
        self.assertIsNone(gps_to_decimal(("x", "y", "z"), "N"))


if __name__ == "__main__":
    unittest.main()
