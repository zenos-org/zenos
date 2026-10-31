# Office compatibility check

Public Word, Excel and PowerPoint files published by Japanese ministries and municipalities (forms, statistics
tables), opened and saved again, and compared with the originals. `corpus.json` lists each file with the page it
was published on, its address and its SHA-256; the files are not copied into this repository. Only public forms
and tables are used, never confidential or personal data.

    python3 tests/office/fetch.py /tmp/office-corpus
    (cd tests/office/engines && npm ci && node build.mjs)      # the ZENOS apps' own open/save code
    python3 tests/office/compat.py /tmp/office-corpus /tmp/office-results

What is compared, and how, is described at the top of `compat.py`. Pages are drawn by LibreOffice for both files;
Microsoft Office is not used, so "looks alike" means alike as LibreOffice draws them.
