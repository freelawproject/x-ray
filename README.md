![Image of REDACTED STAMP](https://raw.githubusercontent.com/freelawproject/x-ray/main/redacted.png)

x-ray is a Python library for finding bad redactions in PDF documents.

## Why?

At Free Law Project, we collect millions of PDFs. An ongoing problem
is that people fail to properly redact things. Instead of doing it the right
way, they just draw a black rectangle or a black highlight on top of black
text and call it a day. Well, when that happens you just select the text under
the rectangle, and you can read it again. Not great.

After witnessing this problem for years, we decided it would be good to figure
out how common it is, so, with some help, we built this simple tool. You give
the tool the path to a PDF. It tells you if it has worthless redactions in it.


## What next?

Right now, `x-ray` works pretty well and we are using it to analyze documents
in our collections. It could be better though. Bad redactions take many forms.
See the issues tab for other examples we don't yet support. We'd love your
help solving some of tougher cases.


## Installation

With poetry, do:

```text
poetry add x-ray
```

With pip, that'd be:
```text
pip install x-ray
```

## Usage

You can easily use this on the command line. Once installed, just:

```bash
% xray path/to/your/file.pdf
{
  "1": [
    {
      "bbox": [
        58.550079345703125,
        72.19873046875,
        75.65007781982422,
        739.3987426757812
      ],
      "text": "The Ring travels by way of Cirith Ungol"
    }
  ]
}
```

Or if you have hte file on a server somewhere, give it a URL. If it starts
with `https://`, it will be interpreted as a PDF to download:

```bash
% xray https://free.law/pdf/congressional-testimony-michael-lissner-free-law-project-hearing-on-ethics-and-transparency-2021-10-26.pdf
{}
```

A fun trick you can now do is to make a file with one URL per line, call it `urls.txt`. Then you can run this to check each URL:

```bash
xargs -n 1 xray  < urls.txt
```

However you run `xray` on the command line, you'll get JSON as output. When you have that, you can use it with tools like [`jq`][jq]. The format is as follows:

 - It's a dict.
 - The keys are page numbers.
 - Each page number maps to a list of dicts.
 - Each of those dicts maps to two keys.
 - The first key is `bbox`. This is a four-tuple that indicates the x,y positions of the upper left corner and then lower right corners of the bad redaction.
 - The second key is `text`. This is the text under the bad rectangle.

Simple enough.

You can also use it as a Python module, if you prefer the long-form:

```
% pathon -m xray some-file.pdf
```

But that's not as easy to remember.

If you want a bit more, you can, of course, use `xray` in Python:

```python
from pprint import pprint
import xray
bad_redactions = xray.inspect("some/path/to/your/file.pdf")  # Pathlib works too
pprint(bad_redactions)
{1: [{'bbox': (58.550079345703125,
               72.19873046875,
               75.65007781982422,
               739.3987426757812),
      'text': 'Aragorn is the one true king.'}]}
```

The output is the same as above, except it's a Python object, not a JSON object.

If you already have the file contents as a `bytes` object, that'll work too:

```python
some_bytes = requests.get("https://lotr-secrets.com/some-doc.pdf").content
bad_redactions = xray.inspect(some_bytes)
```

Note that because the `inspect` method uses the same signature no matter what,
the type of the object you give it is essential:

Input | `xray`'s Assumption
-- | --
`str` or Pathlib `Path` | local file
`str` that starts with `https://` | URL to download
`bytes` | PDF in memory

This means that if you provide the filename on disk as a bytes object instead
of a `str`, it's not going to work. This will fail:

```python
xray.inspect(b"some-file-path.pdf")
```

That's pretty much it. There are no configuration files or other variables to
learn. You give it a file name. If there is a bad redaction in it, you'll soon
find out.


## How it works

Under the covers, `xray` uses the high-performant [PyMuPDF project][mu] to parse PDFs. It has been a wonderful project to work with.

You can read the source to see how it works, but the general idea is to:

1. Find rectangles in a PDF.

2. Find letters in the same location

3. Render the rectangle

4. Inspect the rectangle to see if it's all one color

The PDF format is a big and complicated one, so it's difficult to do all this l and perfectly. We do our best, but there's always more to do to make it better. Donations and sponsored work help.

## Contributions

Please see the issues list on Github for things we need, or start a conversation if you have questions. Before you do your first contribution, we'll need a signed contributor license agreement. See the template in the repo.


## Deployment

Releases happen automatically via Github Actions. To trigger an automated build:

1. Update the version in pyproject.toml

2. Tag the commit with something like "v0.0.0".


If you wish to create a new version manually, the process is:

1. Update version info in `pyproject.toml`

2. Configure your Pypi credentials [with Poetry][creds]

3. Build and publish the version:

```sh
poetry publish --build
```



## License

This repository is available under the permissive BSD license, making it easy and safe to incorporate in your own libraries.

Pull and feature requests welcome. Online editing in GitHub is possible (and easy!).

[jq]: https://stedolan.github.io/jq/
[mu]: https://pymupdf.readthedocs.io/
[asc]: https://en.wikipedia.org/wiki/Ascender_(typography)
[creds]: https://python-poetry.org/docs/repositories/#configuring-credentials
