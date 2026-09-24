---
name: cantoai-test-behavior
description: "Apply whenever you add or change a test in tests/ of this repository. Call the code the way its users do and assert the observed result against a literal expected value. A test you add that would still pass when every imported function returned None gets a real assertion or is not added. A weak test that was already there is reported, not changed, unless this pull request changes the code it guards."
paths:
  - "tests/**"
  - "src/**"
---

# cantoai-test-behavior: test behavior, not implementation

Adapted from the `principle-test-behavior-not-implementation` skill of pstack 0.15.5 (`cursor/plugins`, MIT, see `../LICENSE-pstack`), with the examples restated for pytest.

A test calls the code the way its users do and asserts the result they observe against a literal expected value. A test that asserts which calls the code made, or restates a constant the code contains, does neither.

**The check.** Before you add or change a test, ask whether it would still pass if every function it imports returned `None`. If yes, it observes no behavior and cannot fail for a defect. Give it a real assertion, or do not add it.

**Why.** A test that cannot fail for a defect costs CI time and review attention and catches nothing. A constant pin also fails when someone edits the constant it restates, so it blocks that edit for no gain.

**Five shapes that still pass when every imported function returns `None`:**

- **Weak or no assertion.** No `assert`, or only `assert result`, `assert result is not None`, `isinstance` checks, `len(x) > 0`, or a bare call that merely must not raise.
- **Mock or absence only.** Only `mock.assert_called()`, `assert_not_called()`, `assert x is None`, `assert x == []`.
- **Self-referential.** The expected value comes from the code under test: `assert f(a) == f(a)`, `assert parsed.url == build_url(...)`.
- **Constant pin.** The assertion restates a hand-maintained constant, config default or table row: `assert LIMITS["max_tools"] == 8`.
- **Fixture asserts fixture.** The assertion reads data the test or a fixture built, and the subject never runs in the test body.

**The fix.** Call the subject inside the test with one concrete input and assert the literal output or the observable effect: `assert slugify("Hello, World!") == "hello-world"`. For an absence, assert the presence on the other input in the same test. For a constant, test the mechanism that reads it with one input instead of restating the value. For a mock, assert the payload it received or the state after the call, not that it was called. When no such assertion exists, do not add the test.

**Allowed:** a test of a relation across a table's rows (a key present in two tables, a parent that exists). It is not a constant pin.

**Tests that were already there.** Apply the check only to tests you add, and to tests you change because this pull request changes the code they guard. The analysis contract forbids modifying an assertion that already exists except in the pull request that changes the code it guards, and the body lists each such pair. Every other existing test that has one of the five shapes is reported, not touched: list it in the pull-request body or your final message (file, test name, shape). Never weaken or delete an existing test to make a change pass. Removing a `match=` pattern from any test also counts as moving a bar (history-audit).

**In this repository.** The analysis contract (clause 7) requires a `pytest.raises(<type>, match=r"^<message>")` test for every assertion message in `src/`, with a body that calls a function imported from `src/`, unmocked. That test must trip the assertion through real input, not by raising the exception itself.
