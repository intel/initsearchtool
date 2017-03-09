#!/usr/bin/env python

import argparse
import copy
import re
import sys
import xml.sax


class NumberMatcher(object):
	def __init__(self, matcher, lazy_regex):

		# it can be a range
		if ',' in matcher:
			x = matcher.split(',')
			if len(x) != 2:
				raise ValueError('Expected valid range x,b no spaces, got: "%s"' % matcher)

			found_range = []
			for n in x:
				try:
					n = int(n, 0)
					found_range.append(n)
				except ValueError:
					raise ValueError('Expected range number to be a number, got: "%s"' % n)

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

			# bail, done processing range
			return

		# coerce a raw number to an ==n operator
		try:
			int(matcher, 0)
			self._operator = "=="
			matcher = '==' + matcher
		except:
			pass

		# order matters, check longest first!
		if matcher.startswith("=="):
			self._operator = "=="
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

		n = matcher[len(self._operator):]
		try:
			self._values = int(n, 0)
		except ValueError:
			raise ValueError('Attempted operator "%s", but failed.'
							'Expected a number, got: "%s",'
							'perhaps invalid operator?'
							'Use quotes, the shell steals'
							% (self._operator, n))

	def match(self, number):

		number = number if isinstance(number, int) else int(number, 0)

		# return some coerced match object
		if self._operator == '<' and number < self._values:
			return re.match(str(number), str(number))
		elif self._operator == '<=' and number <= self._values:
			return re.match(str(number), str(number))
		elif self._operator == '==' and number == self._values:
			return re.match(str(number), str(number))
		elif self._operator == '>' and number > self._values:
			return re.match(str(number), str(number))
		elif self._operator == '>=' and number >= self._values:
			return re.match(str(number), str(number))
		elif self._operator == 'in' and number in self._values:
			return re.match(str(number), str(number))

		return None

class RegexMatcher(object):

	def __init__(self, r, lazy_regex):

		if isinstance(r, bool):
			r = str(r).lower()

		if not lazy_regex:
			# Greedify the search if not lazy
			r = '.*' + r + '.*'

		# Anchor the regex
		r = '^' + r + '$'
		self._matcher = re.compile(r)

	def match(self, other):
		return self._matcher.match(other)

class Match(object):
	def __init__(self, section, submatches):
		self._section = section
		self._submatches = submatches

	def get_sub_matches(self):
		return self._submatches

	def get_section(self):
		return self._section

	def __hash__(self):
		return hash(self._section)

	def __eq__(self, other):
		if self._section != other._section:
			return False

		# their must be a match for everything in other._submatches in self or
		# not equal
		selfsubs = self._submatches
		othersubs = other._submatches
		for os in othersubs:
			if os not in selfsubs:
				return False

		return True

	def write(self, filep=sys.stdout, lineno=False, tidy=False):

		s = self.get_section()
		if not tidy:
			s.write(filep=filep, lineno=lineno)
		else:
			filep.write(s.format(lineno=lineno, sub_matches=self._submatches))

	def match(self, other):
		return self._section.match(other, False)

	def filter(self, match):

		left = {}
		subs = self._submatches
		fltr = match.get_sub_matches()
		# The filter might contain arguments that were not matched, ie the search might
		# have been on socket (so sub_matches is only socket_ but the filter might include
		# args. We only filter on what the intersection between the two are.
		fltr_keys = set(fltr.keys())
		sub_keys = set(subs.keys())
		keys = fltr_keys & sub_keys

		# Search each key value in the filter (white list exception)
		for k in keys:
			v = fltr[k]

			# Keep a copy of the list associated with the k, we remove the
			# items from the list when a filter matches
			s = list(subs[k])

			# For each line in the exceptions filter, we compile it
			# as a possible regex and search the sub_matches with it.
			for x in v:
				# If we find a match we remove it from the copy of sub_matches
				if x in subs[k]:
					s.remove(x)

			# If anything is left in the list of things, we add it as 'left', ie the delta
			if len(s) > 0:
				left[k] = s

		self._submatches = left

		# The filter returns true if it was filtered out, ie nothing left, else if their is a delta
		# False is returned.
		return not bool(left)

class SectionValue(object):
	def __init__(self, value, lineno=-1):
		self.value = value
		self.lineno = lineno

	def __str__(self):
		return str(self.value).lower() if isinstance(self.value, bool) else self.value

class SectionKeywordValues(object):
	def __init__(self, keyword, default=None, is_appendable=False, is_default_printable=False, matcher=RegexMatcher):

		self._keyword = keyword
		self._is_appendable = is_appendable
		self._is_set = False
		self._is_default_printable = is_default_printable
		self._default_type = type(default)
		self._values = [ SectionValue(default) ] if default else []
		self._matcher = matcher

	def __len__(self):
		return len(self._values)

	def __str__(self):
		return self._keyword

	def push(self, value, lineno):

		if not self._is_appendable and self._is_set:
			raise Exception("Expected %s keyword to only appear once" % self._keyword)

		# some items don't have values, like bool switches
		if self._default_type == bool:
			value = True

		item = SectionValue(value, lineno)
		if (self._is_appendable):
			self._values.append(item)
		else:
			self._values = [ item ]

		self._is_set = True

	def reset(self):
		self._values = []
		self._is_set = False
		return self

	@property
	def keyword(self):
		return self._keyword

	@property
	def type(self):
		return self._default_type

	@property
	def is_appendable(self):
		return self._is_appendable

	@property
	def is_set(self):
		return self._is_set

	@property
	def matcher(self):
		return self._matcher

	def is_printable(self):
		return self._is_set or self._is_default_printable

	@property
	def values(self):
		return self._values

	def sort(self):
		self._values.sort(key=lambda x: x.lineno)

class Section(object):

	_KW_ARGS = 'args'

	_keywords = { _KW_ARGS : SectionKeywordValues(_KW_ARGS, is_appendable=True) }

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
		filep.write(self.format(lineno=lineno))

	def get_header(self):
		fmtout = self._path + ':\n'
		fmtout += str(self._lineno) + ':\t' + self._name + ' '
		fmtout += ' '.join([ x.value for x in self._option_map[Section._KW_ARGS].values ])
		return fmtout

	def format(self, lineno=False, sub_matches=None):

		fmtout = self.get_header() + '\n'

		if sub_matches == None:
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

		(x, s) = self._section_cmp(other, lazy_regex)
		if x >= 0:
			return Match(self, s)
		else:
			return None

	def get_name(self):
		return self._name

	def get_args(self):
		return self._option_map[Section._KW_ARGS]

	def get_lineno(self):
		return self._lineno

	def push(self, line):
		raise Exception('Implement me!')

	@staticmethod
	def get_keywords():
		return Section.get_keymap().keys()

	@staticmethod
	def get_keymap():
		return Section._keywords

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
				search_values = [ search_values ]

			found = 0
			for section_val in section_vals:

				section_val_str = str(section_val)

				for search_term in search_values:

					matcher = matcher_class(search_term, lazy_regex)

					result = matcher.match(section_val_str)
					if result:
						found = found + 1
						if search_key not in submatches:
							x = copy.deepcopy(section_keyword_values)
							submatches[search_key] = x.reset()
						submatches[search_key].push(section_val.value, section_val.lineno)

			# If i didn't find as many items as I was looking for
			# it's not a match
			if found < len(search_values):
				# no match
				return (-1, submatches)

		# If section map had more keys, then its a super set
		# of search dictionary, else equal
		x = 0 if len(section_keys) == len(search_keys) else 1
		x = (x, submatches)
		return x

	@staticmethod
	def _join(parent, self):
		x = dict(parent)
		x.update(self)
		return x

class OnSection(Section):

	_KW_COMMAND = 'command'

	_keywords = Section._join(
			Section._keywords,
			{ _KW_COMMAND : SectionKeywordValues(_KW_COMMAND, is_appendable=True) })

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

	_keywords = (Section._join
	(
		# This map is awful, I should have used explicit classes for the keywords.
		# The format is as follows:
		#   Either list or tuple:
		# 	 Tuples are for items that should only appear once, like critical.
		# 	 Lists are for items that can appear multiple times, like setenv.
		# 	   Lists themselves contain tuples that adhere to the tuple idoim.
		#
		#   Tuple Idiom:
		# 	 Tuples themselves contain a default and a line number:
		# 	 (Default, -1)
		# 	   The first value in the tuple, its type determines the behavior.
		# 		 Strings are always searched and printed
		# 		 Bools are ignored unless togled off the default
		# 	   The second value is just for line numbers, -1 means not set.
		#
		# Because of the above designe description, handling this map is split into
		# many many locations, such as _section_cmp() and format().
		# XXX Fix this mess.
		Section._keywords,
		{
			_KW_CONSOLE  : SectionKeywordValues(_KW_CONSOLE, default=False),
			_KW_CRITICAL : SectionKeywordValues(_KW_CRITICAL, default=False),
			_KW_DISABLED : SectionKeywordValues(_KW_DISABLED, default=False),
			_KW_SET_ENV  : SectionKeywordValues(_KW_SET_ENV, is_appendable=True),
			_KW_GET_ENV  : SectionKeywordValues(_KW_GET_ENV, is_appendable=True),
			_KW_SOCKET   : SectionKeywordValues(_KW_SOCKET, is_appendable=True),
			_KW_USER	 : SectionKeywordValues(_KW_USER, default='root'),
			_KW_GROUP	 : SectionKeywordValues(_KW_GROUP, default='root'),
			_KW_SECLABEL : SectionKeywordValues(_KW_SECLABEL),
			_KW_ONESHOT  : SectionKeywordValues(_KW_ONESHOT, default=False),
			_KW_CLASS	 : SectionKeywordValues(_KW_CLASS, default='default'),
			_KW_IOPRIO   : SectionKeywordValues(_KW_IOPRIO),
			_KW_ONRESTART: SectionKeywordValues(_KW_ONRESTART, is_appendable=True),
			_KW_WRITEPID : SectionKeywordValues(_KW_WRITEPID, is_appendable=True),
			_KW_KEYCODES : SectionKeywordValues(_KW_KEYCODES, is_appendable=True),
			_KW_PRIORITY : SectionKeywordValues(_KW_PRIORITY, default=0, matcher=NumberMatcher),
			_KW_START	: SectionKeywordValues(_KW_START),
		}
	))

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
			sys.exit('Invalid service option: "%s" on line: %d' % (keyword, lineno))

		kw = self._option_map[keyword]
		kw.push(args, lineno)

	@staticmethod
	def get_keywords():
		return ServiceSection.get_keymap().keys()

	@staticmethod
	def get_keymap():
		return ServiceSection._keywords

class InitParser(object):

	ON = 'on'
	SERVICE = 'service'
	IMPORT = 'import'

	_section_map = {
		ON : OnSection,
		SERVICE : ServiceSection,
		IMPORT : Section
	}

	def __init__(self, files):
		self._files = files
		self._items = {}

		for k in InitParser._section_map:
			self._items[k] = []

	def parse(self):
		for p in self._files:
			self._handle_file(p)

	def _handle_file(self, path):
		with open(path) as f:
			current_section = None
			lineno = 0
			line = ''
			for l in f:
				l = l.strip()
				lineno = lineno + 1

				# Skip empty (whitespace only) lines
				if len(l) == 0:
					continue

				# Skip comments
				if l.startswith('#'):
					continue

				# Ignore pystache conditional lines
				if l.startswith('{{'):
					continue

				# handle line folding
				if l.endswith('\\'):
					line += l + ' '
					continue

				# process the complete line
				line += l

				chunks = line.split()
				section_name = chunks[0]

				# is the keyword a _name?
				if section_name in InitParser._section_map:
					if current_section != None:
						self._items[current_section.get_name()].append(current_section)

					args = ' '.join(chunks[1:])
					current_section = self._section_factory(chunks[0], args, path, lineno)

				# its not a valid section name but were parsing section options
				elif current_section != None:
					try:
						current_section.push(line, lineno)
					except Exception as e:
						raise type(e)(e.message + ' while parsing file "%s on line %d"' % (path, lineno))

				# clear line, repeat
				line = ''

			# when the file ends, we need to push the last section
			# being parsed if set (ie dont push on blank file)
			if current_section != None:
				self._items[current_section.get_name()].append(current_section)

	def _section_factory(self, section_name, section_args, path, lineno):

		if section_name not in self._section_map:
			raise Exception('Error in name ' + section_name + ' line: ' + str(lineno))

		return self._section_map[section_name](section_name, section_args, path, lineno)

	def search(self, section_name, search, lazy_regex=False):

		found = []
		section = self._items[section_name]

		for x in section:
			m = x.match(search, lazy_regex)
			if m:
				found.append(m)
		return found

	def write(self, filep=sys.stdout, lineno=False):

		things = []
		for section_name in InitParser._section_map.keys():
			section = self._items[section_name]
			for x in section:
				things.append(x)

		things.sort(key=lambda sec: sec.get_lineno())

		for x in things:
			x.write(filep=filep, lineno=lineno)
			filep.write('\n')

	@staticmethod
	def get_section(name):
		return InitParser._section_map[name]

	@staticmethod
	def get_sectons():
		return InitParser._section_map

	@staticmethod
	def _merge_dicts(l):
		r = {}
		for d in l:
			r.update(d)
		return r

class Test(object):

	def __init__(self, *args, **kwargs):
		self._name = 'unnamed' if 'name' not in kwargs else kwargs['name']
		self._section = kwargs['section']
		self._searches = []
		self._exceptions = []
		self._violators = None

		self._current = None

	def start_search(self, *args, **kwargs):
		self._current = dict({ 'section' : self._section })

	def start_exception(self, *args, **kwargs):
		self._current = dict()

	def end_search(self):
		self._searches.append(self._current)
		self._current = None

	def end_exception(self):
		# self._current['section'] = self._section
		self._exceptions.append(self._current)
		self._current = None

	def append_keyword(self, search):
		for k, v in search.iteritems():
			if k not in self._current:
				self._current[k] = []
			self._current[k].append(v)

	def get_exceptions(self):
		return self._exceptions

	def get_searches(self):
		return self._searches

	def write(self, filep=sys.stdout, lineno=False):

		filep.write('test: ' + self._name + '\n')
		for x in self._searches:
			filep.write('\tsearch: ' + str(x) + '\n')

		for x in self._exceptions:
			filep.write('\texcept: ' + str(x) + '\n')

	def set_violators(self, violators):
		self._violators = violators

	def get_violators(self):
		return self._violators

	def getName(self):
		return self._name

class AssertParser(xml.sax.ContentHandler):

		def __init__(self, *args, **kwargs):
			xml.sax.ContentHandler.__init__(self, *args, **kwargs)

			self._tests = []
			self._current = None

		def startElement(self, name, attrs):

				# Make a straight python dict from attrs
				attrs = dict(attrs)

				if name == 'test':
					self._current = Test(**attrs)

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

	_commandlets = {}

	def __init__(self, cmd):
		self._cmd = cmd

		if cmd in commandlet._commandlets:
			raise Exception('Duplicate command name' + cmd)

		commandlet._commandlets[cmd] = None

	def __call__(self, cls):
		commandlet._commandlets[self._cmd] = cls
		return cls

	@staticmethod
	def get():
		return commandlet._commandlets

	@staticmethod
	def set(cmdlets):
		commandlet._commandlets = cmdlets

@commandlet("print")
class PrintCommand(object):
	'''
	Dumps the contents of the init.rc file to stdout
	'''

	def generate_options(self, group_parser):
		group_parser.add_argument('--lineno', action='store_true', help='Dump line numbers with keywords')

	def __call__(self, init_parser, args):
		init_parser.write(lineno=args['lineno'])

@commandlet("search")
class SearchCommand(object):
	'''
	Searches the init.rc for the specified section for a specified keyword regex.
	'''

	def __init__(self):
		self._opts = None

	def generate_options(self, group_parser):

		options = self._gen_opts()

		for opt in options:
			args = opt[0]
			args = [ args ] if isinstance(args, str) else args
			kwargs = opt[1] if len(opt) == 2 else {}
			group_parser.add_argument(*args, **kwargs)

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
		d = { k : v for k, v in args.items() if v != None }
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
			print(len(found))
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
		s = 'Searches a section given a section name {' + (','.join(sections.keys()) + '}')
		opts.append(('--section', { 'help' : s, 'required' : True }))
		opts.append(('--lazy', { 'action' : 'store_true', 'help' : 'The default is a greedy search, set this to force lazy searches.'}))
		opts.append(('--tidy', { 'action' : 'store_true', 'help' : 'Set this flag to only print matching keywords for the section'}))
		opts.append(('--lineno', { 'action' : 'store_true', 'help' : 'Print line numbers on matches'}))
		opts.append(('--count', { 'action' : 'store_true', 'help' : 'Print the number of matches'}))

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
						h = 'argument is a valid regex. Multiple specifications of the option result in the logical and of all specified options.'
						class custom_action(argparse.Action):
							def __call__(self, parser, args, values, option_string=None):
								getattr(args, self.dest)
								setattr(args, self.dest, RegexMatcher(values))
						opts.append(('--' + key_word, { 'help' : 'Section: ' + key_word + '. ' + h, 'action' : 'append' }))

					elif istype is bool:
						h = 'true if specified. Multiple specifications of the option result in the last option specified used.'
						opts.append(('--' + key_word , { 'help' : 'Section: ' + key_word + '. ' + h, 'action' : 'store_const', 'const' : True, 'dest' : key_word }))
						opts.append(('--not' + key_word , { 'help' : 'Section: ' + key_word + '. ' + h, 'action' : 'store_const', 'const' : False, 'dest' : key_word}))

					elif istype is int:
						h = ('argument is a valid int, equality expression(<x|<=x|==x|>=x|>x or integer range as a,b. Use quotes to deal with shells.'
							'Multiple specifications of the option result in the last option specified used.')
						opts.append(('--' + key_word, { 'help' : 'Section: ' + key_word + '. ' + h, 'action' : 'store' }))

					else:
						h = 'argument is a valid regex. Multiple specifications of the option result in the last option specified used.'
						opts.append(('--' + key_word , { 'help' : 'Section: ' + key_word + '. ' + h, 'action' : 'store', 'dest' : key_word }))

		self._opts = opts
		return opts

@commandlet("verify")
class VerifyCommand(object):
	'''
	Verifies the contents of the init.rc against a file of assertions and white-list exceptions
	'''

	def generate_options(self, group_parser):
		group_parser.add_argument('--assert', help='Verifies an init.rc file against a list of rules', action='append', required=True)
		group_parser.add_argument('--gen', help='Generate a list of exceptions for tests.', action='store_true')

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

		self._init_parser = init_parser

		failed_tests = []
		# find them all!
		for t in verifier:
			e = t.get_exceptions()
			s = t.get_searches()
			v = self._violations_search(s, e)
			if len(v) > 0:
				t.set_violators(v)
				failed_tests.append(t)

		# nothing failed/reportable
		if len(failed_tests) == 0:
			return

		if not genmode:
			VerifyCommand._print(failed_tests)
			sys.exit(len(failed_tests))

		else:
			VerifyCommand._gen(failed_tests)

	@staticmethod
	def _gen(failed_tests):

		kws = "	<keyword %s ='%s' />\n"

		for t in failed_tests:
			sys.stderr.write('Failed test(' + t.getName() + '):\n')
			for violator in t.get_violators():

				# We print args + keyword hoping to avoid duplicate matches, but perhaps its best
				# to print the whole section here.
				sys.stderr.write('  <except>\n')
				x = violator.get_section().get_args()
				sys.stderr.write(kws % (str(x), x.values[0].value))

				for k, v in violator.get_sub_matches().iteritems():
					for x in v.values:
						sys.stderr.write(kws % (k, x.value))

				sys.stderr.write('  </except>\n')
	@staticmethod
	def _print(failed_tests):
		for t in failed_tests:
			sys.stderr.write('Failed test(' + t.getName() + '):\n')
			for match in t.get_violators():
				submatches = match.get_sub_matches()
				sys.stderr.write(match.get_section().get_header() + '\n')
				for k, section_keyword_values in submatches.iteritems():
					for line_value in section_keyword_values.values:
						sys.stderr.write('\t\t' + k + '(' + str(line_value.lineno) + ') : ' + line_value.value)
						sys.stderr.write('\n')

	def _violations_search(self, search_args, exception_args):

			# we use a set to de-duplicate the results from
			# multiple searches
			# We are building sets of hash objects, this will call
			# the Match.__hash__() method.
			found = set()
			excepts = set()

			for s in search_args:
				# Set the internal search flag to silent so we get
				# a list back and don't print
				s['silent'] = True
				f = self._search(s)
				if f != None:
					for x in f:
						if not self.filter(exception_args, x):
							found.add(x)

			return found - excepts

	def filter(self, exception_args, found):

		for e in exception_args:
			m = found.match(e)
			if m:
				return found.filter(m)

	def _search(self, args):
		return commandlet.get()['search'](self._init_parser, args)

def main():

	opt_parser = argparse.ArgumentParser(description='A tool for intelligent searching of Android init.rc files')

	subparser = opt_parser.add_subparsers(help='commands')

	commandlets = commandlet.get()
	tmp = {}

	# for each commandlet, instantiate and set up their options
	for n, c in commandlets.iteritems():
		p = subparser.add_parser(n, help=c.__doc__)
		p.add_argument('files', help='The init.rc file(s) to search', nargs='+')
		p.set_defaults(which=n)
		# Instantiate
		c = c()
		tmp[n] = c

		opt_gen = getattr(c, 'generate_options', None)
		if callable(opt_gen):
			# get group help
			g = p.add_argument_group(n + ' options')
			# get args
			c.generate_options(g)

	# reassign constructed commandlets
	commandlet.set(tmp)

	args = opt_parser.parse_args()

	init_parser = InitParser(args.files)
	init_parser.parse()

	d = vars(args)
	which = d['which']

	# drop options we added to not confuse commandlets
	del d['files']
	del d['which']

	commandlet.get()[which](init_parser, d)

if __name__ == '__main__':
	main()
