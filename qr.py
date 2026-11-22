"""Minimaler QR-Code-Generator (nur Standardbibliothek).

Byte-Modus, Fehlerkorrektur M, Versionen 1-10 (reicht für URLs bis ~200 Zeichen).
Algorithmus nach dem öffentlich dokumentierten QR-Standard (ISO 18004).
"""

ECC_PER_BLOCK = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
NUM_BLOCKS = [None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        r -= (25 * n - 10) * n - 55
        if ver >= 7:
            r -= 36
    return r


def _data_codewords(ver):
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[ver] * NUM_BLOCKS[ver]


def _rs_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _rs_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _rs_mul(root, 2)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _rs_mul(coef, factor)
    return result


def _align_positions(ver):
    if ver == 1:
        return []
    n = ver // 7 + 2
    size = ver * 4 + 17
    step = (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    pos = [size - 7 - i * step for i in range(n - 1)] + [6]
    return pos[::-1]


def _encode_data(data: bytes, ver):
    bits = []

    def put(val, n):
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)

    put(0b0100, 4)
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    cap = _data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    return [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]


def _add_ecc(data, ver):
    nb = NUM_BLOCKS[ver]
    ecc_len = ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    short_blocks = nb - raw % nb
    short_len = raw // nb
    rs = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(nb):
        n = short_len - ecc_len + (0 if i < short_blocks else 1)
        dat = data[k:k + n]
        k += n
        ecc = _rs_remainder(dat, rs)
        if i < short_blocks:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_blocks:
                out.append(blk[i])
    return out


def _mask_fn(m):
    return [
        lambda x, y: (x + y) % 2 == 0,
        lambda x, y: y % 2 == 0,
        lambda x, y: x % 3 == 0,
        lambda x, y: (x + y) % 3 == 0,
        lambda x, y: (x // 3 + y // 2) % 2 == 0,
        lambda x, y: x * y % 2 + x * y % 3 == 0,
        lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
    ][m]


def make_matrix(text: str):
    data = text.encode("utf-8")
    ver = next((v for v in range(1, 11) if 4 + (8 if v < 10 else 16) + 8 * len(data) <= _data_codewords(v) * 8), None)
    if ver is None:
        raise ValueError("Text zu lang für den QR-Generator")
    size = ver * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]

    def setf(x, y, v):
        mod[y][x] = bool(v)
        fn[y][x] = True

    def finder(cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    setf(x, y, max(abs(dx), abs(dy)) not in (2, 4))

    for i in range(size):
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    finder(3, 3)
    finder(size - 4, 3)
    finder(3, size - 4)
    pos = _align_positions(ver)
    n = len(pos)
    for i in range(n):
        for j in range(n):
            if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)

    def format_bits(mask):
        d = (0 << 3) | mask  # Level M = 0
        rem = d
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (d << 10 | rem) ^ 0x5412
        g = lambda i: (bits >> i) & 1
        for i in range(0, 6):
            setf(8, i, g(i))
        setf(8, 7, g(6))
        setf(8, 8, g(7))
        setf(7, 8, g(8))
        for i in range(9, 15):
            setf(14 - i, 8, g(i))
        for i in range(0, 8):
            setf(size - 1 - i, 8, g(i))
        for i in range(8, 15):
            setf(8, size - 15 + i, g(i))
        setf(8, size - 8, True)

    format_bits(0)
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = ver << 12 | rem
        for i in range(18):
            b = (bits >> i) & 1
            a = size - 11 + i % 3
            c = i // 3
            setf(a, c, b)
            setf(c, a, b)

    codewords = _add_ecc(_encode_data(data, ver), ver)
    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = size - 1 - vert if upward else vert
                if not fn[y][x] and i < len(codewords) * 8:
                    mod[y][x] = ((codewords[i >> 3] >> (7 - (i & 7))) & 1) == 1
                    i += 1
        right -= 2

    def penalty(m):
        s = len(m)
        p = 0
        for grid in (m, [list(r) for r in zip(*m)]):
            for row in grid:
                run = 1
                for k in range(1, s):
                    if row[k] == row[k - 1]:
                        run += 1
                        if run == 5:
                            p += 3
                        elif run > 5:
                            p += 1
                    else:
                        run = 1
        for y in range(s - 1):
            for x in range(s - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    p += 3
        dark = sum(sum(r) for r in m)
        p += abs(dark * 20 - s * s * 10) // (s * s) * 10
        return p

    best, best_mask = None, 0
    for mask in range(8):
        f = _mask_fn(mask)
        cand = [[mod[y][x] ^ (not fn[y][x] and f(x, y)) for x in range(size)] for y in range(size)]
        p = penalty(cand)
        if best is None or p < best[0]:
            best, best_mask = (p, cand), mask
    mod = best[1]
    format_bits(best_mask)
    return mod


def make_svg(text: str, border: int = 4) -> str:
    m = make_matrix(text)
    s = len(m)
    parts = []
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                parts.append(f"M{x + border},{y + border}h1v1h-1z")
    dim = s + border * 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges">'
        f'<rect width="{dim}" height="{dim}" fill="#fff"/><path d="{"".join(parts)}" fill="#000"/></svg>'
    )
