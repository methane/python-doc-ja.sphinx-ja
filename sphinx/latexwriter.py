# -*- coding: utf-8 -*-
"""
    sphinx.latexwriter
    ~~~~~~~~~~~~~~~~~~

    Custom docutils writer for LaTeX.

    Much of this code is adapted from Dave Kuhlman's "docpy" writer from his
    docutils sandbox.

    :copyright: 2007 by Georg Brandl, Dave Kuhlman.
    :license: Python license.
"""

import re
import time
import string

from docutils import frontend, nodes, languages, writers, utils

from . import addnodes
from . import highlighting


HEADER = r'''%% Generated by Sphinx.
\documentclass[%(papersize)s,%(pointsize)s]{%(docclass)s}
\usepackage[colorlinks]{hyperref}
\title{%(title)s}
\date{%(date)s}
\release{%(release)s}
\author{Guido van Rossum\\    %% XXX
  Fred L. Drake, Jr., editor} %% XXX
\authoraddress{
  \strong{Python Software Foundation}\\
  Email: \email{docs@python.org}
}
\makeindex

'''

FOOTER = r'''
\printindex
\end{document}
'''


class LaTeXWriter(writers.Writer):

    supported = ('sphinxlatex',)

    settings_spec = ('No options here.', '', ())
    settings_defaults = {}

    output = None

    def __init__(self, config, buildername):
        writers.Writer.__init__(self)
        self.config = config

    def translate(self):
        try:
            visitor = LaTeXTranslator(self.document, self.config)
            self.document.walkabout(visitor)
            self.output = visitor.astext()
        except:
            import pdb, sys, traceback
            traceback.print_exc()
            tb = sys.exc_info()[2]
            pdb.post_mortem(tb)


# Helper classes

class TableSpec:
    def __init__(self):
        self.columnCount = 0
        self.firstRow = 1

class Desc:
    def __init__(self, node):
        self.env = LaTeXTranslator.desc_map[node['desctype']]
        self.ni = node['noindex']
        self.type = self.cls = self.name = self.params = ''
        self.count = 0


class LaTeXTranslator(nodes.NodeVisitor):
    sectionnames = ["chapter", "chapter", "section", "subsection",
                    "subsubsection", "paragraph", "subparagraph"]

    def __init__(self, document, config):
        nodes.NodeVisitor.__init__(self, document)
        self.body = []
        self.options = {'docclass': document.settings.docclass,
                        'papersize': 'a4paper', # XXX
                        'pointsize': '12pt',
                        'filename': document.settings.filename,
                        'title': None, # comes later
                        'release': config['release'],
                        'date': time.strftime(config.get('today_fmt', '%B %d, %Y')),
                        }
        self.context = []
        self.descstack = []
        self.highlightlang = 'python'
        self.written_ids = set()
        # flags
        self.verbatim = None
        self.in_title = 0
        self.first_document = 1
        self.this_is_the_title = 1
        self.literal_whitespace = 0

    def astext(self):
        return (HEADER % self.options) + \
               highlighting.get_stylesheet('latex') + '\n\n' + \
               u''.join(self.body) + \
               (FOOTER % self.options)

    def visit_document(self, node):
        if self.first_document == 1:
            self.body.append('\\begin{document}\n\\maketitle\n\\tableofcontents\n')
            self.first_document = 0
        elif self.first_document == 0:
            self.body.append('\n\\appendix\n')
            self.first_document = -1
        self.sectionlevel = 0
    def depart_document(self, node):
        pass

    def visit_highlightlang(self, node):
        self.highlightlang = node['lang']
        raise nodes.SkipNode

    def visit_comment(self, node):
        raise nodes.SkipNode

    def visit_section(self, node):
        if not self.this_is_the_title:
            self.sectionlevel += 1
        self.body.append('\n\n')
        if node.get('ids'):
            for id in node['ids']:
                if id not in self.written_ids:
                    self.body.append(r'\hypertarget{%s}{}' % id)
                    self.written_ids.add(id)
    def depart_section(self, node):
        self.sectionlevel -= 1

    def visit_glossary(self, node):
        raise nodes.SkipNode # XXX

    def visit_productionlist(self, node):
        raise nodes.SkipNode # XXX

    def visit_transition(self, node):
        self.body.append('\n\n\\bigskip\\hrule{}\\bigskip\n\n')
    def depart_transition(self, node):
        pass

    def visit_title(self, node):
        if isinstance(node.parent, addnodes.seealso):
            # the environment already handles this
            raise nodes.SkipNode
        elif self.this_is_the_title:
            if len(node.children) != 1 and not isinstance(node.children[0], Text):
                raise RuntimeError("title is not a Text node")
            self.options['title'] = node.children[0].astext()
            self.this_is_the_title = 0
            raise nodes.SkipNode
        elif isinstance(node.parent, nodes.section):
            self.body.append(r'\%s{' % self.sectionnames[self.sectionlevel])
            self.context.append('}\n')
        else:
            raise RuntimeError("XXX title without section")
        self.in_title = 1
    def depart_title(self, node):
        self.in_title = 0
        self.body.append(self.context.pop())

    def visit_field_list(self, node):
        raise nodes.SkipNode # XXX

    desc_map = {
        'function' : 'funcdesc',
        'class': 'classdesc',
        #'classdesc*': ('class', '0'), XXX
        'method': 'methoddesc',
        'exception': 'excdesc',
        #'excclassdesc': ('exception', '0(1)'), XXX
        'data': 'datadesc',
        'attribute': 'memberdesc',
        'opcode': 'opcodedesc',

        'cfunction': 'cfuncdesc',
        'cmember': 'cmemberdesc',
        'cmacro': 'csimplemacrodesc',
        'ctype': 'ctypedesc',
        'cvar': 'cvardesc',

        'describe': 'describe',
        'cmdoption': 'describe', # XXX?
        'envvar': 'describe',
    }

    def visit_desc(self, node):
        self.descstack.append(Desc(node))
    def depart_desc(self, node):
        d = self.descstack.pop()
        self.body.append("\\end{%s%s}\n" % (d.env, d.ni and 'ni' or ''))

    def visit_desc_signature(self, node):
        pass
    def depart_desc_signature(self, node):
        d = self.descstack[-1]
        d.cls = d.cls.rstrip('.')
        if node.parent['desctype'] != 'describe' and node['ids']:
            hyper = '\\hypertarget{%s}{}' % node['ids'][0]
        else:
            hyper = ''
        if d.count == 0:
            t1 = "\n\n%s\\begin{%s%s}" % (hyper, d.env, (d.ni and 'ni' or ''))
        else:
            t1 = "\n%s\\%sline%s" % (hyper, d.env[:-4], (d.ni and 'ni' or ''))
        d.count += 1
        if d.env in ('funcdesc', 'classdesc', 'excclassdesc'):
            t2 = "{%s}{%s}" % (d.name, d.params)
        elif d.env in ('datadesc', 'classdesc*', 'excdesc', 'csimplemacrodesc'):
            t2 = "{%s}" % (d.name)
        elif d.env == 'methoddesc':
            t2 = "[%s]{%s}{%s}" % (d.cls, d.name, d.params)
        elif d.env == 'memberdesc':
            t2 = "[%s]{%s}" % (d.cls, d.name)
        elif d.env == 'cfuncdesc':
            t2 = "{%s}{%s}{%s}" % (d.type, d.name, d.params)
        elif d.env == 'cmemberdesc':
            try:
                type, container = d.type.rsplit(' ', 1)
                container = container.rstrip('.')
            except:
                container = ''
                type = d.type
            t2 = "{%s}{%s}{%s}" % (container, type, d.name)
        elif d.env == 'cvardesc':
            t2 = "{%s}{%s}" % (d.type, d.name)
        elif d.env == 'ctypedesc':
            t2 = "{%s}" % (d.name)
        elif d.env == 'opcodedesc':
            t2 = "{%s}{%s}" % (d.name, d.params)
        elif d.env == 'describe':
            t2 = "{%s}" % d.name
        self.body.append(t1 + t2)

    def visit_desc_type(self, node):
        self.descstack[-1].type = self.encode(node.astext().strip())
        raise nodes.SkipNode

    def visit_desc_name(self, node):
        self.descstack[-1].name = self.encode(node.astext().strip())
        raise nodes.SkipNode

    def visit_desc_classname(self, node):
        self.descstack[-1].cls = self.encode(node.astext().strip())
        raise nodes.SkipNode

    def visit_desc_parameterlist(self, node):
        self.descstack[-1].params = self.encode(node.astext().strip())
        raise nodes.SkipNode

    def visit_refcount(self, node):
        self.body.append("\\emph{")
    def depart_refcount(self, node):
        self.body.append("}\\\\")

    def visit_desc_content(self, node):
        pass
    def depart_desc_content(self, node):
        pass

    def visit_seealso(self, node):
        self.body.append("\n\n\\begin{seealso}\n")
    def depart_seealso(self, node):
        self.body.append("\n\\end{seealso}\n")

    def visit_rubric(self, node):
        if len(node.children) == 1 and node.children[0].astext() == 'Footnotes':
            raise nodes.SkipNode
        raise RuntimeError("rubric not supported except for footnotes heading")

    def visit_footnote(self, node):
        # XXX not optimal, footnotes are at section end
        num = node.children[0].astext().strip()
        self.body.append('\\footnotetext[%s]{' % num)
    def depart_footnote(self, node):
        self.body.append('}')

    def visit_label(self, node):
        raise nodes.SkipNode

    def visit_table(self, node):
        self.tableSpec = TableSpec()
    def depart_table(self, node):
        self.tableSpec = None

    def visit_colspec(self, node):
        pass
    def depart_colspec(self, node):
        pass

    def visit_tgroup(self, node):
        columnCount = int(node.get('cols', 0))
        self.tableSpec.columnCount = columnCount
        if columnCount == 2:
            self.body.append('\\begin{tableii}{l|l}{textrm}')
        elif columnCount == 3:
            self.body.append('\\begin{tableiii}{l|l|l}{textrm}')
        elif columnCount == 4:
            self.body.append('\\begin{tableiv}{l|l|l|l}{textrm}')
        elif columnCount == 5:
            self.body.append('\\begin{tablev}{l|l|l|l|l}{textrm}')
        else:
            raise RuntimeError("XXX table with too many columns found")
    def depart_tgroup(self, node):
        if self.tableSpec.columnCount == 2:
            self.body.append('\n\\end{tableii}\n\n')
        elif self.tableSpec.columnCount == 3:
            self.body.append('\n\\end{tableiii}\n\n')
        elif self.tableSpec.columnCount == 4:
            self.body.append('\n\\end{tableiv}\n\n')
        elif self.tableSpec.columnCount == 5:
            self.body.append('\n\\end{tablev}\n\n')

    def visit_thead(self, node):
        pass
    def depart_thead(self, node):
        pass

    def visit_tbody(self, node):
        pass
    def depart_tbody(self, node):
        pass

    def visit_row(self, node):
        if not self.tableSpec.firstRow:
            if self.tableSpec.columnCount == 2:
                self.body.append('\n\\lineii')
            elif self.tableSpec.columnCount == 3:
                self.body.append('\n\\lineiii')
            elif self.tableSpec.columnCount == 4:
                self.body.append('\n\\lineiv')
            elif self.tableSpec.columnCount == 5:
                self.body.append('\n\\linev')
    def depart_row(self, node):
        if self.tableSpec.firstRow:
            self.tableSpec.firstRow = 0

    def visit_entry(self, node):
        if self.tableSpec.firstRow:
            self.body.append('{%s}' % self.encode(node.astext().strip(' ')))
            raise nodes.SkipNode
        else:
            self.body.append('{')
    def depart_entry(self, node):
        if self.tableSpec.firstRow:
            pass
        else:
            self.body.append('}')

    def visit_bullet_list(self, node):
        self.body.append('\\begin{itemize}\n' )
    def depart_bullet_list(self, node):
        self.body.append('\\end{itemize}\n' )

    def visit_enumerated_list(self, node):
        self.body.append('\\begin{enumerate}\n' )
    def depart_enumerated_list(self, node):
        self.body.append('\\end{enumerate}\n' )

    def visit_list_item(self, node):
        # Append "{}" in case the next character is "[", which would break
        # LaTeX's list environment (no numbering and the "[" is not printed).
        self.body.append(r'\item {} ')
    def depart_list_item(self, node):
        self.body.append('\n')

    def visit_definition_list(self, node):
        self.body.append('\\begin{description}\n')
    def depart_definition_list(self, node):
        self.body.append('\\end{description}\n')

    def visit_definition_list_item(self, node):
        pass
    def depart_definition_list_item(self, node):
        pass

    def visit_term(self, node):
        self.body.append('\\item[')
    def depart_term(self, node):
        # definition list term.
        self.body.append(']\n')

    def visit_classifier(self, node):
        self.body.append('{[}')
    def depart_classifier(self, node):
        self.body.append('{]}')

    def visit_definition(self, node):
        pass
    def depart_definition(self, node):
        self.body.append('\n')

    def visit_paragraph(self, node):
        self.body.append('\n')
    def depart_paragraph(self, node):
        self.body.append('\n')

    def visit_centered(self, node):
        self.body.append('\n\\begin{centering}')
    def depart_centered(self, node):
        self.body.append('\n\\end{centering}')

    def visit_note(self, node):
        self.body.append('\n\\begin{notice}[note]')
    def depart_note(self, node):
        self.body.append('\\end{notice}\n')

    def visit_warning(self, node):
        self.body.append('\n\\begin{notice}[warning]')
    def depart_warning(self, node):
        self.body.append('\\end{notice}\n')

    def visit_versionmodified(self, node):
        self.body.append('\\%s' % node['type'])
        if node['type'] == 'deprecated':
            self.body.append('{%s}{' % node['version'])
            self.context.append('}')
        else:
            if len(node):
                self.body.append('[')
                self.context.append(']{%s}' % node['version'])
            else:
                self.body.append('{%s}' % node['version'])
                self.context.append('')
    def depart_versionmodified(self, node):
        self.body.append(self.context.pop())

    def visit_target(self, node):
        # XXX: no "index-" targets
        if not (node.has_key('refuri') or node.has_key('refid')
                or node.has_key('refname')):
            ctx = ''
            for id in node['ids']:
                if id not in self.written_ids:
                    self.body.append(r'\hypertarget{%s}{' % id)
                    self.written_ids.add(id)
                    ctx += '}'
            self.context.append(ctx)
        elif node.has_key('refid') and node['refid'] not in self.written_ids:
            self.body.append(r'\hypertarget{%s}{' % node['refid'])
            self.written_ids.add(node['refid'])
            self.context.append('}')
        else:
            self.context.append('')
    def depart_target(self, node):
        self.body.append(self.context.pop())

    def visit_index(self, node):
        raise nodes.SkipNode # XXX

    def visit_reference(self, node):
        uri = node.get('refuri', '')
        if self.in_title or not uri:
            self.context.append('')
        elif uri.startswith(('mailto:', 'http:', 'ftp:')):
            self.body.append('\\href{%s}{' % self.encode(uri))
            self.context.append('}')
        elif uri.startswith('#'):
            self.body.append('\\hyperlink{%s}{' % uri[1:])
            self.context.append('}')
        else:
            raise RuntimeError('XXX malformed reference target %s' % uri)
    def depart_reference(self, node):
        self.body.append(self.context.pop())

    def visit_pending_xref(self, node):
        pass
    def depart_pending_xref(self, node):
        pass

    def visit_emphasis(self, node):
        self.body.append(r'\emph{')
    def depart_emphasis(self, node):
        self.body.append('}')

    def visit_literal_emphasis(self, node):
        self.body.append(r'\emph{') # XXX
    def depart_literal_emphasis(self, node):
        self.body.append('}')

    def visit_strong(self, node):
        self.body.append(r'\textbf{')
    def depart_strong(self, node):
        self.body.append('}')

    def visit_title_reference(self, node):
        raise RuntimeError("XXX title reference node found")

    def visit_literal(self, node):
        content = self.encode(node.astext().strip())
        if self.in_title:
            self.body.append(r'\texttt{%s}' % content)
        elif re.search('[ \t\n]', content):
            self.body.append(r'\samp{%s}' % content)
        else:
            self.body.append(r'\code{%s}' % content)
        raise nodes.SkipNode

    def visit_footnote_reference(self, node):
        self.body.append('\\footnotemark[%s]' % node.astext())
        raise nodes.SkipNode

    def visit_literal_block(self, node):
        #self.body.append('\n\\begin{Verbatim}\n')
        self.verbatim = ''
    def depart_literal_block(self, node):
        #self.body.append('\n\\end{Verbatim}\n')
        self.body.append('\n' + highlighting.highlight_block(self.verbatim,
                                                             self.highlightlang,
                                                             'latex'))
        self.verbatim = None
    visit_doctest_block = visit_literal_block
    depart_doctest_block = depart_literal_block

    def visit_line_block(self, node):
        """line-block:
        * whitespace (including linebreaks) is significant
        * inline markup is supported.
        * serif typeface
        """
        self.body.append('\\begin{flushleft}\n')
        self.literal_whitespace = 1
    def depart_line_block(self, node):
        self.literal_whitespace = 0
        self.body.append('\n\\end{flushleft}\n')

    def visit_line(self, node):
        pass
    def depart_line(self, node):
        pass

    def visit_block_quote(self, node):
        # If the block quote contains a single object and that object
        # is a list, then generate a list not a block quote.
        # This lets us indent lists.
        done = 0
        if len(node.children) == 1:
            child = node.children[0]
            if isinstance(child, nodes.bullet_list) or \
                    isinstance(child, nodes.enumerated_list):
                done = 1
        if not done:
            self.body.append('\\begin{quote}\n')
    def depart_block_quote(self, node):
        done = 0
        if len(node.children) == 1:
            child = node.children[0]
            if isinstance(child, nodes.bullet_list) or \
                    isinstance(child, nodes.enumerated_list):
                done = 1
        if not done:
            self.body.append('\\end{quote}\n')

    replacements = [
        (u"\\", u"\x00"),
        (u"$", ur"\$"),
        (r"%", ur"\%"),
        (u"&", ur"\&"),
        (u"#", ur"\#"),
        (u"_", ur"\_"),
        (u"{", ur"\{"),
        (u"}", ur"\}"),
        (u"[", ur"{[}"),
        (u"]", ur"{]}"),
        (u"¶", ur"\P{}"),
        (u"§", ur"\S{}"),
        (u"~", ur"\textasciitilde{}"),
        (u"<", ur"\textless{}"),
        (u">", ur"\textgreater{}"),
        (u"^", ur"\textasciicircum{}"),
        (u"\x00", ur"\textbackslash{}"),
    ]

    def encode(self, text):
        for x, y in self.replacements:
            text = text.replace(x, y)
        if self.literal_whitespace:
            # Insert a blank before the newline, to avoid
            # ! LaTeX Error: There's no line here to end.
            text = text.replace("\n", '~\\\\\n').replace(" ", "~")
        return text

    def visit_Text(self, node):
        if self.verbatim is not None:
            self.verbatim += node.astext()
        else:
            self.body.append(self.encode(node.astext()))
    def depart_Text(self, node):
        pass

    def unknown_visit(self, node):
        raise NotImplementedError("Unknown node: " + node.__class__.__name__)
