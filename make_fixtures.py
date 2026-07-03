"""Generator syntetycznych plików JPEG z danymi EXIF (do testów).

Prawdziwe zdjęcia w repozytorium nie mają fixa GPS, więc do przetestowania
ścieżki ``Latitude``/``Longitude`` w :func:`exif_reader.read_exif` tworzymy
mały obrazek z ręcznie ustawionymi współrzędnymi.

Uruchomienie (nadpisuje pliki w ``fixtures/``)::

    python3 make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import ExifTags, Image
from PIL.TiffImagePlugin import IFDRational

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Współrzędne użyte w próbce: 52°13'56.4"N, 21°00'30"E (okolice Warszawy).
# Te same wartości sprawdzają testy jednostkowe gps_to_decimal.
SAMPLE_LAT_DMS = (52, 13, 56.4)
SAMPLE_LON_DMS = (21, 0, 30)


def _dms_to_rationals(dms: tuple) -> tuple:
    """Zamień (stopnie, minuty, sekundy) na krotkę IFDRational dla Pillow."""
    return tuple(IFDRational(round(v * 1000), 1000) for v in dms)


def make_gps_sample(
    path: str | Path,
    lat_dms: tuple = SAMPLE_LAT_DMS,
    lat_ref: str = "N",
    lon_dms: tuple = SAMPLE_LON_DMS,
    lon_ref: str = "E",
    make: str = "SYNTH",
    model: str = "GPS-TEST",
) -> Path:
    """Zapisz mały JPEG z podanymi współrzędnymi GPS w danych EXIF."""
    img = Image.new("RGB", (8, 8), (40, 80, 160))
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = make
    exif[ExifTags.Base.Model] = model
    exif[ExifTags.IFD.GPSInfo] = {
        0: b"\x02\x03\x00\x00",              # GPSVersionID
        1: lat_ref,
        2: _dms_to_rationals(lat_dms),
        3: lon_ref,
        4: _dms_to_rationals(lon_dms),
        16: "M",                              # GPSImgDirectionRef (magnetyczny)
        17: IFDRational(1235, 10),            # GPSImgDirection = 123.5
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="JPEG", exif=exif)
    return path


def main() -> None:
    sample = make_gps_sample(FIXTURES_DIR / "gps_sample.jpg")
    print(f"Zapisano: {sample}")


if __name__ == "__main__":
    main()
