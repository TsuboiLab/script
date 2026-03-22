#!/bin/bash
 
##anaew.sh
 
 
##
##
###############################################################
# Ver1 
# 2019/06/29 H.Kawai 
#
# Ver1.1
# 2019/07/02 H.Kawai
# -Add chi-square test
# -Add fb-txt and modifiy Flux err
# -Add model make : model alt > 35 deg
#
# Ver1.2 
# 2019/07/31 W.Iwakiri
#  adding new outputfile for the figure of "data - template":
#  input_cont_norm_line=`echo "$input_raw" | sed 's/fct/fbt/g' | sed 's/.txt/_'$line'_cont_norm_line.txt/g' `
#
# Ver1.3
# 2019/08/02 H.Kawai
#  change result-file
#         old : result-file include all data
#         new : result-file include only clear data(exclusive of low count and altitude data)
#               result_all-file include all data
#  add input_resi : this file is same as Ver1.2-file "data - template"
#  add list_resi : The list of input_resi
#
###############################################################
# ex)anaew.sh ha
# You make "all.list" before run ana_ha.sh
# all.list is made the command "ls *fbt.txt"
 
if [ -e "all.list" ] ; then
    echo "--- all.txt is exist! Run Start ! ---"
else
    echo "--- all.txt is not exist! please less anaew.sh ! ---"
    exit
fi
 
all=all.list
all_num=`wc $all | awk '{print $1}'`
line=$1
if [ "$line" == "ha" ] ; then
    linex=6563
elif [ "$line" == "hb" ] ; then
    linex=4861
elif [ "$line" == "hc" ] ; then
    linex=4340
elif [ "$line" == "hd" ] ; then
    linex=4101
else
    echo "---- linex err ! please Run 'anaew.sh ha 2>&1 | tee log.txt' ----"
    exit
fi
output=`echo "result_ew_${line}.txt"`
output_all=`echo "result_all_ew_${line}.txt"`
list_resi=`echo "list_resi_${line}.txt"`
all_nohead=`echo "all_nohead.list"`
xmin=`echo $linex | awk '{print $1-10}'`
xmax=`echo $linex | awk '{print $1+10}'`
echo "---- Run about $linex($line) line ----"
echo "xmin=$xmin xmax=$xmax"
 
#0. input list modify
 
ra=154.90117001
dec=19.8700038994  # For AD Leo
alt_map=alt_map.txt
alt_map_png=alt_map.png
 
if [ -e "$all_nohead" ] ; then
    echo "---- $all_nohead is already exixt! skip this step. ----"
else
    echo "---- make $all_nohead ----"
    loopnum=$all_num
    echo "loopnum of all = $loopnum"
    for i in `seq 1 $loopnum`
    do
    input_raw=`sed -n $i\p $all` # input = hoge_fbt.txt
    input=`echo "$input_raw" | sed 's/.txt/_nohead.txt/g' `
    input_flux_raw=`sed -n $i\p $all | sed 's/fbt/fct/g'`
    input_flux=`echo "$input_flux_raw" | sed 's/.txt/_nohead.txt/g' `
    awk '{if($1 ~ /\./) print $1,$2}' $input_raw | awk '{print NR,$1,$2}' > $input
    awk '{if($1 ~ /\./) print $1,$2}' $input_flux_raw | awk '{print NR,$1,$2}' > $input_flux
    echo $input >> $all_nohead
 
#[ver 1.1] make elavation map for model selection (elv > 35 deg => ok)
    date=`awk '{if($1 ~ /DATE-OBS/) print $2}' $input_raw | sed "s/'//g" | sed 's/T.*//g' | sed 's/-/ /g'`
    time=`awk '{if($1 ~ /DATE-OBS/) print $2}' $input_raw | sed "s/'//g" | sed 's/.*T//g' | sed 's/:/ /g' `
    flux=`awk '{if($2 > 6455) print $0}' $input | head -10 | awk '{OFMT="%.4e"}{sum+=$3} END{print sum}' `
    alt=`RADEC2elaz $date $time $ra $dec | awk '{print $1}'`
    echo "$input $alt $flux" >> $alt_map
    echo "$i $input $alt $flux"
    done
    gnuplot <<EOF
set term png
set output "$alt_map_png"
set xlabel "alt [deg]"
set ylabel "10-bin average Counts about [6455A-] [counts/A]"
plot "$alt_map" u 2:3 lc rgb "red"
EOF
fi
 
#1. 
 
loopnum=$all_num
echo "loopnum of all = $loopnum"
for i in `seq 1 $loopnum`
do
    input_raw=`sed -n $i\p $all`
#    inputc_raw=`sed -n $i\p $all | sed 's/fct/fbt/g'`
    input_flux_raw=`sed -n $i\p $all | sed 's/fbt/fct/g'`
    input=`echo "$input_raw" | sed 's/.txt/_nohead.txt/g' `
    input_flux=`echo "$input_flux_raw" | sed 's/.txt/_nohead.txt/g' `
#    inputc=`echo "$inputc_raw" | sed 's/.txt/_nohead.txt/g' `
#    temp=`echo "$input_raw" | sed 's/.txt/_'$line'_temp.txt/g' `
#    temp_list=`echo "$input_raw" | sed 's/.txt/_'$line'_temp.list/g' `
    temp=`echo "template_${line}.txt"`
    temp_list=`echo "template_${line}.list"`
#    temp_sum=`echo "$input_raw" | sed 's/.txt/_'$line'_temp_sum.txt/g' `
#    temp_sum_tasuyou=`echo "$input_raw" | sed 's/.txt/_'$line'_temp_sum_tasuyou.txt/g' `
    temp_sum=`echo "template_${line}_sum.txt"`
    temp_sum_tasuyou=`echo "template_${line}_sum_tasuyou.txt"`
    input_temp=`echo "$input_raw" | sed 's/.txt/_'$line'_temp.txt/g' `
    input_line=`echo "$input_raw" | sed 's/.txt/_'$line'_line.txt/g' `
    input_cont=`echo "$input_raw" | sed 's/.txt/_'$line'_cont.txt/g' `
    input_cont_norm=`echo "$input_raw" | sed 's/fct/fbt/g' | sed 's/.txt/_'$line'_cont_norm.txt/g' `
    input_cont_norm_line=`echo "$input_raw" | sed 's/fct/fbt/g' | sed 's/.txt/_'$line'_cont_norm_line.txt/g' `
    input_norm=`echo "$input_raw" | sed 's/.txt/_'$line'_norm.txt/g' `
    input_linecont=`echo "$input_raw" | sed 's/.txt/_'$line'_linecont.txt/g' `
    input_flux_line=`echo "$input_flux_raw" | sed 's/.txt/_'$line'_line.txt/g' `
    input_CTF=`echo "$input_raw" | sed 's/.txt/_'$line'_CTF.txt/g' `
    input_chi2=`echo "$input_raw" | sed 's/.txt/_'$line'_chi2.txt/g' `
    input_hist=`echo "$input_raw" | sed 's/.txt/_'$line'_hist.txt/g' `
    input_hist_png=`echo "$input_raw" | sed 's/.txt/_'$line'_hist.png/g' `
    input_resi=`echo "$input_raw" | sed 's/.txt/_'$line'_resi.txt/g' `
 
    all_temp=all_temp.list
 
 
    echo "Start at $input_raw"
    echo
 
    #1.1 peak search -> find emission region.
    echo "-------- 1.1 peak search --------"
 
#    footminx=`awk '{if($2 < '${xmin}') print $2}' $input | tail -1` # this bin is concled in continuum
#    footminn=`awk '{if($2 < '${xmin}') print $1}' $input | tail -1`
#    footmaxx=`awk '{if($2 > '${xmax}') print $2}' $input | head -1` # this bin is concled in continuum
#    footmaxn=`awk '{if($2 > '${xmax}') print $1}' $input | head -1`
 
 
    echo "foot-min-n,x=$footminn $footminx foot-max-n,x=$footmaxn $footmaxx"
    echo
 
 
    #1.2 model make
    echo "-------- 1.2 model make -------"
 
    if [ $i == "1" ] ; then
    awk '{if( $2 > 35) if( $3 > 1000) print $1}' $alt_map > $all_temp ##Counts of good ADleo data is grater than 1000.
    PSMx=`awk '{OFMT="%.0f"}{if($2 < '$linex') print ('$linex'-$2)*10000}' $input | tail -1`  #zansa of PeakSearchMinus_x
    PSMn=`awk '{OFMT="%.0f"}{if($2 < '$linex') print $1}' $input | tail -1`  #zansa of PeakSearchMinus_n
    PSPx=`awk '{OFMT="%.0f"}{if($2 > '$linex') print ($2-'$linex')*10000}' $input | head -1`  #zansa of PeakSearchPlus_x
    PSPn=`awk '{OFMT="%.0f"}{if($2 > '$linex') print $1}' $input | head -1`  #zansa of PeakSearchPlus_n
    if [ $PSMx -gt $PSPx ] ; then
        peak_n=$PSPn
    else
        peak_n=$PSMn
    fi
    echo "peak_n=$peak_n ( PSMx=$PSMx PSPx=$PSPx )"
    peak_x=`awk '{if($1 == '$peak_n') print $2}' $input`
    peak_nm5=`echo $peak_n | awk '{print $1-5}'`  # this bin is included in continuum
    peak_np5=`echo $peak_n | awk '{print $1+5}'`  # this bin is included in continuum
    peak_nm45=`echo $peak_n | awk '{print $1-45}'`  # this bin is included in continuum
    peak_np45=`echo $peak_n | awk '{print $1+45}'`  # this bin is included in continuum
    min1=`awk '{if($1 == '$peak_nm45') print $2}' $input`
    min2=`awk '{if($1 == '$peak_nm5') print $2}' $input`
    max1=`awk '{if($1 == '$peak_np5') print $2}' $input`
    max2=`awk '{if($1 == '$peak_np45') print $2}' $input`
    echo "continuum calc range is [${min1}-${min2}] [${max1}-${max2}]"
     
    lnum_all_temp=`wc $all_temp | awk '{print $1}'`
    echo "loopnum of template make=$lnum_all_temp"
    for j in `seq 1 $lnum_all_temp`
    do
        inp=`sed -n $j\p $all_temp `
        min1=`awk '{if($1 == '$peak_nm45') print $2}' $inp`
        min2=`awk '{if($1 == '$peak_nm5') print $2}' $inp`
        max1=`awk '{if($1 == '$peak_np5') print $2}' $inp`
        max2=`awk '{if($1 == '$peak_np45') print $2}' $inp`
        awk '{if($2 >= '${min1}') if($2 <= '${min2}') print $0}' $inp > $temp
        awk '{if($2 >= '${max1}') if($2 <= '${max2}') print $0}' $inp >> $temp
        if [ "$j" == "1" ] ; then
        cat $temp > $temp_sum_tasuyou
        echo "test test start" > $temp_sum
        else
        paste $temp_sum_tasuyou $temp | awk '{OFMT="%.1f"}{print $1,$2,$3+$6}' > $temp_sum
        cat $temp_sum > $temp_sum_tasuyou
        fi
        echo "model make loop j=$j 1-data=`head -1 $temp | awk '{print $3}'` sum=`head -1 $temp_sum | awk '{print $3}'`"
    done
    awk '{OFMT="%.17f"}{print $1,$2,$3/'${lnum_all_temp}'}' $temp_sum > $temp
    echo "model is $temp"
    echo
 
    echo "file_num in template list = `wc $all_temp | awk '{print $1}'`"
    else
 
    echo "template was already made."
    fi
    min1=`awk '{if($1 == '$peak_nm45') print $2}' $input`
    min2=`awk '{if($1 == '$peak_nm5') print $2}' $input`
    max1=`awk '{if($1 == '$peak_np5') print $2}' $input`
    max2=`awk '{if($1 == '$peak_np45') print $2}' $input`
    echo "continuum calc range is [${min1}-${min2}] [${max1}-${max2}]"
 
    footminn=$peak_nm5
    footminx=$min2
    footmaxn=$peak_np5
    footmaxx=$max1
 
    echo
 
 
    #1.3 model make
 
 
    #1.4 [ver1.1] model norm fitting & make
    echo "-------- 1.4 model norm fitting & make with chi-square --------"
    del=0.01
    delmo=`sed -n 1\p $temp | awk '{OFMT="%.17f"}{print $3*'${del}'}'`
    n=1
    fit1=fit1.txt
    fit2=fit2.txt
 
    awk '{if($2 >= '${min1}') if($2 <= '${min2}') print $1,$2,$3}' $input > $input_cont
    awk '{if($2 >= '${max1}') if($2 <= '${max2}') print $1,$2,$3}' $input >> $input_cont
    awk '{if($2 > '${min2}') if($2 < '${max1}') print $1,$2,$3}' $input > $input_line
    awk '{if($2 > '${min2}') if($2 < '${max1}') print $1,$2,$3}' $input_flux > $input_flux_line
 
    y_fit=`awk '{OFMT="%.2f"}{sum+=$3} END{print sum}' $input_cont`
    ytemp_fit=`awk '{OFMT="%.2f"}{sum+=$3} END{print sum}' $temp`
    temp_to_raw=`echo "$y_fit $ytemp_fit" | awk '{OFMT="%.2f"}{print $1/$2}'`
    n=0.90 #offset fixed by normalization
    echo "y_fit=$y_fit ytemp_fit=$ytemp_fit temp_to_raw=$temp_to_raw"
 
    for j in `seq 1 20`
    do
    paste $input_cont $temp | awk '{OFMT="%.17f"}{print $3,$6*'${temp_to_raw}'*'${n}'}' > $fit1   # fit1=txt for chi2-cal
    awk '{OFMT="%.5f"}{print (($1-$2)**2)/$2}' $fit1 > $fit2
    chi2=`awk '{OFMT="%.2f"}{sum+=$1} END{print sum}' $fit2` #2f=ninni-value
    DOF=`wc $fit1 | awk '{print $1-1}'`
    red_chi2=`echo $chi2 $DOF | awk '{OFMT="%.3f"}{print $1/$2}' `
    echo "$n $red_chi2 $DOF" >> $input_chi2
    echo "n=$n chi2=$chi2 DOF=$DOF red_chi2=$red_chi2"
    n=`echo $n | awk '{OFMT="%.2f"}{print $1+0.01}'`
    done
    chi2_min=`cat $input_chi2 | awk 'BEGIN{m=100000}{if(m>$2) m=$2} END{print m}' `
    chi2_minn=`awk '{if($2 <= '$chi2_min') print $1}' $input_chi2`
    awk '{OFMT="%.1f"}{print $1,$2,$3*'${temp_to_raw}'*'${chi2_minn}'}' $temp > $input_temp
    paste $input_cont $input_temp | awk '{OFMT="%.1f"}{print $1,$2,$3-$6}' > $input_cont_norm
    echo
    echo "red-chi2_min=$chi2_min n=$chi2_minn "
    echo
 
 
 
 
########################################################################
 
    #1.5 get the gausian of continuum for Continuum error
    echo "-------- 1.5 get the gausian of continuum for Continuum error --------"
    footminy=`awk '{if($1 == '$footminn') print $3}' $input`
    footmaxy=`awk '{if($1 == '$footmaxn') print $3}' $input`
    footminy_flux=`awk '{if($1 == '$footminn') print $3}' $input_flux_line`
    footmaxy_flux=`awk '{if($1 == '$footmaxn') print $3}' $input_flux_line`
    footminy_temp=`awk '{OFMT="%.1f"}{print $1,$2,$3*'${temp_to_raw}'*'${chi2_minn}'}' $temp | awk '{if($1 == '$footminn') print $3}'`
    footmaxy_temp=`awk '{OFMT="%.1f"}{print $1,$2,$3*'${temp_to_raw}'*'${chi2_minn}'}' $temp | awk '{if($1 == '$footmaxn') print $3}'`
    echo "footminn=$footminn footmaxn=$footmaxn"
    echo "footminy_temp=$footminy_temp footmaxy_temp=$footmaxy_temp"
 
    paste $input $input_flux | awk '{OFMT="%.20f"}{print $1,$2,($6/$3)*1E+0}' > $input_CTF  #CountToFlux
    #f(x)=a*x+b  count For Section 1.6 calc Flux
    fx_a=`echo "$footminx $footminy_temp $footmaxx $footmaxy_temp" | awk '{OFMT="%.5f"}{print ($3-$4)/($1-$2)}'`
    fx_b=`echo "$footminx $footminy_temp $fx_a" | awk '{OFMT="%.4f"}{print $2-$3*$1}'`
    echo "f(x) : a=$fx_a b=$fx_b"
 
    cont_count=`echo $footminy_temp $footmaxy_temp | awk '{OFMT="%.1f"}{print ($1+$2)/2}'` #continuum (at peak of line) [counts]
    contx=`echo $footminx $footmaxx | awk '{OFMT="%.2f"}{print ($1+$2)/2}'` #x at cont_count [A]
    contn_m1=`awk '{if($2 < '$contx') print $1}' $input_line | tail -1`  #continuum_n_minus1
    contn_p1=`echo $contn_m1 | awk '{print $1+1}'`  #continuum_n_plus1
    echo "contx=$contx contn_m1=$contn_m1 contn_p1=$contn_p1"
    cont_m1_CTF=`awk '{if($1 == '$contn_m1') print $3}' $input_CTF `  #contn_m1_CountToFlux
    cont_p1_CTF=`awk '{if($1 == '$contn_p1') print $3}' $input_CTF `  #contn_p1_CountToFlux
    cont_CTF=`echo $cont_m1_CTF $cont_p1_CTF | awk '{OFMT="%.20f"}{print ($1+$2)/2}'`
    echo "cont_m1_CTF=$cont_m1_CTF cont_p1_CTF=$cont_p1_CTF cont_CTF=$cont_CTF"
    cont=`echo $cont_count $cont_CTF | awk '{OFMT="%.17f"}{print $1*$2}'` #continuum [erg/s/cm2/A]
 
    ave=`echo $footminy_fb $footmaxy_fb | awk '{OFMT="%.17f"}{print ($1+$2)/2}'`   #count of continuum on count/A 
    sig_norm=`awk '{OFMT="%.10f"}{sum+=$3**2} END {print (sum/NR)**0.5}' $input_cont_norm`
    err_cont=`echo "$cont_count $sig_norm $cont" | awk '{OFMT="%.17f"}{print $3*($2/$1)}'`
    echo "calc para : footminy=$footminy footmaxy=$footmaxy cont=`echo $cont | awk '{print $1*1E+0}'`"
    echo "cont_count=$cont_count sig_norm=$sig_norm"
    echo "err_cont=`echo $err_cont | awk '{print $1*1E+0}'`"
    echo
 
    #1.5.1 make histgram
    echo
    hist=hist.txt
    hist_max=`awk '{if(m<$3) m=$3} END{print m}' $input_cont_norm`
    hist_min=`awk '{if(m>$3) m=$3} END{print m}' $input_cont_norm`
    hist_del=`echo $hist_min $hist_max | awk '{OFMT="%.2f"}{print ($2-$1)/10}'`
    echo "hist_max=$hist_max hist_min=$hist_min hist_del=$hist_del"
    hist_x_err=`echo $hist_del | awk '{OFMT="%.2f"}{print $1/2}'`
    for j in `seq 1 10`
    do
    hist_range_min=`echo $hist_min $hist_del $j | awk '{OFMT="%.2f"}{print $1+$2*($3-1)}'`
    hist_range_max=`echo $hist_min $hist_del $j | awk '{OFMT="%.2f"}{print $1+$2*$3}'`
    awk '{OFMT="%.2f"}{if($3 > '$hist_range_min') if($3 <= '$hist_range_max') print $3*1}' $input_cont_norm > $hist
    hist_x=`echo $hist_range_min $hist_range_max | awk '{OFMT="%.2f"}{print ($1+$2)/2}'`
    hist_y=`wc $hist | awk '{print $1}'`
    echo $hist_x $hist_y $hist_x_err >> $input_hist
    echo "loop $j range[$hist_range_min:$hist_range_max] hist is $hist_y"
    done
    gnuplot<<EOF
set term png
set output "$input_hist_png"
set ylabel "Counts/A"
#f(x)=c*exp(-((x-b)**2)/(2*a**2))
#c=10
#a=250
#b=0
#fit f(x) "$input_hist" u 1:2 via a,b,c
#plot "$input_hist" u 1:2:3 w xerrorbar lc rgb "red", f(x) lc rgb "black"
plot "$input_hist" u 1:2:3 w xerrorbar lc rgb "red"
EOF
#    hist_sig=`grep "a               =" fit.log | awk '{print $3,$5}' |tail -1`
    hist_sig="no_avairable"
    echo "sigma of normalized histgram is $hist_sig"
    echo
    echo "num for hist is `wc $input_cont_norm | awk '{print $1}'` . sum of data of hist.txt is `awk '{sum+=$2} END{print sum}' $input_hist` | histgram is $input_hist_png"
    echo
 
    #1.6 calc square of cont & line ; comp [sigma : square] for Flux error
    #[ver1.1] calc S of cont & line in _fb and, calc Flux of line
    echo "------- 1.6 calc square of cont & line ; comp [sigma : square] for Flux error --------"
 
#1.6.1 For line
    s_line=0
    s_line_flux=0
#    dx_sum_line=0
    loopnum2=`wc $input_line | awk '{print $1-1}'`
    echo "loopnum of input_line = $loopnum2"
    for j in `seq 1 $loopnum2`
    do
    j2=`echo $j | awk '{print $1+1}'`
    x1=`sed -n $j\p $input_line | awk '{print $2}'`
    x2=`sed -n $j2\p $input_line | awk '{print $2}'`
    dx=`echo $x1 $x2 | awk '{OFMT="%.5f"}{print $2-$1}'`
    y_CG=`sed -n $j\p $input_line | awk '{print $3}'`  # y included Continuum + Gausian
    y_C=`echo "$x1 $fx_a $fx_b" | awk '{OFMT="%.3f"}{print $1*$2+$3}' `  #y included Continuum
    y=`echo "$y_CG $y_C" | awk '{OFMT="%.3f"}{print $1-$2}' `  #y included Gausian
    echo $x1 $y >> ${input_cont_norm_line}
    xy=`echo $dx $y_CG | awk '{OFMT="%.3f"}{print $1*$2}'`
    s_line=`echo $s_line $xy | awk '{OFMT="%.3f"}{print $1+$2}'`
    x1_n=`sed -n $j\p $input_line | awk '{print $1}'`  #x1_n=y_n
    y_CTF=`awk '{if($1 == '$x1_n') print $3}' $input_CTF `  #y_CountToFlux
    y_flux=`echo $y_CG $y_C $y_CTF | awk '{OFMT="%.17f"}{print ($1-$2)*$3}'`  # [ers/s/cm2]
    xy_flux=`echo $dx $y_flux | awk '{OFMT="%.17f"}{print $1*$2}'`  # [ers/s/cm2]
    s_line_flux=`echo $s_line_flux $xy_flux | awk '{OFMT="%.17f"}{print $1+$2}'`
    echo "j=$j J2=$j2 x1=$x1 x2=$x2 dx=$dx y=$y xy=$xy y_C=$y_C s_line=$s_line s_line_flux=$s_line_flux"
#   dx_sum_line=`echo "$dx_sum_line $dx" | awk '{OFMT="%.5f"}{print $1+$2}'`
    done
    poison_line=`echo $s_line | awk '{OFMT="%.10f"}{print ($1**0.5)/$1}'`
    flux=$s_line_flux
    err_flux=`echo $flux $poison_line | awk '{OFMT="%.17f"}{print $1*$2}'`
    echo "s_line=$s_line"
    echo "poison err [%*0.01] { line = $poison_line }"
    echo
     
 
    #1.7 calc OBS-TIME
    echo "------- 1.7 calc OBS-TIME --------"
    date=`awk '{if($1 ~ /DATE-OBS/) print $2}' $input_raw | sed "s/'//g" | sed 's/T.*//g' | sed 's/-/\//g'`
    time=`awk '{if($1 ~ /DATE-OBS/) print $2}' $input_raw | sed "s/'//g" | sed 's/.*T//g' `
    expt=`awk '{if($1 ~ /EXPTIME/) print $3}' $input_raw | sed 's/\..*//g'`
    echo "date=$date time=$time expt=$expt"
 
    #1.8 calc EW
    echo "------- 1.8 calc EW --------"
    ew=no  #For bug search
    ewerr=no  #For bug search
    ew=`echo "$flux $cont" | awk '{OFMT="%.3f"}{print $1/$2}'`
    ewerr=`echo "$flux $err_flux $cont $err_cont" | awk '{OFMT="%.3f"}{print (($2/$3)**2+($1*$4/($3**2))**2)**0.5}'`
    echo "ew=$ew ewerr=$ewerr  (cont=`echo $cont | awk '{print $1*1E+0}'` cont_err=`echo $err_cont | awk '{print $1*1E+0}'` flux=`echo $flux | awk '{print $1*1E+0}'` flux_err=` echo $err_flux | awk '{print $1*1E+0}'` )"
 
    #1.9　Alt peak_y E-?
    alt=`cat $alt_map | sed -n $i\p | awk '{print $2}'`
    peak_y=`awk '{if($1 == '$peak_n') print $3}' $input`
    flux=`echo $flux | awk '{OFMT="%.4e"}{print $1*1E+0}'`  # Hyouki wo E- ni.
    err_flux=`echo $err_flux | awk '{OFMT="%.4e"}{print $1*1E+0}'`
    cont=`echo $cont | awk '{OFMT="%.4e"}{print $1*1E+0}'`
    err_cont=`echo $err_cont | awk '{OFMT="%.4e"}{print $1*1E+0}'`
 
    echo
    echo "$date $time $expt $ew $ewerr $flux $err_flux $cont $err_cont $peak_y $input_raw $alt $chi2_min $i" >> $output_all

    #1.10 data selection
    echo "------- 1.10 data selection --------"
    count_check=`echo $peak_y | awk '{OFMT="%.0f"}{print $1*1}' `
    alt_check=`echo $alt | awk '{OFMT="%.0f"}{print $1*1}' `
    echo "check count : alt = $count_check $alt_check"
    if [ "$alt_check" -gt 40 ] ; then
        echo "altitude is OK"
        if [ "$count_check" -gt 1000 ] ; then
            echo "count is OK"
            echo "$date $time $expt $ew $ewerr $flux $err_flux $cont $err_cont $peak_y $input_raw $alt $chi2_min $i" >> $output
            awk '{print $2,$3}' $input_cont_norm >> $input_resi
            cat $input_cont_norm_line >> $input_resi
            echo $input_resi >> $list_resi
        else
            echo "count is NOT OK"
        fi
    else
        echo "altitude is NOT OK"
    fi
    echo
 
    #result
    #
    #1  date
    #2  time
    #3  exp-time[sec]
    #4  ew
    #5  ewerr
    #6  flux 
    #7  err_flux 
    #8  cont 
    #9  err_cont
    #10 count-of-peak
    #11 peak-wavelength
    #12 file-name
    #13 altitude
    #14 red-chi2
    #15 seq-number
 
    echo
    echo "============ $i of $all_num is finished ! =============="
    echo
    echo
 
done
 
 
 
 
######################################################################
