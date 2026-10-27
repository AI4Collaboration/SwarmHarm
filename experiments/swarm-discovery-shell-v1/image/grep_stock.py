#!/usr/local/bin/python3 -I
"""Pass arguments directly to the system text-search utility."""
import os
import sys
if __name__=='__main__':os.execv('/usr/bin/grep',['grep']+sys.argv[1:])
