"""Testy integracyjne ścieżki GPS na syntetycznym pliku JPEG.

Fixture ``fixtures/gps_sample.jpg`` jest odtwarzany, jeśli go brakuje, więc
testy działają niezależnie od tego, czy binarny plik znajduje się w repo.
"""

import unittest
from pathlib import Path

from exif_cli import cmd_search, find_images
from exif_reader import read_exif
from make_fixtures import FIXTURES_DIR, make_gps_sample

FIXTURE = FIXTURES_DIR / "gps_sample.jpg"


def ensure_fixture() -> Path:
    if not FIXTURE.exists():
        make_gps_sample(FIXTURE)
    return FIXTURE


class TestGpsFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fields = read_exif(ensure_fixture())

    def test_decimal_coordinates(self):
        self.assertAlmostEqual(self.fields["Latitude"], 52.232333, places=5)
        self.assertAlmostEqual(self.fields["Longitude"], 21.008333, places=5)

    def test_position_string(self):
        self.assertEqual(self.fields["GPSPosition"], "52.232333, 21.008333")

    def test_raw_gps_fields_present(self):
        self.assertEqual(self.fields["GPSImgDirection"], 123.5)
        self.assertEqual(self.fields["GPSLatitudeRef"], "N")

    def test_camera_synthetic_field(self):
        self.assertEqual(self.fields["Camera"], "SYNTH GPS-TEST")


class TestGpsSearchIntegration(unittest.TestCase):
    """Bounding-box po współrzędnych działa na realnym pliku przez CLI."""

    @classmethod
    def setUpClass(cls):
        ensure_fixture()
        cls.images = find_images(FIXTURES_DIR)

    def test_bounding_box_matches(self):
        rc = cmd_search(
            self.images,
            expressions=None,
            query="Latitude>=52 AND Latitude<=53 AND Longitude>=21 AND Longitude<=22",
        )
        self.assertEqual(rc, 0)  # 0 = znaleziono dopasowania

    def test_bounding_box_excludes(self):
        rc = cmd_search(
            self.images,
            expressions=None,
            query="Latitude>=10 AND Latitude<=11",
        )
        self.assertEqual(rc, 1)  # 1 = brak dopasowań


if __name__ == "__main__":
    unittest.main()
