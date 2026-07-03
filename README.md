# ExifParser

[![tests](https://github.com/arturkwiek/ExifParser/actions/workflows/tests.yml/badge.svg)](https://github.com/arturkwiek/ExifParser/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Narzędzie wiersza poleceń do odczytu danych **EXIF** ze zdjęć JPEG oraz
przeszukiwania kolekcji zdjęć po wartościach i **zakresach** pól — z obsługą
wyrażeń logicznych (AND/OR + nawiasy), sortowania, aliasów pól, współrzędnych
GPS i eksportu do JSON.

## Wymagania

- Python 3.10+
- [Pillow](https://python-pillow.org/)

## Instalacja

```bash
python3 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Szybki start

```bash
# Dla każdego zdjęcia w bieżącym katalogu wypisz aparat (pole domyślne)
python3 exif_cli.py

# Inne pole dla każdego pliku
python3 exif_cli.py --field ISO

# Jakie pola EXIF są w ogóle dostępne?
python3 exif_cli.py --list-fields
```

Domyślnie przetwarzany jest bieżący katalog; można podać inny jako argument:

```bash
python3 exif_cli.py /sciezka/do/zdjec --field DateTime
```

### Podkatalogi (`-r` / `--recursive`)

Domyślnie przeszukiwany jest tylko wskazany katalog. Flaga `-r` włącza
zejście do podkatalogów; pliki są wtedy pokazywane jako ścieżki względne
(również w polu `file` przy `--json`):

```bash
python3 exif_cli.py -r --field ISO
python3 exif_cli.py /archiwum -r --where "ISO>=800"
```

Działa we wszystkich trybach (`--field`, `--list-fields`, wyszukiwanie).

## Wyszukiwanie

### Proste warunki (`--where`)

Warunek ma postać `POLE OP WARTOŚĆ`. Można podać `--where` wielokrotnie —
warunki łączone są przez **AND**.

```bash
python3 exif_cli.py --where "ISO>=400"
python3 exif_cli.py --where "FNumber<=3.5" --where "DateTime>=2025:01:01"
python3 exif_cli.py --where "Camera=SONY DSC-HX9V"
```

Obok nazwy pliku wypisywane są wartości pól użytych w warunkach, a na
`stderr` — podsumowanie `Dopasowano N z M plików`. Kod wyjścia to `0`, gdy są
dopasowania, i `1`, gdy ich brak (wygodne w skryptach).

### Operatory

| Operator | Znaczenie | Przykład |
|----------|-----------|----------|
| `=`  | równe (liczby lub tekst, bez wielkości liter) | `ISO=800` |
| `!=` | różne | `Model!=DSC-HX9V` |
| `>` `>=` `<` `<=` | porównania / zakresy | `FNumber<=3.5` |
| `~`  | zawiera podłańcuch (bez wielkości liter) | `Model~HX9` |

Porównania są **liczbowe**, gdy obie strony są liczbami (ISO, przysłona,
ogniskowa, czas naświetlania), a w pozostałych przypadkach **tekstowe**. Daty
EXIF w formacie `RRRR:MM:DD GG:MM:SS` sortują się chronologicznie jako tekst,
więc `DateTime>=2025:01:01` działa jak zakres dat.

### Wyrażenia logiczne (`-q` / `--query`)

Pełne wyrażenia z **AND**, **OR** i nawiasami. `AND` wiąże silniej niż `OR`.

```bash
python3 exif_cli.py -q "ISO<=250 OR ISO>=1600"
python3 exif_cli.py -q "(ISO>=800 OR FNumber<3.5) AND Date>=2025:01:01"
```

`--where` i `--query` można łączyć — wszystkie części zostaną połączone przez
AND:

```bash
python3 exif_cli.py --where "Camera=SONY DSC-HX9V" -q "ISO>=1600"
```

> Uwaga: słowa `AND`/`OR` oraz nawiasy są rozpoznawane tylko jako samodzielne
> tokeny (oddzielone spacją/nawiasem), więc wartości mogą zawierać spacje
> (np. `Camera=SONY DSC-HX9V`). Unikaj natomiast nawiasów wewnątrz wartości.

## Sortowanie

```bash
python3 exif_cli.py --where "ISO>=640" --sort ISO --desc
python3 exif_cli.py -q "ISO>=1000" --sort Date        # chronologicznie
```

Sortowanie jest odporne na typy: liczby porównywane są numerycznie, teksty i
daty leksykograficznie, a braki wartości lądują na końcu.

## Eksport (JSON / CSV)

Flagi `--json` i `--csv` (wzajemnie wykluczające się) działają we wszystkich
trybach. Podsumowanie idzie na `stderr`, więc `stdout` zawiera czyste dane
(można bezpiecznie przekierować lub potokować).

```bash
# Pełny EXIF każdego dopasowanego pliku do JSON
python3 exif_cli.py --where "ISO>=800" --sort Date --json > wyniki.json

# Potok do jq — tylko nazwa pliku i ISO
python3 exif_cli.py -q "ISO>=1600" --json | jq '.[] | {file, ISO: .ISOSpeedRatings}'

# Eksport do CSV (np. do arkusza kalkulacyjnego)
python3 exif_cli.py --where "ISO>=800" --sort Date --csv > wyniki.csv
```

Zawartość zależnie od trybu:

- tryb wyszukiwania → wszystkie dopasowane pliki z **pełnym** zestawem pól
  EXIF (w CSV kolumny to `file` + suma wszystkich pól występujących w wynikach),
- `--field` → `{"file": …, POLE: wartość}` / dwie kolumny CSV,
- `--list-fields` → lista nazw pól.

W CSV wartości wieloelementowe (np. `LensSpecification`) są łączone średnikami,
a pola zawierające przecinki (np. `GPSPosition`) są poprawnie cytowane.

## Aliasy pól

Zamiast długich nazw tagów EXIF można używać skrótów (w `--field`, `--where`,
`--query`, `--sort`):

| Alias | Pole EXIF |
|-------|-----------|
| `ISO` | `ISOSpeedRatings` |
| `Date`, `DateTime` | `DateTime` |
| `F`, `aperture`, `FNumber` | `FNumber` |
| `exposure`, `shutter` | `ExposureTime` |
| `focal` | `FocalLength` |
| `Camera` | `Camera` (syntetyczne: `Make` + `Model`) |
| `Make`, `Model` | `Make`, `Model` |
| `width`, `height` | `ExifImageWidth`, `ExifImageHeight` |
| `lat`, `lon`/`lng` | `Latitude`, `Longitude` |
| `direction` | `GPSImgDirection` |
| `distance`, `dist` | `DistanceKm` (dostępne przy `--near`) |

Nieznana nazwa jest używana dosłownie, więc dowolny surowy tag EXIF (patrz
`--list-fields`) też zadziała.

## GPS

Jeśli zdjęcie ma zapisaną pozycję GPS, `read_exif` dodaje pola syntetyczne w
**stopniach dziesiętnych**: `Latitude`, `Longitude` oraz `GPSPosition`
(`"lat, lon"`). Surowe pola GPS (np. `GPSImgDirection`, `GPSMapDatum`) także
są przeszukiwalne. Dzięki temu można filtrować po prostokącie (bounding box):

```bash
python3 exif_cli.py -q "Latitude>=52 AND Latitude<=53 AND Longitude>=21 AND Longitude<=22"
```

> Wiele zdjęć nie ma faktycznego fixa GPS (`GPSStatus='V'`) — wtedy pól
> `Latitude`/`Longitude` brak. Do testów służy syntetyczny plik
> `fixtures/gps_sample.jpg` (patrz niżej).

### Odległość od punktu (`--near`)

Filtr `--near "LAT,LON,PROMIEŃ_KM"` zostawia zdjęcia w zadanym promieniu
(km) od punktu, licząc odległość po powierzchni Ziemi (wzór haversine).
Dodaje syntetyczne pole `DistanceKm` i domyślnie **sortuje wyniki rosnąco
wg odległości** (można nadpisać przez `--sort`).

```bash
# Zdjęcia w promieniu 5 km od centrum Warszawy
python3 exif_cli.py --near "52.23,21.01,5"

# Łączenie z innymi warunkami (AND) i eksport
python3 exif_cli.py --near "52.23,21.01,10" --where "ISO>=400" --csv
```

Alias `distance`/`dist` odnosi się do pola `DistanceKm` (np. `--sort dist --desc`).
Zdjęcia bez współrzędnych są pomijane.

## Struktura projektu

```
exif_reader.py        # warstwa danych: read_exif() + aliasy + gps_to_decimal()
exif_query.py         # logika zapytań: warunki, And/Or/nawiasy, parse_query()
exif_cli.py           # interfejs CLI
make_fixtures.py      # generator syntetycznych plików testowych z GPS
fixtures/             # pliki testowe (gps_sample.jpg)
test_exif_query.py    # testy jednostkowe zapytań i aliasów
test_gps_fixture.py   # testy integracyjne ścieżki GPS
test_cli.py           # testy CLI (wyszukiwanie plików, rekursja)
requirements.txt
```

`exif_reader.read_exif(path)` zwraca spłaszczony, znormalizowany słownik pól
EXIF (główne IFD + pod-IFD Exif + GPS) i jest wspólnym fundamentem dla CLI oraz
ewentualnych innych narzędzi.

## Testy

```bash
python3 -m unittest discover -p "test_*.py"   # bez dodatkowych zależności
# lub
python3 -m pytest
```

Regeneracja pliku testowego GPS (gdyby go brakowało):

```bash
python3 make_fixtures.py
```

## Pełna lista opcji CLI

```
usage: exif_cli.py [-h] [--field FIELD] [--list-fields] [--where WARUNEK]
                   [-q WYRAŻENIE] [--near LAT,LON,KM] [--sort POLE] [--desc]
                   [--json | --csv] [-r] [directory]
```

| Opcja | Opis |
|-------|------|
| `directory` | Katalog ze zdjęciami (domyślnie bieżący). |
| `--field FIELD` | Pole do wyświetlenia dla każdego pliku (domyślnie `Camera`). |
| `--list-fields` | Wypisz wszystkie dostępne pola EXIF i zakończ. |
| `--where WARUNEK` | Filtr `POLE OP WARTOŚĆ`; wielokrotnie = AND. |
| `-q, --query WYRAŻENIE` | Wyrażenie logiczne z AND/OR i nawiasami. |
| `--near LAT,LON,KM` | Filtr odległości od punktu GPS (dodaje `DistanceKm`). |
| `--sort POLE` | Sortuj wyniki po podanym polu. |
| `--desc` | Sortuj malejąco (z `--sort`). |
| `--json` | Wypisz wynik w formacie JSON. |
| `--csv` | Wypisz wynik w formacie CSV (wyklucza się z `--json`). |
| `-r, --recursive` | Przeszukuj również podkatalogi. |

## Licencja

Projekt udostępniony na licencji [MIT](LICENSE).
