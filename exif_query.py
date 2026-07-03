"""Parsowanie i ewaluacja warunków wyszukiwania po polach EXIF.

Warunek ma postać ``POLE OPERATOR WARTOŚĆ``, np.::

    ISOSpeedRatings>=400
    FNumber<=3.5
    DateTime>=2025:01:01
    Camera=SONY DSC-HX9V
    Model~HX9          # zawiera podłańcuch (bez rozróżniania wielkości liter)

Obsługiwane operatory (kolejność ważna przy parsowaniu — najpierw dłuższe)::

    >=  <=  !=  ~   >  <  =

Porównania liczbowe wykonywane są, gdy obie strony dają się zrzutować na
liczbę (ISO, przysłona, ogniskowa, czas naświetlania). W przeciwnym razie
porównujemy tekstowo — co dla dat EXIF w formacie ``RRRR:MM:DD GG:MM:SS``
działa poprawnie, bo taki zapis sortuje się leksykograficznie zgodnie z
chronologią. Dzięki temu ``DateTime>=2025:01:01`` działa jak zakres dat.
"""

from __future__ import annotations

from dataclasses import dataclass

# Operatory posortowane tak, by dłuższe (>=, <=, !=) były sprawdzane przed
# ich jednoznakowymi prefiksami (>, <, =).
_OPERATORS = [">=", "<=", "!=", "~", ">", "<", "="]


class QueryError(ValueError):
    """Błąd składni warunku wyszukiwania."""


def _as_number(value):
    """Zwróć float, jeśli wartość reprezentuje liczbę; inaczej None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: str

    def matches(self, fields: dict) -> bool:
        """Sprawdź, czy dane EXIF (``fields``) spełniają ten warunek."""
        if self.field not in fields:
            return False
        actual = fields[self.field]

        if self.op == "~":
            return self.value.casefold() in str(actual).casefold()

        num_actual = _as_number(actual)
        num_target = _as_number(self.value)
        numeric = num_actual is not None and num_target is not None

        if self.op in ("=", "!="):
            if numeric:
                equal = num_actual == num_target
            else:
                equal = str(actual).casefold() == self.value.casefold()
            return equal if self.op == "=" else not equal

        # Operatory porównania zakresowego: >, >=, <, <=
        if numeric:
            left, right = num_actual, num_target
        else:
            left, right = str(actual), self.value

        if self.op == ">":
            return left > right
        if self.op == ">=":
            return left >= right
        if self.op == "<":
            return left < right
        if self.op == "<=":
            return left <= right

        raise QueryError(f"Nieznany operator: {self.op}")  # nie powinno wystąpić


def _identity(name: str) -> str:
    return name


def parse_condition(expr: str, resolver=_identity) -> Condition:
    """Zbuduj :class:`Condition` z tekstu ``POLE OP WARTOŚĆ``.

    ``resolver`` pozwala zamienić nazwę pola (np. rozwinąć alias ``ISO`` na
    ``ISOSpeedRatings``); domyślnie nazwa pozostaje bez zmian.
    """
    for op in _OPERATORS:
        idx = expr.find(op)
        if idx > 0:  # > 0: pole nie może być puste
            field = expr[:idx].strip()
            value = expr[idx + len(op):].strip()
            if not field or not value:
                break
            return Condition(field=resolver(field), op=op, value=value)
    raise QueryError(
        f"Niepoprawny warunek: '{expr}'. "
        f"Oczekiwano formatu POLE OP WARTOŚĆ, np. 'ISOSpeedRatings>=400'."
    )


def matches_all(fields: dict, conditions: list[Condition]) -> bool:
    """Prawda, gdy dane EXIF spełniają wszystkie warunki (koniunkcja)."""
    return all(cond.matches(fields) for cond in conditions)


# --------------------------------------------------------------------------
# Wyrażenia logiczne: AND / OR / nawiasy nad warunkami atomowymi.
#
# Gramatyka (AND wiąże silniej niż OR, zgodnie z konwencją):
#     expr    := or_expr
#     or_expr := and_expr (OR and_expr)*
#     and_expr:= factor  (AND factor)*
#     factor  := '(' expr ')' | condition
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class And:
    parts: tuple

    def matches(self, fields: dict) -> bool:
        return all(p.matches(fields) for p in self.parts)


@dataclass(frozen=True)
class Or:
    parts: tuple

    def matches(self, fields: dict) -> bool:
        return any(p.matches(fields) for p in self.parts)


def field_names(node) -> list:
    """Zwróć (w kolejności, bez powtórzeń) nazwy pól użytych w wyrażeniu."""
    if isinstance(node, Condition):
        names = [node.field]
    else:
        names = [n for part in node.parts for n in field_names(part)]
    return list(dict.fromkeys(names))


def _tokenize(expr: str) -> list:
    """Podziel wyrażenie na tokeny: '(', ')', 'AND', 'OR' oraz warunki.

    Słowa kluczowe i nawiasy rozpoznajemy tylko jako samodzielne (oddzielone
    białym znakiem lub nawiasem), więc wartości warunków mogą zawierać spacje,
    np. ``Camera=SONY DSC-HX9V``.
    """
    tokens: list = []
    buf = ""

    def flush():
        nonlocal buf
        if buf.strip():
            tokens.append(("COND", buf.strip()))
        buf = ""

    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch in "()":
            flush()
            tokens.append(("LPAREN" if ch == "(" else "RPAREN", ch))
            i += 1
            continue
        for kw in ("AND", "OR"):
            end = i + len(kw)
            before_ok = i == 0 or expr[i - 1].isspace() or expr[i - 1] == "("
            after_ok = end >= n or expr[end].isspace() or expr[end] in "()"
            if before_ok and after_ok and expr[i:end].upper() == kw:
                flush()
                tokens.append((kw, kw))
                i = end
                break
        else:
            buf += ch
            i += 1
            continue
    flush()
    return tokens


class _Parser:
    def __init__(self, tokens: list, resolver):
        self.tokens = tokens
        self.pos = 0
        self.resolver = resolver

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _advance(self):
        tok = self._peek()
        self.pos += 1
        return tok

    def parse(self):
        node = self._or_expr()
        if self.pos != len(self.tokens):
            raise QueryError(f"Nieoczekiwany token: {self._peek()[1]!r}")
        return node

    def _or_expr(self):
        parts = [self._and_expr()]
        while self._peek()[0] == "OR":
            self._advance()
            parts.append(self._and_expr())
        return parts[0] if len(parts) == 1 else Or(tuple(parts))

    def _and_expr(self):
        parts = [self._factor()]
        while self._peek()[0] == "AND":
            self._advance()
            parts.append(self._factor())
        return parts[0] if len(parts) == 1 else And(tuple(parts))

    def _factor(self):
        kind, text = self._peek()
        if kind == "LPAREN":
            self._advance()
            node = self._or_expr()
            if self._peek()[0] != "RPAREN":
                raise QueryError("Brak zamykającego nawiasu ')'.")
            self._advance()
            return node
        if kind == "COND":
            self._advance()
            return parse_condition(text, self.resolver)
        raise QueryError(
            "Oczekiwano warunku lub '(', "
            f"napotkano: {text!r}" if text else "Puste wyrażenie."
        )


def parse_query(expr: str, resolver=_identity):
    """Zparsuj pełne wyrażenie logiczne (AND/OR/nawiasy) do drzewa węzłów.

    Zwrócony obiekt udostępnia ``.matches(fields)``. Węzły to
    :class:`Condition`, :class:`And` lub :class:`Or`.
    """
    tokens = _tokenize(expr)
    if not tokens:
        raise QueryError("Puste wyrażenie zapytania.")
    return _Parser(tokens, resolver).parse()
