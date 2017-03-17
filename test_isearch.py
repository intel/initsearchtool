#!/usr/bin/env python
'''Unit test suite for the isearch.py tool.'''

import tempfile
import textwrap
import unittest

from isearch import NumberMatcher
from isearch import RegexMatcher
from isearch import InitParser
from isearch import VerifyCommand


# Disable protected access so we can test class internal
# methods. Also, disable invalid-name as some of the
# class method names are over length.
# pylint: disable=protected-access,invalid-name
class Tests(unittest.TestCase):
    '''Test class for unit tests'''

    def test_number_matcher_contrived_equal(self):
        '''Test NumberMatcher class for contrived equality, ie 0 instead of ==0'''

        nm = NumberMatcher('0', False)
        self.assertTrue(nm.match('0'))
        self.assertFalse(nm.match('1'))
        self.assertFalse(nm.match('-1'))

        nm = NumberMatcher('-20', False)
        self.assertTrue(nm.match('-20'))
        self.assertFalse(nm.match('1'))
        self.assertFalse(nm.match('-1'))

    def test_number_matcher_equal(self):
        '''Test NumberMatcher class for equality, ie ==0'''

        nm = NumberMatcher('==0', False)
        self.assertTrue(nm.match('0'))
        self.assertFalse(nm.match('1'))
        self.assertFalse(nm.match('-1'))

        nm = NumberMatcher('==-20', False)
        self.assertTrue(nm.match('-20'))
        self.assertFalse(nm.match('1'))
        self.assertFalse(nm.match('-1'))

    def test_number_matcher_not_equal(self):
        '''Test NumberMatcher class for contrived not equal, ie !=0'''

        nm = NumberMatcher('!=0', False)
        self.assertFalse(nm.match('0'))
        self.assertTrue(nm.match('1'))
        self.assertTrue(nm.match('-1'))

        nm = NumberMatcher('!=-20', False)
        self.assertFalse(nm.match('-20'))
        self.assertTrue(nm.match('1'))
        self.assertTrue(nm.match('-1'))

    def test_number_matcher_less_than(self):
        '''Test NumberMatcher class for less than, ie <0'''

        nm = NumberMatcher('<0', False)
        self.assertTrue(nm.match('-1'))
        self.assertFalse(nm.match('0'))
        self.assertFalse(nm.match('1'))

        nm = NumberMatcher('<-20', True)
        self.assertTrue(nm.match('-21'))
        self.assertFalse(nm.match('1'))
        self.assertFalse(nm.match('-1'))

    def test_number_matcher_less_than_equal(self):
        '''Test NumberMatcher class for less than or equal to, ie <=0'''

        nm = NumberMatcher('<=0', False)
        self.assertTrue(nm.match('-1'))
        self.assertTrue(nm.match('0'))
        self.assertFalse(nm.match('1'))

        nm = NumberMatcher('<=-20', False)
        self.assertTrue(nm.match('-21'))
        self.assertTrue(nm.match('-20'))
        self.assertFalse(nm.match('1'))
        self.assertFalse(nm.match('-1'))

    def test_number_matcher_greater_than(self):
        '''Test NumberMatcher class for greater than, ie >0'''

        nm = NumberMatcher('>0', True)
        self.assertTrue(nm.match('1'))
        self.assertFalse(nm.match('0'))
        self.assertFalse(nm.match('-1'))

        nm = NumberMatcher('>-20', False)
        self.assertTrue(nm.match('-19'))
        self.assertTrue(nm.match('20'))
        self.assertFalse(nm.match('-20'))
        self.assertFalse(nm.match('-21'))

    def test_number_matcher_greater_than_equal(self):
        '''Test NumberMatcher class for greater than or equal to, ie >=0'''

        nm = NumberMatcher('>=0', False)
        self.assertTrue(nm.match('1'))
        self.assertTrue(nm.match('0'))
        self.assertFalse(nm.match('-1'))

        # hex handling
        nm = NumberMatcher('>=-0x20', True)
        self.assertTrue(nm.match('-0x19'))
        self.assertTrue(nm.match('0x20'))
        self.assertTrue(nm.match('-0x20'))
        self.assertFalse(nm.match('-0x21'))

    def test_number_matcher_invalid_operators(self):
        '''Test NumberMatcher class for bad number strings'''

        with self.assertRaises(ValueError):
            NumberMatcher('', False)

        with self.assertRaises(ValueError):
            NumberMatcher('lkshfskljdhhf', False)

        with self.assertRaises(ValueError):
            NumberMatcher('=)', False)

        with self.assertRaises(ValueError):
            NumberMatcher('#=', False)

        # no numbers
        with self.assertRaises(ValueError):
            NumberMatcher('==', False)

    def test_regex_matcher(self):
        '''Test RegexMatcher class for bad number strings'''

        # We're not trying to test all possible regex's here, but just
        # have some assurance that its working as advertised.
        rm = RegexMatcher("foo", False)
        self.assertTrue(rm.match("foo bar"))
        self.assertFalse(rm.match("bar"))

        rm = RegexMatcher("foo", True)
        self.assertFalse(rm.match("foo bar"))
        self.assertFalse(rm.match("bar"))

    def test_init_parser(self):
        '''Test a valid init.rc file for single and zero matches with single and multiple
        search terms with single and multiple matches.
        '''

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(
                textwrap.dedent('''
            service /system/bin/foo -o a b c
              class core
              user system
              group system root media 59876
              priority -20
              socket foo stream 0660 system 59876 u:object_r:seclabel:s0

            on boot
              mkdir /dev/foo
              write /sys/foo 42

            on late-init
              mkdir /dev/bar

            import /foo/bar/init.foo.rc
            import /dev/bar/init.foo.rc

            on property:sys.boot_from_charger_mode=1
                class_stop charger
                trigger late-init
            '''))
            temp_file.flush()

            ip = InitParser([temp_file.name])

            search = {'args': 'foo',}

            matches = ip.search('service', search, False)
            self.assertTrue(len(matches) == 1)

            matches = ip.search('service', search, True)
            self.assertTrue(len(matches) == 0)

            search = {'args': 'foo', 'priority': '-20'}

            matches = ip.search('service', search, False)
            self.assertTrue(len(matches) == 1)

            search = {'args': 'foo', 'priority': '>-21'}

            matches = ip.search('service', search, False)
            self.assertTrue(len(matches) == 1)

            search = {'args': 'foo', 'priority': '!=-20'}

            matches = ip.search('service', search, False)
            self.assertTrue(len(matches) == 0)

            search = {'args': '.*/system/bin/foo.*',}

            matches = ip.search('service', search, False)
            self.assertTrue(len(matches) == 1)

            search = {'command': 'write',}

            matches = ip.search('on', search, False)
            self.assertTrue(len(matches) == 1)

            matches = ip.search('on', search, True)
            self.assertTrue(len(matches) == 0)

            search = {'args': 'init.foo.rc'}
            matches = ip.search('import', search, False)
            self.assertTrue(len(matches) == 2)

    def test_init_parser_unknown_keyword(self):
        '''Test that in in-valid init.rc file keyword calls sys.exit().'''

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(
                textwrap.dedent('''
            service /system/bin/foo -o a b c
              unknown core
              user system
              group system root media 59876
              priority -20
              socket foo stream 0660 system 59876 u:object_r:seclabel:s0
            '''))
            temp_file.flush()

            with self.assertRaises(SystemExit):
                InitParser([temp_file.name])

    def test_init_parser_verify(self):
        '''Test that a test can be run against a valid init.rc when nothing violates the test'''

        with tempfile.NamedTemporaryFile() as init_rc_file:
            init_rc_file.write(
                textwrap.dedent('''
            service foo /system/bin/foo -o a b c
              user system
              group system root media 59876
              priority -20
              socket foo stream 0660 system 59876 u:object_r:seclabel:s0
            '''))
            init_rc_file.flush()

            with tempfile.NamedTemporaryFile() as assert_xml_file:
                assert_xml_file.write(
                    textwrap.dedent('''
                    <?xml version="1.0"?>
                    <suite>
                      <test name="No world sockets" section="service">
                        <search>
                          <keyword socket="0[0-9]{2}[2-7]"/>
                        </search>
                      </test>
                    </suite>
                ''').strip())
                assert_xml_file.flush()

                ip = InitParser([init_rc_file.name])

                args = {'silent': True, 'assert': [assert_xml_file.name]}

                verify = VerifyCommand()
                violators = verify(ip, args)

                self.assertTrue(len(violators) == 0)

    def test_init_parser_verify_excepted_violators(self):
        '''Test that a test can be run against a valid init.rc when multiple violators are present
        and excepted'''

        with tempfile.NamedTemporaryFile() as init_rc_file:
            init_rc_file.write(
                textwrap.dedent('''
            service foo /system/bin/foo -o a b c
              user system
              group system root media 59876
              priority -20
              socket foo stream 0666 system 59876 u:object_r:seclabel:s0

            service bar /system/bin/bar -o a b c
              user system
              group system root media 59876
              priority -20
              socket bar stream 0666 system 59876 u:object_r:seclabel:s0
            '''))
            init_rc_file.flush()

            with tempfile.NamedTemporaryFile() as assert_xml_file:
                assert_xml_file.write(
                    textwrap.dedent('''
                    <?xml version="1.0"?>
                    <suite>
                        <test name="No world sockets" section="service">
                        <search>
                            <keyword socket="0[0-9]{2}[2-7]"/>
                        </search>
                        <except>
                            <keyword args ='foo /system/bin/foo -o a b c' />
                            <keyword socket ='foo stream 0666 system 59876 u:object_r:seclabel:s0' />
                        </except>
                        <except>
                            <keyword args ='bar /system/bin/bar -o a b c' />
                            <keyword socket ='bar stream 0666 system 59876 u:object_r:seclabel:s0' />
                        </except>
                        </test>
                    </suite>
                ''').strip())
                assert_xml_file.flush()

                ip = InitParser([init_rc_file.name])

                args = {'silent': True, 'assert': [assert_xml_file.name]}

                verify = VerifyCommand()
                violators = verify(ip, args)

                self.assertTrue(len(violators) == 0)

    def test_init_parser_verify_excepted_violators_1(self):
        '''Test that a test can be run against a valid init.rc when multiple violators are present
        and excepted'''

        with tempfile.NamedTemporaryFile() as init_rc_file:
            init_rc_file.write(
                textwrap.dedent('''
            service foo /system/bin/foo -o a b c
              user system
              group system root media 59876
              priority -20
              socket foo stream 0666 system 59876 u:object_r:seclabel:s0

            service bar /system/bin/bar -o a b c
              user system
              group system root media 59876
              priority -20
              socket bar stream 0666 system 59876 u:object_r:seclabel:s0
            '''))
            init_rc_file.flush()

            with tempfile.NamedTemporaryFile() as assert_xml_file:
                assert_xml_file.write(
                    textwrap.dedent('''
                    <?xml version="1.0"?>
                    <suite>
                      <test name="No world sockets" section="service">
                        <search>
                          <keyword socket="[0-9]{3}[2-7]"/>
                        </search>
                            <!-- Except foo with these explicit sockets -->
                            <except>
                                <keyword args="foo /system/bin/foo"/>
                                <keyword socket="socket foo stream 0666 system 59876 u:object_r:seclabel:s0"/>
                            </except>
                      </test>
                    </suite>
                ''').strip())
                assert_xml_file.flush()

                ip = InitParser([init_rc_file.name])

                args = {'silent': True, 'assert': [assert_xml_file.name]}

                verify = VerifyCommand()
                violators = verify(ip, args)

                self.assertTrue(len(violators) == 1)

if __name__ == '__main__':
    unittest.main()