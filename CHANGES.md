## Current


### v0.2.4, 2021-10-28

Upgrades to PyMuPDF 1.19.1, which simplifies our handling of colorspaces. We
no longer need to check for various colorspaces (simplifying our code), and we
are now able to compare rectangle color to text color more accurately, since
they are now normalized by PyMuPDF.

Previously we'd have a false positive if a rectangle and text were the same
color but in different colorspaces. For example, 0.0 in grayscale is the same
as (0.0, 0.0, 0.0) in RGB, but we couldn't compare those easily before.


## Past

### v0.2.3, 2021-10-28

Adds support for boxes without fill, so they don't register as false positives.


### v0.2.2, 2021-10-21

Fixes [issue 38](https://github.com/freelawproject/x-ray/issues/38) by adding
analysis for the draw order of text and rectangles. This ensures that
rectangles under text are not detected as bad redactions.

### v0.2.1, 2021-10-21

Failed release.


### v0.2.0, 2021-09-14

Add support for bytes as input, making it easier to check files that are not
on disk. This is common when downloading a file, for example.
