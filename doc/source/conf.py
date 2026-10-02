# Configuration file for the Sphinx documentation builder.
#
# The look (Shibuya theme, dark by default, colours from this app's palette, rules
# for the in-app help page) comes from einstudio.sphinxext; this file only holds what
# is specific to this manual.
#
# Build the HTML from the app folder with:
#
#     uv run --group docs python -m sphinx doc/source doc/build/html
#
# Formulas use imgmath (rendered to images at build time, needs LaTeX), so the manual
# also works offline inside the app. Without LaTeX, avoid ``.. math::`` or switch to
# 'sphinx.ext.mathjax', which needs an internet connection to render formulas.

project = 'Twilite'
author = 'Felipe Velasquez'
copyright = '2026, Swisstrace'

extensions = [
    'einstudio.sphinxext',
    'sphinx.ext.imgmath',
    'sphinx.ext.autosectionlabel',
]

templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'
language = 'en'

html_title = project
html_static_path = ['_static']

