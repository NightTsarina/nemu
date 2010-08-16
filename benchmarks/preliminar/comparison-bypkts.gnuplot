set terminal postscript colour enhanced landscape lw 1 10
set key box left top width 1 title 'Experiment'
set xlabel 'Payload size (UDP packet)'
set ylabel 'Processing cost per packet (10E-6 sec)'
set title 'Processing cost for a 4-node topology'
set xrange [0:1500]
plot \
 'results-simu.txt' index 0 every ::24::31 using 1:3 title "Exp 1" with linespoints, \
 'results-simu.txt' index 1 every ::24::31 using 1:3 title "Exp 2" with linespoints, \
 'results-simu.txt' index 3 every ::24::31 using 1:3 title "Exp 3" with linespoints, \
 'results.txt' index 0 every ::39::51 using ($4-42):($10/$3) title "Exp 4" with linespoints, \
 'results.txt' index 1 every ::39::51 using ($4-42):($10/$3) title "Exp 4bis" with linespoints

