#!/bin/bash

##mjdut.sh

##ex) mjdut.sh hoge.txt
##
## hoge.txt = 57696.418449 57696.419549 3.029399 0.202059
##            57696.482812 57696.483912 3.053586 0.200796
##
## ver 2 support for mac
##2017/10/30 kawai

echo "use $1"
name=`echo $1 | sed 's/.txt/_ut.txt/g'`

cat $1 | awk '{ OFMT="%.6f"} {print ($1+$2)/2-57388;}' > mjdut1.txt
Cat mjdut1.txt | awk '{ OFMT="%.0f"} {print $1*86400+1451606400;}' > mjdut2.txt
#2016/01/01 00:00:00 (UT) を基準

hsum=`wc -l mjdut2.txt | awk '{print $1}'`
Echo "line number is $hsum"
for i in `seq 1 $hsum`
do
 time=`cat mjdut2.txt | sed -n $i\p`
 # echo $time | awk '{ print strftime("%c", $1); }' |sed '{s/年/\//g}'|sed '{s/月/\//g}'|sed '{s/日//g}'|sed '{s/時/:/g}'|sed '{s/分/:/g}'|sed '{s/秒//g}' >> mjdut3.txt
 date -ur $time +"%Y/%m/%d %H:%M:%S" >> mjdut3.txt
done

cat $1 | awk '{print $3,$4;}' > mjdut4.txt
paste mjdut3.txt mjdut4.txt > $name

#rm -f mjdut1.txt
#rm -f mjdut2.txt
#rm -f mjdut3.txt
#rm -f mjdut4.txt
