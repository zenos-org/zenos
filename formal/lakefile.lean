import Lake
open Lake DSL

/-! The ZENOS decision core: the pure functions keyd and guardd run to decide whether a file may be opened and
whether a stop may be released, with machine-checked proofs of what those decisions guarantee. -/
package «zenos-formal» where
  version := v!"0.1.0"

@[default_target]
lean_lib ZenosFormal

/-- The decision program keyd and guardd call (one JSON request on stdin, one JSON answer on stdout). -/
@[default_target]
lean_exe «zenos-decide» where
  root := `Main
