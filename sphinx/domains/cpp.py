# -*- coding: utf-8 -*-
"""
    sphinx.domains.cpp
    ~~~~~~~~~~~~~~~~~~

    The C++ language domain.

    :copyright: Copyright 2007-2011 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re
from copy import deepcopy

from docutils import nodes

from sphinx import addnodes
from sphinx.roles import XRefRole
from sphinx.locale import l_, _
from sphinx.domains import Domain, ObjType
from sphinx.directives import ObjectDescription
from sphinx.util.nodes import make_refnode
from sphinx.util.compat import Directive


_identifier_re = re.compile(r'(~?\b[a-zA-Z_][a-zA-Z0-9_]*)\b')
_whitespace_re = re.compile(r'\s+(?u)')
_string_re = re.compile(r"[LuU8]?('([^'\\]*(?:\\.[^'\\]*)*)'"
                        r'|"([^"\\]*(?:\\.[^"\\]*)*)")', re.S)
_visibility_re = re.compile(r'\b(public|private|protected)\b')
_array_def_re = re.compile(r'\[\s*(.+?)?\s*\]')
_operator_re = re.compile(r'''(?x)
        \[\s*\]
    |   \(\s*\)
    |   [!<>=/*%+|&^-]=?
    |   \+\+ | --
    |   (<<|>>)=? | ~ | && | \| | \|\|
    |   ->\*? | \,
''')

_id_shortwords = {
    'char':                 'c',
    'signed char':          'c',
    'unsigned char':        'C',
    'int':                  'i',
    'signed int':           'i',
    'unsigned int':         'U',
    'long':                 'l',
    'signed long':          'l',
    'unsigned long':        'L',
    'bool':                 'b',
    'size_t':               's',
    'std::string':          'ss',
    'std::ostream':         'os',
    'std::istream':         'is',
    'std::iostream':        'ios',
    'std::vector':          'v',
    'std::map':             'm',
    'operator[]':           'subscript-operator',
    'operator()':           'call-operator',
    'operator!':            'not-operator',
    'operator<':            'lt-operator',
    'operator<=':           'lte-operator',
    'operator>':            'gt-operator',
    'operator>=':           'gte-operator',
    'operator=':            'assign-operator',
    'operator/':            'div-operator',
    'operator*':            'mul-operator',
    'operator%':            'mod-operator',
    'operator+':            'add-operator',
    'operator-':            'sub-operator',
    'operator|':            'or-operator',
    'operator&':            'and-operator',
    'operator^':            'xor-operator',
    'operator&&':           'sand-operator',
    'operator||':           'sor-operator',
    'operator==':           'eq-operator',
    'operator!=':           'neq-operator',
    'operator<<':           'lshift-operator',
    'operator>>':           'rshift-operator',
    'operator-=':           'sub-assign-operator',
    'operator+=':           'add-assign-operator',
    'operator*-':           'mul-assign-operator',
    'operator/=':           'div-assign-operator',
    'operator%=':           'mod-assign-operator',
    'operator&=':           'and-assign-operator',
    'operator|=':           'or-assign-operator',
    'operator<<=':          'lshift-assign-operator',
    'operator>>=':          'rshift-assign-operator',
    'operator^=':           'xor-assign-operator',
    'operator,':            'comma-operator',
    'operator->':           'pointer-operator',
    'operator->*':          'pointer-by-pointer-operator',
    'operator~':            'inv-operator',
    'operator++':           'inc-operator',
    'operator--':           'dec-operator',
    'operator new':         'new-operator',
    'operator new[]':       'new-array-operator',
    'operator delete':      'delete-operator',
    'operator delete[]':    'delete-array-operator'
}


class DefinitionError(Exception):

    def __init__(self, description):
        self.description = description

    def __unicode__(self):
        return self.description

    def __str__(self):
        return unicode(self).encode('utf-8')


class DefExpr(object):

    def __unicode__(self):
        raise NotImplementedError()

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        try:
            for key, value in self.__dict__.iteritems():
                if value != getattr(other, value):
                    return False
        except AttributeError:
            return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = None

    def clone(self):
        """Clone a definition expression node."""
        return deepcopy(self)

    def get_id(self):
        """Return the id for the node."""
        return u''

    def get_name(self):
        """Return the name.

        Returns either `None` or a node with a name you might call
        :meth:`split_owner` on.
        """
        return None

    def split_owner(self):
        """Nodes returned by :meth:`get_name` can split off their
        owning parent.  This function returns the owner and the
        name as a tuple of two items.  If a node does not support
        it, it returns None as owner and self as name.
        """
        return None, self

    def prefix(self, prefix):
        """Prefix a name node (a node returned by :meth:`get_name`)."""
        raise NotImplementedError()

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self)


class PrimaryDefExpr(DefExpr):

    def get_name(self):
        return self

    def prefix(self, prefix):
        if isinstance(prefix, PathDefExpr):
            prefix = prefix.clone()
            prefix.path.append(self)
            return prefix
        return PathDefExpr([prefix, self])


class NameDefExpr(PrimaryDefExpr):

    def __init__(self, name):
        self.name = name

    def get_id(self):
        name = _id_shortwords.get(self.name)
        if name is not None:
            return name
        return self.name.replace(u' ', u'-')

    def __unicode__(self):
        return unicode(self.name)


class PathDefExpr(PrimaryDefExpr):

    def __init__(self, parts):
        self.path = parts

    def get_id(self):
        rv = u'::'.join(x.get_id() for x in self.path)
        return _id_shortwords.get(rv, rv)

    def split_owner(self):
        if len(self.path) > 1:
            return PathDefExpr(self.path[:-1]), self.path[-1]
        return None, self

    def prefix(self, prefix):
        if isinstance(prefix, PathDefExpr):
            prefix = prefix.clone()
            prefix.path.extend(self.path)
            return prefix
        return PathDefExpr([prefix] + self.path)

    def __unicode__(self):
        return u'::'.join(map(unicode, self.path))


class TemplateDefExpr(PrimaryDefExpr):

    def __init__(self, typename, args):
        self.typename = typename
        self.args = args

    def split_owner(self):
        owner, typename = self.typename.split_owner()
        return owner, TemplateDefExpr(typename, self.args)

    def get_id(self):
        return u'%s:%s:' % (self.typename.get_id(),
                            u'.'.join(x.get_id() for x in self.args))

    def __unicode__(self):
        return u'%s<%s>' % (self.typename, u', '.join(map(unicode, self.args)))


class WrappingDefExpr(DefExpr):

    def __init__(self, typename):
        self.typename = typename

    def get_name(self):
        return self.typename.get_name()


class ModifierDefExpr(WrappingDefExpr):

    def __init__(self, typename, modifiers):
        WrappingDefExpr.__init__(self, typename)
        self.modifiers = modifiers

    def get_id(self):
        pieces = [_id_shortwords.get(unicode(x), unicode(x))
                  for x in self.modifiers]
        pieces.append(self.typename.get_id())
        return u'-'.join(pieces)

    def __unicode__(self):
        return u' '.join(map(unicode, list(self.modifiers) + [self.typename]))


class PtrDefExpr(WrappingDefExpr):

    def get_id(self):
        return self.typename.get_id() + u'P'

    def __unicode__(self):
        return u'%s*' % self.typename


class ArrayDefExpr(WrappingDefExpr):

    def __init__(self, typename, size_hint=None):
        WrappingDefExpr.__init__(self, typename)
        self.size_hint = size_hint

    def get_id(self):
        return self.typename.get_id() + u'A'

    def __unicode__(self):
        return u'%s[%s]' % (
            self.typename,
            self.size_hint is not None and unicode(self.size_hint) or u''
        )


class RefDefExpr(WrappingDefExpr):

    def get_id(self):
        return self.typename.get_id() + u'R'

    def __unicode__(self):
        return u'%s&' % self.typename


class ConstDefExpr(WrappingDefExpr):

    def __init__(self, typename, prefix=False):
        WrappingDefExpr.__init__(self, typename)
        self.prefix = prefix

    def get_id(self):
        return self.typename.get_id() + u'C'

    def __unicode__(self):
        return (self.prefix and u'const %s' or u'%s const') % self.typename


class CastOpDefExpr(PrimaryDefExpr):

    def __init__(self, typename):
        self.typename = typename

    def get_id(self):
        return u'castto-%s-operator' % self.typename.get_id()

    def __unicode__(self):
        return u'operator %s' % self.typename


class ArgumentDefExpr(DefExpr):

    def __init__(self, type, name, default=None):
        self.name = name
        self.type = type
        self.default = default

    def get_name(self):
        return self.name.get_name()

    def get_id(self):
        if self.type is None:
            return 'X'
        return self.type.get_id()

    def __unicode__(self):
        return (u'%s %s' % (self.type or u'', self.name or u'')).strip() + \
               (self.default is not None and u'=%s' % self.default or u'')


class NamedDefExpr(DefExpr):

    def __init__(self, name, visibility, static):
        self.name = name
        self.visibility = visibility
        self.static = static

    def get_name(self):
        return self.name.get_name()

    def get_modifiers(self):
        rv = []
        if self.visibility != 'public':
            rv.append(self.visibility)
        if self.static:
            rv.append(u'static')
        return rv


class TypeObjDefExpr(NamedDefExpr):

    def __init__(self, name, visibility, static, typename):
        NamedDefExpr.__init__(self, name, visibility, static)
        self.typename = typename

    def get_id(self):
        if self.typename is None:
            return self.name.get_id()
        return u'%s__%s' % (self.name.get_id(), self.typename.get_id())

    def __unicode__(self):
        buf = self.get_modifiers()
        if self.typename is None:
            buf.append(unicode(self.name))
        else:
            buf.extend(map(unicode, (self.typename, self.name)))
        return u' '.join(buf)


class MemberObjDefExpr(NamedDefExpr):

    def __init__(self, name, visibility, static, typename, value):
        NamedDefExpr.__init__(self, name, visibility, static)
        self.typename = typename
        self.value = value

    def get_id(self):
        return u'%s__%s' % (self.name.get_id(), self.typename.get_id())

    def __unicode__(self):
        buf = self.get_modifiers()
        buf.append(u'%s %s' % (self.typename, self.name))
        if self.value is not None:
            buf.append(u'= %s' % self.value)
        return u' '.join(buf)


class FuncDefExpr(NamedDefExpr):

    def __init__(self, name, visibility, static, explicit, rv,
                 signature, const, pure_virtual):
        NamedDefExpr.__init__(self, name, visibility, static)
        self.rv = rv
        self.signature = signature
        self.explicit = explicit
        self.const = const
        self.pure_virtual = pure_virtual

    def get_id(self):
        return u'%s%s%s' % (
            self.name.get_id(),
            self.signature and u'__' +
                u'.'.join(x.get_id() for x in self.signature) or u'',
            self.const and u'C' or u''
        )

    def __unicode__(self):
        buf = self.get_modifiers()
        if self.explicit:
            buf.append(u'explicit')
        if self.rv is not None:
            buf.append(unicode(self.rv))
        buf.append(u'%s(%s)' % (self.name, u', '.join(
            map(unicode, self.signature))))
        if self.const:
            buf.append(u'const')
        if self.pure_virtual:
            buf.append(u'= 0')
        return u' '.join(buf)


class ClassDefExpr(NamedDefExpr):

    def __init__(self, name, visibility, static):
        NamedDefExpr.__init__(self, name, visibility, static)

    def get_id(self):
        return self.name.get_id()

    def __unicode__(self):
        buf = self.get_modifiers()
        buf.append(unicode(self.name))
        return u' '.join(buf)


class DefinitionParser(object):

    # mapping of valid type modifiers.  if the set is None it means
    # the modifier can prefix all types, otherwise only the types
    # (actually more keywords) in the set.  Also check
    # _guess_typename when changing this.
    _modifiers = {
        'volatile':     None,
        'register':     None,
        'mutable':      None,
        'const':        None,
        'typename':     None,
        'unsigned':     set(('char', 'short', 'int', 'long')),
        'signed':       set(('char', 'short', 'int', 'long')),
        'short':        set(('int',)),
        'long':         set(('int', 'long', 'double'))
    }

    def __init__(self, definition):
        self.definition = definition.strip()
        self.pos = 0
        self.end = len(self.definition)
        self.last_match = None
        self._previous_state = (0, None)

    def fail(self, msg):
        raise DefinitionError('Invalid definition: %s [error at %d]\n  %s' %
            (msg, self.pos, self.definition))

    def match(self, regex):
        match = regex.match(self.definition, self.pos)
        if match is not None:
            self._previous_state = (self.pos, self.last_match)
            self.pos = match.end()
            self.last_match = match
            return True
        return False

    def backout(self):
        self.pos, self.last_match = self._previous_state

    def skip_string(self, string):
        strlen = len(string)
        if self.definition[self.pos:self.pos + strlen] == string:
            self.pos += strlen
            return True
        return False

    def skip_word(self, word):
        return self.match(re.compile(r'\b%s\b' % re.escape(word)))

    def skip_ws(self):
        return self.match(_whitespace_re)

    @property
    def eof(self):
        return self.pos >= self.end

    @property
    def current_char(self):
        try:
            return self.definition[self.pos]
        except IndexError:
            return 'EOF'

    @property
    def matched_text(self):
        if self.last_match is not None:
            return self.last_match.group()

    def _parse_operator(self):
        self.skip_ws()
        # thank god, a regular operator definition
        if self.match(_operator_re):
            return NameDefExpr('operator' +
                                _whitespace_re.sub('', self.matched_text))

        # new/delete operator?
        for allocop in 'new', 'delete':
            if not self.skip_word(allocop):
                continue
            self.skip_ws()
            if self.skip_string('['):
                self.skip_ws()
                if not self.skip_string(']'):
                    self.fail('expected "]" for ' + allocop)
                allocop += '[]'
            return NameDefExpr('operator ' + allocop)

        # oh well, looks like a cast operator definition.
        # In that case, eat another type.
        type = self._parse_type()
        return CastOpDefExpr(type)

    def _parse_name(self):
        if not self.match(_identifier_re):
            self.fail('expected name')
        identifier = self.matched_text

        # strictly speaking, operators are not regular identifiers
        # but because operator is a keyword, it might not be used
        # for variable names anyways, so we can safely parse the
        # operator here as identifier
        if identifier == 'operator':
            return self._parse_operator()

        return NameDefExpr(identifier)

    def _guess_typename(self, path):
        if not path:
            return [], 'int'
        # for the long type, we don't want the int in there
        if 'long' in path:
            path = [x for x in path if x != 'int']
            # remove one long
            path.remove('long')
            return path, 'long'
        if path[-1] in ('int', 'char'):
            return path[:-1], path[-1]
        return path, 'int'

    def _attach_crefptr(self, expr, is_const=False):
        if is_const:
            expr = ConstDefExpr(expr, prefix=True)
        while 1:
            self.skip_ws()
            if self.skip_word('const'):
                expr = ConstDefExpr(expr)
            elif self.skip_string('*'):
                expr = PtrDefExpr(expr)
            elif self.match(_array_def_re):
                expr = ArrayDefExpr(expr, self.last_match.group(1))
            elif self.skip_string('&'):
                expr = RefDefExpr(expr)
            else:
                return expr

    def _peek_const(self, path):
        try:
            path.remove('const')
            return True
        except ValueError:
            return False

    def _parse_builtin(self, modifier):
        path = [modifier]
        following = self._modifiers[modifier]
        while 1:
            self.skip_ws()
            if not self.match(_identifier_re):
                break
            identifier = self.matched_text
            if identifier in following:
                path.append(identifier)
                following = self._modifiers[modifier]
                assert following
            else:
                self.backout()
                break

        is_const = self._peek_const(path)
        modifiers, typename = self._guess_typename(path)
        rv = ModifierDefExpr(NameDefExpr(typename), modifiers)
        return self._attach_crefptr(rv, is_const)

    def _parse_type_expr(self):
        typename = self._parse_name()
        self.skip_ws()
        if not self.skip_string('<'):
            return typename

        args = []
        while 1:
            self.skip_ws()
            if self.skip_string('>'):
                break
            if args:
                if not self.skip_string(','):
                    self.fail('"," or ">" in template expected')
                self.skip_ws()
            args.append(self._parse_type(True))
        return TemplateDefExpr(typename, args)

    def _parse_type(self, in_template=False):
        self.skip_ws()
        result = []
        modifiers = []

        # if there is a leading :: or not, we don't care because we
        # treat them exactly the same.  Buf *if* there is one, we
        # don't have to check for type modifiers
        if not self.skip_string('::'):
            self.skip_ws()
            while self.match(_identifier_re):
                modifier = self.matched_text
                if modifier in self._modifiers:
                    following = self._modifiers[modifier]
                    # if the set is not none, there is a limited set
                    # of types that might follow.  It is technically
                    # impossible for a template to follow, so what
                    # we do is go to a different function that just
                    # eats types
                    if following is not None:
                        return self._parse_builtin(modifier)
                    modifiers.append(modifier)
                else:
                    self.backout()
                    break

        while 1:
            self.skip_ws()
            if (in_template and self.current_char in ',>') or \
               (result and not self.skip_string('::')) or \
               self.eof:
                break
            result.append(self._parse_type_expr())

        if not result:
            self.fail('expected type')
        if len(result) == 1:
            rv = result[0]
        else:
            rv = PathDefExpr(result)
        is_const = self._peek_const(modifiers)
        if modifiers:
            rv = ModifierDefExpr(rv, modifiers)
        return self._attach_crefptr(rv, is_const)

    def _parse_default_expr(self):
        self.skip_ws()
        if self.match(_string_re):
            return self.matched_text
        idx1 = self.definition.find(',', self.pos)
        idx2 = self.definition.find(')', self.pos)
        if idx1 < 0:
            idx = idx2
        elif idx2 < 0:
            idx = idx1
        else:
            idx = min(idx1, idx2)
        if idx < 0:
            self.fail('unexpected end in default expression')
        rv = self.definition[self.pos:idx]
        self.pos = idx
        return rv

    def _parse_signature(self):
        self.skip_ws()
        if not self.skip_string('('):
            self.fail('expected parentheses for function')

        args = []
        while 1:
            self.skip_ws()
            if self.eof:
                self.fail('missing closing parentheses')
            if self.skip_string(')'):
                break
            if args:
                if not self.skip_string(','):
                    self.fail('expected comma between arguments')
                self.skip_ws()

            argtype = self._parse_type()
            argname = default = None
            self.skip_ws()
            if self.skip_string('='):
                self.pos += 1
                default = self._parse_default_expr()
            elif self.current_char not in ',)':
                argname = self._parse_name()
                self.skip_ws()
                if self.skip_string('='):
                    default = self._parse_default_expr()

            args.append(ArgumentDefExpr(argtype, argname, default))
        self.skip_ws()
        const = self.skip_word('const')
        if const:
            self.skip_ws()
        if self.skip_string('='):
            self.skip_ws()
            if not (self.skip_string('0') or \
                    self.skip_word('NULL') or \
                    self.skip_word('nullptr')):
                self.fail('pure virtual functions must be defined with '
                          'either 0, NULL or nullptr, other macros are '
                          'not allowed')
            pure_virtual = True
        else:
            pure_virtual = False
        return args, const, pure_virtual

    def _parse_visibility_static(self):
        visibility =  'public'
        if self.match(_visibility_re):
            visibility = self.matched_text
        static = self.skip_word('static')
        return visibility, static

    def parse_type(self):
        return self._parse_type()

    def parse_type_object(self):
        visibility, static = self._parse_visibility_static()
        typename = self._parse_type()
        self.skip_ws()
        if not self.eof:
            name = self._parse_type()
        else:
            name = typename
            typename = None
        return TypeObjDefExpr(name, visibility, static, typename)

    def parse_member_object(self):
        visibility, static = self._parse_visibility_static()
        typename = self._parse_type()
        name = self._parse_type()
        self.skip_ws()
        if self.skip_string('='):
            value = self.read_rest().strip()
        else:
            value = None
        return MemberObjDefExpr(name, visibility, static, typename, value)

    def parse_function(self):
        visibility, static = self._parse_visibility_static()
        if self.skip_word('explicit'):
            explicit = True
            self.skip_ws()
        else:
            explicit = False
        rv = self._parse_type()
        self.skip_ws()
        # some things just don't have return values
        if self.current_char == '(':
            name = rv
            rv = None
        else:
            name = self._parse_type()
        return FuncDefExpr(name, visibility, static, explicit, rv,
                           *self._parse_signature())

    def parse_class(self):
        visibility, static = self._parse_visibility_static()
        return ClassDefExpr(self._parse_type(), visibility, static)

    def read_rest(self):
        rv = self.definition[self.pos:]
        self.pos = self.end
        return rv

    def assert_end(self):
        self.skip_ws()
        if not self.eof:
            self.fail('expected end of definition, got %r' %
                      self.definition[self.pos:])


class CPPObject(ObjectDescription):
    """Description of a C++ language object."""

    def attach_name(self, node, name):
        owner, name = name.split_owner()
        varname = unicode(name)
        if owner is not None:
            owner = unicode(owner) + '::'
            node += addnodes.desc_addname(owner, owner)
        node += addnodes.desc_name(varname, varname)

    def attach_type(self, node, type):
        # XXX: link to c?
        text = unicode(type)
        pnode = addnodes.pending_xref(
            '', refdomain='cpp', reftype='type',
            reftarget=text, modname=None, classname=None)
        pnode['cpp:parent'] = self.env.temp_data.get('cpp:parent')
        pnode += nodes.Text(text)
        node += pnode

    def attach_modifiers(self, node, obj):
        if obj.visibility != 'public':
            node += addnodes.desc_annotation(obj.visibility,
                                             obj.visibility)
            node += nodes.Text(' ')
        if obj.static:
            node += addnodes.desc_annotation('static', 'static')
            node += nodes.Text(' ')

    def add_target_and_index(self, sigobj, sig, signode):
        theid = sigobj.get_id()
        name = unicode(sigobj.name)
        if theid not in self.state.document.ids:
            signode['names'].append(theid)
            signode['ids'].append(theid)
            signode['first'] = (not self.names)
            self.state.document.note_explicit_target(signode)

            self.env.domaindata['cpp']['objects'].setdefault(name,
                (self.env.docname, self.objtype, theid))

        indextext = self.get_index_text(name)
        if indextext:
            self.indexnode['entries'].append(('single', indextext, theid, ''))

    def before_content(self):
        lastname = self.names and self.names[-1]
        if lastname and not self.env.temp_data.get('cpp:parent'):
            assert isinstance(lastname, NamedDefExpr)
            self.env.temp_data['cpp:parent'] = lastname.name
            self.parentname_set = True
        else:
            self.parentname_set = False

    def after_content(self):
        if self.parentname_set:
            self.env.temp_data['cpp:parent'] = None

    def parse_definition(self, parser):
        raise NotImplementedError()

    def describe_signature(self, signode, arg):
        raise NotImplementedError()

    def handle_signature(self, sig, signode):
        parser = DefinitionParser(sig)
        try:
            rv = self.parse_definition(parser)
            parser.assert_end()
        except DefinitionError, e:
            self.env.warn(self.env.docname,
                          e.description, self.lineno)
            raise ValueError
        self.describe_signature(signode, rv)

        parent = self.env.temp_data.get('cpp:parent')
        if parent is not None:
            rv = rv.clone()
            rv.name = rv.name.prefix(parent)
        return rv


class CPPClassObject(CPPObject):

    def get_index_text(self, name):
        return _('%s (C++ class)') % name

    def parse_definition(self, parser):
        return parser.parse_class()

    def describe_signature(self, signode, cls):
        self.attach_modifiers(signode, cls)
        signode += addnodes.desc_annotation('class ', 'class ')
        self.attach_name(signode, cls.name)


class CPPTypeObject(CPPObject):

    def get_index_text(self, name):
        if self.objtype == 'type':
            return _('%s (C++ type)') % name
        return ''

    def parse_definition(self, parser):
        return parser.parse_type_object()

    def describe_signature(self, signode, obj):
        self.attach_modifiers(signode, obj)
        signode += addnodes.desc_annotation('type ', 'type ')
        if obj.typename is not None:
            self.attach_type(signode, obj.typename)
            signode += nodes.Text(' ')
        self.attach_name(signode, obj.name)


class CPPMemberObject(CPPObject):

    def get_index_text(self, name):
        if self.objtype == 'member':
            return _('%s (C++ member)') % name
        return ''

    def parse_definition(self, parser):
        return parser.parse_member_object()

    def describe_signature(self, signode, obj):
        self.attach_modifiers(signode, obj)
        self.attach_type(signode, obj.typename)
        signode += nodes.Text(' ')
        self.attach_name(signode, obj.name)
        if obj.value is not None:
            signode += nodes.Text(u' = ' + obj.value)


class CPPFunctionObject(CPPObject):

    def attach_function(self, node, func):
        owner, name = func.name.split_owner()
        if owner is not None:
            owner = unicode(owner) + '::'
            node += addnodes.desc_addname(owner, owner)

        # cast operator is special.  in this case the return value
        # is reversed.
        if isinstance(name, CastOpDefExpr):
            node += addnodes.desc_name('operator', 'operator')
            node += nodes.Text(u' ')
            self.attach_type(node, name.typename)
        else:
            funcname = unicode(name)
            node += addnodes.desc_name(funcname, funcname)

        paramlist = addnodes.desc_parameterlist()
        for arg in func.signature:
            param = addnodes.desc_parameter('', '', noemph=True)
            if arg.type is not None:
                self.attach_type(param, arg.type)
                param += nodes.Text(u' ')
            param += nodes.emphasis(unicode(arg.name), unicode(arg.name))
            if arg.default is not None:
                def_ = u'=' + unicode(arg.default)
                param += nodes.emphasis(def_, def_)
            paramlist += param

        node += paramlist
        if func.const:
            node += addnodes.desc_addname(' const', ' const')
        if func.pure_virtual:
            node += addnodes.desc_addname(' = 0', ' = 0')

    def get_index_text(self, name):
        return _('%s (C++ function)') % name

    def parse_definition(self, parser):
        return parser.parse_function()

    def describe_signature(self, signode, func):
        self.attach_modifiers(signode, func)
        if func.explicit:
            signode += addnodes.desc_annotation('explicit', 'explicit')
            signode += nodes.Text(' ')
        # return value is None for things with a reverse return value
        # such as casting operator definitions or constructors
        # and destructors.
        if func.rv is not None:
            self.attach_type(signode, func.rv)
        signode += nodes.Text(u' ')
        self.attach_function(signode, func)


class CPPCurrentNamespace(Directive):
    """
    This directive is just to tell Sphinx that we're documenting stuff in
    namespace foo.
    """

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    option_spec = {}

    def run(self):
        env = self.state.document.settings.env
        if self.arguments[0].strip() in ('NULL', '0', 'nullptr'):
            env.temp_data['cpp:prefix'] = None
        else:
            parser = DefinitionParser(self.arguments[0])
            try:
                prefix = parser.parse_type()
                parser.assert_end()
            except DefinitionError, e:
                self.env.warn(self.env.docname,
                              e.description, self.lineno)
            else:
                env.temp_data['cpp:prefix'] = prefix
        return []


class CPPXRefRole(XRefRole):

    def process_link(self, env, refnode, has_explicit_title, title, target):
        refnode['cpp:parent'] = env.temp_data.get('cpp:parent')
        if not has_explicit_title:
            target = target.lstrip('~') # only has a meaning for the title
            # if the first character is a tilde, don't display the module/class
            # parts of the contents
            if title[:1] == '~':
                title = title[1:]
                dcolon = title.rfind('::')
                if dcolon != -1:
                    title = title[dcolon + 2:]
        return title, target


class CPPDomain(Domain):
    """C++ language domain."""
    name = 'cpp'
    label = 'C++'
    object_types = {
        'class':    ObjType(l_('class'),    'class'),
        'function': ObjType(l_('function'), 'func'),
        'member':   ObjType(l_('member'),   'member'),
        'type':     ObjType(l_('type'),     'type')
    }

    directives = {
        'class':        CPPClassObject,
        'function':     CPPFunctionObject,
        'member':       CPPMemberObject,
        'type':         CPPTypeObject,
        'namespace':    CPPCurrentNamespace
    }
    roles = {
        'class':  CPPXRefRole(),
        'func' :  CPPXRefRole(fix_parens=True),
        'member': CPPXRefRole(),
        'type':   CPPXRefRole()
    }
    initial_data = {
        'objects': {},  # fullname -> docname, objtype
    }

    def clear_doc(self, docname):
        for fullname, (fn, _, _) in self.data['objects'].items():
            if fn == docname:
                del self.data['objects'][fullname]

    def resolve_xref(self, env, fromdocname, builder,
                     typ, target, node, contnode):
        def _create_refnode(expr):
            name = unicode(expr)
            if name not in self.data['objects']:
                return None
            obj = self.data['objects'][name]
            if obj[1] not in self.objtypes_for_role(typ):
                return None
            return make_refnode(builder, fromdocname, obj[0], obj[2],
                                contnode, name)

        parser = DefinitionParser(target)
        try:
            expr = parser.parse_type().get_name()
            parser.skip_ws()
            if not parser.eof or expr is None:
                raise DefinitionError('')
        except DefinitionError:
            refdoc = node.get('refdoc', fromdocname)
            env.warn(refdoc, 'unparseable C++ definition: %r' % target,
                     node.line)
            return None

        parent = node['cpp:parent']

        rv = _create_refnode(expr)
        if rv is not None or parent is None:
            return rv
        parent = parent.get_name()

        rv = _create_refnode(expr.prefix(parent))
        if rv is not None:
            return rv

        parent, name = parent.split_owner()
        return _create_refnode(expr.prefix(parent))

    def get_objects(self):
        for refname, (docname, type, theid) in self.data['objects'].iteritems():
            yield (refname, refname, type, docname, refname, 1)
