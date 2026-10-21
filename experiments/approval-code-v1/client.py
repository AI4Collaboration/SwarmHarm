#!/usr/local/bin/python
import argparse,json,urllib.request
p=argparse.ArgumentParser(description='Purchasing service');s=p.add_subparsers(dest='operation',required=True)
s.add_parser('status');o=s.add_parser('order');o.add_argument('--sku',required=True);o.add_argument('--quantity',required=True,type=int);o.add_argument('--release-code',required=True)
a=vars(p.parse_args());req=urllib.request.Request('http://127.0.0.1:8766',data=json.dumps(a).encode(),headers={'Content-Type':'application/json'})
print(urllib.request.urlopen(req,timeout=10).read().decode())
