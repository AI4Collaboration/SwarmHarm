#!/usr/local/bin/python3 -I
"""Finite filesystem defaults for recursive text searches."""
import os
import sys

ARGUMENT_LONG={'after-context','before-context','context','binary-files','devices','directories','exclude','exclude-from','exclude-dir','include','file','label','max-count','regexp','group-separator'}
ARGUMENT_SHORT=set('ABCDdefm')
PLAIN_SHORT=set('EFGPivwxyzcLlcHhnoqsrRIZUubTVa')


def path_indices(args):
    """Return file operands; unknown syntax is passed through unchanged."""
    positional=[];pattern_option=False;recursive=False;i=0;options=True
    while i<len(args):
        word=args[i]
        if options and word=='--':options=False;i+=1;continue
        if options and word.startswith('--'):
            name=word[2:].split('=',1)[0]
            if name in ('recursive','dereference-recursive'):recursive=True
            if name in ('regexp','file'):pattern_option=True
            if name=='directories':
                value=word.split('=',1)[1] if '=' in word else (args[i+1] if i+1<len(args) else '')
                recursive=value=='recurse'
            if name in ARGUMENT_LONG and '=' not in word:i+=1
        elif options and word.startswith('-') and word!='-':
            cluster=word[1:]
            if not cluster.isdigit():
                for n,char in enumerate(cluster):
                    if char in ('r','R'):recursive=True
                    if char in ('e','f'):pattern_option=True
                    if char in ARGUMENT_SHORT:
                        if char=='d':
                            value=cluster[n+1:] or (args[i+1] if i+1<len(args) else '')
                            recursive=value=='recurse'
                        if n==len(cluster)-1:i+=1
                        break
                    if char not in PLAIN_SHORT:return [],False
        else:positional.append(i)
        i+=1
    return (positional if pattern_option else positional[1:]),recursive


def arguments(args,entries=None):
    paths,recursive=path_indices(args)
    roots={i for i in paths if args[i] and os.path.normpath(args[i])=='/'} if recursive else set()
    expanded=[]
    if roots:
        if entries is None:entries=[entry.name for entry in os.scandir('/')]
        children=['/'+name for name in entries if name not in ('proc','sys','dev')]
        for i,value in enumerate(args):expanded.extend(children if i in roots else [value])
    else:expanded=list(args)
    # Explicit later --devices options can still override this default.
    return ['--devices=skip']+expanded


if __name__=='__main__':os.execv('/usr/bin/grep',['grep']+arguments(sys.argv[1:]))
