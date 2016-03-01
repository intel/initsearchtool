# Init Search Tool

## About
The init search tool aka ingrep, is a tool for intelligently searching Android
[<sup>TM</sup>](#trademark)
init.rc files. The tool can print, search and verify init.rc files.

## The *init.rc* Layout
For the purpose of searching, init.rc files in Android can be thought of
as having three sections:
 - on
 - service
 - import

Each section is comprised of the section keyword (in the list above) a possible
argument and keywords.

In other words, each section can be thought of as this:
```
<section> [args]*
   <keyword>
     ...
```

*args* will always be specified, however not all sections contain keywords.
For instance, consider the *import* section. Also, the keyword might be
implicit, for instance, the *on* section just has a list of commands to run,
but no keyword. The implicit keyword for *on* sections is *command*. The
service section has the explicit keywords defined for the service section
per the AOSP init readme.txt under system/core/init.

## search
Likely one of the best features, the basics are:
```
$ ingrep search --section=<section> <search parameters> init.rc ...
```
To search for all on sections that relate to propery foo.bar, one could perform
the following search command:

```
$ ./ingrep.py search --section=on --args='property:foo\.bar' init.rc
on(test/init.aosp.rc : 28): property:foo.bar=*
	mkdir /foo/bar 0777 system system

```

If you wanted to narrow this search, we could specify the --command string for
the search. This option can be added numerous times, and is cumulative. All
supplied strings must match. Many section keywords are cumulative with the
exception of args (for all sections) and some service keywords. Boolean service
keywords, like *critical* are not cumulative and can be also searched by their
boolean logic not equivalent, *--critical* or *--notcritical*. The general format
for search keywords is --<keyword> and --not<keyword>

Additional output options include *--tidy* which prints only matches within
the section, and *--lineno* to print linenumbers with the output. An unset
line number means its a section default. For instance, with the section service
user contains a default of 'root'.

Another search option is *--strict*. By default search strings are lazy. Each
search string is modified to be \.\*searchstring\.\*. The strict option takes
the search string as specified. Its important to note, search strings are
regular expressions supported by pythons re module. Additionally, regular
expressions are implicitly line anchored by $regex^.

### verify

The verify command searches the init.rc file(s) for search parameters specified
in assert.xml. If anything is found, that is not also white-listed, the command
will exit in error and print out the offending lines. The option *--gen* can be
specified to produce the list of test exceptions.

```
$ ./ingrep.py verify --asert=assert.xml init.rc
$ ./ingrep.py verify --assert=test/assert.xml test/init.aosp.rc
Failed test(No world files):
on(test/init.aosp.rc : 13): early-init
	command(25) : mkdir /danger 0777 root root
on(test/init.aosp.rc : 29): property:foo.bar=*
	command(30) : mkdir /foo/bar 0777 system system
```

### print

This option just prints the init.rc file(s) specified. It takes the option
*--lineno* to optionally print each linenumer in the section.

```
$ ./ingrep.py print test/init.aosp.rc
```

<a name="trademark"></a>
Android is a trademark of Google Inc.
