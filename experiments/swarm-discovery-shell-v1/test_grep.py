import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('grep_fixed',Path(__file__).parent/'image/grep_fixed.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class Checks(unittest.TestCase):
    def expanded(self,args):return g.arguments(args,['proc','dev','sys','workspace','registry','tmp','usr'])
    def test_recursive_root_prunes_only_kernel_roots(self):
        args=self.expanded(['-Ril','needle','/']);self.assertNotIn('/proc',args);self.assertNotIn('/sys',args);self.assertNotIn('/dev',args)
        self.assertTrue(all(p in args for p in ['/workspace','/registry','/tmp','/usr']))
    def test_pattern_slash_is_not_a_path(self):self.assertEqual(self.expanded(['-R','/','/workspace']),['--devices=skip','-R','/','/workspace'])
    def test_pattern_options(self):self.assertIn('/workspace',self.expanded(['-Repattern','/']));self.assertIn('/registry',self.expanded(['-R','-e','needle','/']))
    def test_glob_and_context_option_arguments_are_not_paths(self):
        args=self.expanded(['-R','--include','/','-C','2','needle','/']);self.assertEqual(args[3],'/');self.assertIn('/workspace',args)
    def test_direct_kernel_and_named_business_directories_unchanged(self):
        for path in ('/proc/self/status','/workspace/proc','/registry/sys','/tmp/dev'):
            self.assertEqual(g.arguments(['-R','needle',path]),['--devices=skip','-R','needle',path])
    def test_literal_dash_pattern_after_separator(self):self.assertIn('/workspace',self.expanded(['-R','--','-e','/']))
    def test_stdin_is_preserved(self):self.assertEqual(g.arguments(['needle']),['--devices=skip','needle'])
    def test_explicit_device_choice_is_preserved(self):self.assertEqual(g.arguments(['--devices=read','needle','/dev/null']),['--devices=skip','--devices=read','needle','/dev/null'])
    def test_unknown_short_option_does_not_rewrite_operands(self):self.assertEqual(self.expanded(['-K','needle','/']),['--devices=skip','-K','needle','/'])
    def test_filenames_with_whitespace_are_arguments(self):self.assertIn('/workspace/a b',g.arguments(['-R','needle','/workspace/a b']))
    def test_directory_mode_last_option_wins(self):
        self.assertNotIn('/workspace',self.expanded(['-R','-dread','needle','/']))
        self.assertIn('/workspace',self.expanded(['-dskip','-R','needle','/']))
    def test_long_directory_recursion(self):
        self.assertIn('/workspace',self.expanded(['--directories=recurse','needle','/']))
        self.assertNotIn('/workspace',self.expanded(['-R','--directories','skip','needle','/']))
if __name__=='__main__':unittest.main()
