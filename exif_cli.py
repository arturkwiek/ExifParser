"""Prosty interfejs wiersza poleceń do przeglądania danych EXIF.

Pierwszy krok docelowej aplikacji: dla każdego zdjęcia w katalogu wyświetla
wartość wybranego pola EXIF (domyślnie aparat). W kolejnych krokach dołożymy
przeszukiwanie po wartościach i zakresach.

Przykłady:
    python3 exif_cli.py                     # aparat dla każdego pliku (.)
    python3 exif_cli.py --field ISOSpeedRatings
    python3 exif_cli.py --field DateTime /sciezka/do/zdjec
    python3 exif_cli.py --list-fields       # jakie pola są dostępne

Wyszukiwanie (koniunkcja warunków, można podać --where wielokrotnie):
    python3 exif_cli.py --where "ISOSpeedRatings>=400"
    python3 exif_cli.py --where "FNumber<=3.5" --where "DateTime>=2025:01:01"
    python3 exif_cli.py --where "Camera=SONY DSC-HX9V"
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from exif_reader import haversine_km, read_exif, resolve_field
from exif_query import And, QueryError, field_names, parse_condition, parse_query

__version__ = "1.0.0"

JPEG_SUFFIXES = {".jpg", ".jpeg"}


def _json_safe(value):
    """Zamień wartość EXIF na typ serializowalny do JSON.

    Pillow zwraca m.in. ``IFDRational`` (przysłona, czas) oraz krotki
    (np. LensSpecification) — konwertujemy je na float/list, a wszystko inne
    niestandardowe na tekst.
    """
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        return float(value)  # IFDRational i podobne
    except (TypeError, ValueError):
        return str(value)


def _dump_json(data) -> None:
    """Wypisz dane jako JSON (UTF-8, czytelne wcięcia)."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _csv_value(value) -> str:
    """Zamień wartość EXIF na tekst nadający się do komórki CSV."""
    value = _json_safe(value)
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def _dump_csv(rows: list[dict], fieldnames: list[str]) -> None:
    """Wypisz wiersze (słowniki) jako CSV z podanym nagłówkiem.

    Używamy stałego terminatora '\\n' i piszemy przez bufor, aby uniknąć
    podwójnych końców linii na Windows.
    """
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    sys.stdout.write(buf.getvalue())


def find_images(directory: Path, recursive: bool = False) -> list[Path]:
    """Zwróć posortowaną listę plików JPEG w katalogu.

    Przy ``recursive=True`` przeszukiwane są również podkatalogi.
    """
    entries = directory.rglob("*") if recursive else directory.iterdir()
    return sorted(
        p for p in entries
        if p.is_file() and p.suffix.lower() in JPEG_SUFFIXES
    )


def _label(path: Path, base: Path) -> str:
    """Etykieta pliku do wyświetlenia: ścieżka względna wobec przeszukiwanego
    katalogu (dla trybu rekurencyjnego), a w razie potrzeby sama nazwa."""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def cmd_list_fields(images: list[Path], fmt: str = "text") -> int:
    """Wypisz zbiór wszystkich nazw pól EXIF występujących w zdjęciach."""
    names: set[str] = set()
    for path in images:
        names.update(read_exif(path).keys())
    if not names:
        if fmt == "json":
            _dump_json([])
        elif fmt == "csv":
            _dump_csv([], ["field"])
        else:
            print("Nie znaleziono żadnych danych EXIF.")
        return 1
    ordered = sorted(names)
    if fmt == "json":
        _dump_json(ordered)
        return 0
    if fmt == "csv":
        _dump_csv([{"field": n} for n in ordered], ["field"])
        return 0
    print(f"Dostępne pola EXIF ({len(names)}):")
    for name in ordered:
        print(f"  {name}")
    return 0


def cmd_show_field(
    images: list[Path], field: str, base: Path, fmt: str = "text"
) -> int:
    """Dla każdego zdjęcia wyświetl wartość wybranego pola."""
    if fmt == "json":
        rows = [
            {"file": _label(path, base), field: _json_safe(read_exif(path).get(field))}
            for path in images
        ]
        _dump_json(rows)
        return 0
    if fmt == "csv":
        rows = [
            {"file": _label(path, base), field: _csv_value(read_exif(path).get(field))}
            for path in images
        ]
        _dump_csv(rows, ["file", field])
        return 0
    labels = {p: _label(p, base) for p in images}
    width = max((len(v) for v in labels.values()), default=0)
    for path in images:
        fields = read_exif(path)
        value = fields.get(field, "—")
        print(f"{labels[path]:<{width}}  {value}")
    return 0


def _parse_near(spec: str) -> tuple:
    """Rozłóż argument ``--near`` postaci 'LAT,LON,PROMIEŃ' na trzy liczby.

    Zwraca krotkę (lat, lon, radius_km). Rzuca :class:`QueryError` przy błędzie.
    """
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 3:
        raise QueryError(
            f"Niepoprawny argument --near: '{spec}'. "
            f"Oczekiwano 'LAT,LON,PROMIEŃ_KM', np. '52.23,21.01,5'."
        )
    try:
        lat, lon, radius = (float(p) for p in parts)
    except ValueError:
        raise QueryError(
            f"Wartości w --near muszą być liczbami: '{spec}'."
        )
    if radius < 0:
        raise QueryError("Promień w --near nie może być ujemny.")
    return lat, lon, radius


def _sort_key(value):
    """Klucz sortowania: (brak?, liczba-lub-tekst). Braki lądują na końcu.

    Zwracamy krotkę (rodzaj, wartość), aby liczby i teksty nie były
    porównywane ze sobą (co w Pythonie 3 rzucałoby wyjątkiem).
    """
    if value is None:
        return (2, 0.0, "")
    try:
        return (0, float(value), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(value).casefold())


def cmd_search(
    images: list[Path],
    expressions: list[str] | None,
    query: str | None = None,
    sort_field: str | None = None,
    descending: bool = False,
    fmt: str = "text",
    base: Path | None = None,
    near: str | None = None,
) -> int:
    """Wypisz pliki spełniające zapytanie.

    Warunki z ``--where`` (łączone przez AND) i wyrażenie ``--query`` (z AND/OR
    i nawiasami) składane są w jedno drzewo predykatów. ``--near`` dodaje filtr
    odległości od punktu GPS (pole syntetyczne ``DistanceKm``). Obok nazwy pliku
    pokazujemy wartości użytych pól. Wyniki można posortować po dowolnym polu.
    """
    try:
        parts = [parse_condition(e, resolve_field) for e in (expressions or [])]
        if query:
            parts.append(parse_query(query, resolve_field))
        center = _parse_near(near) if near else None
        if center is not None:
            # Filtr odległości = warunek na syntetycznym polu DistanceKm.
            parts.append(parse_condition(f"DistanceKm<={center[2]}", resolve_field))
    except QueryError as err:
        print(f"Błąd zapytania: {err}", file=sys.stderr)
        return 2

    if not parts:
        print("Podaj co najmniej jeden warunek (--where / --query / --near).",
              file=sys.stderr)
        return 2

    predicate = parts[0] if len(parts) == 1 else And(tuple(parts))

    shown_fields = field_names(predicate)  # unikalne, w kolejności
    # Domyślnie sortuj wg odległości, gdy użyto --near bez własnego --sort.
    if center is not None and not sort_field:
        sort_field = "DistanceKm"
    sort_field = resolve_field(sort_field) if sort_field else None
    if sort_field and sort_field not in shown_fields:
        shown_fields.append(sort_field)  # pokaż też pole, po którym sortujemy

    # Zbierz dopasowania jako (ścieżka, dane EXIF).
    matches: list[tuple[Path, dict]] = []
    for path in images:
        fields = read_exif(path)
        if center is not None:
            lat, lon = fields.get("Latitude"), fields.get("Longitude")
            if lat is not None and lon is not None:
                fields["DistanceKm"] = round(
                    haversine_km(center[0], center[1], lat, lon), 3
                )
        if predicate.matches(fields):
            matches.append((path, fields))

    if sort_field:
        matches.sort(
            key=lambda pair: _sort_key(pair[1].get(sort_field)),
            reverse=descending,
        )

    def label(path: Path) -> str:
        return _label(path, base) if base is not None else path.name

    if fmt == "json":
        rows = [
            {"file": label(path), **{k: _json_safe(v) for k, v in fields.items()}}
            for path, fields in matches
        ]
        _dump_json(rows)
        print(f"Dopasowano {len(matches)} z {len(images)} plików.", file=sys.stderr)
        return 0 if matches else 1

    if fmt == "csv":
        # Kolumny: 'file' + suma wszystkich pól występujących w dopasowaniach.
        all_keys: dict = {}
        for _, fields in matches:
            all_keys.update(dict.fromkeys(fields))
        fieldnames = ["file"] + sorted(all_keys)
        rows = [
            {"file": label(path), **{k: _csv_value(v) for k, v in fields.items()}}
            for path, fields in matches
        ]
        _dump_csv(rows, fieldnames)
        print(f"Dopasowano {len(matches)} z {len(images)} plików.", file=sys.stderr)
        return 0 if matches else 1

    width = max((len(label(p)) for p, _ in matches), default=0)
    for path, fields in matches:
        details = "  ".join(
            f"{name}={fields.get(name, '—')}" for name in shown_fields
        )
        print(f"{label(path):<{width}}  {details}")

    print(f"\nDopasowano {len(matches)} z {len(images)} plików.", file=sys.stderr)
    return 0 if matches else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Odczyt danych EXIF z plików JPEG.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Katalog ze zdjęciami (domyślnie bieżący).",
    )
    parser.add_argument(
        "--field",
        default="Camera",
        help="Nazwa pola EXIF do wyświetlenia (domyślnie: Camera).",
    )
    parser.add_argument(
        "--list-fields",
        action="store_true",
        help="Wypisz wszystkie dostępne pola EXIF i zakończ.",
    )
    parser.add_argument(
        "--where",
        action="append",
        metavar="WARUNEK",
        help="Filtr postaci 'POLE OP WARTOŚĆ' (op: = != > >= < <= ~). "
             "Można podać wielokrotnie — warunki łączone są przez AND.",
    )
    parser.add_argument(
        "-q", "--query",
        metavar="WYRAŻENIE",
        help="Wyrażenie logiczne z AND/OR i nawiasami, np. "
             "'(ISO>=800 OR FNumber<3.5) AND DateTime>=2025:01:01'.",
    )
    parser.add_argument(
        "--near",
        metavar="LAT,LON,KM",
        help="Filtruj zdjęcia w promieniu KM kilometrów od punktu (LAT, LON), "
             "np. '52.23,21.01,5'. Dodaje pole DistanceKm i domyślnie sortuje "
             "po odległości.",
    )
    parser.add_argument(
        "--sort",
        metavar="POLE",
        help="Posortuj wyniki wyszukiwania po podanym polu.",
    )
    parser.add_argument(
        "--desc",
        action="store_true",
        help="Sortuj malejąco (razem z --sort).",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        help="Wypisz wynik w formacie JSON (do dalszego przetwarzania).",
    )
    output.add_argument(
        "--csv",
        action="store_true",
        help="Wypisz wynik w formacie CSV (do arkusza / dalszego przetwarzania).",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Przeszukuj również podkatalogi.",
    )
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"Błąd: '{directory}' nie jest katalogiem.", file=sys.stderr)
        return 2

    images = find_images(directory, args.recursive)
    if not images:
        gdzie = "katalogu i podkatalogach" if args.recursive else "katalogu"
        print(f"Brak plików JPEG w {gdzie} '{directory}'.", file=sys.stderr)
        return 1

    fmt = "csv" if args.csv else "json" if args.json else "text"

    if args.list_fields:
        return cmd_list_fields(images, fmt)
    if args.where or args.query or args.near:
        return cmd_search(
            images, args.where, args.query, args.sort, args.desc, fmt,
            base=directory, near=args.near,
        )
    return cmd_show_field(images, resolve_field(args.field), directory, fmt)


if __name__ == "__main__":
    raise SystemExit(main())
