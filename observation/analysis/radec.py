#!/usr/bin/env python

# radec.py
# ex)radec.py ra 54.0
#    radec.py ra 23 48 20
#    radec.py dec +0.59
#    radec.py dec +00 35 15.937
#
## 2018/2/13 Ver 1.0 H.Kawai

import sys
radec=sys.argv[1]
val_list=sys.argv[2:]
val_len=len(val_list)
error=set()

if radec == "ra":
    if val_len == 3:
        h=int(val_list[0])
        m=int(val_list[1])
        s=float(val_list[2])
        deg=((h * 360.0 / 24) + (m * 360.0 / (24.0*60)) + (s * 360.0 / (24.0*60*60)))
        print(deg)
    elif val_len == 1:
        deg=float(val_list[0])
        h=int(deg / (360.0/24))
        m=int((deg % (360.0/24)) / (15.0/60))
        s=float(((deg % (360.0/24)) % (15.0/60)) / (15.0/3600))
        print("{0} {1} {2}".format(h,m,s))
    else:
        error.add('Error_ra_len')
        
elif radec == "dec":
    pm_pre=str(val_list[0])
    if pm_pre.find('-') == 0:
        pm=int(-1)
    elif pm_pre.find('-') == -1:
        pm=int(1)
    else:
        error.add('Error_dec_pm')
        
    if val_len == 3:
        d=int(val_list[0])
        m=int(val_list[1])
        m*=pm
        s=float(val_list[2])
        s*=pm
        deg=(d + (m / 60.0) + (s / 3600.0))
        print(deg)
    elif val_len == 1:
        deg=float(val_list[0])
        d=int(deg)
        m=int((float(deg)-int(deg)) * 60)
        s=(float((float(deg)-int(deg)) * 60) - m) * 60
        print("{0} {1} {2}".format(d,m,s))
    else:
        error.add('Error_dec_len')
else:
    error.add('Error_radec')

if len(error) > 0:
    print error
