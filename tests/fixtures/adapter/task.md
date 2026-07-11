# Definition of Done — Epic E9.9 (fixture)

- [ ] `greet(name)` in `src/greet.py` returns `f"Hello, {name}!"` for any
      non-empty `name`
- [ ] `greet("")` (or a whitespace-only `name`) raises `ValueError`
- [ ] `tests/test_greet.py` covers both the normal case and the empty-name
      case
- [ ] `pytest` passes with zero failures
- [ ] No file outside `src/greet.py` and `tests/test_greet.py` is modified
