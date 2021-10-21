## Current


### v0.2.2, 2021-10-21

Fixes [issue 38](https://github.com/freelawproject/x-ray/issues/38) by adding
analysis for the draw order of text and rectangles. This ensures that
rectangles under text are not detected as bad redactions.

### v0.2.1, 2021-10-21

Failed release.



## Past

### v0.2.0, 2021-09-14

Add support for bytes as input, making it easier to check files that are not
on disk. This is common when downloading a file, for example.
