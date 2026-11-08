#!/bin/bash

##ana_nicer.sh

##ex) ana_nicer.sh hoge.txt
##
##
##2018/08/30 kawai
# At first, you should download event file about object star by url"https://heasarc.gsfc.nasa.gov/db-perl/W3Browse/w3table.pl?tablehead=name%3Dnicermastr&Action=More+Options"
# Since you run wget command, lets use this script.
#
##2019/03/24 kawai
# add option of analise many days
# run ) ana_nicer.sh hr1099 hoge.txt
# hge.txt = list of dir_name
# for HR1099 ?

# 1. Definition
obj=$1
list=$2
list_eve=eve.list
here=`pwd`
outfile_curve=nicer_0p5to8.lc
outfile_qdp=nicer_0p5to8
bin_size_xselect=16 #[sec]
ch_min=50
ch_max=800
cp ~/kawai/bin/ana_nicer.sh ./ana_nicer.log #for log

if [ "$obj" = "hr1099" ]; then
    ra=54.19689
    dec=0.586967
else
    echo "ra (ex:20.0202) :"
    read ra
    echo "dec (ex:+0.2234)"
    read dec
fi

loopnum=`wc ${here}/$list | awk '{print $1}'`
cd ../
for i in `seq 1 $loopnum`
do
	input=`awk '{print $1}' ${here}/$list | sed -n $i\p`
	infile_bary=ni${input}_0mpu7_cl.evt
	outfile_bary=ni${input}_0mpu7_cl_bary.evt
	#cd ../${input}/xti/event_cl
	if [ -f "./${input}/xti/event_cl/${infile_bary}" ]; then
		echo "${input} is already analaised."
	else

# 2. nicerl2
	nicerl2 $input nimaketime_gtiexpr="'(FPM_OVERONLY_COUNT < (1.52*COR_SAX**(-0.633)))&&(FPM_OVERONLY_COUNT < 0.9)&&(ST_VALID==1)'"

# 3. barycorr
	cd $input/xti/event_cl/
	barycorr infile=${infile_bary} outfile=${outfile_bary} orbitfiles="../../auxil/ni${input}.orb" ra=${ra} dec=${dec} refframe=ICRS
	cd ../../../
	fi
done	

# 4. xselect
cd $here
#ls ../*/xti/event_cl/ni*_0mpu7_cl_bary.evt > $list_eve
awk '{print "../"$1"/xti/event_cl/ni"$1"_0mpu7_cl_bary.evt"}' $list > $list_eve

cat << EOF >xcomand.txt
nicer
read eve $list_eve
./
yes
extract events
save event evt.fits
yes
filter pha_cutoff ${ch_min} ${ch_max}
extract curve
set binsize $bin_size_xselect
save curve ${outfile_curve}
pl curve
we all_lc
exit
exit
yes
EOF

  xselect < xcomand.txt
  ####

# 5. lcurve
bin_num=`tail -1 all_lc.qdp | awk '{print $1*1.1/'${bin_size_xselect}'}'` #1.1 = rough offset
cat << EOF >lccomand.txt
1
${outfile_curve}
-
${bin_size_xselect}
${bin_num}
default
yes
/XW
pl
we all_lcurve
exit


EOF

  lcurve < lccomand.txt
  (sleep 10; echo "seijou")&

# 6. Calc
offset=`awk '{print $1}' all_lcurve.qdp | sed -n 4\p`
sed -e '1,3d' all_lcurve.qdp | awk '{print $1-'$offset',$2,$3,$4}' > all_lc.txt
start_time=`cat all_lc.pco | awk '{if($3 ~ /Offset/) print $6}' | sed 's/\..*//g'`
start_time_d=`echo ${start_time} | awk -F: '{OFMT="%.6f"}{print ($1*3600+$2*60+$3)/86400}'`
start_mjd=`cat all_lc.pco | awk '{if($3 ~ /Offset/) print $5}' `
start_mjd=`echo "${start_time_d} ${start_mjd}" | awk '{OFMT="%.6f"}{print $1+$2}'`
awk '{OFMT="%.6f"}{print '${start_mjd}'+($1/86400),$2,$3,$4;}' all_lc.txt > output_mjd.txt

hsum=`wc -l output_mjd.txt | awk '{print $1}'`
echo "line number is $hsum"
for i in `seq 1 $hsum`
do
	time=`awk '{print $1}' output_mjd.txt | sed -n $i\p | awk '{ OFMT="%.0f"} {print ($1-57388)*86400+1451606400;}'`
	time_min=`awk '{print $1-$2}' output_mjd.txt | sed -n $i\p | awk '{ OFMT="%.0f"} {print ($1-57388)*86400+1451606400;}'`
	time_max=`awk '{print $1+$2}' output_mjd.txt | sed -n $i\p | awk '{ OFMT="%.0f"} {print ($1-57388)*86400+1451606400;}'`
	#2016/01/01 00:00:00 (UT) を基準
	date=`date -ur $time +"%Y/%m/%d %H:%M:%S"`
	date_min=`date -ur ${time_min} +"%Y/%m/%d %H:%M:%S"`
	date_max=`date -ur ${time_max} +"%Y/%m/%d %H:%M:%S"`
	para=`awk '{print $3}' output_mjd.txt | sed -n $i\p`
	para_min=`awk '{print $3-$4}' output_mjd.txt | sed -n $i\p`
	para_max=`awk '{print $3+$4}' output_mjd.txt | sed -n $i\p`
	echo "$date $para $date_min $date_max $para_min $para_max" | awk '{print $1,$2,$3,$4,$5,$6,$7,$8,$9}' >> output_ut.txt
done

# 7. summary
echo ""
echo "End of script. output_curve = ${outfile_curve}"
echo "output txt = output_mjd.txt, output_ut.txt"
echo ""
