"""Testy warstwy CLI: wyszukiwanie plików, w tym rekurencyjne."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from exif_cli import _label, cmd_search, find_images
from make_fixtures import make_gps_sample


class TestFindImages(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Struktura: a.jpg, sub/b.jpg, sub/nested/c.jpg
        make_gps_sample(self.root / "a.jpg")
        make_gps_sample(self.root / "sub" / "b.jpg")
        make_gps_sample(self.root / "sub" / "nested" / "c.jpg")

    def tearDown(self):
        self._tmp.cleanup()

    def test_flat_finds_only_top_level(self):
        found = find_images(self.root)
        self.assertEqual([p.name for p in found], ["a.jpg"])

    def test_recursive_finds_all(self):
        found = find_images(self.root, recursive=True)
        self.assertEqual(
            sorted(p.name for p in found), ["a.jpg", "b.jpg", "c.jpg"]
        )

    def test_recursive_labels_are_relative_paths(self):
        found = find_images(self.root, recursive=True)
        labels = sorted(_label(p, self.root) for p in found)
        self.assertEqual(labels, ["a.jpg", "sub/b.jpg", "sub/nested/c.jpg"])


class TestCsvExport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_gps_sample(self.root / "a.jpg")

    def tearDown(self):
        self._tmp.cleanup()

    def test_search_csv_is_parseable(self):
        images = find_images(self.root)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cmd_search(
                images, expressions=None, query="Latitude>=52 AND Latitude<=53",
                fmt="csv", base=self.root,
            )
        self.assertEqual(rc, 0)
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file"], "a.jpg")
        self.assertEqual(rows[0]["Latitude"], "52.232333")
        # Krotka (LensSpecification brak; sprawdzamy GPSPosition z przecinkiem
        # jest poprawnie cytowana i odczytana jako jedna komórka)
        self.assertEqual(rows[0]["GPSPosition"], "52.232333, 21.008333")


if __name__ == "__main__":
    unittest.main()
