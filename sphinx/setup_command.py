# -*- coding: utf-8 -*-
"""
    sphinx.setup_command
    ~~~~~~~~~~~~~~~~~~~~

    Setuptools/distutils commands to assist the building of sphinx
    documentation.

    :author: Sebastian Wiesner
    :contact: basti.wiesner@gmx.net
    :copyright: Copyright 2007-2010 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import sys
import os
from StringIO import StringIO
from distutils.cmd import Command

from sphinx.application import Sphinx
from sphinx.util.console import darkred, nocolor, color_terminal


class BuildDoc(Command):
    """
    Distutils command to build Sphinx documentation.

    The Sphinx build can then be triggered from distutils, and some Sphinx
    options can be set in ``setup.py`` or ``setup.cfg`` instead of Sphinx own
    configuration file.

    For instance, from `setup.py`::

       # this is only necessary when not using setuptools/distribute
       from sphinx.setup_command import BuildDoc
       cmdclass = {'build_sphinx': BuildDoc}

       name = 'My project'
       version = '1.2'
       release = '1.2.0'
       setup(
           name=name,
           author='Bernard Montgomery',
           version=release,
           cmdclass=cmdclass,
           # these are optional and override conf.py settings
           command_options={
               'build_sphinx': {
                   'project': ('setup.py', name),
                   'version': ('setup.py', version),
                   'release': ('setup.py', release)}},
       )

    Or add this section in ``setup.cfg``::

       [build_sphinx]
       project = 'My project'
       version = 1.2
       release = 1.2.0
    """

    description = 'Build Sphinx documentation'
    user_options = [
        ('fresh-env', 'E', 'discard saved environment'),
        ('all-files', 'a', 'build all files'),
        ('source-dir=', 's', 'Source directory'),
        ('build-dir=', None, 'Build directory'),
        ('config-dir=', 'c', 'Location of the configuration directory'),
        ('builder=', 'b', 'The builder to use. Defaults to "html"'),
        ('project=', None, 'The documented project\'s name'),
        ('version=', None, 'The short X.Y version'),
        ('release=', None, 'The full version, including alpha/beta/rc tags'),
        ('today=', None, 'How to format the current date, used as the '
         'replacement for |today|'),
        ('link-index', 'i', 'Link index.html to the master doc'),
    ]
    boolean_options = ['fresh-env', 'all-files', 'link-index']


    def initialize_options(self):
        self.fresh_env = self.all_files = False
        self.source_dir = self.build_dir = None
        self.builder = 'html'
        self.version = ''
        self.release = ''
        self.today = ''
        self.config_dir = None
        self.link_index = False

    def _guess_source_dir(self):
        for guess in ('doc', 'docs'):
            if not os.path.isdir(guess):
                continue
            for root, dirnames, filenames in os.walk(guess):
                if 'conf.py' in filenames:
                    return root
        return None

    def finalize_options(self):
        if self.source_dir is None:
            self.source_dir = self._guess_source_dir()
            self.announce('Using source directory %s' % self.source_dir)
        self.ensure_dirname('source_dir')
        if self.source_dir is None:
            self.source_dir = os.curdir
        self.source_dir = os.path.abspath(self.source_dir)
        if self.config_dir is None:
            self.config_dir = self.source_dir

        if self.build_dir is None:
            build = self.get_finalized_command('build')
            self.build_dir = os.path.join(build.build_base, 'sphinx')
            self.mkpath(self.build_dir)
        self.doctree_dir = os.path.join(self.build_dir, 'doctrees')
        self.mkpath(self.doctree_dir)
        self.builder_target_dir = os.path.join(self.build_dir, self.builder)
        self.mkpath(self.builder_target_dir)

    def run(self):
        if not color_terminal():
            # Windows' poor cmd box doesn't understand ANSI sequences
            nocolor()
        if not self.verbose:
            status_stream = StringIO()
        else:
            status_stream = sys.stdout
        confoverrides = {}
        if self.version:
             confoverrides['version'] = self.version
        if self.release:
             confoverrides['release'] = self.release
        if self.today:
             confoverrides['today'] = self.today
        app = Sphinx(self.source_dir, self.config_dir,
                     self.builder_target_dir, self.doctree_dir,
                     self.builder, confoverrides, status_stream,
                     freshenv=self.fresh_env)

        try:
            if self.all_files:
                app.builder.build_all()
            else:
                app.builder.build_update()
        except Exception, err:
            from docutils.utils import SystemMessage
            if isinstance(err, SystemMessage):
                print >>sys.stderr, darkred('reST markup error:')
                print >>sys.stderr, err.args[0].encode('ascii',
                                                       'backslashreplace')
            else:
                raise

        if self.link_index:
            src = app.config.master_doc + app.builder.out_suffix
            dst = app.builder.get_outfilename('index')
            os.symlink(src, dst)
