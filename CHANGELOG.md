# Changelog

Wszystkie istotne zmiany w projekcie dokumentowane są w tym pliku.
Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie zgodne z [SemVer](https://semver.org/lang/pl/).

## [1.0.0] – 2026-07-03

Pierwsze wydanie. Narzędzie CLI do odczytu i przeszukiwania danych EXIF ze
zdjęć JPEG.

### Dodane
- Odczyt EXIF z plików JPEG — `read_exif()` zwraca znormalizowany słownik pól
  (główne IFD + pod-IFD Exif + GPS).
- Podgląd wybranego pola dla każdego zdjęcia (`--field`) oraz lista dostępnych
  pól (`--list-fields`).
- Wyszukiwanie po wartościach i zakresach (`--where`) z operatorami
  `=`, `!=`, `>`, `>=`, `<`, `<=`, `~`; wiele warunków łączonych przez AND.
- Wyrażenia logiczne z AND/OR i nawiasami (`-q` / `--query`).
- Aliasy pól (`ISO`, `Date`, `F`, `lat`/`lon`, `dist`, …).
- Współrzędne GPS w stopniach dziesiętnych (`Latitude`, `Longitude`,
  `GPSPosition`) oraz filtrowanie prostokątem (bounding box).
- Filtr odległości od punktu GPS (`--near "LAT,LON,KM"`, wzór haversine) z
  polem `DistanceKm` i domyślnym sortowaniem wg odległości.
- Sortowanie wyników (`--sort`, `--desc`).
- Rekurencyjne przeszukiwanie podkatalogów (`-r` / `--recursive`).
- Eksport wyników do JSON (`--json`) i CSV (`--csv`).
- Flaga `--version`.
- 39 testów jednostkowych i integracyjnych; CI na Pythonie 3.10–3.13.
- Licencja MIT.

[1.0.0]: https://github.com/arturkwiek/ExifParser/releases/tag/v1.0.0
