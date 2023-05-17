## Change Log

### v0.3.4, 2023-05-17

 - Upgrade dependencies.

### v0.3.3, 2021-11-24

 - Upgrade to PyMuPDF 1.19.2, and use its new `is_unicolor` attribute to
   identify redaction boxes.
 - If all redactions for a document are dates, consider them good redactions.

### v0.3.2, 2021-11-12

Makes xray installable. You can now do this:

```
xray path/to/some/file.pdf
```

And it'll return JSON like usual.


### v0.3.1, 2021-11-12

Adds support for URLs. This now does what you'd expect:

```
% python -m xray https://example.com/some-path.pdf
```


### v0.3.0, 2021-11-12

Reduces false positives by inspecting the pixels of every possible bad
redaction. This comes at a small performance cost, but will eliminate many of
the false positives we've been dealing with. This approach was selected because
understanding the ins and outs of PDFs and trying to *guess* the color of their
x-y locations is impossible in Python.

Adds support for bad redactions under rectangles that are not pure black.
Previously, we ignored all non-black rectangles, which meant that redactions
that weren't black wouldn't be caught. With our new pixel-inspection approach,
we can include these without them causing issues.


### v0.2.4, 2021-10-28

Upgrades to PyMuPDF 1.19.1, which simplifies our handling of colorspaces. We
no longer need to check for various colorspaces (simplifying our code), and we
are now able to compare rectangle color to text color more accurately, since
they are now normalized by PyMuPDF.

Previously we'd have a false positive if a rectangle and text were the same
color but in different colorspaces. For example, 0.0 in grayscale is the same
as (0.0, 0.0, 0.0) in RGB, but we couldn't compare those easily before.


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
