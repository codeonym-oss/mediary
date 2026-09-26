"""Sphinx configuration: MyST pages, autodoc API reference, Shibuya theme."""

from importlib.metadata import version as _version

project = "mediary"
author = "codeonym-oss"
copyright = "codeonym-oss — MIT License"
release = _version("mediary")
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
]
exclude_patterns = ["_build"]

# Pages: Markdown, with ```{directive} blocks and `#heading` anchors for links.
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

# API reference: Google-style docstrings, public API only (each module's __all__), in source order.
autodoc_default_options = {"members": True, "member-order": "bysource"}
autodoc_typehints = "signature"
autodoc_preserve_defaults = True
autoclass_content = "class"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_rtype = False
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

html_theme = "shibuya"
html_title = "mediary"
html_baseurl = "https://docs.codeonym.work/projects/mediary/"
html_context = {
    "source_type": "github",
    "source_user": "codeonym-oss",
    "source_repo": "mediary",
    "source_version": "main",
    "source_docs_path": "/docs/",
}
html_theme_options = {
    "accent_color": "indigo",
    "github_url": "https://github.com/codeonym-oss/mediary",
    "nav_links": [
        {"title": "Guide", "url": "guide/getting-started"},
        {"title": "API reference", "url": "reference/mediary"},
        {"title": "PyPI", "url": "https://pypi.org/project/mediary/", "external": True},
    ],
}
