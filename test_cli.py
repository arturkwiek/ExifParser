"""Testy warstwy CLI: wyszukiwanie plików, w tym rekurencyjne."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from exif_cli import _label, _parse_near, cmd_search, find_images
from exif_query import QueryError
from exif_reader import haversine_km
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


class TestHaversine(unittest.TestCase):
    def test_known_distances(self):
        # Warszawa -> Kraków ≈ 252 km
        d = haversine_km(52.2297, 21.0122, 50.0647, 19.9450)
        self.assertAlmostEqual(d, 252, delta=3)
        # Ten sam punkt -> 0
        self.assertAlmostEqual(haversine_km(52.0, 21.0, 52.0, 21.0), 0.0, places=6)


class TestParseNear(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(_parse_near("52.23, 21.01, 5"), (52.23, 21.01, 5.0))

    def test_invalid(self):
        for bad in ["52,21", "a,b,c", "52,21,-1", ""]:
            with self.assertRaises(QueryError):
                _parse_near(bad)


class TestNearFilter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Warszawa (~0 km od centrum), punkt ~2 km na północ, Kraków (~250 km).
        make_gps_sample(self.root / "warszawa.jpg",
                        lat_dms=(52, 13, 56.4), lon_dms=(21, 0, 30))
        make_gps_sample(self.root / "blisko.jpg",
                        lat_dms=(52, 15, 0), lon_dms=(21, 0, 30))
        make_gps_sample(self.root / "krakow.jpg",
                        lat_dms=(50, 3, 36), lon_dms=(19, 56, 24))
        self.images = find_images(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_csv(self, near):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cmd_search(self.images, expressions=None, fmt="csv",
                            base=self.root, near=near)
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        return rc, rows

    def test_radius_selects_and_sorts_by_distance(self):
        rc, rows = self._run_csv("52.2323,21.0083,5")
        self.assertEqual(rc, 0)
        # Kraków poza promieniem; zostają dwa punkty, rosnąco wg odległości.
        self.assertEqual([r["file"] for r in rows], ["warszawa.jpg", "blisko.jpg"])
        dists = [float(r["DistanceKm"]) for r in rows]
        self.assertEqual(dists, sorted(dists))
        self.assertLess(dists[0], 0.5)

    def test_large_radius_includes_krakow(self):
        rc, rows = self._run_csv("52.2323,21.0083,300")
        self.assertEqual(rc, 0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["file"], "krakow.jpg")  # najdalszy na końcu

    def test_tiny_radius_excludes_all(self):
        rc, rows = self._run_csv("0,0,1")
        self.assertEqual(rc, 1)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
