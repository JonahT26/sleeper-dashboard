# Bundled motion scripts

Copied from npm and published in the page's `js/` folder on every build (`dashboard/build.py`), so the page loads
nothing new from outside (docs/UI_GUIDE.md "Motion"). Versions are pinned in `dashboard/build.py` (`MOTION_SCRIPTS`); tests check each
file's version matches.

| File | Package | License |
|---|---|---|
| `gsap.min.js`, `ScrollTrigger.min.js`, `Flip.min.js`, `SplitText.min.js` | `gsap@3.15.0` (`dist/`) | GSAP Standard "no charge" license, https://gsap.com/standard-license (notice kept in each file) |
| `lenis.min.js` | `lenis@1.3.26` (`dist/`) | MIT, `LICENSE-lenis.txt` |

Two edits to `lenis.min.js` only: a one-line license header added at the top, and the source-map comment removed (the
map isn't bundled, so browsers would ask for a file that doesn't exist).

Updating: `npm pack gsap@X lenis@Y` in a scratch folder, copy the same `dist/` files here, repeat the two Lenis edits,
and change the versions in `build.py`.
