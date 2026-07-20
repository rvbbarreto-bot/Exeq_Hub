def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _dv_cnpj(base: str) -> str:
    weights_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def calc(digits: str, weights: list[int]) -> str:
        total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    d1 = calc(base, weights_1)
    d2 = calc(base + d1, weights_2)
    return d1 + d2


def _dv_cpf(base: str) -> str:
    def calc(digits: str, weight_start: int) -> str:
        total = sum(int(d) * w for d, w in zip(digits, range(weight_start, 1, -1), strict=True))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    d1 = calc(base, 10)
    d2 = calc(base + d1, 11)
    return d1 + d2


def validate_cnpj(value: str) -> str:
    digits = _digits_only(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        raise ValueError("CNPJ inválido")
    if digits[-2:] != _dv_cnpj(digits[:12]):
        raise ValueError("CNPJ inválido")
    return digits


def validate_cpf(value: str) -> str:
    digits = _digits_only(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        raise ValueError("CPF inválido")
    if digits[-2:] != _dv_cpf(digits[:9]):
        raise ValueError("CPF inválido")
    return digits
