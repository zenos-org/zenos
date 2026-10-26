import ZenosFormal.Decide

/-!
`zenos-decide`: reads one JSON request on stdin, writes one JSON answer on stdout, runs the proven decision
functions of `ZenosFormal.Decide` and nothing else. Any input it cannot read is refused (exit status 2, answer
`{"error": ...}`); the services treat that as a refusal.

  {"op":"open", "user", "clearance", "level", "file_hash", "now", "halted", "roster":[..],
   "grant": null | {"requester","holder","file_hash","level","kind":null|str,"expires","digest_ok",
                    "approvals":[{"approver","sig_ok"}]}}
      -> {"allow": bool, "by": "clearance"|"grant"|null, "reason": str|null}
  {"op":"approve", "request":{"id","requester","level","required","status","approvals":[..]}, "roster":[..],
   "who", "act":"approve"|"decline", "sig_ok", "code_ok"}
      -> {"result": "added"|"declined"|"refused", "reason": str|null}
  {"op":"release", "halted", "request":{..}, "roster":[..]}
      -> {"release": bool, "approvers":[..]}
  {"op":"release-required", "roster":[..], "requester", "level"}
      -> {"required": n}
  {"op":"required", "level"}       -> {"required": n}   (approvals a level needs; the services' table must agree)
-/


/-! A small JSON reader and writer, so the program needs only Lean's core library (no `Lean` package: the binary
    stays small). It accepts what the services send: objects, arrays, strings, non-negative integers, booleans,
    null. -/

inductive J where
  | null
  | bool (b : Bool)
  | num (n : Nat)
  | str (s : String)
  | arr (xs : List J)
  | obj (kvs : List (String × J))
  deriving Inhabited

namespace J

abbrev P := StateT (List Char) (Except String)

def peek : P (Option Char) := do return (← get).head?
def next : P Char := do
  match ← get with
  | c :: cs => set cs; return c
  | [] => throw "unexpected end"
def ws : P Unit := modify (·.dropWhile (fun c => c == ' ' || c == '\n' || c == '\r' || c == '\t'))
def expect (c : Char) : P Unit := do
  if (← next) != c then throw s!"expected {c}"
def word (w : String) : P Unit := w.toList.forM expect

def hex (c : Char) : P Nat :=
  if '0' ≤ c && c ≤ '9' then pure (c.toNat - '0'.toNat)
  else if 'a' ≤ c && c ≤ 'f' then pure (c.toNat - 'a'.toNat + 10)
  else if 'A' ≤ c && c ≤ 'F' then pure (c.toNat - 'A'.toNat + 10)
  else throw "bad \\u escape"

partial def strBody (acc : List Char) : P String := do
  match ← next with
  | '"' => return String.mk acc.reverse
  | '\\' =>
    match ← next with
    | '"' => strBody ('"' :: acc)
    | '\\' => strBody ('\\' :: acc)
    | '/' => strBody ('/' :: acc)
    | 'n' => strBody ('\n' :: acc)
    | 't' => strBody ('\t' :: acc)
    | 'r' => strBody ('\r' :: acc)
    | 'b' => strBody (Char.ofNat 8 :: acc)
    | 'f' => strBody (Char.ofNat 12 :: acc)
    | 'u' =>
      let a ← hex (← next); let b ← hex (← next); let c ← hex (← next); let d ← hex (← next)
      strBody (Char.ofNat (((a * 16 + b) * 16 + c) * 16 + d) :: acc)
    | _ => throw "bad escape"
  | c => strBody (c :: acc)

partial def digits (n : Nat) : P Nat := do
  match ← peek with
  | some c => if '0' ≤ c && c ≤ '9' then do let _ ← next; digits (n * 10 + (c.toNat - '0'.toNat)) else return n
  | none => return n

mutual
partial def value : P J := do
  ws
  match ← peek with
  | some '{' => let _ ← next; ws; if (← peek) == some '}' then (do let _ ← next; return .obj []) else members []
  | some '[' => let _ ← next; ws; if (← peek) == some ']' then (do let _ ← next; return .arr []) else elems []
  | some '"' => let _ ← next; return .str (← strBody [])
  | some 't' => word "true"; return .bool true
  | some 'f' => word "false"; return .bool false
  | some 'n' => word "null"; return .null
  | some c =>
    if '0' ≤ c && c ≤ '9' then do
      let n ← digits 0
      if (← peek) == some '.' then          -- a fraction (time.time()): keep the whole seconds
        let _ ← next
        let _ ← digits 0
      return .num n
    else throw s!"unexpected {c}"
  | none => throw "unexpected end"

partial def members (acc : List (String × J)) : P J := do
  ws; expect '"'
  let k ← strBody []
  ws; expect ':'
  let v ← value
  ws
  match ← next with
  | ',' => members ((k, v) :: acc)
  | '}' => return .obj ((k, v) :: acc).reverse
  | _ => throw "expected , or }"

partial def elems (acc : List J) : P J := do
  let v ← value
  ws
  match ← next with
  | ',' => elems (v :: acc)
  | ']' => return .arr (v :: acc).reverse
  | _ => throw "expected , or ]"
end

def parse (s : String) : Except String J := do
  let (v, rest) ← (do let v ← value; ws; return v).run s.toList
  if rest.isEmpty then return v else throw "trailing input"

def esc (s : String) : String :=
  s.foldl (fun acc c =>
    if c == '"' then acc ++ "\\\"" else if c == '\\' then acc ++ "\\\\"
    else if c.toNat < 32 then
      let d := (Nat.toDigits 16 c.toNat).asString
      acc ++ "\\u" ++ String.mk (List.replicate (4 - d.length) '0') ++ d
    else acc.push c) ""

partial def render : J → String
  | .null => "null"
  | .bool b => if b then "true" else "false"
  | .num n => toString n
  | .str s => "\"" ++ esc s ++ "\""
  | .arr xs => "[" ++ ",".intercalate (xs.map render) ++ "]"
  | .obj kvs => "{" ++ ",".intercalate (kvs.map fun (k, v) => "\"" ++ esc k ++ "\":" ++ render v) ++ "}"

def get? (j : J) (k : String) : Option J :=
  match j with
  | .obj kvs => kvs.lookup k
  | _ => none

end J

open Zenos

namespace ZenosDecide

def field (j : J) (k : String) : Except String J :=
  match j.get? k with
  | some v => pure v
  | none => throw s!"missing {k}"

def getS (j : J) (k : String) : Except String String := do
  match ← field j k with | .str s => pure s | _ => throw s!"{k}: not a string"
def getN (j : J) (k : String) : Except String Nat := do
  match ← field j k with | .num n => pure n | _ => throw s!"{k}: not a number"
def getB (j : J) (k : String) : Except String Bool := do
  match ← field j k with | .bool b => pure b | _ => throw s!"{k}: not a boolean"
def getArr (j : J) (k : String) : Except String (List J) := do
  match ← field j k with | .arr xs => pure xs | _ => throw s!"{k}: not an array"
def getSs (j : J) (k : String) : Except String (List String) := do
  (← getArr j k).mapM fun | .str s => pure s | _ => throw s!"{k}: not a list of strings"

def approval (j : J) : Except String Approval := do
  return { approver := ← getS j "approver", sigOk := ← getB j "sig_ok" }

def approvalsOf (j : J) (k : String) : Except String (List Approval) := do
  (← getArr j k).mapM approval

def grant (j : J) : Except String Grant := do
  let kind ← match j.get? "kind" with
    | none | some .null => pure none
    | some (.str k) => pure (some k)
    | some _ => throw "kind: not a string"
  return { requester := ← getS j "requester", holder := ← getS j "holder", fileHash := ← getS j "file_hash",
           level := ← getN j "level", kind, expires := ← getN j "expires", digestOk := ← getB j "digest_ok",
           approvals := ← approvalsOf j "approvals" }

def status : String → Except String Status
  | "pending" => pure .pending
  | "declined" => pure .declined
  | "approved" => pure .approved
  | s => throw s!"unknown status {s}"

def request (j : J) : Except String Request := do
  return { id := ← getS j "id", requester := ← getS j "requester", level := ← getN j "level",
           required := ← getN j "required", status := ← status (← getS j "status"),
           approvals := ← approvalsOf j "approvals" }

def answer (j : J) : Except String J := do
  match ← getS j "op" with
  | "open" =>
    let g ← match j.get? "grant" with
      | none | some .null => pure none
      | some v => some <$> grant v
    let o : OpenReq := { user := ← getS j "user", clearance := ← getN j "clearance", level := ← getN j "level",
                         fileHash := ← getS j "file_hash", now := ← getN j "now", halted := ← getB j "halted",
                         roster := ← getSs j "roster", grant := g }
    return match decideOpen o with
      | .byClearance => .obj [("allow", .bool true), ("by", .str "clearance"), ("reason", .null)]
      | .byGrant => .obj [("allow", .bool true), ("by", .str "grant"), ("reason", .null)]
      | .refuse r => .obj [("allow", .bool false), ("by", .null), ("reason", .str r)]
  | "approve" =>
    let act ← match ← getS j "act" with
      | "approve" => pure Act.approve
      | "decline" => pure Act.decline
      | a => throw s!"unknown act {a}"
    let a : ApproveReq := { request := ← request (← field j "request"), roster := ← getSs j "roster",
                            who := ← getS j "who", act, sigOk := ← getB j "sig_ok", codeOk := ← getB j "code_ok" }
    return match decideApprove a with
      | .added => .obj [("result", .str "added"), ("reason", .null)]
      | .declined => .obj [("result", .str "declined"), ("reason", .null)]
      | .refused r => .obj [("result", .str "refused"), ("reason", .str r)]
  | "release" =>
    let r ← request (← field j "request")
    let roster ← getSs j "roster"
    return .obj [("release", .bool (decideRelease (← getB j "halted") r roster)),
                 ("approvers", .arr ((approvers roster r.requester r.approvals).map .str))]
  | "required" =>
    return .obj [("required", .num (required (← getN j "level")))]
  | "release-required" =>
    return .obj [("required", .num (releaseRequired (← getSs j "roster") (← getS j "requester") (← getN j "level")))]
  | op => throw s!"unknown op {op}"

end ZenosDecide

open ZenosDecide in
def main : IO UInt32 := do
  let input ← (← IO.getStdin).readToEnd
  match (J.parse input).bind answer with
  | .ok j => IO.println j.render; return 0
  | .error e => IO.println (J.render (.obj [("error", .str e)])); return 2
