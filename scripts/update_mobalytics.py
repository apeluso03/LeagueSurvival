"""Download Mobalytics' widget script and save a fixed copy for the app.

    python scripts/update_mobalytics.py

Why a copy: their bundle asks Mobalytics for only the first 400 items of its item catalog (two
pages of 200), but the catalog has grown past that (about 950 items, mostly mode-specific copies),
so normal Summoner's Rift items are missing and the Items section draws no icons. This fetches the
latest bundle, asks for PAGES pages instead, renames the leftover "Mythic & Core Items" label
(Mythic items left the game in 2024), and writes it to frontend/public/vendor/ with the license
notice. Run it again whenever Mobalytics updates their widget.
"""

import sys
import urllib.request
from pathlib import Path

SOURCE = "https://cdn.jsdelivr.net/gh/mobalyticshq/mobalytics-widgets/build/mobalytics-widgets.js"
OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "vendor" / "mobalytics-widgets.js"
PAGES = 8  # 1,600 items of room

BS = "\\"  # the bundle keeps its GraphQL query in a JS string: newlines are a backslash + n
NL = BS + "n"

HEADER = """/*!
 * Mobalytics Widgets - https://github.com/mobalyticshq/mobalytics-widgets
 * MIT License (as stated in the project's README; the repository has no separate LICENSE file).
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software
 * and associated documentation files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use, copy, modify, merge, publish,
 * distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions: The above copyright
 * notice and this permission notice shall be included in all copies or substantial portions of
 * the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
 * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 * LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
 * OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 *
 * Modified by Hardcore Draft (scripts/update_mobalytics.py): loads %d pages of the item catalog
 * instead of 2, and says "Core Items" instead of "Mythic & Core Items".
 */
"""


def chunk(i: int) -> str:
    return (
        f"{NL}    itemsChunk{i}: queryGameItemsV1Contents(top: 200, skip: {(i - 1) * 200}) {{{NL}"
        f"      flatData {{{NL}        ...LolGameItemFragment{NL}      }}{NL}    }}"
    )


def patch(src: str, pages: int = PAGES) -> str:
    old_query = chunk(2)
    if src.count(old_query) != 1:
        raise SystemExit("Couldn't find the item query: Mobalytics changed their bundle. Check it by hand.")
    src = src.replace(old_query, "".join(chunk(i) for i in range(2, pages + 1)), 1)
    old_merge = "[].concat(q.itemsChunk1||[],q.itemsChunk2||[])"
    if src.count(old_merge) != 1:
        raise SystemExit("Couldn't find where items are merged: Mobalytics changed their bundle.")
    src = src.replace(old_merge, "[].concat(" + ",".join(f"q.itemsChunk{i}||[]" for i in range(1, pages + 1)) + ")", 1)
    return src.replace('"Mythic & Core Items"', '"Core Items"')


def main() -> int:
    with urllib.request.urlopen(SOURCE, timeout=30) as res:  # noqa: S310 - fixed https URL
        src = res.read().decode("utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HEADER % PAGES + patch(src), encoding="utf-8", newline="")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {PAGES} item pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
