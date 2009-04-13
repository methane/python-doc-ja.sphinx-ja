# -*- coding: utf-8 -*-
"""
    sphinx.ext.autosummary.generate
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Usable as a library or script to generate automatic RST source files for
    items referred to in autosummary:: directives.

    Each generated RST file contains a single auto*:: directive which
    extracts the docstring of the referred item.

    Example Makefile rule::

       generate:
               sphinx-autogen source/*.rst source/generated

    :copyright: Copyright 2007-2009 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
import os
import re
import sys
import optparse
import inspect
import pydoc

from jinja2 import Environment, PackageLoader

from sphinx.ext.autosummary import import_by_name, get_documenter
from sphinx.util import ensuredir


def main(argv=sys.argv):
    usage = """%prog [OPTIONS] SOURCEFILE ..."""
    p = optparse.OptionParser(usage.strip())
    p.add_option("-o", "--output-dir", action="store", type="string",
                 dest="output_dir", default=None,
                 help="Directory to place all output in")
    p.add_option("-s", "--suffix", action="store", type="string",
                 dest="suffix", default="rst",
                 help="Default suffix for files (default: %default)")
    options, args = p.parse_args(argv[1:])

    if len(args) < 1:
        p.error('no input files given')

    generate_autosummary_docs(args, options.output_dir,
                              "." + options.suffix)


def _simple_info(msg):
    print msg

def _simple_warn(msg):
    print >> sys.stderr, 'WARNING: ' + msg

# -- Generating output ---------------------------------------------------------

# create our own templating environment, for module template only
env = Environment(loader=PackageLoader('sphinx.ext.autosummary', 'templates'))

def generate_autosummary_docs(sources, output_dir=None, suffix='.rst',
                              warn=_simple_warn, info=_simple_info,
                              base_path=None):

    info('[autosummary] generating autosummary for: %s' %
         ', '.join(sorted(sources)))

    if output_dir:
        info('[autosummary] writing to %s' % output_dir)

    if base_path is not None:
        sources = [os.path.join(base_path, filename) for filename in sources]

    # read
    items = find_autosummary_in_files(sources)

    # remove possible duplicates
    items = dict([(item, True) for item in items]).keys()

    # write
    for name, path in sorted(items):
        if path is None:
            # The corresponding autosummary:: directive did not have
            # a :toctree: option
            continue

        path = output_dir or os.path.abspath(path)
        ensuredir(path)

        try:
            obj, name = import_by_name(name)
        except ImportError, e:
            warn('[autosummary] failed to import %r: %s' % (name, e))
            continue

        fn = os.path.join(path, name + suffix)

        # skip it if it exists
        if os.path.isfile(fn):
            continue

        f = open(fn, 'w')

        try:
            if inspect.ismodule(obj):
                tmpl = env.get_template('module')

                def get_items(mod, typ):
                    return [
                        getattr(mod, name).__name__ for name in dir(mod)
                        if get_documenter(getattr(mod, name)).objtype == typ
                    ]

                functions = get_items(obj, 'function')
                classes = get_items(obj, 'class')
                exceptions = get_items(obj, 'exception')

                rendered = tmpl.render(name=name,
                                       underline='='*len(name),
                                       functions=functions,
                                       classes=classes,
                                       exceptions=exceptions,
                                       len_functions=len(functions),
                                       len_classes=len(classes),
                                       len_exceptions=len(exceptions))
                f.write(rendered)
            else:
                f.write('%s\n%s\n\n' % (name, '='*len(name)))

                doc = get_documenter(obj)
                if doc.objtype in ('method', 'attribute'):
                    f.write(format_classmember(name, 'auto%s' % doc.objtype))
                else:
                    f.write(format_modulemember(name, 'auto%s' % doc.objtype))
        finally:
            f.close()


def format_modulemember(name, directive):
    parts = name.split('.')
    mod, name = '.'.join(parts[:-1]), parts[-1]
    return '.. currentmodule:: %s\n\n.. %s:: %s\n' % (mod, directive, name)


def format_classmember(name, directive):
    parts = name.split('.')
    mod, name = '.'.join(parts[:-2]), '.'.join(parts[-2:])
    return '.. currentmodule:: %s\n\n.. %s:: %s\n' % (mod, directive, name)


# -- Finding documented entries in files ---------------------------------------

def find_autosummary_in_files(filenames):
    """
    Find out what items are documented in source/*.rst.
    See `find_autosummary_in_lines`.
    """
    documented = []
    for filename in filenames:
        f = open(filename, 'r')
        lines = f.read().splitlines()
        documented.extend(find_autosummary_in_lines(lines, filename=filename))
        f.close()
    return documented

def find_autosummary_in_docstring(name, module=None, filename=None):
    """
    Find out what items are documented in the given object's docstring.
    See `find_autosummary_in_lines`.
    """
    try:
        obj, real_name = import_by_name(name)
        lines = pydoc.getdoc(obj).splitlines()
        return find_autosummary_in_lines(lines, module=name, filename=filename)
    except AttributeError:
        pass
    except ImportError, e:
        print "Failed to import '%s': %s" % (name, e)
    return []

def find_autosummary_in_lines(lines, module=None, filename=None):
    """
    Find out what items appear in autosummary:: directives in the given lines.

    Returns a list of (name, toctree) where *name* is a name of an object
    and *toctree* the :toctree: path of the corresponding autosummary directive
    (relative to the root of the file name). *toctree* is ``None`` if
    the directive does not have the :toctree: option set.
    """
    autosummary_re = re.compile(r'^\.\.\s+autosummary::\s*')
    automodule_re = re.compile(r'.. automodule::\s*([A-Za-z0-9_.]+)\s*$')
    module_re = re.compile(r'^\.\.\s+(current)?module::\s*([a-zA-Z0-9_.]+)\s*$')
    autosummary_item_re = re.compile(r'^\s+([_a-zA-Z][a-zA-Z0-9_.]*)\s*.*?')
    toctree_arg_re = re.compile(r'^\s+:toctree:\s*(.*?)\s*$')

    documented = []

    toctree = None
    current_module = module
    in_autosummary = False

    for line in lines:
        if in_autosummary:
            m = toctree_arg_re.match(line)
            if m:
                toctree = m.group(1)
                if filename:
                    toctree = os.path.join(os.path.dirname(filename),
                                           toctree)
                continue

            if line.strip().startswith(':'):
                continue # skip options

            m = autosummary_item_re.match(line)
            if m:
                name = m.group(1).strip()
                if current_module and \
                       not name.startswith(current_module + '.'):
                    name = "%s.%s" % (current_module, name)
                documented.append((name, toctree))
                continue

            if not line.strip():
                continue

            in_autosummary = False

        m = autosummary_re.match(line)
        if m:
            in_autosummary = True
            toctree = None
            continue

        m = automodule_re.search(line)
        if m:
            current_module = m.group(1).strip()
            # recurse into the automodule docstring
            documented.extend(find_autosummary_in_docstring(
                current_module, filename=filename))
            continue

        m = module_re.match(line)
        if m:
            current_module = m.group(2)
            continue

    return documented


if __name__ == '__main__':
    main()
