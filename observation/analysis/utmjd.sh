#!/bin/bash

######このスクリプトはUTをMJDに変換するもの。
######MAXI on-demandのlcのデータに用いる。

key=1
mjd=0
########################### check file ############
if test 0$1 -eq 0; then
key=0
fi
#######################################################################
############################ honbunn ############
if test $key -eq 0; then
echo
echo "I can't read your purpose file."
echo "Please type your purpose file after follow utmjd.sh"
echo "ex) utmjd.sh hoge.txt"
echo
elif test $key -eq 1;then
echo "I use data of $1"

cat $1 | awk '{print $1}' > ut1.txt
cat $1 | awk '{print $2}' > ut2.txt

gyou=`wc -l jst1.txt | cut -d ' ' -f1`
for i in `seq 1 $gyou`
do
 year=`cat jst1.txt | sed -n $i\p | sed 's/\/.*//'`
 month=`cat jst1.txt | sed -n $i\p | sed "s/$year\///" | sed 's/\/.*//'`
 day=`cat jst1.txt | sed -n $i\p | sed "s/$year\/$month\///"`
 hh=`cat jst2.txt | sed -n $i\p | sed 's/:.*//'`
 mm=`cat jst2.txt | sed -n $i\p | sed "s/$hh://" | sed 's/:.*//'`
 ss=`cat jst2.txt | sed -n $i\p | sed "s/$hh:$mm://"`
 shousu=`echo "$hh $mm $ss"|awk '{print ($1*3600+$2*60+$3)/86400}'`

 if test $year -eq 2016;then
  if test $month -eq 11;then
  seisu=`echo "$day"|awk '{print $1+57692}'`
  mjd=1
  elif test $month -eq 12;then
  seisu=`echo "$day"|awk '{print $1+57692+30}'`
  mjd=1
  else mjd=0
  fi
 else 
 echo "date is over(error year)"
 fi
 if test $mjd -eq 0;then
 echo "no" >> ut3.txt
 else shousu2=`echo "$shousu"|sed 's/0//'`
 echo "$seisu$shousu2" >> ut3.txt
 fi

done

cat $1 | awk '{print $3;}' > ut4.txt
cat $1 | awk '{print $4;}' > ut5.txt
file=`echo $1|sed 's/.txt/_mjd.txt/'`
paste ut3.txt ut4.txt ut5.txt > $file

rm -f ut1.txt
rm -f ut2.txt
rm -f ut3.txt
rm -f ut4.txt
rm -f ut5.txt

fi