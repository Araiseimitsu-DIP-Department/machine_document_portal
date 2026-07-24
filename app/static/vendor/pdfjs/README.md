# PDF.js

This directory contains the browser build of PDF.js `5.7.284` from the
official `pdfjs-dist` npm package.

- Source: https://github.com/mozilla/pdf.js/releases/tag/v5.7.284
- Downloaded package SHA-512:
  `87811D61073398685B3A5A9CDCF3D9C317AF9FB0297563DBA2F02E597381FC38C8CA28129F07F2DA8CDEEDCEA645C4ABF5780BA7778DDC478BE03CB24933CC17`
- License: Apache License 2.0; see `LICENSE`

The modern and legacy modules and workers, CMaps, standard fonts, and WASM
decoders are stored locally so the drawing viewer does not depend on a CDN or
internet access. The viewer selects the legacy build for Safari and Apple
mobile devices.
