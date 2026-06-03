/**
 * Minimal LexoRank — a fractional lexical ordering key (PRD §7A.5 / glossary).
 *
 * A LexoRank is a string ordering key that lets a list item be positioned
 * between any two neighbours WITHOUT re-indexing the whole list: to move B
 * between A and C you compute a new key that sorts lexically between
 * `rank(A)` and `rank(C)`. The Board (AT-041) uses it for manual drag (drop a
 * card between two others) and to keep its sort coherent with the autonomous
 * writes the AT-020b emitter appends at each stage transition.
 *
 * This is a direct TS port of the dependency-free midpoint-string implementation
 * in `atelier-core/src/atelier/board/lexorank.py`. Porting it inline keeps the
 * cross-language ordering identical AND honours the sprint `<lockfile_only_installs>`
 * invariant — we add no `lexorank` npm dependency for a ~40-line algorithm.
 *
 * Alphabet: lowercase base-36 `[0-9a-z]` (36 digits). Keys compare with plain
 * string `<` (lexicographic). The empty string sorts before every key, so
 * `rankAfter(null)` seeds the first key and `rankBetween('', x)` prepends before
 * `x`.
 *
 * Invariants (asserted by lexorank.test.ts):
 *   - `rankAfter(prev) > prev` for any `prev`.
 *   - `a < rankBetween(a, b) < b` for any `a < b`.
 *   - keys never collide for distinct insertions on the same lane.
 */

/** base-36 digit alphabet; index in this string IS the digit value. */
const ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz';
const BASE = ALPHABET.length; // 36
/**
 * A comfortable starting key in the middle of the space so both prepend and
 * append have room before the string has to grow. Matches the Python `_INITIAL`.
 */
const INITIAL = 'n'; // ALPHABET[23], roughly mid-range

function digit(ch: string): number {
  const v = ALPHABET.indexOf(ch);
  if (v < 0) {
    throw new RangeError(`lexorank: out-of-alphabet character ${JSON.stringify(ch)}`);
  }
  return v;
}

/**
 * Return a key strictly between `lower` and `upper` (lexicographically).
 *
 * Bounds semantics:
 *   - `lower === ''` -> negative infinity (prepend before everything).
 *   - `upper === ''` -> positive infinity (append after everything).
 *   - otherwise `lower < upper` is REQUIRED.
 *
 * Walks the two keys digit-by-digit: while the digits match it copies them; at
 * the first position with room it inserts a midpoint digit. If no gap exists at
 * the shared-prefix length (adjacent digits), it extends `lower` by a midpoint
 * digit — always strictly greater than `lower` and (because `upper` had no room
 * at that position) strictly less than `upper`.
 */
export function rankBetween(lower: string, upper: string): string {
  if (lower && upper && !(lower < upper)) {
    throw new RangeError(
      `rankBetween requires lower < upper, got ${JSON.stringify(lower)}, ${JSON.stringify(upper)}`
    );
  }

  const result: string[] = [];
  let i = 0;
  for (;;) {
    const lo = i < lower.length ? digit(lower[i]) : 0;
    // When `upper` is the empty (+inf) sentinel, the conceptual upper digit is
    // one past the max so there is always room to step forward.
    const hi = i < upper.length ? digit(upper[i]) : BASE;
    if (lo === hi) {
      // Digits identical -> copy and descend to the next position.
      result.push(ALPHABET[lo]);
      i += 1;
      continue;
    }
    const mid = Math.floor((lo + hi) / 2);
    if (mid !== lo) {
      // A free digit strictly between the bounds exists at this position.
      result.push(ALPHABET[mid]);
      return result.join('');
    }
    // lo and hi are adjacent (hi === lo + 1): no room here. Keep lower's digit
    // and descend — on the next position `upper` is unbounded (we have passed
    // its constraining digit), so a midpoint digit there lands strictly between.
    result.push(ALPHABET[lo]);
    i += 1;
    // Safety: append a mid digit if `lower` runs out (prevents an infinite loop
    // on equal-prefix inputs; mid of [0, BASE) is non-zero).
    if (i >= lower.length) {
      result.push(ALPHABET[Math.floor(BASE / 2)]);
      return result.join('');
    }
  }
}

/**
 * Return a key that sorts strictly after `prev` (append to a lane tail).
 *
 * `prev` null/empty seeds the first key on a fresh lane. Otherwise we return the
 * midpoint between `prev` and the conceptual upper bound (`''` == +inf), which
 * is the standard "insert at end" operation.
 */
export function rankAfter(prev: string | null): string {
  if (!prev) return INITIAL;
  return rankBetween(prev, '');
}

/**
 * Compute a rank for inserting BETWEEN two (possibly absent) neighbours. Pass
 * `null`/`undefined` for a missing neighbour:
 *   - no `before` (top of list) -> prepend (`rankBetween('', after)`).
 *   - no `after` (bottom of list) -> append (`rankAfter(before)`).
 *   - both present -> midpoint between them.
 *   - neither -> a seed key on an empty lane.
 */
export function generateRank(
  before: string | null | undefined,
  after: string | null | undefined
): string {
  const b = before ?? '';
  const a = after ?? '';
  if (!b && !a) return INITIAL;
  if (!b) return rankBetween('', a);
  if (!a) return rankAfter(b);
  return rankBetween(b, a);
}

/** Lexicographic comparator for sorting cards by their LexoRank. */
export function compareRanks(a: string, b: string): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
