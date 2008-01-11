# -*- coding: utf-8 -*-
"""
    Sphinx - Python documentation toolchain
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: 2007-2008 by Georg Brandl.
    :license: BSD.
"""

import sys

if __name__ == '__main__':
    from sphinx import main
    try:
        sys.exit(main(sys.argv))
    except Exception:
        import traceback
        traceback.print_exc()
        import pdb
        pdb.post_mortem(sys.exc_traceback)
