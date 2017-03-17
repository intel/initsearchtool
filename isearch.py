#!/usr/bin/env python
"""This tool allows for the searching and verification of Android init.rc scripts.

The tool internally consists of a plug-in commandlet system.

Run the help for a list of supported plugins and their capabilities.

Further documentation can be found in the README.
"""

#pylint: disable=too-many-lines

import argparse
import copy
import re
import sys
import xml.sax


# pylint: disable=too-few-public-methods
class NumberMatcher(object):
    '''NumberMatchers are used when building a number search string option
    from the command line. This is used when you want to search
    for things like, "find all services with priorities greater than
    -20. Regex searches suck for this.

    Supported matcher strings are:
      literal : number eg: "-20"
                Literal is the same as an equality search.
      equality operator:
        equality: "==<number>" eg: "==-20".
        not equal: "!=<number>" eg: "!=-20".
        less than: "<<number>" eg: "<-20".
        less than or equal to: "<=<number>" eg: "<=-20".
        greater than: "><number>" eg: ">-20".
        greater than or equal to: ">=<number>" eg: ">=-20".

    Args:
        matcher (str): A match pattern search string.
        lazy_regex (bool): unused, required for interface.

    Exceptions:
        ValueError: With a descriptive error message set.

    Example:
        n = NumberMatcher("<=4", False)
        n.match(1) : SubMatches()
        n.match(4) : SubMatches()
        n.match(5) : None

        Where SubMatches() objects mean it was a match.
    '''

    # This has to fit an interface, so we pass lazy_regex
    # even though it is unused. Also, too many branches
    # complaint is a bit much here...
    # pylint: disable=unused-argument,too-many-branches
    def __init__(self, matcher, lazy_regex):

        # it can be a range
        if ',' in matcher:
            self._handle_range(matcher)
        else:
            self._handle_operator(matcher)

    def _handle_operator(self, matcher):

        # coerce a raw number to an ==n operator
        try:
            int(matcher, 0)
            self._operator = "=="
            matcher = '==' + matcher
        except ValueError:
            pass

        # order matters, check longest first!
        if matcher.startswith("=="):
            self._operator = "=="
        elif matcher.startswith("!="):
            self._operator = "!="
        elif matcher.startswith("<="):
            self._operator = "<="
        elif matcher.startswith(">="):
            self._operator = ">="
        elif matcher.startswith(">"):
            self._operator = ">"
        elif matcher.startswith("<"):
            self._operator = "<"
        else:
            raise ValueError('Unknown operator in "%s"' % matcher)

        number = matcher[len(self._operator):]
        try:
            self._values = int(number, 0)
        except ValueError:
            raise ValueError('Attempted operator "%s", but failed.'
                             'Expected a number, got: "%s",'
                             'perhaps invalid operator?'
                             'Use quotes, the shell steals' %
                             (self._operator, number))

    def _handle_range(self, matcher):

        chunks = matcher.split(',')
        if len(chunks) != 2:
            sys.exit('Expected valid range x,b no spaces, got: "%s"' % matcher)

        found_range = []
        for item in chunks:
            try:
                found_range.append(int(item, 0))
            except ValueError:
                sys.exit('Expected range number to be a number, got: "%s"' %
                         item)

        # if they are equal, coerce to ==n format
        if found_range[0] == found_range[1]:
            self._values = found_range[0]
            self._operator = "=="
            # nothing more to do
            return

        # range(a, b) expects a < b or returns empty range
        # thus sort so a < b
        if found_range[1] < found_range[0]:
            tmp = found_range[0]
            found_range[0] = found_range[1]
            found_range[1] = tmp

        # set the range
        self._values = range(found_range[0], found_range[1])
        self._operator = "in"

    def match(self, number):
        """Matches a number based on the initialized search option.

        Args:
            number (str|int): The number to compare to.
            if it is a str, it is converted to an int internall via int(number, 0)

        Returns:
            A MatchObject like re.match().
        """
        number = number if isinstance(number, int) else int(number, 0)

        match = None

        # return some coerced match object
        if self._operator == '<' and number < self._values:
            match = re.match(str(number), str(number))
        elif self._operator == '<=' and number <= self._values:
            match = re.match(str(number), str(number))
        elif self._operator == '==' and number == self._values:
            match = re.match(str(number), str(number))
        elif self._operator == '!=' and number != self._values:
            match = re.match(str(number), str(number))
        elif self._operator == '>' and number > self._values:
            match = re.match(str(number), str(number))
        elif self._operator == '>=' and number >= self._values:
            match = re.match(str(number), str(number))
        elif self._operator == 'in' and number in self._values:
            match = re.match(str(number), str(number))

        return match


# pylint: disable=too-few-public-methods
class RegexMatcher(object):
    '''RegexMatchers are used when building a matcher that
    is to be used for regex searches.

    Args:
        regex_str (str): A match pattern search string.
        lazy_regex (bool): Whether or not the search is lazy.
          See for more info: https://goo.gl/rNvUma

    Example:
        n = RegexMatcher("foo", False)
        n.match("foo bar") : SubMatches()
        n.match("bar") : None

        n = RegexMatcher("foo", True)
        n.match("foo bar") : None
        n.match("bar") : None

        Where SubMatches() objects mean it was a match.
    '''

    def __init__(self, regex_str, lazy_regex):

        if isinstance(regex_str, bool):
            regex_str = str(regex_str).lower()

        if not lazy_regex:
            # Greedify the search if not lazy
            regex_str = '.*' + regex_str + '.*'

        # Anchor the regex
        regex_str = '^' + regex_str + '$'
        self._matcher = re.compile(regex_str)

    def match(self, other):
        """Matches a string based on the initialized search regex.

        Args:
            number (str): The string to compare.

        Returns:
            A MatchObject like re.match().
        """
        return self._matcher.match(other)


class SubMatches(object):
    '''SubMatches is a container class that keeps
    the section submatches grouped together.
    '''

    def __init__(self, section, submatches):
        self._section = section
        self._submatches = submatches

    @property
    def submatches(self):
        '''The submatches for a section.

        Returns
         The submatches
        '''
        return self._submatches

    @property
    def section(self):
        '''The section name.

        Returns
         The section name
        '''
        return self._section

    def __hash__(self):
        return hash(self._section)

    # equality operators need access to internal fields
    # by design.
    # pylint: disable=protected-access
    def __eq__(self, other):
        if self._section != other._section:
            return False

        # their must be a match for everything in other._submatches in self or
        # not equal
        selfsubs = self._submatches
        othersubs = other._submatches
        for othersub in othersubs:
            if othersub not in selfsubs:
                return False

        return True

    def write(self, filep=sys.stdout, lineno=False, tidy=False):
        '''Writes a match to a file.

        Args:
            filep(file): The file to write to, defaults to stdout.
            lineno(bool): True to print line numbers, false to not. Default is false.
            tidy(bool): False to print the whole section on a match, True to print just the
                        matching parts of the service. Default is False.
        '''
        section = self.section
        if not tidy:
            section.write(filep=filep, lineno=lineno)
        else:
            filep.write(
                section.format(
                    lineno=lineno, sub_matches=self._submatches))

    def match(self, other):
        '''Match on another match object by calling the sections _match() routine.

        Returns:
            A SubMatches object on a match or None if not matches.
        '''
        return self._section.match(other, False)

    def filter(self, match):
        '''Filter out arguments that were not matched.

        Returns:
            True if it was filtered out or False otherwise.
        '''
        left = {}
        subs = self._submatches
        fltr = match.submatches
        # The filter might contain arguments that were not matched, ie the search might
        # have been on socket (so sub_matches is only socket_ but the filter might include
        # args. We only filter on what the intersection between the two are.
        fltr_keys = set(fltr.keys())
        sub_keys = set(subs.keys())
        keys = fltr_keys & sub_keys

        # Search each key section_keyword_values in the filter (white list exception)
        for key in keys:
            section_keyword_values = fltr[key]

            # Keep a copy of the list associated with the key, we remove the
            # items from the list when a filter matches
            sub = list(subs[key].values)

            # For each line in the exceptions filter, we compile it
            # as a possible regex and search the sub_matches with it.
            for value in section_keyword_values.values:
                # If we find a match we remove it from the copy of sub_matches
                if value in subs[key].values:
                    sub.remove(value)

            # If anything is left in the list of things, we add it as 'left', ie the delta
            if len(sub) > 0:
                left[key] = sub

        self._submatches = left

        # The filter returns true if it was filtered out, ie nothing left, else if their is a delta
        # False is returned.
        return not bool(left)


class SectionValue(object):
    '''Container class for storing a keywords value and line number found.'''

    def __init__(self, value, lineno=-1):
        self.value = value
        self.lineno = lineno

    def __str__(self):
        return str(self.value).lower() if isinstance(self.value,
                                                     bool) else self.value

    def __eq__(self, other):
        return self.value == other.value


class SectionKeywordValues(object):
    '''An object of this class is a section keyword item with its corresponding values

    service foo bar
        oneshot        <- this is a SectionKeywordValues
        onrestart foo  <- this is a SectionKeywordValues
        onrestart boo  <-|
        onrestart coo  <-|


    After parsing this:
        SecionKeywordValues for oneshot would be a list: [ SectionValue(True, 2) ]
        SecionKeywordValues for onrestart would be a list:
            [ SectionValue(foo, 3), SectionValue(boo, 4), SectionValue(coo, 5) ]

    There are numerous attributes to used when setting this up that affect things
    like print behavior.

    Args:
        keyword(str) : The keyword, like oneshot.
        default(type) : What is the default type, you can pass things like str, None or int
          This is used to indicate the expected type, and what the value is. For instance,
          the service keyword "user" uses the value "root" for this.
        is_appendable(bool): Is this expected to have one keyword per section, or multiple?
        is_default_printable(bool): Should a default value be printed in output?
        matcher: What matcher should be used to compare it with found text? The default is
          RegexMatcher, but anything implementing that interface can be passed.

    Example:
        SectionKeywordValues("user", default='root')
    '''

    # pylint: disable=too-many-arguments
    def __init__(self,
                 keyword,
                 default=None,
                 is_appendable=False,
                 is_default_printable=False,
                 matcher=RegexMatcher):

        self._keyword = keyword
        self._is_appendable = is_appendable
        self._is_set = False
        self._is_default_printable = is_default_printable
        self._default_type = type(default)
        self._values = [SectionValue(default)] if default else []
        self._matcher = matcher

    def __len__(self):
        return len(self._values)

    def __str__(self):
        return self._keyword

    def push(self, value, lineno):
        '''Adds a value and line number to a keyword.
        Args:
            value(str): The value to append, can be anything for type bool, as push
              is a implicit "True" for value.
        lineno (int): The line number the value for the keyword was found on.
        '''
        if not self._is_appendable and self._is_set:
            raise Exception("Expected %s keyword to only appear once" %
                            self._keyword)

        # some items don't have values, like bool switches
        if self._default_type == bool:
            value = True

        item = SectionValue(value, lineno)
        if self._is_appendable:
            self._values.append(item)
        else:
            self._values = [item]

        self._is_set = True

    def reset(self):
        '''Reset's a Section to it's initialized state'''
        self._values = []
        self._is_set = False
        return self

    @property
    def keyword(self):
        '''The keyword (str) associated with the section'''
        return self._keyword

    @property
    def type(self):
        '''The type (type) associated with the section'''
        return self._default_type

    @property
    def is_appendable(self):
        '''Whether or not a keyword is appendable. An appendable keyword is one that is expected
        multiple times in a section. For instance, the onrestart keyword for a Service can appear
        multiple times and thus is appendable.'''
        return self._is_appendable

    @property
    def is_set(self):
        '''Whether or not it's been set or is still on a default value'''
        return self._is_set

    @property
    def matcher(self):
        '''The matcher registered for the keyword.'''
        return self._matcher

    def is_printable(self):
        '''Whether or not the value should be printed.
        A value should be printed if it has been set off
        of the default or the default value is printable.

        Return:
          True if printable, False otherwise.
        '''
        return self._is_set or self._is_default_printable

    @property
    def values(self):
        '''The value list of SectionValue objects.

        Returns:
            A list of SectionValue objects: [ SectionValue, ... ]
        '''

        return self._values


class Section(object):
    '''Base class for all Sections. An init sections are things like service and on keywords.'''
    _KW_ARGS = 'args'

    _keywords = {_KW_ARGS: SectionKeywordValues(_KW_ARGS, is_appendable=True)}

    # pylint: disable=too-many-arguments
    def __init__(self, name, args, path, lineno, keywords=None):
        self._name = name
        self._lineno = lineno
        self._path = path

        self._option_strip = []
        self._no_print = Section._keywords.keys()

        self._option_map = copy.deepcopy(Section._keywords)
        if keywords != None:
            self._option_map.update(copy.deepcopy(keywords))

        self._option_map[Section._KW_ARGS].push(args, lineno)

    def write(self, filep=sys.stdout, lineno=False):
        '''Writes a formated version of itself to a file.
        Just calls Format and writes to the file.

        Args:
            filep (file): the file to write to. Defaults to stdout.
            lineno (bool): True to print line numbers, False not to. Defaults to False.
        '''
        filep.write(self.format(lineno=lineno))

    def get_header(self):
        '''Retrieves a formated version known as the header. A section header

        Returns:
            A a formated header as a str.
        '''
        fmtout = self._path + ':\n'
        fmtout += str(self._lineno) + ':\t' + self._name + ' '
        fmtout += ' '.join(
            [x.value for x in self._option_map[Section._KW_ARGS].values])
        return fmtout

    def format(self, lineno=False, sub_matches=None):
        '''Formats a section header.

        Args:
            lineno (bool): True to include line numbers, false otherwise. Defaults to false.
            sub_matches ({ keyword (str) : [ SectionKeyWords ] }): The dictionary of submatches.

        Returns:
            A formated str.
        '''
        fmtout = self.get_header() + '\n'

        if sub_matches is None:
            sub_matches = self._option_map

        # convert dict of keyword : [ SectionKeyWords ] to a line order sorted list
        items = []
        for skws in sub_matches.values():
            if skws.keyword in self._no_print:
                continue

            if not skws.is_printable():
                continue

            items.extend([(skws.keyword, x) for x in skws.values])

        items.sort(key=lambda x: x[1].lineno)

        for (key, section_val) in items:
            if lineno:
                fmtout += str(section_val.lineno) + ':'
            fmtout += '\t\t'
            is_bool = isinstance(section_val.value, bool)
            fmtout += key
            if not is_bool:
                fmtout += ': ' + section_val.value
            fmtout += '\n'

        return fmtout

    def match(self, other, lazy_regex):
        '''Matches one section to another.

        Args:
            other (Section): The other section to match to.
            lazy_regex: True if the regex's should be lazy, False for greedy regex's.

        Returns:
            A SubMatches object on a match or None on no match.
        '''
        (comparator, submatches) = self._section_cmp(other, lazy_regex)
        if comparator >= 0:
            return SubMatches(self, submatches)
        else:
            return None

    @property
    def name(self):
        '''A section name, as a str, like "service" or "on". This is really just a keyword, but
        a keyword for a whole section, not just a section item.'''
        return self._name

    @property
    def lineno(self):
        '''The line number, as an int, that the section started on.'''
        return self._lineno

    def get_args(self):
        '''The argument values for the section name as a list of SectionKeywordValues'''
        return self._option_map[Section._KW_ARGS]

    # pylint: disable=unused-argument,no-self-use
    def push(self, value, lineo):
        '''Implement me if you subclass me.
        I add a value to the SectionKeywordValues internal object. Doing any formatting
        and error detection along the way.

        Raises:
            NotImplementedError: You must subclass this class for push.
        '''
        raise NotImplementedError('Implement: push(value, lineno)')

    @staticmethod
    def get_keywords():
        '''Retrieves the list of keywords for this section. This is not the section name, but rather
        the keyword options valid for a section. For instance, for service, user is a valid keyword
        option.

        Returns:
            The keywords as a list of strings: [ str, ... ]
            Eg.) [ "user", "group", "onrestart", ... ]
        '''

        return Section.get_keymap().keys()

    @staticmethod
    def get_keymap():
        '''Returns the keymap of a section. The keymap is the major data structure, it is defined
        as follows:

        { "keyword" : SectionKeyWordValues }

        The keymap is static and deep copied on initialization of a Section. Be careful when using
        this structure.

        Returns:
            The section keymap.
        '''
        return Section._keywords

    # This is one of the most complicated routines, lots of locals
    # increased readability.
    # pylint: disable=too-many-locals
    def _section_cmp(self, search_dict, lazy_regex):

        section_options = self._option_map
        section_keys = section_options.keys()
        search_keys = set(search_dict.keys())

        submatches = {}

        # For each key in the section map (ie things I am searching)
        # and the search dictionary
        # ...
        for search_key, search_values in search_dict.iteritems():
            section_keyword_values = section_options[search_key]

            matcher_class = section_keyword_values.matcher
            section_vals = section_keyword_values.values

            # empty fields are a no-match situation
            if len(section_vals) == 0:
                return (-1, submatches)

            # Search values is allowed to be a string or list of string, normalize
            if not isinstance(search_values, list):
                search_values = [search_values]

            found = 0
            for section_val in section_vals:

                section_val_str = str(section_val)

                for search_term in search_values:

                    matcher = matcher_class(search_term, lazy_regex)

                    result = matcher.match(section_val_str)
                    if result:
                        found = found + 1
                        if search_key not in submatches:
                            submatches[search_key] = copy.deepcopy(
                                section_keyword_values).reset()
                        submatches[search_key].push(section_val.value,
                                                    section_val.lineno)

            # If i didn't find as many items as I was looking for
            # it's not a match
            if found < len(search_values):
                # no match
                return (-1, submatches)

        # If section map had more keys, then its a super set
        # of search dictionary, else equal
        comparator = 0 if len(section_keys) == len(search_keys) else 1
        comparator = (comparator, submatches)
        return comparator

    @staticmethod
    def _join(parent, self):
        new_dict = dict(parent)
        new_dict.update(self)
        return new_dict


class OnSection(Section):
    '''The on section in init.rc files. A subclass of Section.'''

    _KW_COMMAND = 'command'

    _keywords = Section._join(
        Section._keywords,
        {_KW_COMMAND: SectionKeywordValues(
            _KW_COMMAND, is_appendable=True)})

    def __init__(self, *args, **kwargs):
        kwargs = dict(kwargs)
        kwargs['keywords'] = OnSection._keywords
        super(OnSection, self).__init__(*args, **kwargs)
        self._option_strip.append(OnSection._KW_COMMAND)

    def push(self, line, lineno):
        self._option_map[OnSection._KW_COMMAND].push(line, lineno)

    @staticmethod
    def get_keywords():
        return OnSection.get_keymap().keys()

    @staticmethod
    def get_keymap():
        return OnSection._keywords


class ServiceSection(Section):
    '''The service section in init.rc files. A subclass of Section.'''

    _KW_CONSOLE = 'console'
    _KW_CRITICAL = 'critical'
    _KW_DISABLED = 'disabled'
    _KW_SET_ENV = 'setenv'
    _KW_GET_ENV = 'getenv'
    _KW_SOCKET = 'socket'
    _KW_USER = 'user'
    _KW_GROUP = 'group'
    _KW_SECLABEL = 'seclabel'
    _KW_ONESHOT = 'oneshot'
    _KW_CLASS = 'class'
    _KW_IOPRIO = 'ioprio'
    _KW_ONRESTART = 'onrestart'
    _KW_WRITEPID = 'writepid'
    _KW_KEYCODES = 'keycodes'
    _KW_PRIORITY = 'priority'
    _KW_START = 'start'

    _keywords = (Section._join(
        Section._keywords, {
            _KW_CONSOLE: SectionKeywordValues(
                _KW_CONSOLE, default=False),
            _KW_CRITICAL: SectionKeywordValues(
                _KW_CRITICAL, default=False),
            _KW_DISABLED: SectionKeywordValues(
                _KW_DISABLED, default=False),
            _KW_SET_ENV: SectionKeywordValues(
                _KW_SET_ENV, is_appendable=True),
            _KW_GET_ENV: SectionKeywordValues(
                _KW_GET_ENV, is_appendable=True),
            _KW_SOCKET: SectionKeywordValues(
                _KW_SOCKET, is_appendable=True),
            _KW_USER: SectionKeywordValues(
                _KW_USER, default='root', is_default_printable=True),
            _KW_GROUP: SectionKeywordValues(
                _KW_GROUP, default='root', is_default_printable=True),
            _KW_SECLABEL: SectionKeywordValues(_KW_SECLABEL),
            _KW_ONESHOT: SectionKeywordValues(
                _KW_ONESHOT, default=False),
            _KW_CLASS: SectionKeywordValues(
                _KW_CLASS, default='default'),
            _KW_IOPRIO: SectionKeywordValues(_KW_IOPRIO),
            _KW_ONRESTART: SectionKeywordValues(
                _KW_ONRESTART, is_appendable=True),
            _KW_WRITEPID: SectionKeywordValues(
                _KW_WRITEPID, is_appendable=True),
            _KW_KEYCODES: SectionKeywordValues(
                _KW_KEYCODES, is_appendable=True),
            _KW_PRIORITY: SectionKeywordValues(
                _KW_PRIORITY, default=0, matcher=NumberMatcher),
            _KW_START: SectionKeywordValues(_KW_START),
        }))

    def __init__(self, *args, **kwargs):
        kwargs = dict(kwargs)
        kwargs['keywords'] = ServiceSection._keywords
        super(ServiceSection, self).__init__(*args, **kwargs)
        self._group_cleared = False

    def push(self, line, lineno):

        chunks = line.split()
        keyword = chunks[0]

        args = ' '.join(chunks[1:])

        if keyword not in self._option_map:
            sys.exit('Invalid service option: "%s" on line: %d' %
                     (keyword, lineno))

        self._option_map[keyword].push(args, lineno)

    @staticmethod
    def get_keywords():
        return ServiceSection.get_keymap().keys()

    @staticmethod
    def get_keymap():
        return ServiceSection._keywords


# Complains about CAPS for statics like ON
# pylint: disable=invalid-name
class InitParser(object):
    '''This class parses the Android init.rc files  into a data structure for general consumption
    by commandlets.

    Args:
        files ([ str, ... ]): A list of file paths to init.rc files to parse.
    '''
    ON = 'on'
    SERVICE = 'service'
    IMPORT = 'import'

    _section_map = {ON: OnSection, SERVICE: ServiceSection, IMPORT: Section}

    def __init__(self, files):
        self._files = files
        self._items = {}

        for key in InitParser._section_map:
            self._items[key] = []

        for pfile in self._files:
            self._handle_file(pfile)

    def _handle_file(self, path):
        with open(path) as open_file:
            current_section = None
            lineno = 0
            line = ''
            for line_segment in open_file:
                line_segment = line_segment.strip()
                lineno = lineno + 1

                # Skip empty (whitespace only) lines
                if len(line_segment) == 0:
                    continue

                # Skip comments
                if line_segment.startswith('#'):
                    continue

                # Ignore pystache conditional lines
                if line_segment.startswith('{{'):
                    continue

                # handle line folding
                if line_segment.endswith('\\'):
                    line += line_segment + ' '
                    continue

                # process the complete line
                line += line_segment

                chunks = line.split()
                section_name = chunks[0]

                # is the keyword a _name?
                if section_name in InitParser._section_map:
                    if current_section != None:
                        self._items[current_section.name].append(
                            current_section)

                    args = ' '.join(chunks[1:])
                    current_section = self._section_factory(chunks[0], args,
                                                            path, lineno)

                # its not a valid section name but were parsing section options
                elif current_section != None:
                    try:
                        current_section.push(line, lineno)
                    except Exception as e:
                        raise type(e)(e.message +
                                      ' while parsing file "%s on line %d"' % (
                                          path, lineno))

                # clear line, repeat
                line = ''

            # when the file ends, we need to push the last section
            # being parsed if set (ie dont push on blank file)
            if current_section != None:
                self._items[current_section.name].append(current_section)

    def _section_factory(self, section_name, section_args, path, lineno):

        if section_name not in self._section_map:
            raise Exception('Error in name ' + section_name + ' line: ' + str(
                lineno))

        return self._section_map[section_name](section_name, section_args, path,
                                               lineno)

    def search(self, section_name, search, lazy_regex=False):
        '''Searches the parsed init.rc data structure for a match.

        The search dict is as described:
        A dictionary of section keywords in string form, mapping to a list, or string of search
        strings. Search strings can be strings supported by the NumberMatcher or RegexMatcher
        classes.

        Args:
            section_name: The section to search, like "on" or "service".
            search ({ str : [ str, ... ] }): the search dict.
            lazy_regex(bool): True for lazy regex's False otherwise. Defaults to False.

        Returns:
            A list of matched Section objects, ie [ Section, ... ]

        Example:
            To search the service section for user foo and group foo and bar that has a
            priority greater than 0:

            d = {
              'user'     : 'foo'
              'group'    : [ 'foo', 'bar' ]
              'priority' : '>0'
            }

            p = InitParser(['path/to/init.rc'])
            matches = p.search('service', d, False)

        '''

        found = []
        section = self._items[section_name]

        for x in section:
            m = x.match(search, lazy_regex)
            if m:
                found.append(m)
        return found

    def write(self, filep=sys.stdout, lineno=False):
        '''Write the parsed init.rc structures to a file.

        Args:
            filep (file): The file to write to. Defaults to stdout.
            lineno (bool): True to print line numbers, False otherwise.
        '''

        things = []
        for section_name in InitParser._section_map.keys():
            section = self._items[section_name]
            for x in section:
                things.append(x)

        things.sort(key=lambda sec: sec.lineno)

        for x in things:
            x.write(filep=filep, lineno=lineno)
            filep.write('\n')

    @staticmethod
    def get_section(name):
        '''Given a section name aka keyword (like on, or service), returns the class for the
        section.

        Args:
            name (str): The section name, "like" on or "service".

        Returns:
            The Section class, eg: ServiceSection.
        '''
        return InitParser._section_map[name]

    @staticmethod
    def get_sectons():
        '''Returns the raw section map as a dict.

        Returns:
            A dict of section names to section classes: { "str" : Section }.
        '''

        return InitParser._section_map

    @staticmethod
    def _merge_dicts(l):
        r = {}
        for d in l:
            r.update(d)
        return r


class Test(object):
    '''Creates a Test from the XML file. It processes test tags.

    Args:
        arg_dict (dict): Passed the argument dictionary from the XML parser.
    '''

    # complains about not using args
    # pylint: disable=unused-argument
    def __init__(self, arg_dict):
        self._name = 'unnamed' if 'name' not in arg_dict else arg_dict['name']
        self._section = arg_dict['section']
        self._searches = []
        self._exceptions = []
        self.violators = None

        self._current = None

    # complains about not using args and arg_dict
    # pylint: disable=unused-argument
    def start_search(self, *args, **kwargs):
        '''Given the opening tag for search.'''

        self._current = dict({'section': self._section})

    def start_exception(self, *args, **kwargs):
        '''Given the opening tag for exception'''
        self._current = dict()

    def end_search(self):
        '''Given the closing tag for search'''
        self._searches.append(self._current)
        self._current = None

    def end_exception(self):
        '''Given the closing tag for exception'''
        # self._current['section'] = self._section
        self._exceptions.append(self._current)
        self._current = None

    def append_keyword(self, search):
        '''Appends an element to the current parser state.
        The parser could be in a search or except block, and
        it's adding keywords to that section. Keywords are
        the same as section keywords.
        '''
        for k, v in search.iteritems():
            if k not in self._current:
                self._current[k] = []
            self._current[k].append(v)

    @property
    def exceptions(self):
        '''The list of exceptions'''
        return self._exceptions

    @property
    def searches(self):
        '''The list of searches'''
        return self._searches

    def write(self, filep=sys.stdout, lineno=False):
        '''Writes the result of a test to a file

        Args:
            filep (file): The file to write to. Defaults to stdout.
            lineno (bool): True to provide line numbers, False otherwise.
        '''

        filep.write('test: ' + self._name + '\n')
        for x in self._searches:
            filep.write('\tsearch: ' + str(x) + '\n')

        for x in self._exceptions:
            filep.write('\texcept: ' + str(x) + '\n')

    @property
    def name(self):
        '''The name of the test as set via the name attribute of the test tag.'''
        return self._name


class AssertParser(xml.sax.ContentHandler):
    '''Parses an Assert xml file. An assert xml file contains assertions that
    one would like to make about a particular init.rc file.

    Example structure:
    <suite>
      <test name="No world sockets" section="service">
        <search>
          <keyword socket="[0-9]{3}[2-7]"/>
        </search>
        <except>
          <!-- Except logd with these explicit sockets -->
          <keyword args="logd /system/bin/logd"/>
          <keyword socket="logd stream 0666 logd logd"/>
          <keyword socket="logdr seqpacket 0666 logd logd"/>
          <keyword socket="logdw dgram 0222 logd logd"/>
        </except>
      </test>
    </suite>
    '''

    def __init__(self, *args, **kwargs):
        xml.sax.ContentHandler.__init__(self, *args, **kwargs)

        self._tests = []
        self._current = None

    def startElement(self, name, attrs):

        # Make a straight python dict from attrs
        attrs = dict(attrs)

        if name == 'test':
            self._current = Test(attrs)

        elif name == 'search':
            if 'lazy' not in attrs:
                attrs['lazy'] = True

            self._current.start_search(**attrs)

        elif name == 'keyword':
            self._current.append_keyword(attrs)

        elif name == 'except':
            self._current.start_exception(attrs)

        elif name == 'suite':
            pass

        else:
            raise Exception('Unknown Keyword: ' + name)

    def endElement(self, name):
        if name == 'test':
            self._tests.append(self._current)
            self._current = None

        elif name == 'search':
            self._current.end_search()

        elif name == 'except':
            self._current.end_exception()

    def __iter__(self):
        return iter(self._tests)


class commandlet(object):
    '''Decorator class for commandlet. You can add commandlets to the tool with this decorator.'''

    _commandlets = {}

    def __init__(self, cmd):
        self._cmd = cmd

        if cmd in commandlet._commandlets:
            raise Exception('Duplicate command name' + cmd)

        commandlet._commandlets[cmd] = None

    def __call__(self, cls):
        commandlet._commandlets[self._cmd] = cls()
        return cls

    @staticmethod
    def get():
        '''Retrieves the list of registered commandlets.'''
        return commandlet._commandlets


class Command(object):
    '''Baseclass for a commandlet. Commandlets shall implement this interface.'''

    def generate_options(self, group_parser):
        '''Adds it's options to the group parser. The parser passed in is a result from
        calling add_argument_group(ArgumentGroup): https://docs.python.org/2/library/argparse.html

        Args:
            group_parser(): The parser to add options too.

        '''
        raise NotImplementedError('Implement: generate_options')

    def __call__(self, init_parser, args):
        '''Called when the user selects your commandlet and passed the dictionary of arguments.

        Arguments:
            init_parser (InitParser): The init parser.
            args ({str: arg}: The dictionary version of the attrs of the parser.
                The args value is obtained by:
                args = opt_parser.parse_args()
                args = vars(args)

                So to access args just do args['name']
        '''
        raise NotImplementedError('Implement: __call__')


@commandlet("print")
class PrintCommand(Command):
    '''
	Dumps the contents of the init.rc file to stdout
	'''

    # This has to adhere to an interface.
    # pylint: disable=no-self-use
    def generate_options(self, group_parser):
        group_parser.add_argument(
            '--lineno',
            action='store_true',
            help='Dump line numbers with keywords')

    def __call__(self, init_parser, args):
        init_parser.write(lineno=args['lineno'])


@commandlet("search")
class SearchCommand(Command):
    '''
	Searches the init.rc for the specified section for a specified keyword regex.
	'''

    def __init__(self):
        self._opts = None

    def generate_options(self, group_parser):

        options = self._gen_opts()

        for opt in options:
            args = opt[0]
            args = [args] if isinstance(args, str) else args
            kwargs = opt[1] if len(opt) == 2 else {}
            group_parser.add_argument(*args, **kwargs)

    # pylint: disable=too-many-locals
    def __call__(self, init_parser, args):

        # Get the option map and filter it for the selected
        # section

        section_name = args['section']

        lazy_search = False
        if 'lazy' in args:
            lazy_search = args['lazy']
            del args['lazy']

        tidy = False
        if 'tidy' in args:
            tidy = args['tidy']
            del args['tidy']

        lineno = False
        if 'lineno' in args:
            lineno = args['lineno']
            del args['lineno']

        count = False
        if 'count' in args:
            count = args['count']
            del args['count']

        del args['section']

        # This option is not exposed externally to the commandline
        issilent = False
        if 'silent' in args:
            issilent = args['silent']
            del args['silent']

        section = InitParser.get_section(section_name)

        # validate all 'set' options are valid per section
        # If they are not set or are False (store_true action)
        # we remove them. This would be simpler if argparse supported
        # subsub parsers.
        d = {k: v for k, v in args.items() if v != None}
        unknown = set(d.keys())
        valid = set(section.get_keywords())
        invalid = unknown - valid

        if len(invalid) > 0:
            raise Exception("Invalid arguments found: " + str(invalid))

        # A list of match objects
        found = init_parser.search(section_name, d, lazy_search)

        if issilent:
            return found

        if count:
            print len(found)
            return found

        for m in found:
            m.write(lineno=lineno, tidy=tidy)
            sys.stdout.write('\n')

        return found

    def _gen_opts(self):
        if self._opts != None:
            return self._opts

        opts = []
        sections = InitParser.get_sectons()
        s = 'Searches a section given a section name {' + (
            ','.join(sections.keys()) + '}')
        opts.append(('--section', {'help': s, 'required': True}))
        opts.append(('--lazy', {
            'action': 'store_true',
            'help':
            'The default is a greedy search, set this to force lazy searches.'
        }))
        opts.append(('--tidy', {
            'action': 'store_true',
            'help':
            'Set this flag to only print matching keywords for the section'
        }))
        opts.append(('--lineno', {
            'action': 'store_true',
            'help': 'Print line numbers on matches'
        }))
        opts.append(('--count', {
            'action': 'store_true',
            'help': 'Print the number of matches'
        }))

        seen = {}
        for n in sections:
            s = sections[n]
            for section_key_words in s.get_keymap().values():
                if section_key_words not in seen:
                    seen[section_key_words] = True

                    key_word = str(section_key_words)
                    is_appendable = section_key_words.is_appendable
                    istype = section_key_words.type

                    if is_appendable:
                        h = (
                            'argument is a valid regex. Multiple specifications of the option'
                            ' result in the logical and of all specified options.'
                        )

                        opts.append(('--' + key_word, {
                            'help': 'Section: ' + key_word + '. ' + h,
                            'action': 'append'
                        }))

                    elif istype is bool:
                        h = (
                            'true if specified. Multiple specifications of the option result in'
                            ' the last option specified used.')
                        opts.append(('--' + key_word, {
                            'help': 'Section: ' + key_word + '. ' + h,
                            'action': 'store_const',
                            'const': True,
                            'dest': key_word
                        }))
                        opts.append(('--not' + key_word, {
                            'help': 'Section: ' + key_word + '. ' + h,
                            'action': 'store_const',
                            'const': False,
                            'dest': key_word
                        }))

                    elif istype is int:
                        h = (
                            'argument is a valid int, equality expression(<x|<=x|==x|>=x|>x or'
                            ' integer range as a,b. Use quotes to deal with shells. Multiple'
                            ' specifications of the option result in the last option specified'
                            ' used.')
                        opts.append(('--' + key_word, {
                            'help': 'Section: ' + key_word + '. ' + h,
                            'action': 'store'
                        }))

                    else:
                        h = (
                            'argument is a valid regex. Multiple specifications of the option'
                            ' result in the last option specified used.')
                        opts.append(('--' + key_word, {
                            'help': 'Section: ' + key_word + '. ' + h,
                            'action': 'store',
                            'dest': key_word
                        }))

        self._opts = opts
        return opts


@commandlet("verify")
class VerifyCommand(Command):
    '''
	Verifies the contents of the init.rc against a file of assertions and white-list exceptions
	'''

    def __init__(self):
        self._init_parser = None

    # adhere to an interface
    # pylint: disable=no-self-use
    def generate_options(self, group_parser):
        group_parser.add_argument(
            '--assert',
            help='Verifies an init.rc file against a list of rules',
            action='append',
            required=True)
        group_parser.add_argument(
            '--gen',
            help='Generate a list of exceptions for tests.',
            action='store_true')

    def __call__(self, init_parser, args):
        verifier = AssertParser()
        parser = xml.sax.make_parser()
        parser.setContentHandler(verifier)

        for p in args['assert']:
            with open(p, 'r') as f:
                parser.parse(f)

        genmode = False
        if 'gen' in args:
            genmode = args['gen']
            del args['gen']

        # Hidden option for testing
        silent = args['silent'] if 'silent' in args else False

        self._init_parser = init_parser

        failed_tests = []
        # find them all!
        for t in verifier:
            e = t.exceptions
            s = t.searches
            v = self._violations_search(s, e)
            if len(v) > 0:
                t.violators = v
                failed_tests.append(t)

        if silent:
            return failed_tests

        if not genmode:
            VerifyCommand._print(failed_tests)
            sys.exit(len(failed_tests))
        else:
            VerifyCommand._gen(failed_tests)

    @staticmethod
    def _gen(failed_tests):

        kws = "	<keyword %s ='%s' />\n"

        for t in failed_tests:
            sys.stderr.write('Failed test(' + t.name + '):\n')
            for violator in t.violators:

                # We print args + keyword hoping to avoid duplicate matches, but perhaps its best
                # to print the whole section here.
                sys.stderr.write('  <except>\n')
                skv = violator.section.get_args()
                sys.stderr.write(kws % (str(skv), skv.values[0].value))

                for keyword, skw in violator.submatches.iteritems():

                    for sv in skw.values:
                        sys.stderr.write(kws % (keyword, sv.value))

                sys.stderr.write('  </except>\n')

    @staticmethod
    def _print(failed_tests):
        for t in failed_tests:
            sys.stderr.write('Failed test(' + t.name + '):\n')
            for match in t.violators:
                submatches = match.submatches
                sys.stderr.write(match.section.get_header() + '\n')
                for k, section_keyword_values in submatches.iteritems():
                    for sv in section_keyword_values.values:
                        sys.stderr.write('\t\t' + k + '(' + str(sv.lineno) +
                                         ') : ' + sv.value)
                        sys.stderr.write('\n')

    def _violations_search(self, search_args, exception_args):

        # we use a set to de-duplicate the results from
        # multiple searches
        # We are building sets of hash objects, this will call
        # the SubMatches.__hash__() method.
        found = set()

        for s in search_args:
            # Set the internal search flag to silent so we get
            # a list back and don't print
            s['silent'] = True
            f = self._search(s)
            if f != None:
                for x in f:
                    if not VerifyCommand.filter(exception_args, x):
                        found.add(x)

        return found

    @staticmethod
    def filter(exception_args, found):
        '''Filters the found exceptions against the list of exceptions, removing them.
            Args:
                found ([Section]): The found Sections from the search.
                exception_args({}): The exceptions that can be removed from found.

            Returns:
                The list of Filtered Sections.
        '''

        for e in exception_args:
            m = found.match(e)
            if m:
                return found.filter(m)

    def _search(self, args):
        return commandlet.get()['search'](self._init_parser, args)


def main():
    '''The main entry point.'''

    opt_parser = argparse.ArgumentParser(
        description='A tool for intelligent searching of Android init.rc files')

    subparser = opt_parser.add_subparsers(help='commands')

    commandlets = commandlet.get()

    # for each commandlet, instantiate and set up their options
    for n, c in commandlets.iteritems():
        p = subparser.add_parser(n, help=c.__doc__)
        p.add_argument('files', help='The init.rc file(s) to search', nargs='+')
        p.set_defaults(which=n)
        # Instantiate

        opt_gen = getattr(c, 'generate_options', None)
        if callable(opt_gen):
            # get group help
            g = p.add_argument_group(n + ' options')
            # get args
            c.generate_options(g)

    args = opt_parser.parse_args()

    init_parser = InitParser(args.files)

    d = vars(args)
    which = d['which']

    # drop options we added to not confuse commandlets
    del d['files']
    del d['which']

    commandlet.get()[which](init_parser, d)


if __name__ == '__main__':
    main()
