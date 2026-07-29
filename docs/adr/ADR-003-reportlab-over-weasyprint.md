# ADR-003: ReportLab over WeasyPrint for exception memos

- **Date:** 2026-07-29
- **Status:** Accepted
- **Supersedes:** the HTML-fallback decision recorded in the project retrospective

## Context

Exception memos were rendered by templating HTML with Jinja2 and converting it
with WeasyPrint. WeasyPrint depends on native GTK/Pango/Cairo libraries that are
not present on a stock Windows host, so `import weasyprint` raised on every call.

The generator caught that exception and wrote the rendered HTML instead. The
consequences were quietly bad:

- **No memo was ever a PDF on Windows.** Every flagged or rejected application
  produced an `.html` file while the database column, the API response and the
  dashboard all called it a memo path, implying a PDF.
- **Each failure printed a multi-line installation notice** to the server log —
  eight lines per packet, so a 30-packet run emitted well over a hundred lines
  of noise around the real output.
- **The failure was invisible to callers.** The fallback returned a path and a
  200 response, so nothing downstream could tell a real PDF from a fallback.

PacketWise already depends on ReportLab transitively through the document
generation path, and the sister project realitydb-docs uses it to produce W-2s
and bank statements — so the library is already proven in this codebase.

## Decision

Render memos directly with **ReportLab's platypus layer**. Remove WeasyPrint and
Jinja2 from the dependency set, and remove the HTML fallback entirely.

`MemoGenerator.generate()` keeps its signature and still returns a path, but the
path is now always a real PDF.

## Consequences

**Positive**

- Memos are genuine PDFs on every platform, with no native dependencies
- No silent degradation: there is no fallback to mask a rendering failure
- The per-memo installation warning is gone from the logs
- Two dependencies removed (`weasyprint`, `jinja2`); one added (`reportlab`,
  which was already required by the sister project)
- Page furniture ReportLab does well — repeating footers, page numbers,
  `KeepTogether` blocks — is now available

**Negative**

- Layout is expressed as Python flowables rather than CSS, so restyling a memo
  means editing code rather than a template
- The HTML template's exact look was not reproduced pixel-for-pixel; the memo was
  rebuilt to the same structure (header, decision, metrics, violations, document
  inventory, notes, footer)
- A rendering failure is now a hard error rather than a degraded artifact. This
  is intentional, but it means a malformed memo can fail a request that
  previously returned 200

## Verification

A memo generated with three violations and three documents produced a 2-page
PDF, 4.5KB, containing every section heading, the decision, all three rule codes
and the page footer. Rendered and inspected visually.
