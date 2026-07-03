"""Odczyt danych EXIF z plików JPEG.

Moduł dostarcza jedną, wielokrotnego użytku funkcję ``read_exif``, która
zwraca "spłaszczony", znormalizowany słownik pól EXIF dla pojedynczego
pliku. Jest to fundament pod docelową aplikację przeszukującą zdjęcia po
wartościach i zakresach pól — warstwa CLI (``exif_cli.py``) korzysta z tej
samej funkcji.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import ExifTags, Image

# Wygodne, krótkie aliasy na kanoniczne (długie) nazwy tagów EXIF. Klucze
# porównujemy bez rozróżniania wielkości liter (patrz ``resolve_field``).
ALIASES = {
    "iso": "ISOSpeedRatings",
    "date": "DateTime",
    "datetime": "DateTime",
    "aperture": "FNumber",
    "fnumber": "FNumber",
    "f": "FNumber",
    "camera": "Camera",
    "model": "Model",
    "make": "Make",
    "exposure": "ExposureTime",
    "shutter": "ExposureTime",
    "focal": "FocalLength",
    "focallength": "FocalLength",
    "width": "ExifImageWidth",
    "height": "ExifImageHeight",
    "lat": "Latitude",
    "latitude": "Latitude",
    "lon": "Longitude",
    "lng": "Longitude",
    "longitude": "Longitude",
    "direction": "GPSImgDirection",
    "distance": "DistanceKm",
    "dist": "DistanceKm",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Odległość po powierzchni Ziemi (w km) między dwoma punktami GPS.

    Używa wzoru haversine i średniego promienia Ziemi ~6371 km.
    """
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def gps_to_decimal(coord, ref) -> float | None:
    """Przelicz współrzędną GPS (stopnie, minuty, sekundy) na stopnie dziesiętne.

    ``coord`` to trójka wartości (deg, min, sec), a ``ref`` to półkula
    ('N'/'S'/'E'/'W'). Dla półkuli południowej i zachodniej wynik jest ujemny.
    Zwraca ``None``, gdy dane są niekompletne lub nieprawidłowe.
    """
    if not coord or len(coord) != 3:
        return None
    try:
        deg, minutes, sec = (float(x) for x in coord)
    except (TypeError, ValueError):
        return None
    decimal = deg + minutes / 60 + sec / 3600
    if ref and str(ref).strip().upper() in ("S", "W"):
        decimal = -decimal
    return decimal


def resolve_field(name: str) -> str:
    """Zamień alias (np. ``ISO``) na kanoniczną nazwę tagu EXIF.

    Jeśli nazwa nie jest aliasem, zwracamy ją bez zmian — dzięki temu można
    swobodnie używać zarówno skrótów, jak i pełnych nazw tagów.
    """
    return ALIASES.get(name.strip().casefold(), name.strip())


def _clean(value):
    """Uporządkuj surową wartość EXIF do postaci wygodnej do wyświetlania.

    - bajty dekodujemy (lub pomijamy, jeśli to dane binarne),
    - łańcuchy przycinamy z nadmiarowych spacji i znaków NUL,
    - resztę zwracamy bez zmian.
    """
    if isinstance(value, bytes):
        try:
            text = value.decode("ascii").strip("\x00 ").strip()
        except UnicodeDecodeError:
            return None  # dane binarne (np. MakerNote) — pomijamy
        # Odrzuć bloby binarne (PrintImageMatching, FileSource itp.), które po
        # dekodowaniu wciąż zawierają NUL/znaki sterujące — nie nadają się do
        # wyświetlania ani wyszukiwania i psują eksport CSV.
        if not text or any(ord(c) < 0x20 or ord(c) == 0x7F for c in text):
            return None
        return text
    if isinstance(value, str):
        return value.strip("\x00 ").strip()
    return value


def read_exif(path: str | Path) -> dict:
    """Zwróć znormalizowany słownik pól EXIF dla podanego pliku.

    Scalane są tagi z głównego IFD oraz z pod-IFD ``Exif`` (tam znajdują się
    m.in. ISO, czas naświetlania, przysłona, ogniskowa). Dodatkowo tworzone
    jest pole syntetyczne ``Camera`` = "Make Model" dla wygody.

    Zwraca pusty słownik, jeśli plik nie zawiera danych EXIF.
    """
    fields: dict = {}
    with Image.open(path) as img:
        exif = img.getexif()
        if not exif:
            return fields

        # Główne IFD
        for tag_id, raw in exif.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            value = _clean(raw)
            if value is not None:
                fields[name] = value

        # Pod-IFD "Exif" — najciekawsze parametry zdjęcia
        try:
            sub_ifd = exif.get_ifd(ExifTags.IFD.Exif)
        except Exception:
            sub_ifd = {}
        for tag_id, raw in sub_ifd.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            value = _clean(raw)
            if value is not None:
                fields[name] = value

        # Pod-IFD "GPS" — kierunek, datum, a jeśli był fix: współrzędne
        try:
            gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        except Exception:
            gps_ifd = {}
        gps: dict = {}
        for tag_id, raw in gps_ifd.items():
            name = ExifTags.GPSTAGS.get(tag_id, str(tag_id))
            value = _clean(raw)
            if value is not None:
                gps[name] = value
        fields.update(gps)  # surowe pola GPS też są przeszukiwalne

        # Pola syntetyczne: współrzędne w stopniach dziesiętnych
        lat = gps_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
        lon = gps_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
        if lat is not None and lon is not None:
            fields["Latitude"] = round(lat, 6)
            fields["Longitude"] = round(lon, 6)
            fields["GPSPosition"] = f"{fields['Latitude']}, {fields['Longitude']}"

    # Pole syntetyczne: pełna nazwa aparatu
    make = fields.get("Make")
    model = fields.get("Model")
    if make or model:
        fields["Camera"] = " ".join(p for p in (make, model) if p)

    return fields
