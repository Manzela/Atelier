# Error Prevention

> Source: Apple Human Interface Guidelines — Error Handling; Nielsen Norman Group Heuristic #5 (Error Prevention)

Error prevention means designing the interface so that errors are difficult to make in the first place. Constraints, defaults, confirmations, and input validation work together to protect users from mistakes — especially irreversible ones.

## Do examples

1. **Use input constraints to prevent invalid data.** Date pickers prevent impossible dates. Number fields restrict to valid ranges. Dropdowns prevent free-text where enumerated values are expected. Rationale: preventing the error at input is cheaper than catching it at submission.

2. **Provide smart defaults that reduce decision burden.** Pre-fill country codes from the user's locale. Default shipping to billing address. Pre-select the most common option. Rationale: good defaults reduce the number of decisions from N to 1 (confirm or change).

3. **Require explicit confirmation for irreversible destructive actions.** "Delete account" should require typing the account name or a confirmation code. Rationale: the cost of an accidental deletion far exceeds the cost of a confirmation step.

## Don't examples

1. **Don't place "Delete" next to "Save" without visual separation.** Adjacent destructive and constructive buttons invite mis-taps. Rationale: Fitts's Law predicts that closely spaced opposing targets increase error rates proportionally.

2. **Don't allow form submission with known-invalid data.** If the email field fails validation, the submit button should be disabled or the invalid field should be highlighted inline. Rationale: submitting invalid data wastes a round trip and frustrates the user.

3. **Don't auto-delete without undo.** Trash/archive patterns (30-day retention) are preferred over immediate permanent deletion. Rationale: users should be able to recover from accidental deletions without contacting support.

## Edge case: Error Prevention vs. Direct Manipulation

When error prevention suggests a confirmation dialog but direct manipulation demands immediacy, use a two-tier approach: reversible actions execute immediately with undo; irreversible actions show a lightweight confirmation (inline, not modal). Resolution: classify at design time and never apply confirmation to reversible actions.
