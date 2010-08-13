set terminal postscript colour enhanced landscape lw 1 10
set key box left top width 1 title 'Test run'
set xlabel 'Payload size (UDP packet)'
set ylabel 'Processing cost per packet (10E-6 sec)'
set title 'Comparison of the different methods w/4 nodes'
set xrange [0:1500]
plot \
 'results.txt' index 0 every ::24::31 using 1:3 title "posixuser-ns3kernel" with linespoints, \
 'results.txt' index 1 every ::24::31 using 1:3 title "ns3user-ns3kernel" with linespoints, \
 'results.txt' index 2 every ::24::31 using 1:3 title "posixuser-linuxkernel-small" with linespoints, \
 'results.txt' index 3 every ::39::51 using ($4-42):($10/$3) title "netns" with linespoints, \
 'results.txt' index 4 every ::39::51 using ($4-42):($10/$3) title "netns+bridging" with linespoints

