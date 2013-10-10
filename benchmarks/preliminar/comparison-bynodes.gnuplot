set terminal postscript colour enhanced landscape lw 1 10
set key box left top width 1 title 'Experiment'
set xlabel 'Number of nodes'
set ylabel 'Processing cost per packet (10E-6 sec)'
set title 'Processing cost for 1000-byte packets'
set xrange [0:35]
plot \
 'results-simu.txt' index 0 every 8::1 using 2:3 title "Exp 1" with linespoints, \
 'results-simu.txt' index 1 every 8::1 using 2:3 title "Exp 2" with linespoints, \
 'results-simu.txt' index 2 every 8::1 using 2:3 title "Exp 3" with linespoints, \
 'results.txt' index 0 every 13::11 using 1:($10/$3) title "Exp 4" with linespoints, \
 'results.txt' index 1 every 13::11 using 1:($10/$3) title "Exp 4bis" with linespoints

